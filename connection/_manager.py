# connection/_manager.py

"""
Gestiona la inicialización y el acceso a las sesiones de cliente API de Bybit (Live Mode).

Su única responsabilidad es establecer, configurar y proporcionar las sesiones
de conexión cruda (`pybit.HTTP`). La abstracción de las llamadas API específicas
se delega al paquete `core/api`.
"""
import os
import sys
import uuid
import traceback
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Importar dependencias core y de configuración desde su nueva ubicación.
try:
    # Ajustar el sys.path para encontrar la raíz del proyecto.
    if __name__ != "__main__":
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir) # Raíz del proyecto
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    # Importar config y el logger usando rutas absolutas desde la raíz.
    import config
    from core.logging import memory_logger

except ImportError as e:
    # Fallback si las importaciones fallan
    print(f"ERROR CRITICO [Manager Import]: No se pudo importar un módulo esencial. Detalle: {e}")
    config = type('obj', (object,), {
        'PROJECT_ROOT': '.', 'ACCOUNTS_TO_INITIALIZE': [], 'ACCOUNT_API_KEYS_ENV_MAP': {},
        'ACCOUNT_UID_ENV_VAR_MAP': {}, 'POSITION_TRADING_MODE': 'N/A', 'TICKER_SYMBOL': 'N/A',
        'CATEGORY_LINEAR': 'linear', 'UNIVERSAL_TESTNET_MODE': True,
        'DEFAULT_RECV_WINDOW': 10000, 'LOADED_UIDS': {}
    })()
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# Attempt to import specific exceptions, provide fallbacks
try:
    from pybit.exceptions import InvalidRequestError, FailedRequestError
except ImportError:
    print("Advertencia [Manager]: No se encontraron excepciones específicas de pybit. Usando fallbacks.")
    class InvalidRequestError(Exception): pass
    class FailedRequestError(Exception):
        def __init__(self, message, status_code=None):
            super().__init__(message)
            self.status_code = status_code


# Module state
_clients = {}     # Dictionary to store initialized client sessions {account_name: session}
_initialized = False # Flag to track if initialization has run

# --- Helper Functions (Responsabilidad de este módulo) ---

def _load_api_keys_and_uids() -> dict:
    """
    Carga credenciales API y UIDs desde .env basado en los mapas de config.
    Puebla config.LOADED_UIDS si los UIDs son válidos.
    Retorna solo las credenciales API encontradas.
    """
    env_path = os.path.join(getattr(config, 'PROJECT_ROOT', '.'), '.env')
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        memory_logger.log("Advertencia [Manager]: .env no encontrado. No se pueden cargar claves/UIDs.", level="WARN")

    api_credentials = {}
    all_keys_found = True
    all_uids_valid = True
    memory_logger.log("Cargando credenciales API y UIDs desde .env (connection._manager)...", level="INFO")

    accounts_to_check = getattr(config, 'ACCOUNTS_TO_INITIALIZE', [])
    api_map = getattr(config, 'ACCOUNT_API_KEYS_ENV_MAP', {})

    if not accounts_to_check:
        memory_logger.log("Advertencia: No hay cuentas definidas en config.ACCOUNTS_TO_INITIALIZE.", level="WARN")
    if not api_map:
        memory_logger.log("Advertencia: No hay mapeo de claves API en config.ACCOUNT_API_KEYS_ENV_MAP.", level="WARN")

    for account_name in accounts_to_check:
        if account_name in api_map:
            key_env_var, secret_env_var = api_map[account_name]
            api_key = os.getenv(key_env_var)
            api_secret = os.getenv(secret_env_var)
            if not api_key or not api_secret or api_key.startswith("YOUR_") or api_secret.startswith("YOUR_"):
                memory_logger.log(f"ERROR: Claves API no encontradas o sin configurar para '{account_name}' (Variables: {key_env_var}, {secret_env_var})", level="ERROR")
                all_keys_found = False
            else:
                memory_logger.log(f"Claves encontradas para '{account_name}'. Key: ...{api_key[-4:]}", level="INFO")
                api_credentials[account_name] = {"key": api_key, "secret": api_secret}

    if not all_keys_found:
        memory_logger.log("Advertencia: Faltan o son inválidas una o más claves API para las cuentas listadas.", level="WARN")

    uid_map = getattr(config, 'ACCOUNT_UID_ENV_VAR_MAP', {})
    loaded_uids_temp = {}
    if not uid_map:
        memory_logger.log("Info: No hay mapeo de UIDs en config.ACCOUNT_UID_ENV_VAR_MAP.", level="INFO")
    else:
        memory_logger.log("Cargando y Validando UIDs...", level="INFO")
        for account_name, env_var_name in uid_map.items():
            uid_value = os.getenv(env_var_name)
            if uid_value is None:
                memory_logger.log(f"ERROR: Variable entorno UID '{env_var_name}' (cuenta '{account_name}') NO ENCONTRADA.", level="ERROR")
                all_uids_valid = False
            elif not uid_value.isdigit():
                memory_logger.log(f"ERROR: Valor UID para '{env_var_name}' (cuenta '{account_name}') = '{uid_value}' NO ES NUMÉRICO.", level="ERROR")
                all_uids_valid = False
            else:
                loaded_uids_temp[account_name] = uid_value

    if all_uids_valid and uid_map:
        if hasattr(config, 'LOADED_UIDS'):
            config.LOADED_UIDS = loaded_uids_temp
        else:
            memory_logger.log("ERROR INTERNO: El objeto config no tiene el atributo LOADED_UIDS.", level="ERROR")
        memory_logger.log(f"UIDs validados y almacenados en config.LOADED_UIDS: {list(getattr(config, 'LOADED_UIDS', {}).keys())}", level="INFO")
    elif not uid_map:
        pass
    else:
        memory_logger.log("Error Crítico: Faltan o son inválidos UIDs necesarios. Las transferencias fallarán.", level="ERROR")
        if hasattr(config, 'LOADED_UIDS'):
            config.LOADED_UIDS = {}

    return api_credentials

