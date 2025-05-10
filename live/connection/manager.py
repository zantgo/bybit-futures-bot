# live/connection/manager.py
"""
Gestiona la inicialización y el acceso a las sesiones de cliente API de Bybit (Live Mode),
y proporciona wrappers para llamadas API comunes (v5).
v7.5 - Mensaje de éxito explícito para Hedge Mode check y advertencia más clara.
"""
import os
import sys
import uuid
import traceback # Para errores detallados
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# Use absolute import for core modules
# (Asumiendo que config.py está en core/ y accesible)
try:
    # Necesario para determinar PROJECT_ROOT si no se importa desde main
    if __name__ != "__main__": # Evitar error si se ejecuta este archivo directamente
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root_from_manager = os.path.dirname(os.path.dirname(script_dir))
        if project_root_from_manager not in sys.path:
            sys.path.insert(0, project_root_from_manager)

    import config # Import config para acceder a mapas de cuentas, UIDs, etc.
except ImportError as e:
     print(f"ERROR CRITICO [Live Manager Import]: No se pudo importar 'core.config'. Asegúrate que la estructura del proyecto sea correcta. Detalle: {e}")
     # Definir un config dummy mínimo para evitar más errores, aunque la funcionalidad estará rota.
     config = type('obj', (object,), {'PROJECT_ROOT': '.', 'ACCOUNTS_TO_INITIALIZE': [], 'ACCOUNT_API_KEYS_ENV_MAP': {}, 'ACCOUNT_UID_ENV_VAR_MAP': {}, 'POSITION_TRADING_MODE': 'N/A', 'TICKER_SYMBOL':'N/A', 'CATEGORY_LINEAR': 'linear', 'UNIVERSAL_TESTNET_MODE': True, 'DEFAULT_RECV_WINDOW': 10000, 'LOADED_UIDS': {}})()


# Attempt to import specific exceptions, provide fallbacks
try:
    from pybit.exceptions import InvalidRequestError, FailedRequestError
except ImportError:
    print("Advertencia [Live Manager]: No se encontraron excepciones específicas de pybit. Usando fallbacks.")
    class InvalidRequestError(Exception): pass
    # Añadir status_code a FailedRequestError dummy si no existe
    class FailedRequestError(Exception):
        def __init__(self, message, status_code=None):
            super().__init__(message)
            self.status_code = status_code


# Module state
_clients = {}     # Dictionary to store initialized client sessions {account_name: session}
_initialized = False # Flag to track if initialization has run

# --- Helper Functions ---

