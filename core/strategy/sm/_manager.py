"""
Módulo Gestor de Sesión (SessionManager).

v4.0 (Recarga en Caliente y Resumen Agregado):
- `update_session_parameters` ahora reinicia el TAManager si los parámetros de TA cambian,
  permitiendo una reconfiguración dinámica sin detener el Ticker.
- `get_session_summary` ahora agrega el PNL y capital de ambas operaciones (LONG y SHORT)
  para calcular el rendimiento total de la sesión.
"""
import datetime
from datetime import timezone
import traceback
from typing import Dict, Any, Optional

# --- Dependencias del Proyecto (inyectadas a través de __init__) ---
try:
    from core.logging import memory_logger
    from core.strategy._event_processor import GlobalStopLossException, EventProcessor
    from connection import Ticker
    # --- INICIO DE LA MODIFICACIÓN ---
    # Se añade la importación de TAManager para poder acceder a él.
    from core.strategy.ta import TAManager
    # --- FIN DE LA MODIFICACIÓN ---
except ImportError:
    # Fallbacks para análisis estático y resiliencia
    memory_logger = type('obj', (object,), {'log': print})()
    class GlobalStopLossException(Exception): pass
    class EventProcessor: pass
    class Ticker: pass
    class TAManager: pass


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
        self._om = dependencies.get('operation_manager')
        self._pm = dependencies.get('position_manager')
        self._trading_api = dependencies.get('trading_api')
        self._om_api = dependencies.get('operation_manager_api_module')
        self._pm_api = dependencies.get('position_manager_api_module')

        Ticker_class = dependencies.get('Ticker', Ticker)
        if not Ticker_class:
            raise ValueError("La clase Ticker no fue encontrada en las dependencias.")
        self._ticker = Ticker_class(dependencies)

        EventProcessor_class = dependencies.get('EventProcessor')
        if not EventProcessor_class:
            raise ValueError("La clase EventProcessor no fue encontrada en las dependencias.")
        
        TAManager_class = dependencies.get('TAManager')
        SignalGenerator_class = dependencies.get('SignalGenerator')
        
        if not TAManager_class or not SignalGenerator_class:
             raise ValueError("TAManager o SignalGenerator no encontrados en las dependencias.")

        session_specific_deps = dependencies.copy()
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Guardamos la instancia del TAManager para poder reiniciarla.
        self._ta_manager = TAManager_class()
        session_specific_deps['ta_manager'] = self._ta_manager
        # --- FIN DE LA MODIFICACIÓN ---
        
        session_specific_deps['signal_generator'] = SignalGenerator_class(dependencies)
        
        self._event_processor = EventProcessor_class(session_specific_deps)

        # --- Estado Interno ---
        self._initialized = False
        self._is_running = False
        self._session_start_time: Optional[datetime.datetime] = None
        self._global_stop_loss_event = None

    def initialize(self):
        """
        Prepara la sesión para ser iniciada, inicializando sus componentes hijos.
        """
        memory_logger.log("SessionManager: Inicializando nueva sesión...", "INFO")

        symbol = getattr(self._config, 'TICKER_SYMBOL')
        operation_mode = "live_interactive"

        if not self._exchange_adapter.initialize(symbol):
            raise RuntimeError(f"SessionManager: Fallo al inicializar adaptador para '{symbol}'.")

        self._pm.initialize(operation_mode=operation_mode)
        
        # Comentario: La obtención del leverage desde config podría moverse a la creación de la operación.
        # Por ahora, se mantiene para compatibilidad.
        leverage = getattr(self._config, 'POSITION_LEVERAGE', None)
        if leverage:
            self._trading_api.set_leverage(symbol=symbol, buy_leverage=str(leverage), sell_leverage=str(leverage))

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
        
        self._ticker.start(
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
        self._ticker.stop()
        self._is_running = False
        memory_logger.log("SessionManager: Sesión detenida.", "INFO")

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Construye y devuelve un resumen completo del estado de la sesión actual,
        agregando datos de rendimiento total.
        """
        if not self._pm_api.is_initialized():
            return {"error": "El Position Manager de la sesión no está inicializado."}

        try:
            # 1. Obtener el resumen base desde el Position Manager
            summary = self._pm_api.get_position_summary()
            if not summary or summary.get('error'):
                return summary # Devolver el error si existe

            # 2. Enriquecer el resumen con datos del Event Processor
            if self._event_processor:
                latest_signal = self._event_processor.get_latest_signal_data()
                summary['latest_signal'] = latest_signal
            
            # --- INICIO DE LA MODIFICACIÓN ---
            # 3. Calcular y agregar el rendimiento total de la sesión
            long_op = self._om_api.get_operation_by_side('long')
            short_op = self._om_api.get_operation_by_side('short')
            
            total_initial_capital = 0
            total_session_pnl = 0
            
            if long_op:
                total_initial_capital += long_op.capital_inicial_usdt
                total_session_pnl += summary.get('operation_long_pnl', 0.0) # Usa el PNL ya calculado
            
            if short_op:
                total_initial_capital += short_op.capital_inicial_usdt
                total_session_pnl += summary.get('operation_short_pnl', 0.0)
                
            summary['total_session_initial_capital'] = total_initial_capital
            summary['total_session_pnl'] = total_session_pnl
            summary['total_session_roi'] = self._utils.safe_division(total_session_pnl, total_initial_capital) * 100
            # --- FIN DE LA MODIFICACIÓN ---
            
            return summary
        except Exception as e:
            error_msg = f"Error generando el resumen de la sesión: {e}"
            memory_logger.log(f"SessionManager: {error_msg}", "ERROR")
            traceback.print_exc()
            return {"error": error_msg}

    def update_session_parameters(self, params: Dict[str, Any]):
        """
        Actualiza los parámetros de la sesión en tiempo real. Si cambian parámetros
        de TA, reinicia el TAManager para que aplique los nuevos valores.
        """
        changes_found = False
        ta_params_changed = False
        
        # Un set de los parámetros que afectan al TAManager
        ta_related_keys = {
            'TA_WINDOW_SIZE', 'TA_EMA_WINDOW', 
            'TA_WEIGHTED_INC_WINDOW', 'TA_WEIGHTED_DEC_WINDOW'
        }

        for attr, new_value in params.items():
            if hasattr(self._config, attr):
                old_value = getattr(self._config, attr, None)
                if new_value != old_value:
                    changes_found = True
                    memory_logger.log(f"SessionManager: Actualizando '{attr}': '{old_value}' -> '{new_value}'", "WARN")
                    setattr(self._config, attr, new_value)
                    
                    if attr in ta_related_keys:
                        ta_params_changed = True
                    
                    # Lógica para disyuntores de sesión (sin cambios)
                    if attr in ['SESSION_STOP_LOSS_ROI_PCT', 'SESSION_ROI_SL_ENABLED']:
                        sl_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT') if getattr(self._config, 'SESSION_ROI_SL_ENABLED', False) else 0
                        self._pm_api.set_global_stop_loss_pct(sl_pct)
                    elif attr in ['SESSION_TAKE_PROFIT_ROI_PCT', 'SESSION_ROI_TP_ENABLED']:
                        tp_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT') if getattr(self._config, 'SESSION_ROI_TP_ENABLED', False) else 0
                        self._pm_api.set_global_take_profit_pct(tp_pct)

        if not changes_found:
            memory_logger.log("SessionManager: No se detectaron cambios en la configuración.", "INFO")
            return
            
        # --- INICIO DE LA MODIFICACIÓN ---
        # Si cambiaron parámetros de TA, reiniciamos el TAManager para que los tome.
        if ta_params_changed:
            if self._ta_manager:
                memory_logger.log("SessionManager: Parámetros de TA cambiados. Reiniciando TAManager...", "WARN")
                self._ta_manager.initialize()
            else:
                memory_logger.log("SessionManager: ERROR: ta_params_changed es True pero _ta_manager no existe.", "ERROR")
        # --- FIN DE LA MODIFICACIÓN ---


    def is_running(self) -> bool:
        """Indica si la sesión está actualmente en ejecución (ticker activo)."""
        return self._is_running