def _check_and_set_hedge_mode(session, account_name_used: str) -> bool:
    """Intenta establecer Hedge Mode y verifica el resultado."""
    symbol = getattr(config, 'TICKER_SYMBOL', None)
    category = getattr(config, 'CATEGORY_LINEAR', 'linear')
    target_mode = 3 # 3 para Hedge Mode

    if not symbol:
        memory_logger.log("WARN [Hedge Mode Check]: Falta TICKER_SYMBOL.", level="WARN")
        return False

    memory_logger.log(f"INFO [Hedge Mode Check]: Verificando/Estableciendo Hedge Mode (mode=3) para {symbol} ({category}) usando cuenta '{account_name_used}'...", level="INFO")
    try:
        response = session.switch_position_mode(category=category, symbol=symbol, mode=target_mode)
        if response and response.get('retCode') == 0:
            memory_logger.log(f"ÉXITO [Hedge Mode Check]: Modo establecido a Hedge para {symbol} (o ya lo estaba y API OK).", level="INFO")
            return True
        elif response and response.get('retCode') == 110021:
            memory_logger.log(f"ÉXITO [Hedge Mode Check]: Modo ya era Hedge para {symbol} (Respuesta 110021).", level="INFO")
            return True
        elif response:
            ret_code = response.get('retCode', -1)
            ret_msg = response.get('retMsg', 'Unknown API Error')
            memory_logger.log(f"ERROR API [Hedge Mode Check]: Código={ret_code}, Mensaje='{ret_msg}'", level="ERROR")
            return False
        else:
            memory_logger.log(f"ERROR [Hedge Mode Check]: No se recibió respuesta de la API.", level="ERROR")
            return False
    except InvalidRequestError as invalid_req_err:
        error_message = str(invalid_req_err)
        if "110021" in error_message or "position mode is not modified" in error_message.lower():
            memory_logger.log(f"ÉXITO [Hedge Mode Check]: Modo ya era Hedge para {symbol} (InvalidRequestError 110021).", level="INFO")
            return True
        else:
            memory_logger.log(f"ERROR API [Hedge Mode Check] - Invalid Request: {invalid_req_err}", level="ERROR")
            return False
    except FailedRequestError as api_err:
        status_code = getattr(api_err, 'status_code', None)
        memory_logger.log(f"ERROR HTTP [Hedge Mode Check]: {api_err} (Status: {status_code})", level="ERROR")
        return False
    except AttributeError:
        memory_logger.log("ERROR Fatal [Hedge Mode Check]: Método 'switch_position_mode' NO existe.", level="ERROR")
        return False
    except Exception as e:
        memory_logger.log(f"ERROR Inesperado [Hedge Mode Check]: {e}", level="ERROR")
        memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")
        return False

# --- Funciones de Gestión de Conexión (Responsabilidad de este módulo) ---

