"""
Módulo Gestor de Sesión (SessionManager).

v2.2 (Corrección Final de Dependencias):
- Se corrigen las claves para obtener 'om_api' y 'pm_api' del diccionario de
  dependencias, asegurando que coincidan con las definidas en el inicializador.
  Esto soluciona el AttributeError final en la inicialización de la sesión.

v2.1 (Corrección de Dependencias):
- Se corrige la clave para obtener 'connection_ticker'.

v2.0 (Refactor EventProcessor):
- Se actualiza el __init__ para instanciar la clase `EventProcessor`.
"""
import datetime
from datetime import timezone
import traceback
from typing import Dict, Any, Optional

# --- Dependencias del Proyecto (inyectadas a través de __init__) ---
try:
    from core.logging import memory_logger
    # La excepción ahora vive dentro del módulo EventProcessor.
    from core.strategy._event_processor import GlobalStopLossException
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
        self._connection_ticker = dependencies.get('connection_ticker_module')
        self._om = dependencies.get('operation_manager')
        self._pm = dependencies.get('position_manager')
        self._trading_api = dependencies.get('trading_api')

        # --- INICIO DE LA CORRECCIÓN ---
        # Se comentan las líneas originales que usaban las claves incorrectas.
        # self._om_api = dependencies.get('om_api')
        # self._pm_api = dependencies.get('pm_api')
        # Usar las claves completas y correctas definidas en el inicializador.
        self._om_api = dependencies.get('operation_manager_api_module')
        self._pm_api = dependencies.get('position_manager_api_module')
        # --- FIN DE LA CORRECCIÓN ---

        # --- Instanciación del EventProcessor ---
        EventProcessor_class = dependencies.get('EventProcessor')
        if not EventProcessor_class:
            raise ValueError("La clase EventProcessor no fue encontrada en las dependencias.")
        # Creamos una INSTANCIA del EventProcessor para esta sesión.
        self._event_processor = EventProcessor_class(dependencies)

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
        operation_mode = "live_interactive" # Modo por defecto para la nueva arquitectura

        # 2. Inicializar el adaptador de exchange con el símbolo de la sesión
        if not self._exchange_adapter.initialize(symbol):
            raise RuntimeError(f"SessionManager: Fallo al inicializar el adaptador de Exchange para el símbolo '{symbol}'.")

        # 3. Inicializar el Position Manager
        self._pm.initialize(operation_mode=operation_mode)
        
        # 4. Establecer apalancamiento si está definido en la configuración
        leverage = getattr(self._config, 'POSITION_LEVERAGE', None)
        if leverage:
            self._trading_api.set_leverage(symbol=symbol, buy_leverage=str(leverage), sell_leverage=str(leverage))

        # 5. Inicializar el procesador de eventos.
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
        
        # El callback ahora es el método 'process_event' de nuestra instancia de EventProcessor.
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
        """
        # Esta llamada ahora funcionará porque self._pm_api ya no será None
        if not self._pm_api.is_initialized():
            return {"error": "El Position Manager de la sesión no está inicializado."}

        try:
            summary = self._pm_api.get_position_summary()
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
                    if attr in ['SESSION_STOP_LOSS_ROI_PCT', 'SESSION_ROI_SL_ENABLED']:
                        sl_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT') if getattr(self._config, 'SESSION_ROI_SL_ENABLED', False) else 0
                        self._pm_api.set_global_stop_loss_pct(sl_pct)
                    elif attr in ['SESSION_TAKE_PROFIT_ROI_PCT', 'SESSION_ROI_TP_ENABLED']:
                        tp_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT') if getattr(self._config, 'SESSION_ROI_TP_ENABLED', False) else 0
                        self._pm_api.set_global_take_profit_pct(tp_pct)

        if not changes_found:
            memory_logger.log("SessionManager: No se detectaron cambios en la configuración.", "INFO")

    def is_running(self) -> bool:
        """Indica si la sesión está actualmente en ejecución (ticker activo)."""
        return self._is_running