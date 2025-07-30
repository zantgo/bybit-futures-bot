# connection/_manager.py

"""
Módulo Gestor de Sesiones API.

Su única responsabilidad es orquestar la inicialización de todos los clientes API
y actuar como el punto de acceso central (caché) a las sesiones activas.
Utiliza los módulos `_credentials` y `_client_factory` para realizar las tareas
de bajo nivel.
"""
import sys
from typing import Optional, Dict, Tuple
from pybit.unified_trading import HTTP
import time
import uuid
# --- Dependencias del Proyecto ---
import config
from core.logging import memory_logger
from . import _credentials
from . import _client_factory

# --- Estado del Módulo (Privado) ---
_clients: Dict[str, HTTP] = {}
_initialized = False

# --- Funciones Públicas ---
def initialize_all_clients():
    """
    Orquesta la inicialización y VALIDACIÓN ESTRICTA de todos los clientes API configurados.
    El bot se detendrá si alguna de las cuentas requeridas falla al conectar o al obtener su balance.
    """
    global _clients, _initialized
    if _initialized:
        memory_logger.log("Advertencia: Clientes API ya inicializados.", level="WARN")
        return

    print("\n" + "="*80)
    print("INICIANDO GESTOR DE CONEXIONES Y VALIDANDO CUENTAS API...")
    print("="*80)
    
    # --- PASO 1: Cargar credenciales y UIDs (detendrá el bot si el .env o los UIDs faltan) ---
    _credentials.load_and_validate_uids()
    api_credentials = _credentials.load_api_credentials()
    
    required_accounts = set(config.ACCOUNTS_TO_INITIALIZE)
    
    # Verificación de que existen credenciales para todas las cuentas requeridas en el .env
    if not required_accounts.issubset(set(api_credentials.keys())):
        missing_creds = required_accounts - set(api_credentials.keys())
        print("!!! ERROR FATAL: Faltan credenciales API en el archivo .env para las siguientes cuentas:")
        for acc in missing_creds:
            print(f"  - {acc}")
        print("El bot no puede continuar. Por favor, completa tu archivo .env.")
        print("="*80)
        sys.exit(1)

    # --- PASO 2: Crear clientes y validar conexión obteniendo el balance ---
    print("\nIntentando conectar y validar cada cuenta...")
    failed_accounts = {}
    
    for account_name in required_accounts:
        creds = api_credentials.get(account_name)
        if not creds:
            # Esta comprobación es redundante por la anterior, pero es una buena práctica de seguridad.
            failed_accounts[account_name] = "Credenciales no encontradas."
            continue

        # Crear cliente
        session = _client_factory.create_client(account_name, creds)
        if not session:
            failed_accounts[account_name] = "Fallo al crear el cliente o al conectar (get_server_time)."
            continue
            
        # Prueba definitiva: Obtener balance
        try:
            # Usamos la llamada directa de pybit, ya que el adaptador aún no está listo.
            balance_response = session.get_wallet_balance(accountType="UNIFIED")
            if balance_response and balance_response.get('retCode') == 0:
                result_list = balance_response.get('result', {}).get('list', [])
                if result_list:
                    equity = result_list[0].get('totalEquity', 'N/A')
                    print(f"  -> ÉXITO: Conexión con '{account_name}' validada. Equity: {equity} USD")
                    _clients[account_name] = session
                else:
                    # Respuesta exitosa pero sin datos de balance, podría ser una cuenta nueva. Aceptable.
                    print(f"  -> ÉXITO: Conexión con '{account_name}' validada. (Sin datos de balance, puede ser una cuenta nueva)")
                    _clients[account_name] = session
            else:
                error_msg = balance_response.get('retMsg', 'Error desconocido de la API')
                failed_accounts[account_name] = f"Fallo al obtener balance: {error_msg}"
        except Exception as e:
            failed_accounts[account_name] = f"Excepción al obtener balance: {str(e)}"

    # --- PASO 3: Verificación final y parada si hay fallos ---
    if failed_accounts:
        print("\n" + "="*80)
        print("!!! ERROR FATAL: No se pudieron validar todas las cuentas API requeridas !!!")
        for acc, reason in failed_accounts.items():
            print(f"  - Cuenta '{acc}': {reason}")
        print("\nEl bot no puede continuar de forma segura. Revisa tus claves API, permisos y conexión.")
        print("="*80)
        sys.exit(1)
        
    # --- PASO 4: Configurar modos de cuenta para los clientes validados ---
    print("\nConfigurando modos de cuenta (Hedge Mode)...")
    _configure_active_clients()

    _initialized = True
    print("\n" + "="*80)
    print("GESTOR DE CONEXIONES INICIALIZADO. TODAS LAS CUENTAS ESTÁN ACTIVAS Y VALIDADAS.")
    print("="*80)
    #memory_logger.log(f"Gestor de Conexiones inicializado. Cuentas activas: {list(_clients.keys())}", level="INFO")


