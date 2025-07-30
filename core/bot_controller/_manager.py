"""
Módulo Gestor del Bot (BotController).
... (docstring) ...
"""
import sys
import time
import traceback
from typing import Dict, Any, Optional, Tuple

# --- Dependencias del Proyecto (inyectadas a través de __init__) ---
try:
    # Clases que el BotController debe poder instanciar
    from core.strategy.sm._manager import SessionManager
    from core.strategy.om._manager import OperationManager
    from core.strategy.pm.manager import PositionManager
    from core.strategy.pm._balance import BalanceManager
    from core.strategy.pm._position_state import PositionState
    from core.strategy.pm._executor import PositionExecutor
    from core.exchange._bybit_adapter import BybitAdapter

    # Módulos de soporte que el BotController utiliza
    from core.logging import memory_logger
    from core.api import trading as trading_api
    from connection import manager as connection_manager
    from core.menu._helpers import get_input, UserInputCancelled

except ImportError:
    # Fallbacks para análisis estático y resiliencia
    SessionManager = OperationManager = PositionManager = BalanceManager = None
    PositionState = PositionExecutor = BybitAdapter = None
    memory_logger = type('obj', (object,), {'log': print})()
    trading_api = connection_manager = None
    UserInputCancelled = Exception
    def get_input(*args, **kwargs): pass