def _load_api_keys_and_uids() -> dict:
    """
    Carga credenciales API y UIDs desde .env basado en los mapas de core.config.
    Puebla config.LOADED_UIDS si los UIDs son válidos.
    Retorna solo las credenciales API encontradas.
    """
    # (Código v7.5 sin cambios)
    env_path = os.path.join(getattr(config, 'PROJECT_ROOT', '.'), '.env') # Acceso seguro a PROJECT_ROOT
    if os.path.exists(env_path): load_dotenv(dotenv_path=env_path, override=True)
    else: print("Advertencia [Live Manager]: .env no encontrado. No se pueden cargar claves/UIDs.")

    api_credentials = {}
    all_keys_found = True
    all_uids_valid = True
    print("Cargando credenciales API y UIDs desde .env (live.connection.manager)...")

    accounts_to_check = getattr(config, 'ACCOUNTS_TO_INITIALIZE', [])
    api_map = getattr(config, 'ACCOUNT_API_KEYS_ENV_MAP', {})

    if not accounts_to_check: print("  Advertencia: No hay cuentas definidas en config.ACCOUNTS_TO_INITIALIZE.")
    if not api_map: print("  Advertencia: No hay mapeo de claves API en config.ACCOUNT_API_KEYS_ENV_MAP.")

    for account_name in accounts_to_check:
        if account_name in api_map:
            key_env_var, secret_env_var = api_map[account_name]
            api_key = os.getenv(key_env_var)
            api_secret = os.getenv(secret_env_var)
            if not api_key or not api_secret or api_key.startswith("YOUR_") or api_secret.startswith("YOUR_"):
                print(f"  ERROR: Claves API no encontradas o sin configurar para '{account_name}' (Variables: {key_env_var}, {secret_env_var})")
                all_keys_found = False
            else:
                print(f"  Claves encontradas para '{account_name}'. Key: ...{api_key[-4:]}")
                api_credentials[account_name] = {"key": api_key, "secret": api_secret}

    if not all_keys_found: print("\nAdvertencia: Faltan o son inválidas una o más claves API para las cuentas listadas.")

    uid_map = getattr(config, 'ACCOUNT_UID_ENV_VAR_MAP', {})
    loaded_uids_temp = {}
    if not uid_map: print("  Info: No hay mapeo de UIDs en config.ACCOUNT_UID_ENV_VAR_MAP.")
    else:
        print("Cargando y Validando UIDs...")
        for account_name, env_var_name in uid_map.items():
            uid_value = os.getenv(env_var_name)
            if uid_value is None: print(f"  ERROR: Variable entorno UID '{env_var_name}' (cuenta '{account_name}') NO ENCONTRADA."); all_uids_valid = False
            elif not uid_value.isdigit(): print(f"  ERROR: Valor UID para '{env_var_name}' (cuenta '{account_name}') = '{uid_value}' NO ES NUMÉRICO."); all_uids_valid = False
            else: loaded_uids_temp[account_name] = uid_value

    if all_uids_valid and uid_map:
        if hasattr(config, 'LOADED_UIDS'): config.LOADED_UIDS = loaded_uids_temp
        else: print("ERROR INTERNO: El objeto config no tiene el atributo LOADED_UIDS.")
        print(f"  UIDs validados y almacenados en config.LOADED_UIDS: {list(getattr(config, 'LOADED_UIDS', {}).keys())}") # Acceso seguro
    elif not uid_map: pass
    else:
        print("\nError Crítico: Faltan o son inválidos UIDs necesarios. Las transferencias fallarán.")
        if hasattr(config, 'LOADED_UIDS'): config.LOADED_UIDS = {}

    return api_credentials

def _check_and_set_hedge_mode(session, account_name_used: str) -> bool:
    """Intenta establecer Hedge Mode y verifica el resultado."""
    # (Código v7.5 sin cambios - ya tenía mensajes de éxito explícitos)
    symbol = getattr(config, 'TICKER_SYMBOL', None)
    category = getattr(config, 'CATEGORY_LINEAR', 'linear')
    target_mode = 3 # 3 para Hedge Mode

    if not symbol: print("WARN [Hedge Mode Check]: Falta TICKER_SYMBOL."); return False

    print(f"INFO [Hedge Mode Check]: Verificando/Estableciendo Hedge Mode (mode=3) para {symbol} ({category}) usando cuenta '{account_name_used}'...")
    try:
        response = session.switch_position_mode(category=category, symbol=symbol, mode=target_mode)
        if response and response.get('retCode') == 0: print(f"  ÉXITO [Hedge Mode Check]: Modo establecido a Hedge para {symbol} (o ya lo estaba y API OK)."); return True
        elif response and response.get('retCode') == 110021: print(f"  ÉXITO [Hedge Mode Check]: Modo ya era Hedge para {symbol} (Respuesta 110021)."); return True
        elif response: ret_code = response.get('retCode', -1); ret_msg = response.get('retMsg', 'Unknown API Error'); print(f"  ERROR API [Hedge Mode Check]: Código={ret_code}, Mensaje='{ret_msg}'"); return False
        else: print(f"  ERROR [Hedge Mode Check]: No se recibió respuesta de la API."); return False
    except InvalidRequestError as invalid_req_err:
        error_message = str(invalid_req_err)
        if "110021" in error_message or "position mode is not modified" in error_message.lower(): print(f"  ÉXITO [Hedge Mode Check]: Modo ya era Hedge para {symbol} (InvalidRequestError 110021)."); return True
        else: print(f"ERROR API [Hedge Mode Check] - Invalid Request: {invalid_req_err}"); return False
    except FailedRequestError as api_err: status_code = getattr(api_err, 'status_code', None); print(f"ERROR HTTP [Hedge Mode Check]: {api_err} (Status: {status_code})"); return False
    except AttributeError: print(f"ERROR Fatal [Hedge Mode Check]: Método 'switch_position_mode' NO existe."); return False
    except Exception as e: print(f"ERROR Inesperado [Hedge Mode Check]: {e}"); traceback.print_exc(); return False

