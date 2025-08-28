# core/strategy/sm/_manager.py

"""
Módulo Gestor de Sesión (SessionManager).
"""

import datetime
from datetime import timezone
import traceback
from typing import Dict, Any, Optional
import numpy as np # Importado para cálculos de promedio

# --- Dependencias del Proyecto (inyectadas a través de __init__) ---
try:
    from core.logging import memory_logger
    from core.strategy._event_processor import EventProcessor
    from connection import Ticker
    from core.strategy.ta import TAManager
    from core.strategy.signal import SignalGenerator
    # --- Añadido para tipado correcto ---
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
        self._ta_manager = TAManager_class(self._config)
        self._signal_generator = SignalGenerator_class(dependencies)
        session_specific_deps['ta_manager'] = self._ta_manager
        session_specific_deps['signal_generator'] = self._signal_generator
        
        self._event_processor = EventProcessor_class(session_specific_deps)

        self._initialized = False
        self._is_running = False
        self._session_start_time: Optional[datetime.datetime] = None
        self._last_known_valid_symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
        
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
    
        self._event_processor.initialize(
            operation_mode=operation_mode,
            pm_instance=self._pm
        )
        
        if self._ta_manager:
            self._ta_manager.initialize()
        if self._signal_generator:
            self._signal_generator.initialize()

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
        
        if not self._session_start_time: 
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
            
            # --- INICIO DE LA CORRECCIÓN ---
            # Se refactoriza la función interna `get_op_details` para que siempre
            # devuelva el estado y la información relevante, sin importar el estado.
            def get_op_details(op: Optional[Operacion]) -> Dict[str, Any]:
                # Si el objeto de operación no existe, devolvemos valores por defecto.
                if not op: 
                    return {
                        "id": "N/A", 
                        "estado": "NO_INICIADA", 
                        "tendencia": "N/A",
                        "duracion_activa": "N/A"
                    }
                
                # Calcular la duración solo si está ACTIVA y tiene un tiempo de inicio.
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

            # Se asegura que la clave 'operations_info' siempre se construya en el resumen.
            summary['operations_info'] = {
                'long': get_op_details(long_op),
                'short': get_op_details(short_op)
            }
            # --- FIN DE LA CORRECCIÓN ---
            
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
            traceback.print_exc()
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

        if strategy_needs_reset:
            memory_logger.log("SessionManager: Cambios en parámetros de estrategia detectados. Reiniciando componentes de TA y Señal...", "WARN")
            if self._ta_manager: self._ta_manager.initialize()
            if self._signal_generator: self._signal_generator.initialize()

        if 'TICKER_INTERVAL_SECONDS' in changed_keys:
            memory_logger.log("SessionManager: Parámetros del Ticker actualizados. Reiniciando el hilo del Ticker...", "WARN")
            self.stop()
            self.start()
        
    def is_running(self) -> bool:
        """Indica si la sesión está actualmente en ejecución (ticker activo)."""
        return self._is_running