class BotController:
    """
    Orquesta el ciclo de vida completo de la aplicación del bot.
    """
    def __init__(self, dependencies: Dict[str, Any]):
        """
        Inicializa el BotController inyectando todas las dependencias necesarias.
        """
        self._dependencies = dependencies
        self._config = dependencies.get('config_module')
        self._utils = dependencies.get('utils_module')
        self._logging_package = dependencies.get('logging_package')
        self._connection_manager = dependencies.get('connection_manager_module')
        self._connection_ticker = dependencies.get('connection_ticker_module')
        self._event_processor = dependencies.get('event_processor_module')
        self._pm_helpers = dependencies.get('pm_helpers_module')
        self._pm_calculations = dependencies.get('pm_calculations_module')
        self._om_api = dependencies.get('operation_manager_api_module')
        self._pm_api = dependencies.get('position_manager_api_module')
        self._trading_api = dependencies.get('trading_api')

        self._SessionManager = dependencies.get('SessionManager')
        self._OperationManager = dependencies.get('OperationManager')
        self._PositionManager = dependencies.get('PositionManager')
        self._BalanceManager = dependencies.get('BalanceManager')
        self._PositionState = dependencies.get('PositionState')
        self._PositionExecutor = dependencies.get('PositionExecutor')
        self._BybitAdapter = dependencies.get('BybitAdapter')

        self._connections_initialized: bool = False
        self._active_clients: Dict[str, Any] = {}

    def are_connections_initialized(self) -> bool:
        """Indica si las conexiones API han sido inicializadas con éxito."""
        return self._connections_initialized

    # --- INICIO DE LA MODIFICACIÓN ---
    def initialize_connections(self) -> Tuple[bool, str]:
        """
        Orquesta la inicialización y validación de las cuentas API.
        La impresión detallada se delega al connection_manager.
        """
        if self._connections_initialized:
            return True, "Las conexiones ya han sido validadas previamente."

        memory_logger.log("BotController: Iniciando validación de conexiones...", "INFO")
        
        try:
            # 1. El connection_manager realiza la conexión y la impresión detallada.
            # Esta función es ahora la única fuente de impresión de estado de conexión.
            self._connection_manager.initialize_all_clients()
            
            successful_accounts = self._connection_manager.get_initialized_accounts()
            
            # 2. Rellenar el diccionario de clientes activos SIN imprimir nada,
            #    ya que la validación detallada se imprimió en el paso anterior.
            for account_name in successful_accounts:
                self._active_clients[account_name] = self._connection_manager.get_client(account_name)

            # 3. Verificar si hubo algún fallo (aunque initialize_all_clients ya detendría el bot).
            if not successful_accounts:
                self._connections_initialized = False
                error_msg = "Error: No se pudo establecer conexión con NINGUNA cuenta."
                memory_logger.log(error_msg, "ERROR")
                return False, error_msg

            # 4. Continuar con el resto de la lógica.
            self._connections_initialized = True
            msg = "Validación completada. Todas las conexiones requeridas fueron exitosas."
            time.sleep(1) # Reducido el tiempo de espera para una experiencia más fluida
            memory_logger.log(f"BotController: {msg}", "INFO")
            return True, msg

        except SystemExit as e:
            # Captura la salida forzada por el connection_manager si algo falla.
            self._connections_initialized = False
            error_msg = f"Error fatal de conexión: {e}"
            memory_logger.log(error_msg, "ERROR")
            return False, str(e)
        except Exception as e:
            self._connections_initialized = False
            error_msg = f"Excepción inesperada durante la conexión: {e}"
            memory_logger.log(error_msg, "ERROR")
            traceback.print_exc()
            return False, error_msg
    # --- FIN DE LA MODIFICACIÓN ---

    def get_balances(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Obtiene y devuelve los balances de todas las cuentas configuradas."""
        if not self._connections_initialized:
            return None
        
        from core import api as core_api

        balances = {}
        # Usamos las cuentas que se inicializaron con éxito.
        for account_name in self._active_clients.keys():
            balance_info = core_api.get_unified_account_balance_info(account_name)
            balances[account_name] = balance_info
        return balances

    def run_transfer_test(self) -> Tuple[bool, str]:
        """Ejecuta la prueba de transferencias entre cuentas."""
        if not self._connections_initialized:
            return False, "Las conexiones API deben ser inicializadas primero."
        return self._connection_manager.test_subaccount_transfers()

    def run_position_test(self) -> Tuple[bool, str]:
        """Orquesta y ejecuta una prueba completa de apertura y cierre de posiciones."""
        if not self._connections_initialized:
            return False, "Las conexiones API deben ser inicializadas primero."

        try:
            default_ticker = getattr(self._config, 'TICKER_SYMBOL', 'BTCUSDT')
            default_size = getattr(self._config, 'POSITION_BASE_SIZE_USDT', 1.0)
            default_leverage = getattr(self._config, 'POSITION_LEVERAGE', 10.0)

            ticker = get_input("Introduce el Ticker a probar", str, default_ticker)
            ticker = ticker.upper()
            size_usdt = get_input("Introduce el tamaño (USDT)", float, default_size, min_val=0.5)
            leverage = get_input("Introduce el apalancamiento", float, default_leverage, min_val=1.0)
        except UserInputCancelled:
            return False, "Prueba cancelada por el usuario."
        
        print(f"\nObteniendo precio de mercado para {ticker}... ", end="", flush=True)
        adapter = self._BybitAdapter()
        adapter.initialize(symbol=ticker)
        ticker_info = adapter.get_ticker(ticker)
        if not ticker_info or not ticker_info.price > 0:
            print("FALLO.")
            return False, f"No se pudo obtener un precio válido para {ticker}."
        print(f"ÉXITO. Precio: {ticker_info.price:.4f} USD")
        
        qty_to_trade = (size_usdt * leverage) / ticker_info.price

        try:
            print("\nEstableciendo apalancamiento...")
            if not self._trading_api.set_leverage(symbol=ticker, buy_leverage=str(leverage), sell_leverage=str(leverage)):
                return False, "Fallo al establecer el apalancamiento."
            print(" -> Éxito.")

            print(f"Abriendo posición LONG en '{self._config.ACCOUNT_LONGS}'...")
            long_res = self._trading_api.place_market_order(symbol=ticker, side="Buy", quantity=qty_to_trade, account_name=self._config.ACCOUNT_LONGS)
            if not long_res or long_res.get('retCode') != 0:
                return False, f"Fallo al abrir LONG: {long_res.get('retMsg', 'Error') if long_res else 'N/A'}"
            print(f" -> Éxito. OrderID: {long_res.get('result', {}).get('orderId')}")
            time.sleep(1)

            print(f"Abriendo posición SHORT en '{self._config.ACCOUNT_SHORTS}'...")
            short_res = self._trading_api.place_market_order(symbol=ticker, side="Sell", quantity=qty_to_trade, account_name=self._config.ACCOUNT_SHORTS)
            if not short_res or short_res.get('retCode') != 0:
                return False, f"Fallo al abrir SHORT: {short_res.get('retMsg', 'Error') if short_res else 'N/A'}"
            print(f" -> Éxito. OrderID: {short_res.get('result', {}).get('orderId')}")
            time.sleep(2)
        finally:
            print("\n--- Fase de Limpieza ---")
            print(f"Cerrando posiciones de {ticker} en '{self._config.ACCOUNT_LONGS}'...")
            self._trading_api.close_all_symbol_positions(symbol=ticker, account_name=self._config.ACCOUNT_LONGS)
            print(f"Cerrando posiciones de {ticker} en '{self._config.ACCOUNT_SHORTS}'...")
            self._trading_api.close_all_symbol_positions(symbol=ticker, account_name=self._config.ACCOUNT_SHORTS)
            memory_logger.log("BotController[Test]: Limpieza completada.", "INFO")

        return True, f"Prueba de trading completada con éxito para {ticker}."

    def create_session(self) -> Optional[SessionManager]:
        """Fábrica para crear una nueva sesión de trading."""
        if not self._connections_initialized:
            memory_logger.log("BotController: No se puede crear sesión, las conexiones no están inicializadas.", "ERROR")
            return None

        memory_logger.log("BotController: Creando nueva sesión de trading...", "INFO")
        try:
            exchange_adapter = self._BybitAdapter()
            om_instance = self._OperationManager(config=self._config, memory_logger_instance=memory_logger)
            self._om_api.init_om_api(om_instance)
            balance_manager = self._BalanceManager(config=self._config, utils=self._utils, exchange_adapter=exchange_adapter)
            position_state = self._PositionState(config=self._config, utils=self._utils, exchange_adapter=exchange_adapter)
            pm_instance = self._PositionManager(balance_manager=balance_manager, position_state=position_state, exchange_adapter=exchange_adapter, config=self._config, utils=self._utils, memory_logger=memory_logger, helpers=self._pm_helpers, operation_manager_api=self._om_api)
            executor = self._PositionExecutor(config=self._config, utils=self._utils, balance_manager=balance_manager, position_state=position_state, exchange_adapter=exchange_adapter, calculations=self._pm_calculations, helpers=self._pm_helpers, closed_position_logger=self._logging_package.closed_position_logger, state_manager=pm_instance)
            pm_instance.set_executor(executor)
            self._pm_helpers.set_dependencies(self._config, self._utils)
            self._pm_api.init_pm_api(pm_instance)
            
            session_deps = {
                'config_module': self._config, 'utils_module': self._utils, 'memory_logger_module': memory_logger,
                'exchange_adapter': exchange_adapter, 'connection_ticker': self._connection_ticker,
                'event_processor': self._event_processor, 'operation_manager': om_instance,
                'position_manager': pm_instance, 'om_api': self._om_api, 'pm_api': self._pm_api,
                'trading_api': self._trading_api
            }
            session_manager_instance = self._SessionManager(session_deps)
            session_manager_instance.initialize()
            return session_manager_instance
        except Exception as e:
            memory_logger.log(f"BotController: Fallo catastrófico creando la sesión: {e}", "ERROR")
            traceback.print_exc()
            return None

    def get_general_config(self) -> Dict[str, Any]:
        """Obtiene la configuración a nivel de aplicación."""
        if not self._config: return {}
        return { 
            'Exchange': getattr(self._config, 'EXCHANGE_NAME', 'N/A'),
            'Modo Testnet': getattr(self._config, 'UNIVERSAL_TESTNET_MODE', False),
            'Paper Trading': getattr(self._config, 'PAPER_TRADING_MODE', False)
        }

    def update_general_config(self, params: Dict[str, Any]) -> bool:
        """Actualiza la configuración a nivel de aplicación."""
        if not self._config: return False
        for key, value in params.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
                memory_logger.log(f"BotController: Config general actualizada -> {key} = {value}", "WARN")
        return True

    def shutdown_bot(self):
        """Orquesta el apagado de los servicios de bajo nivel."""
        memory_logger.log("BotController: Solicitud de apagado recibida.", "INFO")
        if self._logging_package and hasattr(self._logging_package, 'shutdown_loggers'):
            self._logging_package.shutdown_loggers()
        memory_logger.log("BotController: Apagado completado.", "INFO")