def test_subaccount_transfers() -> Tuple[bool, str]:
    """
    Realiza una secuencia de micro-transferencias para validar la funcionalidad.
    Transfiere 0.001 USDT de longs->profit->longs y de shorts->profit->shorts.
    Devuelve un booleano de éxito y un mensaje con el resultado.
    """
    main_session = get_client(config.ACCOUNT_MAIN)
    if not main_session:
        return False, "Fallo crítico: La cuenta principal no está disponible para iniciar la prueba."

    test_amount = "0.001"
    coin = "USDT"
    
    # Lista de cuentas a probar
    accounts_to_test = [config.ACCOUNT_LONGS, config.ACCOUNT_SHORTS]
    profit_account = config.ACCOUNT_PROFIT
    
    # Verificar que todos los UIDs necesarios están cargados
    required_uids = accounts_to_test + [profit_account]
    for acc in required_uids:
        if acc not in config.LOADED_UIDS:
            return False, f"Fallo: El UID para la cuenta '{acc}' no se encontró en la configuración."

    profit_uid = config.LOADED_UIDS[profit_account]

    for source_account in accounts_to_test:
        source_uid = config.LOADED_UIDS[source_account]
        
        # --- Transferencia de Ida (Fuente -> Profit) ---
        try:
            transfer_id_forward = str(uuid.uuid4())
            print(f"  -> Probando: {source_account} -> {profit_account} ({test_amount} {coin})... ", end="")
            
            response_fwd = main_session.create_universal_transfer(
                transferId=transfer_id_forward, coin=coin, amount=test_amount,
                fromMemberId=int(source_uid), toMemberId=int(profit_uid),
                fromAccountType="UNIFIED", toAccountType="UNIFIED"
            )
            if not (response_fwd and response_fwd.get('retCode') == 0):
                msg = response_fwd.get('retMsg', 'Error desconocido')
                print("FALLO.")
                return False, f"Fallo en la transferencia de '{source_account}' a 'profit'. Razón: {msg}"
            
            print("ÉXITO.")
            time.sleep(1) # Pausa para asegurar que la API procese

        except Exception as e:
            print("FALLO.")
            return False, f"Excepción durante la transferencia de '{source_account}' a 'profit': {e}"

        # --- Transferencia de Vuelta (Profit -> Fuente) ---
        try:
            transfer_id_backward = str(uuid.uuid4())
            print(f"  -> Devolviendo: {profit_account} -> {source_account} ({test_amount} {coin})... ", end="")

            response_bwd = main_session.create_universal_transfer(
                transferId=transfer_id_backward, coin=coin, amount=test_amount,
                fromMemberId=int(profit_uid), toMemberId=int(source_uid),
                fromAccountType="UNIFIED", toAccountType="UNIFIED"
            )
            if not (response_bwd and response_bwd.get('retCode') == 0):
                msg = response_bwd.get('retMsg', 'Error desconocido')
                print("FALLO.")
                return False, f"¡CRÍTICO! Fallo en la transferencia de retorno a '{source_account}'. Mueve {test_amount} {coin} manualmente. Razón: {msg}"
            
            print("ÉXITO.")
            time.sleep(1)

        except Exception as e:
            print("FALLO.")
            return False, f"¡CRÍTICO! Excepción en la transferencia de retorno a '{source_account}'. Mueve {test_amount} {coin} manualmente: {e}"

    return True, "Prueba de transferencias completada con éxito para todas las cuentas."