# --- Main Initialization Function ---

def initialize_all_clients():
    """Initializes Bybit HTTP clients and checks/sets Hedge Mode if needed."""
    # (Código v7.5 sin cambios - ya tiene la advertencia clara)
    global _clients, _initialized
    if _initialized: print("Advertencia: Clientes API (Live) ya inicializados."); return

    print("\nInicializando Clientes API Bybit (Live)...")
    api_credentials = _load_api_keys_and_uids()
    any_client_successful = False

    accounts_to_init = getattr(config, 'ACCOUNTS_TO_INITIALIZE', [])
    if not accounts_to_init: print("  No hay cuentas listadas para inicializar."); _initialized = False; return

    for account_name in accounts_to_init:
        if account_name in api_credentials:
            creds = api_credentials[account_name]; print(f"  Inicializando cliente para: '{account_name}'...")
            try:
                session = HTTP( testnet=getattr(config, 'UNIVERSAL_TESTNET_MODE', True), api_key=creds["key"], api_secret=creds["secret"], recv_window=getattr(config, 'DEFAULT_RECV_WINDOW', 10000) )
                server_time = session.get_server_time()
                if server_time and server_time.get('retCode') == 0: print(f"    -> Conexión exitosa para '{account_name}'."); _clients[account_name] = session; any_client_successful = True
                else: ret_msg = server_time.get('retMsg', '?'); ret_code = server_time.get('retCode', -1); print(f"    -> ERROR de conexión para '{account_name}': {ret_msg} (Code: {ret_code})");
            except Exception as e: print(f"    -> ERROR crítico inicializando cliente '{account_name}': {str(e)}")
        else:
             loaded_uids_dict = getattr(config, 'LOADED_UIDS', {});
             if account_name in loaded_uids_dict: print(f"  Info: No se inicializó cliente API para '{account_name}' (sin credenciales), UID cargado.")
             else: print(f"  Advertencia: No se inicializó cliente API para '{account_name}' (sin credenciales ni UID).")

    if not any_client_successful and any(acc in api_credentials for acc in accounts_to_init): print("\nError Fatal: No se pudo inicializar NINGÚN cliente API."); _initialized = False; return
    elif not _clients: print("\nAdvertencia: No se inicializó ningún cliente API activo."); _initialized = True; return
    else: print(f"\nInicialización clientes API completada. Activos: {list(_clients.keys())}"); _initialized = True

    # --- ***** INICIO CAMBIO: Chequeo/Seteo Hedge Mode para TODAS las Cuentas Operativas ***** ---
    trading_mode = getattr(config, 'POSITION_TRADING_MODE', 'N/A')
    if trading_mode == "LONG_SHORT":
        print("-" * 30)
        print("INFO [Hedge Mode Check]: Verificando/Estableciendo Hedge Mode para cuentas operativas...")

        # Lista de cuentas que deben estar en Hedge Mode (excluye 'profit')
        accounts_to_check = []
        # Usar getattr para acceso seguro a los nombres de cuenta en config
        main_acc_name = getattr(config, 'ACCOUNT_MAIN', 'main')
        longs_acc_name = getattr(config, 'ACCOUNT_LONGS', 'longs')
        shorts_acc_name = getattr(config, 'ACCOUNT_SHORTS', 'shorts')

        # Añadir solo si la cuenta fue inicializada (tiene cliente API)
        if main_acc_name in _clients: accounts_to_check.append(main_acc_name)
        if longs_acc_name in _clients: accounts_to_check.append(longs_acc_name)
        if shorts_acc_name in _clients: accounts_to_check.append(shorts_acc_name)

        if not accounts_to_check:
             print("WARN [Hedge Mode Check]: Ninguna cuenta operativa (main, longs, shorts) fue inicializada. No se puede verificar/establecer Hedge Mode.")
        else:
            all_accounts_ok = True # Flag para rastrear si todas las cuentas están OK
            for acc_name in accounts_to_check:
                session_to_use = _clients.get(acc_name) # Obtener la sesión específica
                if session_to_use:
                    hedge_mode_ok = _check_and_set_hedge_mode(session_to_use, acc_name)
                    if not hedge_mode_ok:
                        all_accounts_ok = False # Marcar que al menos una falló
                        # Imprimir advertencia específica para esta cuenta
                        print(f"  -> ERROR CRÍTICO: Falló verificación/seteo de Hedge Mode para cuenta '{acc_name}'.")
                else:
                    # Esto no debería pasar si está en accounts_to_check, pero por seguridad
                    print(f"  -> ERROR INTERNO: No se encontró sesión para cuenta '{acc_name}' que debería estar inicializada.")
                    all_accounts_ok = False

            # Decisión final basada en si todas las cuentas están OK
            if not all_accounts_ok:
                 print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                 print("!! ERROR CRÍTICO: No se pudo confirmar/establecer Hedge Mode en TODAS      !!")
                 print("!!                las cuentas operativas requeridas (main/longs/shorts).  !!")
                 print("!! El bot NO PUEDE continuar en modo LONG_SHORT de forma segura.         !!")
                 print("!! Verifica manualmente la configuración en Bybit para TODAS las cuentas. !!")
                 print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                 # Detener la ejecución es lo más seguro aquí
                 sys.exit("Error crítico configurando Hedge Mode.")
            else:
                 print("INFO [Hedge Mode Check]: Modo Hedge verificado/establecido correctamente para todas las cuentas operativas.")

        print("-" * 30)
    # --- ***** FIN CAMBIO: Chequeo/Seteo Hedge Mode ***** ---


