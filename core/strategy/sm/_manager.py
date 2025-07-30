"""
Módulo Gestor de Sesión (SessionManager).

Define la clase `SessionManager`, que actúa como el orquestador para una única
sesión de trading. Su responsabilidad es contener y gestionar todos los
componentes y parámetros que definen una sesión, desde su inicio hasta su fin.

Responsabilidades Clave:
- Contener las instancias de OM y PM para la sesión.
- Gestionar el ciclo de vida del Ticker de precios (iniciar/detener).
- Centralizar y gestionar los parámetros de la sesión (Ticker, Estrategia, Capital).
- Comprobar y actuar sobre los límites globales de la sesión (disyuntores).
- Acumular y calcular el PNL y ROI total de la sesión.
"""
import datetime
from datetime import timezone
import traceback
from typing import Dict, Any, Optional

# --- Dependencias del Proyecto (inyectadas a través de __init__) ---
try:
    from core.logging import memory_logger
    from core.strategy.workflow._limit_checks import GlobalStopLossException
except ImportError:
    # Fallbacks para análisis estático y resiliencia
    memory_logger = type('obj', (object,), {'log': print})()
    class GlobalStopLossException(Exception): pass


class SessionManager:
    """
    Orquesta el ciclo de vida y la lógica de una sesión de trading.
    """
    def __init__(self, dependencies: Dict[str, Any]):
        """
        Inicializa el SessionManager inyectando todas sus dependencias.
        Estas dependencias son creadas por el BotController.
        """
        # --- Módulos y Clases de Dependencia ---
        self._config = dependencies.get('config_module')
        self._utils = dependencies.get('utils_module')
        self._exchange_adapter = dependencies.get('exchange_adapter')
        self._connection_ticker = dependencies.get('connection_ticker')
        self._event_processor = dependencies.get('event_processor')
        self._om = dependencies.get('operation_manager')
        self._pm = dependencies.get('position_manager')
        self._om_api = dependencies.get('om_api')
        self._pm_api = dependencies.get('pm_api')
        self._trading_api = dependencies.get('trading_api')

        # --- Estado Interno ---
        self._initialized = False
        self._is_running = False
        self._session_start_time: Optional[datetime.datetime] = None
        self._global_stop_loss_event = None # Se pasará a los subcomponentes si es necesario

    def initialize(self):
        """
        Prepara la sesión para ser iniciada, inicializando sus componentes hijos.
        """
        memory_logger.log("SessionManager: Inicializando nueva sesión...", "INFO")

        # 1. Obtener parámetros de sesión desde la configuración
        symbol = getattr(self._config, 'TICKER_SYMBOL')
        base_size = getattr(self._config, 'POSITION_BASE_SIZE_USDT')
        initial_slots = getattr(self._config, 'POSITION_MAX_LOGICAL_POSITIONS')
        leverage = getattr(self._config, 'POSITION_LEVERAGE')
        operation_mode = "live_interactive" # Modo por defecto para la nueva arquitectura

        # 2. Inicializar el adaptador de exchange con el símbolo de la sesión
        if not self._exchange_adapter.initialize(symbol):
            raise RuntimeError(f"SessionManager: Fallo al inicializar el adaptador de Exchange para el símbolo '{symbol}'.")

        # 3. Inicializar el Position Manager con los parámetros de la sesión
        self._pm.initialize(operation_mode=operation_mode)
        
        # El BalanceManager se inicializa aquí, ya que depende de los parámetros de la sesión.
        # Nota: En una futura refactorización, la inicialización del balance podría ser
        # parte de la creación de la operación en el OM.
        self._pm._balance_manager.initialize(
            base_position_size_usdt=base_size,
            initial_max_logical_positions=initial_slots
        )
        
        # 4. Establecer apalancamiento inicial
        self._trading_api.set_leverage(symbol=symbol, buy_leverage=str(leverage), sell_leverage=str(leverage))

        # 5. Inicializar el procesador de eventos
        self._event_processor.initialize(
            operation_mode=operation_mode,
            pm_instance=self._pm,
            global_stop_loss_event=self._global_stop_loss_event
        )

        self._initialized = True
        memory_logger.log("SessionManager: Sesión inicializada y lista para arrancar.", "INFO")

    def start(self):
        """Inicia el ticker y marca la sesión como en ejecución."""
        if not self._initialized:
            memory_logger.log("SessionManager: No se puede iniciar, la sesión no está inicializada.", "ERROR")
            return
        if self._is_running:
            memory_logger.log("SessionManager: La sesión ya está en ejecución.", "WARN")
            return

        memory_logger.log("SessionManager: Iniciando Ticker de precios...", "INFO")
        self._connection_ticker.start_ticker_thread(
            exchange_adapter=self._exchange_adapter,
            raw_event_callback=self._event_processor.process_event
        )

        self._session_start_time = datetime.datetime.now(timezone.utc)
        self._is_running = True
        memory_logger.log("SessionManager: Sesión iniciada y Ticker operativo.", "INFO")

    def stop(self):
        """Detiene el ticker y marca la sesión como no en ejecución."""
        if not self._is_running:
            return

        memory_logger.log("SessionManager: Deteniendo Ticker de precios...", "INFO")
        self._connection_ticker.stop_ticker_thread()
        self._is_running = False
        memory_logger.log("SessionManager: Sesión detenida.", "INFO")

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Construye y devuelve un resumen completo del estado de la sesión actual.
        Este es el "modelo de datos" para la vista del dashboard.
        """
        # El Position Manager ya genera un resumen muy completo.
        # En el futuro, podemos enriquecerlo aquí con datos exclusivos de la sesión si es necesario.
        if not self._pm_api.is_initialized():
            return {"error": "El Position Manager de la sesión no está inicializado."}

        try:
            summary = self._pm_api.get_position_summary()
            
            # Aquí podríamos añadir o modificar datos del resumen. Por ahora, es un proxy.
            # Por ejemplo, podríamos añadir un PNL/ROI global de la sesión si fuera
            # diferente del PNL de la operación actual.
            
            return summary
        except Exception as e:
            error_msg = f"Error generando el resumen de la sesión: {e}"
            memory_logger.log(f"SessionManager: {error_msg}", "ERROR")
            traceback.print_exc()
            return {"error": error_msg}

    def update_session_parameters(self, params: Dict[str, Any]):
        """
        Actualiza los parámetros de la sesión en tiempo real.
        Delega la actualización a los componentes correspondientes.
        """
        changes_found = False
        for attr, new_value in params.items():
            if hasattr(self._config, attr):
                old_value = getattr(self._config, attr, None)
                if new_value != old_value:
                    changes_found = True
                    memory_logger.log(f"SessionManager: Actualizando parámetro '{attr}': '{old_value}' -> '{new_value}'", "WARN")
                    setattr(self._config, attr, new_value)
                    
                    # Notificar a los componentes que dependen de estos parámetros
                    if attr == 'SESSION_STOP_LOSS_ROI_PCT':
                        if getattr(self._config, 'SESSION_ROI_SL_ENABLED', False):
                            self._pm_api.set_global_stop_loss_pct(new_value)
                    elif attr == 'SESSION_TAKE_PROFIT_ROI_PCT':
                        if getattr(self._config, 'SESSION_ROI_TP_ENABLED', False):
                            self._pm_api.set_global_take_profit_pct(new_value)
                    elif attr == 'SESSION_ROI_SL_ENABLED':
                        self._pm_api.set_global_stop_loss_pct(getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT') if new_value else 0)
                    elif attr == 'SESSION_ROI_TP_ENABLED':
                        self._pm_api.set_global_take_profit_pct(getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT') if new_value else 0)

        if not changes_found:
            memory_logger.log("SessionManager: No se detectaron cambios en la configuración.", "INFO")

    def is_running(self) -> bool:
        """Indica si la sesión está actualmente en ejecución (ticker activo)."""
        return self._is_running