def get_client(account_name: str) -> Optional[HTTP]:
    """Obtiene una sesión de cliente inicializada por su nombre de cuenta."""
    if not _initialized:
        memory_logger.log("ERROR: Se intentó obtener un cliente antes de inicializar el gestor.", level="ERROR")
        return None
    return _clients.get(account_name)

def get_initialized_accounts() -> list[str]:
    """Devuelve una lista con los nombres de las cuentas inicializadas con éxito."""
    return list(_clients.keys())

# ARCHIVO: ./connection/_manager.py

def get_session_for_operation(
    purpose: str,
    side: Optional[str] = None,
    specific_account: Optional[str] = None
) -> Tuple[Optional[HTTP], Optional[str]]:
    """
    Centraliza la lógica para obtener la sesión API y el nombre de la cuenta correctos.
    --- VERSIÓN MODIFICADA: Lógica de fallback eliminada para un comportamiento estricto. ---
    """
    if not _initialized:
        return None, None

    # Prioridad 1: Usar la cuenta específica si se proporciona y es válida
    if specific_account:
        session = _clients.get(specific_account)
        if session:
            return session, specific_account
        else:
            # Si se pide una cuenta específica y no existe, la operación debe fallar.
            memory_logger.log(f"ERROR [Session Selector]: La cuenta específica requerida '{specific_account}' no está inicializada.", level="ERROR")
            return None, None

    # Prioridad 2: Lógica basada en el propósito
    target_map = {
        'ticker': getattr(config, 'TICKER_SOURCE_ACCOUNT', config.ACCOUNT_PROFIT),
        'trading_long': getattr(config, 'ACCOUNT_LONGS', None), # Importante: default a None
        'trading_short': getattr(config, 'ACCOUNT_SHORTS', None), # Importante: default a None
        'general': getattr(config, 'ACCOUNT_MAIN', None),
        'market_data': getattr(config, 'ACCOUNT_MAIN', None)
    }
    purpose_key = f"trading_{side}" if purpose == 'trading' and side else purpose
    target_account_name = target_map.get(purpose_key)

    if target_account_name:
        session = _clients.get(target_account_name)
        if session:
            return session, target_account_name

    # Si no se encontró una sesión para el propósito específico, la operación falla.
    memory_logger.log(f"ERROR [Session Selector]: No se pudo encontrar una sesión API válida para el propósito '{purpose_key}' (Cuenta objetivo: '{target_account_name}').", level="ERROR")
    return None, None
  
# --- Funciones Internas (Privadas) ---

def _configure_active_clients():
    """
    Itera sobre los clientes activos y aplica configuraciones necesarias, como el modo de cuenta.
    """
    long_session, long_acc = get_session_for_operation('trading', side='long')
    short_session, short_acc = get_session_for_operation('trading', side='short')

    accounts_to_configure = {}
    if long_session: accounts_to_configure[long_acc] = long_session
    if short_session: accounts_to_configure[short_acc] = short_session

    if not accounts_to_configure:
        memory_logger.log("WARN [Manager]: No hay cuentas de trading activas para configurar.", level="WARN")
        return

    all_ok = all(
        _client_factory.configure_account_mode(session, name)
        for name, session in accounts_to_configure.items()
    )
    
    if not all_ok:
        error_msg = "!! ERROR CRÍTICO: Falló la configuración de modo de cuenta para una o más cuentas. El bot no puede continuar de forma segura."
        memory_logger.log(error_msg, level="ERROR")
        sys.exit(error_msg)