# --- Client Access Functions ---
def get_client(account_name: str):
    # (Código v7.4 sin cambios)
    global _initialized
    if not _initialized: return None
    client_instance = _clients.get(account_name)
    return client_instance

def get_initialized_accounts() -> list:
    # (Código v7.4 sin cambios)
    return list(_clients.keys())

# --- API Wrapper Functions ---
def _handle_api_error(response: dict | None, function_name: str) -> bool:
    # (Código v7.4 sin cambios)
    if response:
        ret_code = response.get('retCode', -1)
        if ret_code == 0: return True
        ret_msg = response.get('retMsg', 'Unknown API Error'); time_now = response.get('time', 'N/A')
        print(f"Error API ({function_name} @ {time_now}): {ret_msg} (Code: {ret_code})")
        if ret_code == 10001: print("  -> Sugerencia: Parámetros inválidos o faltantes.")
        if ret_code == 10002: print("  -> Sugerencia: Error interno Bybit/timeout.")
        if ret_code == 10004: print("  -> Sugerencia: Firma API (Key/Secret/Timestamp/RecvWindow). IP?")
        if ret_code == 10005: print("  -> Sugerencia: Permisos API insuficientes.")
        if ret_code == 10006: print("  -> Sugerencia: Rate Limit.")
        if ret_code in [110012, 110013, 110014, 130010, 130021]: print("  -> Sugerencia: Balance/Fondos/Margen.")
        if ret_code == 10016: print("  -> Sugerencia: API Key expirada/inválida.")
        if ret_code == 10017: print("  -> Sugerencia: Tipo cuenta inválido.")
        if ret_code == 131204: print("  -> Sugerencia (Transfer): Transferencia no soportada.")
        if ret_code == 131210: print("  -> Sugerencia (Transfer): Precisión del monto incorrecta.")
        if ret_code == 131214: print("  -> Sugerencia (Transfer): UID miembro inválido.")
        if ret_code == 110021: print("  -> Sugerencia (Mode): Modo de posición no modificado.")
        if ret_code == 110041: print("  -> Sugerencia (Order): positionIdx no coincide con modo.")
        return False
    else: print(f"Error API ({function_name}): No se recibió respuesta."); return False

