"""
Módulo Gestor de Sesiones API (Versión de Clase).

v2.1 (Singleton Accessor):
- Se añade un patrón de accesor global (`get_connection_manager_instance`) para que los
  módulos de API de bajo nivel puedan acceder a la única instancia creada por el
  BotController sin necesidad de inyección de dependencias directa, facilitando la
  transición a la nueva arquitectura.

v2.0 (Refactor a Clase):
- Toda la lógica de gestión de clientes API se encapsula en la clase ConnectionManager.
"""
import sys
import time
import uuid
from typing import Optional, Dict, Tuple, List, Any
from pybit.unified_trading import HTTP

# --- Dependencias del Proyecto ---
import config
from core.logging import memory_logger
from . import _credentials
from . import _client_factory

# --- INICIO DE LA MODIFICACIÓN: Patrón de Instancia Única ---
_connection_manager_instance: Optional['ConnectionManager'] = None

def get_connection_manager_instance() -> Optional['ConnectionManager']:
    """Devuelve la instancia global única del ConnectionManager."""
    return _connection_manager_instance
# --- FIN DE LA MODIFICACIÓN ---


class ConnectionManager:
    """
    Gestiona la inicialización, validación y acceso a todas las sesiones de cliente API.
    Actúa como un repositorio centralizado para los clientes API activos de una sesión.
    """

    def __init__(self, dependencies: Dict[str, Any]):
        """
        Inicializa el ConnectionManager, inyectando sus dependencias.
        """
        # --- INICIO DE LA MODIFICACIÓN: Registrar la instancia global ---
        global _connection_manager_instance
        if _connection_manager_instance is not None:
            # Esto previene que se creen múltiples instancias, reforzando el patrón
            memory_logger.log("WARN: Se intentó crear una segunda instancia de ConnectionManager.", "WARN")
        _connection_manager_instance = self
        # --- FIN DE LA MODIFICACIÓN ---

        self._config = dependencies.get('config_module', config)
        self._memory_logger = dependencies.get('memory_logger_module', memory_logger)
        
        # Módulos internos que actúan como librerías de utilidad
        self._credentials = _credentials
        self._client_factory = _client_factory
        
        # El estado ahora es de la instancia, no global
        self._clients: Dict[str, HTTP] = {}
        self._initialized = False

    def initialize_all_clients(self):
        """
        Orquesta la inicialización y VALIDACIÓN ESTRICTA de todos los clientes API configurados.
        El bot se detendrá si alguna de las cuentas requeridas falla.
        La lógica es idéntica a la versión funcional, pero ahora opera sobre 'self'.
        """
        if self._initialized:
            self._memory_logger.log("Advertencia: Clientes API ya inicializados.", level="WARN")
            return

        print("\n" + "="*80)
        print("INICIANDO GESTOR DE CONEXIONES Y VALIDANDO CUENTAS API...")
        print("="*80)
        
        self._credentials.load_and_validate_uids()
        api_credentials = self._credentials.load_api_credentials()
        
        required_accounts = set(self._config.ACCOUNTS_TO_INITIALIZE)
        
        if not required_accounts.issubset(set(api_credentials.keys())):
            missing_creds = required_accounts - set(api_credentials.keys())
            print("!!! ERROR FATAL: Faltan credenciales API en el archivo .env para las siguientes cuentas:")
            for acc in missing_creds: print(f"  - {acc}")
            print("El bot no puede continuar. Por favor, completa tu archivo .env.")
            print("="*80)
            sys.exit(1)

        print("\nIntentando conectar y validar cada cuenta...")
        failed_accounts = {}
        
        for account_name in required_accounts:
            creds = api_credentials.get(account_name)
            
            session = self._client_factory.create_client(account_name, creds)
            if not session:
                failed_accounts[account_name] = "Fallo al crear el cliente o al conectar (get_server_time)."
                continue
            
            try:
                balance_response = session.get_wallet_balance(accountType="UNIFIED")
                if balance_response and balance_response.get('retCode') == 0:
                    result_list = balance_response.get('result', {}).get('list', [])
                    if result_list:
                        equity = result_list[0].get('totalEquity', 'N/A')
                        print(f"  -> ÉXITO: Conexión con '{account_name}' validada. Equity: {equity} USD")
                        self._clients[account_name] = session
                    else:
                        print(f"  -> ÉXITO: Conexión con '{account_name}' validada. (Sin datos de balance)")
                        self._clients[account_name] = session
                else:
                    error_msg = balance_response.get('retMsg', 'Error desconocido')
                    failed_accounts[account_name] = f"Fallo al obtener balance: {error_msg}"
            except Exception as e:
                failed_accounts[account_name] = f"Excepción al obtener balance: {str(e)}"

        if failed_accounts:
            print("\n" + "="*80)
            print("!!! ERROR FATAL: No se pudieron validar todas las cuentas API requeridas !!!")
            for acc, reason in failed_accounts.items(): print(f"  - Cuenta '{acc}': {reason}")
            print("\nEl bot no puede continuar. Revisa tus claves API, permisos y conexión.")
            print("="*80)
            sys.exit(1)
            
        print("\nConfigurando modos de cuenta (Hedge Mode)...")
        self._configure_active_clients()

        self._initialized = True
        self._memory_logger.log(f"Gestor de Conexiones inicializado. Cuentas activas: {list(self._clients.keys())}", level="INFO")
        print("\n" + "="*80)
        print("GESTOR DE CONEXIONES INICIALIZADO. TODAS LAS CUENTAS ESTÁN ACTIVAS Y VALIDADAS.")
        print("="*80)

    def test_subaccount_transfers(self) -> Tuple[bool, str]:
        """
        Realiza una secuencia de micro-transferencias para validar la funcionalidad.
        """
        main_session = self.get_client(self._config.ACCOUNT_MAIN)
        if not main_session:
            return False, "Fallo crítico: La cuenta principal no está disponible para iniciar la prueba."

        test_amount = "0.001"
        coin = "USDT"
        
        accounts_to_test = [self._config.ACCOUNT_LONGS, self._config.ACCOUNT_SHORTS]
        profit_account = self._config.ACCOUNT_PROFIT
        
        required_uids = accounts_to_test + [profit_account]
        for acc in required_uids:
            if acc not in self._config.LOADED_UIDS:
                return False, f"Fallo: El UID para la cuenta '{acc}' no se encontró en la configuración."

        profit_uid = self._config.LOADED_UIDS[profit_account]

        for source_account in accounts_to_test:
            source_uid = self._config.LOADED_UIDS[source_account]
            
            try:
                print(f"  -> Probando: {source_account} -> {profit_account} ({test_amount} {coin})... ", end="")
                response_fwd = main_session.create_universal_transfer(transferId=str(uuid.uuid4()), coin=coin, amount=test_amount, fromMemberId=int(source_uid), toMemberId=int(profit_uid), fromAccountType="UNIFIED", toAccountType="UNIFIED")
                if not (response_fwd and response_fwd.get('retCode') == 0):
                    print("FALLO.")
                    return False, f"Fallo en la transferencia de '{source_account}' a 'profit'. Razón: {response_fwd.get('retMsg', 'Error desconocido')}"
                print("ÉXITO.")
                time.sleep(1)
            except Exception as e:
                print("FALLO.")
                return False, f"Excepción durante la transferencia de '{source_account}' a 'profit': {e}"

            try:
                print(f"  -> Devolviendo: {profit_account} -> {source_account} ({test_amount} {coin})... ", end="")
                response_bwd = main_session.create_universal_transfer(transferId=str(uuid.uuid4()), coin=coin, amount=test_amount, fromMemberId=int(profit_uid), toMemberId=int(source_uid), fromAccountType="UNIFIED", toAccountType="UNIFIED")
                if not (response_bwd and response_bwd.get('retCode') == 0):
                    print("FALLO.")
                    return False, f"¡CRÍTICO! Fallo en la transferencia de retorno a '{source_account}'. Mueve {test_amount} {coin} manualmente. Razón: {response_bwd.get('retMsg', 'Error desconocido')}"
                print("ÉXITO.")
                time.sleep(1)
            except Exception as e:
                print("FALLO.")
                return False, f"¡CRÍTICO! Excepción en la transferencia de retorno a '{source_account}'. Mueve {test_amount} {coin} manualmente: {e}"

        return True, "Prueba de transferencias completada con éxito para todas las cuentas."

    def get_client(self, account_name: str) -> Optional[HTTP]:
        """Obtiene una sesión de cliente inicializada por su nombre de cuenta."""
        if not self._initialized:
            self._memory_logger.log("ERROR: Se intentó obtener un cliente antes de inicializar el gestor.", level="ERROR")
            return None
        return self._clients.get(account_name)

    def get_initialized_accounts(self) -> List[str]:
        """Devuelve una lista con los nombres de las cuentas inicializadas con éxito."""
        return list(self._clients.keys())

    def get_session_for_operation(self, purpose: str, side: Optional[str] = None, specific_account: Optional[str] = None) -> Tuple[Optional[HTTP], Optional[str]]:
        """
        Centraliza la lógica para obtener la sesión API y el nombre de la cuenta correctos.
        """
        if not self._initialized:
            return None, None

        if specific_account:
            session = self._clients.get(specific_account)
            if session:
                return session, specific_account
            else:
                self._memory_logger.log(f"ERROR [Session Selector]: La cuenta específica requerida '{specific_account}' no está inicializada.", level="ERROR")
                return None, None

        target_map = {
            'ticker': self._config.TICKER_SOURCE_ACCOUNT,
            'trading_long': self._config.ACCOUNT_LONGS,
            'trading_short': self._config.ACCOUNT_SHORTS,
            'general': self._config.ACCOUNT_MAIN,
            'market_data': self._config.ACCOUNT_MAIN
        }
        purpose_key = f"trading_{side}" if purpose == 'trading' and side else purpose
        target_account_name = target_map.get(purpose_key)

        if target_account_name:
            session = self._clients.get(target_account_name)
            if session:
                return session, target_account_name

        self._memory_logger.log(f"ERROR [Session Selector]: No se pudo encontrar una sesión API válida para el propósito '{purpose_key}' (Cuenta objetivo: '{target_account_name}').", level="ERROR")
        return None, None
  
    def _configure_active_clients(self):
        """
        Itera sobre los clientes activos y aplica configuraciones necesarias.
        Método privado de ayuda.
        """
        long_session, long_acc = self.get_session_for_operation('trading', side='long')
        short_session, short_acc = self.get_session_for_operation('trading', side='short')

        accounts_to_configure = {}
        if long_session: accounts_to_configure[long_acc] = long_session
        if short_session: accounts_to_configure[short_acc] = short_session

        if not accounts_to_configure:
            self._memory_logger.log("WARN [Manager]: No hay cuentas de trading activas para configurar.", level="WARN")
            return

        all_ok = all(
            self._client_factory.configure_account_mode(session, name)
            for name, session in accounts_to_configure.items()
        )
    
        if not all_ok:
            error_msg = "!! ERROR CRÍTICO: Falló la configuración de modo de cuenta. El bot no puede continuar de forma segura."
            self._memory_logger.log(error_msg, level="ERROR")
            print(error_msg)
            sys.exit(1)