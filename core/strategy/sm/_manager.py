"""
Módulo Gestor de Sesión (SessionManager).
"""

import datetime
from datetime import timezone
import traceback
from typing import Dict, Any, Optional
import numpy as np
import threading

# --- Dependencias del Proyecto ---
try:
    from core.logging import memory_logger
    from core.strategy._event_processor import EventProcessor
    from connection import Ticker
    from core.strategy.ta import TAManager
    from core.strategy.signal import SignalGenerator
    from core.strategy.entities import Operacion
except ImportError:
    memory_logger = type('obj', (object,), {'log': print})()
    class EventProcessor: pass
    class Ticker: pass
    class TAManager: pass
    class SignalGenerator: pass
    class Operacion: pass

STRATEGY_AFFECTING_KEYS = {
    'EMA_WINDOW',
    'WEIGHTED_INC_WINDOW',
    'WEIGHTED_DEC_WINDOW',
    'PRICE_CHANGE_BUY_PERCENTAGE',
    'PRICE_CHANGE_SELL_PERCENTAGE',
    'WEIGHTED_DECREMENT_THRESHOLD',
    'WEIGHTED_INCREMENT_THRESHOLD',
    'ENABLED' 
}

class SessionManager:
    """
    Orquesta el ciclo de vida y la lógica de una sesión de trading.
    """
    def __init__(self, dependencies: Dict[str, Any]):
        """
        Inicializa el SessionManager inyectando todas sus dependencias.
        Estas dependencias son creadas por el BotController.
        """
        self._dependencies = dependencies
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

        self._ta_manager: Optional[TAManager] = None
        self._signal_generator: Optional[SignalGenerator] = None
        self._event_processor: Optional[EventProcessor] = None

        self._initialized = False
        self._is_running = False
        self._session_start_time: Optional[datetime.datetime] = None
        self._last_known_valid_symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
        
    def _build_strategy_components(self):
        """
        Construye o reconstruye las instancias de los componentes de la estrategia
        asegurando que todos estén sincronizados.
        """
        memory_logger.log("SM: Construyendo componentes de estrategia (TA, Signal, EventProcessor)...", "DEBUG")
        
        TAManager_class = self._dependencies.get('TAManager')
        SignalGenerator_class = self._dependencies.get('SignalGenerator')
        EventProcessor_class = self._dependencies.get('EventProcessor')

        if not all([TAManager_class, SignalGenerator_class, EventProcessor_class]):
             raise ValueError("Dependencias de estrategia (TA, Signal, EventProcessor) no encontradas.")

        self._ta_manager = TAManager_class(self._config)
        self._signal_generator = SignalGenerator_class(self._dependencies)
        
        strategy_deps = self._dependencies.copy()
        strategy_deps['ta_manager'] = self._ta_manager
        strategy_deps['signal_generator'] = self._signal_generator
        
        self._event_processor = EventProcessor_class(strategy_deps)

        self._event_processor.initialize(
            operation_mode="live_interactive",
            pm_instance=self._pm
        )

    def initialize(self):
        """
        Prepara la sesión para ser iniciada, inicializando sus componentes hijos
        y manejando un posible símbolo de ticker inválido.
        """
        memory_logger.log("SessionManager: Inicializando nueva sesión...", "INFO")
        symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]

        operation_mode = "live_interactive"

        if not self._exchange_adapter.initialize(symbol):
            memory_logger.log(f"SessionManager: Fallo al inicializar adaptador para '{symbol}'. "
                              f"Reintentando con el símbolo de respaldo '{self._last_known_valid_symbol}'.", "WARN")
            self._config.BOT_CONFIG["TICKER"]["SYMBOL"] = self._last_known_valid_symbol
            symbol = self._last_known_valid_symbol

            if not self._exchange_adapter.initialize(symbol):
                raise RuntimeError(f"SessionManager: Fallo crítico al inicializar adaptador. "
                                   f"Incluso el símbolo de respaldo '{symbol}' falló.")
        
        self._last_known_valid_symbol = symbol

        self._pm.initialize(operation_mode=operation_mode)
    
        self._build_strategy_components()

        self._initialized = True
        memory_logger.log("SessionManager: Sesión inicializada y lista para arrancar.", "INFO")

    def _process_and_callback(self, intermediate_ticks_info: list, final_price_info: dict):
        """
        Wrapper interno para el callback que procesa el evento y luego
        comprueba el estado del Ticker.
        """
        if self._event_processor:
            self._event_processor.process_event(intermediate_ticks_info, final_price_info)
        
        self._check_and_manage_ticker_state()

    def _check_and_manage_ticker_state(self):
        """
        Comprueba el estado de las operaciones y detiene el Ticker si ambas están detenidas.
        """
        if not self.is_running():
            return

        try:
            long_op = self._om_api.get_operation_by_side('long')
            short_op = self._om_api.get_operation_by_side('short')

            if long_op and short_op and long_op.estado == 'DETENIDA' and short_op.estado == 'DETENIDA':
                self.stop()
        except Exception as e:
            memory_logger.log(f"SM: Error en _check_and_manage_ticker_state: {e}", "ERROR")

    def force_single_tick(self):
        """
        Fuerza al Ticker a ejecutar una única consulta de precio y procesar el evento.
        Ideal para un botón de refresco cuando el Ticker está detenido.
        """
        if self._ticker:
            self._ticker.run_single_real_tick()

    def start(self):
        """Inicia el ticker y marca la sesión como en ejecución."""
        if not self._initialized:
            memory_logger.log("SessionManager: No se puede iniciar, la sesión no está inicializada.", "ERROR")
            return
        if self._is_running:
            memory_logger.log("SessionManager: La sesión ya está en ejecución.", "WARN")
            return

        memory_logger.log("SessionManager: Iniciando Ticker de precios...", "INFO")
        
        if not self.is_running():
            memory_logger.log("SM: Reactivando Ticker desde estado detenido. Reiniciando indicadores.", "WARN")
            self._build_strategy_components()

        self._ticker.start(
            exchange_adapter=self._exchange_adapter,
            raw_event_callback=self._process_and_callback 
        )
        
        if not self._session_start_time: 
            self._session_start_time = datetime.datetime.now(timezone.utc)
        
        self._is_running = True
        memory_logger.log("SessionManager: Sesión iniciada y Ticker operativo.", "INFO")

    def stop(self):
        """
        Detiene el ticker y marca la sesión como no en ejecución.
        Maneja el caso de ser llamado desde el propio hilo del ticker para evitar deadlocks.
        """
        if not self._is_running:
            return

        if self._ticker._thread and threading.current_thread() is self._ticker._thread:
            self._ticker.signal_stop()
        else:
            self._ticker.stop()

        self._is_running = False

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Construye y devuelve un resumen completo del estado de la sesión actual.
        """
        if not self._pm_api.is_initialized():
            return {"error": "El Position Manager de la sesión no está inicializado."}

        try:
            summary = self._pm_api.get_position_summary()
            if not summary or summary.get('error'):
                return summary

            if self._event_processor:
                latest_signal = self._event_processor.get_latest_signal_data()
                summary['latest_signal'] = latest_signal
            
            long_op = self._om_api.get_operation_by_side('long')
            short_op = self._om_api.get_operation_by_side('short')
            
            def get_op_details(op: Optional[Operacion]) -> Dict[str, Any]:
                if not op: 
                    return {
                        "id": "N/A", 
                        "estado": "NO_INICIADA", 
                        "tendencia": "N/A",
                        "duracion_activa": "N/A"
                    }
                
                duration_str = "N/A"
                if op.estado == 'ACTIVA' and getattr(op, 'tiempo_ultimo_inicio_activo', None):
                    start_time = op.tiempo_ultimo_inicio_activo
                    duration = datetime.datetime.now(timezone.utc) - start_time
                    duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))
                
                return {
                    "id": op.id,
                    "estado": op.estado,
                    "tendencia": op.tendencia,
                    "duracion_activa": duration_str
                }

            summary['operations_info'] = {
                'long': get_op_details(long_op),
                'short': get_op_details(short_op)
            }
            
            if long_op:
                summary['comisiones_totales_usdt_long'] = long_op.comisiones_totales_usdt
                long_positions = summary.get('open_long_positions', [])
                if long_positions:
                    entry_prices = [p.entry_price for p in long_positions if p.entry_price is not None]
                    summary['avg_entry_price_long'] = np.mean(entry_prices) if entry_prices else 'N/A'
                else:
                    summary['avg_entry_price_long'] = 'N/A'

            if short_op:
                summary['comisiones_totales_usdt_short'] = short_op.comisiones_totales_usdt
                short_positions = summary.get('open_short_positions', [])
                if short_positions:
                    entry_prices = [p.entry_price for p in short_positions if p.entry_price is not None]
                    summary['avg_entry_price_short'] = np.mean(entry_prices) if entry_prices else 'N/A'
                else:
                    summary['avg_entry_price_short'] = 'N/A'
                            
            return summary
        except Exception as e:
            error_msg = f"Error generando el resumen de la sesión: {e}"
            memory_logger.log(f"SessionManager: {error_msg}", "ERROR")
            memory_logger.log(traceback.format_exc(), "ERROR")
            return {"error": error_msg}

    def update_session_parameters(self, params: Dict[str, Any]):
        """
        Actualiza los parámetros, valida cambios críticos como el símbolo del ticker,
        y reinicia los componentes necesarios.
        """
        if not isinstance(params, dict):
            params = {}
        changed_keys = set(params.keys())
        
        if not changed_keys:
            memory_logger.log("SessionManager: No se detectaron cambios en la configuración.", "INFO")
            return
            
        if 'MAX_SYNC_FAILURES' in changed_keys:
            new_value = self._config.SESSION_CONFIG["RISK"]["MAX_SYNC_FAILURES"]
            self._pm_api.update_max_sync_failures(new_value)

        if 'TICKER_SYMBOL' in changed_keys:
            new_symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
            memory_logger.log(f"SessionManager: Se detectó cambio de símbolo a '{new_symbol}'. Validando...", "WARN")

            is_new_symbol_valid = self._exchange_adapter.get_instrument_info(new_symbol) is not None
            
            if is_new_symbol_valid:
                memory_logger.log(f"SessionManager: Símbolo '{new_symbol}' validado con éxito.", "INFO")
                self._last_known_valid_symbol = new_symbol
                changed_keys.add('TICKER_INTERVAL_SECONDS') 
            else:
                memory_logger.log(f"SessionManager: ERROR - El símbolo '{new_symbol}' es INVÁLIDO. Revertiendo a '{self._last_known_valid_symbol}'.", "ERROR")
                self._config.BOT_CONFIG["TICKER"]["SYMBOL"] = self._last_known_valid_symbol
                changed_keys.discard('TICKER_SYMBOL')
        
        strategy_needs_reset = any(key in STRATEGY_AFFECTING_KEYS for key in changed_keys)

        if strategy_needs_reset or 'TICKER_INTERVAL_SECONDS' in changed_keys:
            if strategy_needs_reset:
                memory_logger.log("SM: Cambios en estrategia detectados. Reconstruyendo componentes...", "WARN")
                self._build_strategy_components()
            
            memory_logger.log("SM: Parámetros actualizados. Reiniciando Ticker para aplicar cambios.", "WARN")
            self.stop()
            self.start()

        
    def is_running(self) -> bool:
        """Indica si la sesión está actualmente en ejecución (ticker activo)."""
        return self._is_running
