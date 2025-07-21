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
    Orquesta la inicialización de todos los clientes API configurados.
    """
    global _clients, _initialized
    if _initialized:
        memory_logger.log("Advertencia: Clientes API ya inicializados.", level="WARN")
        return

    memory_logger.log("Iniciando Gestor de Conexiones...", level="INFO")
    
    # 1. Cargar credenciales
    _credentials.load_and_validate_uids()
    api_credentials = _credentials.load_api_credentials()
    
    if not api_credentials:
        memory_logger.log("Advertencia: No se encontraron credenciales API válidas. No se inicializarán clientes.", level="WARN")
        _initialized = True
        return

    # 2. Crear clientes usando la fábrica
    for account_name, creds in api_credentials.items():
        session = _client_factory.create_client(account_name, creds)
        if session:
            _clients[account_name] = session

    if not _clients:
        memory_logger.log("Error Fatal: No se pudo inicializar NINGÚN cliente API con éxito.", level="ERROR")
        _initialized = False
        return
        
    # 3. Configurar modos de cuenta para los clientes creados
    _configure_active_clients()

    _initialized = True
    memory_logger.log(f"Gestor de Conexiones inicializado. Cuentas activas: {list(_clients.keys())}", level="INFO")

def get_client(account_name: str) -> Optional[HTTP]:
    """Obtiene una sesión de cliente inicializada por su nombre de cuenta."""
    if not _initialized:
        memory_logger.log("ERROR: Se intentó obtener un cliente antes de inicializar el gestor.", level="ERROR")
        return None
    return _clients.get(account_name)

def get_initialized_accounts() -> list[str]:
    """Devuelve una lista con los nombres de las cuentas inicializadas con éxito."""
    return list(_clients.keys())

def get_session_for_operation(
    purpose: str,
    side: Optional[str] = None,
    specific_account: Optional[str] = None
) -> Tuple[Optional[HTTP], Optional[str]]:
    """
    Centraliza la lógica para obtener la sesión API y el nombre de la cuenta correctos.
    """
    if not _initialized:
        return None, None

    # Prioridad 1: Usar la cuenta específica si se proporciona y es válida
    if specific_account:
        session = _clients.get(specific_account)
        if session:
            return session, specific_account
        else:
            memory_logger.log(f"WARN [Session Selector]: Cuenta específica '{specific_account}' solicitada pero no está inicializada.", level="WARN")

    # Prioridad 2: Lógica basada en el propósito
    target_map = {
        'ticker': getattr(config, 'TICKER_SOURCE_ACCOUNT', config.ACCOUNT_PROFIT),
        'trading_long': getattr(config, 'ACCOUNT_LONGS', config.ACCOUNT_MAIN),
        'trading_short': getattr(config, 'ACCOUNT_SHORTS', config.ACCOUNT_MAIN),
        'general': getattr(config, 'ACCOUNT_MAIN', None),
        'market_data': getattr(config, 'ACCOUNT_MAIN', None)
    }
    purpose_key = f"trading_{side}" if purpose == 'trading' and side else purpose
    target_account_name = target_map.get(purpose_key)

    if target_account_name:
        session = _clients.get(target_account_name)
        if session:
            return session, target_account_name

    # Prioridad 3: Fallback a la cuenta principal
    main_account_name = getattr(config, 'ACCOUNT_MAIN', None)
    if main_account_name and main_account_name in _clients:
        memory_logger.log(f"WARN [Session Selector]: Cuenta objetivo para '{purpose}' ('{target_account_name}') no disponible. Usando fallback a cuenta principal '{main_account_name}'.", level="WARN")
        return _clients[main_account_name], main_account_name
        
    # Prioridad 4: Fallback a CUALQUIER cuenta disponible
    if _clients:
        fallback_account_name = next(iter(_clients))
        memory_logger.log(f"WARN [Session Selector]: Ni la cuenta objetivo ni la principal están disponibles. Usando primera cuenta disponible: '{fallback_account_name}'.", level="WARN")
        return _clients[fallback_account_name], fallback_account_name

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