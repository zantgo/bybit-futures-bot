# ./core/bot_controller/_manager.py

"""
Módulo Gestor del Bot (BotController).

v6.2 (Refactor de Configuración):
- Adaptado para leer la configuración desde los nuevos diccionarios
  anidados en `config.py`.

v6.1 (Validación de Símbolo Centralizada):
- Se añade el método `validate_and_update_ticker_symbol` para validar un
  nuevo símbolo de ticker en tiempo real usando el ExchangeAdapter.
- La TUI de Configuración General ahora delega la validación a este método.
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
    from core.strategy.pm._position_state import PositionState
    from core.strategy.pm._executor import PositionExecutor
    from core.exchange._bybit_adapter import BybitAdapter
    # --- INICIO DE LA INTEGRACIÓN: Importar el modelo StandardOrder ---
    from core.exchange._models import StandardOrder
    # --- FIN DE LA INTEGRACIÓN ---
    
    # Módulos y APIs de soporte
    from core.logging import memory_logger as memory_logger_module
    from core.api import trading as trading_api
    from core.menu._helpers import get_input, UserInputCancelled

    from connection import ConnectionManager

except ImportError:
    # Fallbacks para análisis estático y resiliencia
    SessionManager = OperationManager = PositionManager = None
    PositionState = PositionExecutor = BybitAdapter = ConnectionManager = None
    # --- INICIO DE LA INTEGRACIÓN: Fallback para StandardOrder ---
    StandardOrder = None
    # --- FIN DE LA INTEGRACIÓN ---
    memory_logger_module = type('obj', (object,), {'log': print})()
    trading_api = None
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
        self._memory_logger = dependencies.get('memory_logger_module')

        ConnectionManager_class = dependencies.get('ConnectionManager')
        if not ConnectionManager_class:
            raise ValueError("La clase ConnectionManager no fue encontrada en las dependencias.")
        
        self._connection_manager = ConnectionManager_class(dependencies)
        
        self._pm_helpers = dependencies.get('pm_helpers_module')
        self._pm_calculations = dependencies.get('pm_calculations_module')
        self._om_api = dependencies.get('operation_manager_api_module')
        self._pm_api = dependencies.get('position_manager_api_module')
        self._trading_api = dependencies.get('trading_api')

        self._SessionManager = dependencies.get('SessionManager')
        self._OperationManager = dependencies.get('OperationManager')
        self._PositionManager = dependencies.get('PositionManager')
        self._PositionState = dependencies.get('PositionState')
        self._PositionExecutor = dependencies.get('PositionExecutor')
        self._BybitAdapter = dependencies.get('BybitAdapter')
        
        self._connections_initialized: bool = False

    def validate_and_update_ticker_symbol(self, new_symbol: str) -> Tuple[bool, str]:
        """
        Valida un nuevo símbolo de ticker contra el exchange y lo actualiza si es válido.
        """
        if not self._connections_initialized:
            return False, "Las conexiones no están inicializadas para validar el símbolo."

        new_symbol = new_symbol.upper()
        self._memory_logger.log(f"BotController: Solicitud para validar y cambiar Ticker a '{new_symbol}'...", "INFO")

        # Usamos una instancia temporal del adaptador solo para la validación
        validation_adapter = self._BybitAdapter(self._connection_manager)
        
        # El método initialize del adaptador ya contiene la lógica de validación
        is_valid = validation_adapter.initialize(symbol=new_symbol)

        if is_valid:
            old_symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
            self._config.BOT_CONFIG["TICKER"]["SYMBOL"] = new_symbol
            msg = f"Símbolo del Ticker actualizado con éxito a '{new_symbol}'."
            self._memory_logger.log(f"BotController: {msg} (Anterior: '{old_symbol}')", "WARN")
            return True, msg
        else:
            msg = f"El símbolo '{new_symbol}' es inválido o no existe. El cambio ha sido rechazado."
            self._memory_logger.log(f"BotController: {msg}", "ERROR")
            return False, msg

    def are_connections_initialized(self) -> bool:
        """Indica si las conexiones API han sido inicializadas con éxito."""
        return self._connections_initialized

    def initialize_connections(self) -> Tuple[bool, str]:
        """
        Orquesta la inicialización y validación de las cuentas API.
        """
        if self._connections_initialized:
            return True, "Las conexiones ya han sido validadas previamente."

        self._memory_logger.log("BotController: Iniciando validación de conexiones...", "INFO")
        
        try:
            self._connection_manager.initialize_all_clients()
            
            self._connections_initialized = True
            msg = "Validación completada. Todas las conexiones requeridas fueron exitosas."
            time.sleep(1)
            self._memory_logger.log(f"BotController: {msg}", "INFO")
            return True, msg

        except SystemExit as e:
            self._connections_initialized = False
            error_msg = f"Error fatal de conexión: {e}"
            self._memory_logger.log(error_msg, "ERROR")
            return False, str(e)
        except Exception as e:
            self._connections_initialized = False
            error_msg = f"Excepción inesperada durante la conexión: {e}"
            self._memory_logger.log(error_msg, "ERROR")
            traceback.print_exc()
            return False, error_msg

    def get_balances(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Obtiene y devuelve los balances de todas las cuentas configuradas."""
        if not self._connections_initialized:
            self._memory_logger.log("Error: get_balances llamado antes de inicializar conexiones.", "ERROR")
            return None
        
        from core import api as core_api
        
        initialized_accounts = self._connection_manager.get_initialized_accounts()

        balances = {}
        for account_name in initialized_accounts:
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
            default_ticker = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
            default_size = self._config.OPERATION_DEFAULTS["CAPITAL"]["BASE_SIZE_USDT"]
            default_leverage = self._config.OPERATION_DEFAULTS["CAPITAL"]["LEVERAGE"]

            ticker = get_input("Introduce el Ticker a probar", str, default_ticker)
            ticker = ticker.upper()
            size_usdt = get_input("Introduce el tamaño (USDT)", float, default_size, min_val=0.5)
            leverage = get_input("Introduce el apalancamiento", float, default_leverage, min_val=1.0)
        except UserInputCancelled:
            return False, "Prueba cancelada por el usuario."
        
        # --- INICIO DE LA MODIFICACIÓN (Mantenido del código antiguo) ---
        # 1. Definir los nombres de las cuentas al principio.
        long_account = self._config.BOT_CONFIG["ACCOUNTS"].get("LONGS")
        short_account = self._config.BOT_CONFIG["ACCOUNTS"].get("SHORTS")

        if not long_account or not short_account:
            return False, "Nombres de cuenta para LONGS o SHORTS no definidos en la configuración."
        
        # 2. Banderas para saber si las posiciones se abrieron con éxito.
        long_position_opened = False
        short_position_opened = False
        # --- FIN DE LA MODIFICACIÓN (Mantenido del código antiguo) ---

        print(f"\nObteniendo precio de mercado para {ticker}... ", end="", flush=True)
        # --- INICIO DE LA INTEGRACIÓN: Se usa una única instancia del adaptador ---
        adapter = self._BybitAdapter(self._connection_manager)
        # --- FIN DE LA INTEGRACIÓN ---
        
        if not adapter.initialize(symbol=ticker):
            print("FALLO.")
            return False, f"El símbolo '{ticker}' no es válido o no se pudo inicializar el adaptador."
            
        ticker_info = adapter.get_ticker(ticker)

        if not ticker_info or not ticker_info.price > 0:
            print("FALLO.")
            return False, f"No se pudo obtener un precio válido para {ticker}."
        print(f"ÉXITO. Precio: {ticker_info.price:.4f} USD")
        
        qty_to_trade = (size_usdt * leverage) / ticker_info.price

        try:
            print("\nEstableciendo apalancamiento...")
            # --- INICIO DE LA INTEGRACIÓN: Uso del adaptador para apalancamiento ---
            # Se usa el adaptador para establecer el apalancamiento
            if not adapter.set_leverage(symbol=ticker, leverage=leverage, account_purpose='longs'):
                return False, f"Fallo al establecer apalancamiento en '{long_account}'."
            if not adapter.set_leverage(symbol=ticker, leverage=leverage, account_purpose='shorts'):
                return False, f"Fallo al establecer apalancamiento en '{short_account}'."
            
            # --- CÓDIGO ANTIGUO COMENTADO ---
            # # Se establece en ambas cuentas para asegurar consistencia
            # if not self._trading_api.set_leverage(symbol=ticker, buy_leverage=str(leverage), sell_leverage=str(leverage), account_name=long_account):
            #     return False, f"Fallo al establecer apalancamiento en '{long_account}'."
            # if not self._trading_api.set_leverage(symbol=ticker, buy_leverage=str(leverage), sell_leverage=str(leverage), account_name=short_account):
            #     return False, f"Fallo al establecer apalancamiento en '{short_account}'."
            # --- FIN DE LA INTEGRACIÓN ---
            print(" -> Éxito.")

            print(f"Abriendo posición LONG en '{long_account}'...")
            # --- INICIO DE LA INTEGRACIÓN: Uso del adaptador para abrir posición LONG ---
            # Se crea un objeto StandardOrder y se usa el adaptador
            long_order = StandardOrder(
                symbol=ticker, side="buy", order_type="market", quantity_contracts=qty_to_trade
            )
            success_long, msg_long = adapter.place_order(long_order, account_purpose='longs')
            
            if not success_long:
                return False, f"Fallo al abrir LONG: {msg_long}"

            # --- CÓDIGO ANTIGUO COMENTADO ---
            # long_res = self._trading_api.place_market_order(symbol=ticker, side="Buy", quantity=qty_to_trade, account_name=long_account)
            # if not long_res or long_res.get('retCode') != 0:
            #     return False, f"Fallo al abrir LONG: {long_res.get('retMsg', 'Error') if long_res else 'N/A'}"
            # --- FIN DE LA INTEGRACIÓN ---
            
            # --- INICIO DE LA INTEGRACIÓN: Mensaje de éxito actualizado ---
            print(f" -> Éxito. OrderID: {msg_long}")
            # --- CÓDIGO ANTIGUO COMENTADO ---
            # print(f" -> Éxito. OrderID: {long_res.get('result', {}).get('orderId')}")
            # --- FIN DE LA INTEGRACIÓN ---
            
            long_position_opened = True # Marcar como abierta
            time.sleep(1)

            print(f"Abriendo posición SHORT en '{short_account}'...")
            # --- INICIO DE LA INTEGRACIÓN: Uso del adaptador para abrir posición SHORT ---
            # Se crea un objeto StandardOrder y se usa el adaptador
            short_order = StandardOrder(
                symbol=ticker, side="sell", order_type="market", quantity_contracts=qty_to_trade
            )
            success_short, msg_short = adapter.place_order(short_order, account_purpose='shorts')

            if not success_short:
                return False, f"Fallo al abrir SHORT: {msg_short}"
            
            # --- CÓDIGO ANTIGUO COMENTADO ---
            # short_res = self._trading_api.place_market_order(symbol=ticker, side="Sell", quantity=qty_to_trade, account_name=short_account)
            # if not short_res or short_res.get('retCode') != 0:
            #     return False, f"Fallo al abrir SHORT: {short_res.get('retMsg', 'Error') if short_res else 'N/A'}"
            # --- FIN DE LA INTEGRACIÓN ---
            
            # --- INICIO DE LA INTEGRACIÓN: Mensaje de éxito actualizado ---
            print(f" -> Éxito. OrderID: {msg_short}")
            # --- CÓDIGO ANTIGUO COMENTADO ---
            # print(f" -> Éxito. OrderID: {short_res.get('result', {}).get('orderId')}")
            # --- FIN DE LA INTEGRACIÓN ---
            
            short_position_opened = True # Marcar como abierta
            time.sleep(2)

        finally:
            # --- INICIO DE LA MODIFICACIÓN (Mantenido del código antiguo) ---
            # 3. El bloque de limpieza ahora usa las banderas para actuar de forma segura.
            print("\n--- Fase de Limpieza ---")
            # --- INICIO DE LA INTEGRACIÓN: Uso del adaptador para cerrar posiciones ---
            # Se usa el adaptador para cerrar las posiciones
            if long_position_opened:
                print(f"Cerrando posiciones de {ticker} en '{long_account}'...")
                close_long_order = StandardOrder(
                    symbol=ticker, side="sell", order_type="market",
                    quantity_contracts=qty_to_trade, reduce_only=True
                )
                adapter.place_order(close_long_order, account_purpose='longs')
            
            if short_position_opened:
                print(f"Cerrando posiciones de {ticker} en '{short_account}'...")
                close_short_order = StandardOrder(
                    symbol=ticker, side="buy", order_type="market",
                    quantity_contracts=qty_to_trade, reduce_only=True
                )
                adapter.place_order(close_short_order, account_purpose='shorts')

            # --- CÓDIGO ANTIGUO COMENTADO ---
            # if long_position_opened:
            #     print(f"Cerrando posiciones de {ticker} en '{long_account}'...")
            #     self._trading_api.close_all_symbol_positions(symbol=ticker, account_name=long_account)
            # 
            # if short_position_opened:
            #     print(f"Cerrando posiciones de {ticker} en '{short_account}'...")
            #     self._trading_api.close_all_symbol_positions(symbol=ticker, account_name=short_account)
            # --- FIN DE LA INTEGRACIÓN ---
            
            self._memory_logger.log("BotController[Test]: Limpieza completada.", "INFO")
            # --- FIN DE LA MODIFICACIÓN (Mantenido del código antiguo) ---

        return True, f"Prueba de trading completada con éxito para {ticker}."
    
    def create_session(self) -> Optional[SessionManager]:
        """Fábrica para crear una nueva sesión de trading."""
        if not self._connections_initialized:
            self._memory_logger.log("BotController: No se puede crear sesión, conexiones no inicializadas.", "ERROR")
            return None

        self._memory_logger.log("BotController: Creando nueva sesión de trading...", "INFO")
        try:
            exchange_adapter = self._BybitAdapter(self._connection_manager)
            
            om_instance = self._OperationManager(config=self._config, memory_logger_instance=self._memory_logger)
            self._om_api.init_om_api(om_instance)
            
            position_state = self._PositionState(config=self._config, utils=self._utils, exchange_adapter=exchange_adapter)
            
            pm_instance = self._PositionManager(
                position_state=position_state, 
                exchange_adapter=exchange_adapter, 
                config=self._config, 
                utils=self._utils, 
                memory_logger=self._memory_logger, 
                helpers=self._pm_helpers, 
                operation_manager_api=self._om_api
            )
            
            executor = self._PositionExecutor(
                config=self._config, 
                utils=self._utils, 
                position_state=position_state, 
                exchange_adapter=exchange_adapter, 
                calculations=self._pm_calculations, 
                helpers=self._pm_helpers, 
                closed_position_logger=self._logging_package.closed_position_logger, 
                state_manager=pm_instance
            )

            pm_instance.set_executor(executor)
            self._pm_helpers.set_dependencies(self._config, self._utils)
            self._pm_api.init_pm_api(pm_instance)
            
            session_deps = self._dependencies.copy()
            
            session_deps['connection_manager'] = self._connection_manager 
            session_deps['exchange_adapter'] = exchange_adapter
            session_deps['operation_manager'] = om_instance
            session_deps['position_manager'] = pm_instance
            
            session_manager_instance = self._SessionManager(session_deps)
            session_manager_instance.initialize()
            return session_manager_instance
        except Exception as e:
            self._memory_logger.log(f"BotController: Fallo catastrófico creando la sesión: {e}", "ERROR")
            traceback.print_exc()
            return None

    def get_general_config(self) -> Dict[str, Any]:
        """Obtiene la configuración a nivel de aplicación."""
        if not self._config: return {}
        return { 
            'Exchange': self._config.BOT_CONFIG["EXCHANGE_NAME"],
            'Modo Testnet': self._config.BOT_CONFIG["UNIVERSAL_TESTNET_MODE"],
            'Paper Trading': self._config.BOT_CONFIG["PAPER_TRADING_MODE"],
            'Ticker Symbol': self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
        }

    def update_general_config(self, params: Dict[str, Any]) -> bool:
        """
        Actualiza la configuración a nivel de aplicación (BOT_CONFIG).
        Esta función está diseñada para ser llamada con un diccionario de cambios,
        aunque la TUI actual modifica el config directamente.
        """
        if not self._config: 
            return False
            
        config_changed = False
        bot_config = self._config.BOT_CONFIG

        for key, value in params.items():
            original_value = None
            key_to_update = None
            
            # Mapeamos las claves públicas a las rutas internas del diccionario de configuración.
            if key == 'Exchange' and 'EXCHANGE_NAME' in bot_config:
                original_value = bot_config['EXCHANGE_NAME']
                if original_value != value:
                    bot_config['EXCHANGE_NAME'] = value
                    config_changed = True
            
            elif key == 'Modo Testnet' and 'UNIVERSAL_TESTNET_MODE' in bot_config:
                original_value = bot_config['UNIVERSAL_TESTNET_MODE']
                if original_value != value:
                    bot_config['UNIVERSAL_TESTNET_MODE'] = value
                    config_changed = True

            elif key == 'Paper Trading' and 'PAPER_TRADING_MODE' in bot_config:
                original_value = bot_config['PAPER_TRADING_MODE']
                if original_value != value:
                    bot_config['PAPER_TRADING_MODE'] = value
                    config_changed = True

            elif key == 'Ticker Symbol' and 'TICKER' in bot_config and 'SYMBOL' in bot_config['TICKER']:
                # Para el Ticker Symbol, se recomienda usar el método dedicado que incluye validación.
                # Pero si se llama directamente, lo actualizamos.
                original_value = bot_config['TICKER']['SYMBOL']
                if original_value != value:
                    self.validate_and_update_ticker_symbol(value) # Usamos el método con validación
                    config_changed = True # Asumimos que cambió si se llamó a la función
            
            if config_changed and original_value is not None:
                 self._memory_logger.log(f"BotController: Config general actualizada -> {key}: '{original_value}' -> '{value}'", "WARN")
                 config_changed = False # Reseteamos para el siguiente item del bucle

        return True

    def shutdown_bot(self):
        """Orquesta el apagado de los servicios de bajo nivel."""
        self._memory_logger.log("BotController: Solicitud de apagado recibida.", "INFO")
        if self._logging_package and hasattr(self._logging_package, 'shutdown_loggers'):
            self._logging_package.shutdown_loggers()
        self._memory_logger.log("BotController: Apagado completado.", "INFO")