def initialize_all_clients():
    """Initializes Bybit HTTP clients and checks/sets Hedge Mode if needed."""
    global _clients, _initialized
    if _initialized:
        memory_logger.log("Advertencia: Clientes API (Live) ya inicializados.", level="WARN")
        return

    memory_logger.log("Inicializando Clientes API Bybit (Live)...", level="INFO")
    api_credentials = _load_api_keys_and_uids()
    any_client_successful = False

    accounts_to_init = getattr(config, 'ACCOUNTS_TO_INITIALIZE', [])
    if not accounts_to_init:
        memory_logger.log("No hay cuentas listadas para inicializar.", level="INFO")
        _initialized = False
        return

    for account_name in accounts_to_init:
        if account_name in api_credentials:
            creds = api_credentials[account_name]
            memory_logger.log(f"Inicializando cliente para: '{account_name}'...", level="INFO")
            try:
                session = HTTP(
                    testnet=getattr(config, 'UNIVERSAL_TESTNET_MODE', True),
                    api_key=creds["key"],
                    api_secret=creds["secret"],
                    recv_window=getattr(config, 'DEFAULT_RECV_WINDOW', 10000)
                )
                server_time = session.get_server_time()
                if server_time and server_time.get('retCode') == 0:
                    memory_logger.log(f"Conexión exitosa para '{account_name}'.", level="INFO")
                    _clients[account_name] = session
                    any_client_successful = True
                else:
                    ret_msg = server_time.get('retMsg', '?')
                    ret_code = server_time.get('retCode', -1)
                    memory_logger.log(f"ERROR de conexión para '{account_name}': {ret_msg} (Code: {ret_code})", level="ERROR")
            except Exception as e:
                memory_logger.log(f"ERROR crítico inicializando cliente '{account_name}': {str(e)}", level="ERROR")
        else:
             loaded_uids_dict = getattr(config, 'LOADED_UIDS', {})
             if account_name in loaded_uids_dict:
                 memory_logger.log(f"Info: No se inicializó cliente API para '{account_name}' (sin credenciales), UID cargado.", level="INFO")
             else:
                 memory_logger.log(f"Advertencia: No se inicializó cliente API para '{account_name}' (sin credenciales ni UID).", level="WARN")

    if not any_client_successful and any(acc in api_credentials for acc in accounts_to_init):
        memory_logger.log("Error Fatal: No se pudo inicializar NINGÚN cliente API.", level="ERROR")
        _initialized = False
        return
    elif not _clients:
        memory_logger.log("Advertencia: No se inicializó ningún cliente API activo.", level="WARN")
        _initialized = True
        return
    else:
        memory_logger.log(f"Inicialización clientes API completada. Activos: {list(_clients.keys())}", level="INFO")
        _initialized = True

    trading_mode = getattr(config, 'POSITION_TRADING_MODE', 'N/A')
    if trading_mode == "LONG_SHORT":
        memory_logger.log("INFO [Hedge Mode Check]: Verificando/Estableciendo Hedge Mode para cuentas operativas...", level="INFO")

        accounts_to_check = []
        main_acc_name = getattr(config, 'ACCOUNT_MAIN', 'main')
        longs_acc_name = getattr(config, 'ACCOUNT_LONGS', 'longs')
        shorts_acc_name = getattr(config, 'ACCOUNT_SHORTS', 'shorts')

        # Usar set para evitar duplicados si main es igual a longs/shorts
        if main_acc_name in _clients: accounts_to_check.append(main_acc_name)
        if longs_acc_name in _clients: accounts_to_check.append(longs_acc_name)
        if shorts_acc_name in _clients: accounts_to_check.append(shorts_acc_name)

        if not accounts_to_check:
             memory_logger.log("WARN [Hedge Mode Check]: Ninguna cuenta operativa (main, longs, shorts) fue inicializada.", level="WARN")
        else:
            all_accounts_ok = all(
                _check_and_set_hedge_mode(_clients[acc_name], acc_name)
                for acc_name in set(accounts_to_check)
            )

            if not all_accounts_ok:
                error_msg = (
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                    "!! ERROR CRÍTICO: No se pudo confirmar/establecer Hedge Mode en TODAS      !!\n"
                    "!!                las cuentas operativas requeridas. El bot no puede      !!\n"
                    "!!                continuar de forma segura.                              !!\n"
                    "!! Verifica manualmente la configuración en Bybit para TODAS las cuentas. !!\n"
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                )
                memory_logger.log(error_msg, level="ERROR")
                sys.exit("Error crítico configurando Hedge Mode.")
            else:
                 memory_logger.log("INFO [Hedge Mode Check]: Modo Hedge verificado/establecido correctamente para todas las cuentas operativas.", level="INFO")

def get_client(account_name: str):
    """Obtiene una sesión de cliente inicializada por nombre de cuenta."""
    global _initialized
    if not _initialized: return None
    client_instance = _clients.get(account_name)
    return client_instance

def get_initialized_accounts() -> list:
    """Devuelve una lista con los nombres de las cuentas que se inicializaron con éxito."""
    return list(_clients.keys())

# --- [Temporal] API Wrapper para el Ticker ---
# Esta función se mantiene temporalmente porque _ticker.py depende de ella.
# En una refactorización futura, _ticker.py podría usar core.api directamente.
def get_tickers(session, category, symbol):
    """Wrapper simple para la llamada get_tickers de la API."""
    if not session:
        memory_logger.log(f"Error (get_tickers): Sesión inválida.", level="ERROR")
        return None
    try:
        response = session.get_tickers(category=category, symbol=symbol)
        return response
    except Exception as e:
        memory_logger.log(f"Excepción en get_tickers({symbol}): {str(e)}", level="ERROR")
        return None