# --- Specific API Call Wrappers (sin cambios funcionales) ---
def get_wallet_balance(session, account_type="UNIFIED"):
    # (Código v7.4 sin cambios)
    if not session: print("Error (GWBa): Sesión inválida."); return None
    try: response = session.get_wallet_balance(accountType=account_type.upper()); return response
    except Exception as e: print(f"Excepción en get_wallet_balance({account_type}): {str(e)}"); return None

def get_tickers(session, category, symbol):
    # (Código v7.4 sin cambios)
    if not session: print(f"Error (ticker): Sesión inválida."); return None
    try: response = session.get_tickers(category=category, symbol=symbol); return response
    except Exception as e: print(f"Excepción en get_tickers({symbol}): {str(e)}"); return None

def get_coins_balance(session, account_type, coin=None):
    # (Código v7.4 sin cambios)
    if not session: print("Error (GCBa): Sesión inválida."); return None
    params = {"accountType": account_type.upper()}; function_name = f"get_coins_balance({account_type.upper()}"
    if coin: params["coin"] = coin.upper(); function_name += f", {coin.upper()})"
    else: function_name += ")"
    try: response = session.get_coins_balance(**params); return response
    except (InvalidRequestError, FailedRequestError, AttributeError, Exception) as e:
        print(f"Excepción en {function_name} ({type(e).__name__}): {str(e)}")
        if isinstance(e, AttributeError): print(f"  -> Sugerencia: Verifica si 'get_coins_balance' existe.")
        return None

def create_universal_transfer( session, coin: str, amount: str,
                               from_member_id: int | str, to_member_id: int | str,
                               from_account_type: str, to_account_type: str ):
    # (Código v7.4 sin cambios)
    if not session: print("Error (UniTransfer): Sesión inválida."); return None
    try: from_member_id_int = int(from_member_id); to_member_id_int = int(to_member_id)
    except (ValueError, TypeError) as e: print(f"Error (UniTransfer): IDs miembro inválidos: {e}"); return None
    if not amount or not isinstance(amount, str): print(f"Error (UniTransfer): Amount inválido o no es string: '{amount}'"); return None
    amount_str = amount
    transfer_id = str(uuid.uuid4())
    params = { "transferId": transfer_id, "coin": coin.upper(), "amount": amount_str,
               "fromMemberId": from_member_id_int, "toMemberId": to_member_id_int,
               "fromAccountType": from_account_type.upper(), "toAccountType": to_account_type.upper(), }
    function_name = f"create_universal_transfer(ID:{transfer_id[:8]})"
    print(f"API Call: {function_name} From:{from_member_id_int} To:{to_member_id_int} Amt:{amount_str} {coin}")
    try:
        response = session.create_universal_transfer(**params)
        if _handle_api_error(response, function_name):
            result = response.get('result', {})
            print(f"  -> Éxito envío T. Universal. ID: {result.get('transferId','N/A')}, Status: {result.get('status','UNKNOWN')}")
            return response
        else:
             if response: rc = response.get('retCode');
             if rc == 131210: print("    -> Causa posible: Precisión del monto (amount) incorrecta para API.")
             elif rc in [131200,131001,131228]: print("    -> Causa posible: Saldo insuficiente / Límite de transferencia?")
             elif rc in [10003,10005,10019,131214]: print("    -> Causa posible: Permisos API / IDs Miembro inválidos / Tipos de Cuenta inválidos?")
             elif rc == 131206: print("    -> Causa posible: Restricción de tipo de cuenta para transferencias?")
             elif rc == 131204: print("    -> Causa posible: Transferencia no soportada entre estos tipos de cuenta/miembro?")
             return None
    except AttributeError: print(f"Error Fatal: Método 'create_universal_transfer' NO existe en pybit."); return None
    except (InvalidRequestError, FailedRequestError) as api_err: print(f"Error API específico en {function_name}: {api_err}"); return None
    except Exception as e: print(f"Excepción inesperada en {function_name}: {e}"); traceback.print_exc(); return None