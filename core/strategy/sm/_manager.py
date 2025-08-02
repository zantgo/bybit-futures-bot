"""
Módulo Gestor de Sesión (SessionManager).

v5.2 (Validación de Símbolo en Caliente):
- `update_session_parameters` ahora valida activamente un cambio en `TICKER_SYMBOL`.
- Si el nuevo símbolo es inválido, revierte el cambio al último símbolo válido
  conocido y notifica al usuario, evitando que el Ticker opere con un
  símbolo incorrecto.

v5.1 (Fallback de Símbolo):
- El método `initialize` ahora maneja el caso en que el `TICKER_SYMBOL`
  configurado por el usuario sea inválido.

v5.0 (Recarga en Caliente Completa):
- `update_session_parameters` ahora detecta cambios en la configuración que
  afectan a la estrategia o al ticker.
- Si se detectan cambios, reinicia los componentes relevantes (`TAManager`,
  `SignalGenerator`, `Ticker`) para aplicar la nueva configuración sin
  detener la sesión por completo.

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
    from core.strategy.ta import TAManager
    from core.strategy.signal import SignalGenerator
except ImportError:
    # Fallbacks para análisis estático y resiliencia
    memory_logger = type('obj', (object,), {'log': print})()
    class GlobalStopLossException(Exception): pass
    class EventProcessor: pass
    class Ticker: pass
    class TAManager: pass
    class SignalGenerator: pass


STRATEGY_AFFECTING_KEYS = {
    'TA_WINDOW_SIZE',
    'TA_EMA_WINDOW',
    'TA_WEIGHTED_INC_WINDOW',
    'TA_WEIGHTED_DEC_WINDOW',
    'STRATEGY_MARGIN_BUY',
    'STRATEGY_MARGIN_SELL',
    'STRATEGY_DECREMENT_THRESHOLD',
    'STRATEGY_INCREMENT_THRESHOLD',
    'STRATEGY_ENABLED'
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
        self._ta_manager = TAManager_class()
        self._signal_generator = SignalGenerator_class(dependencies)
        session_specific_deps['ta_manager'] = self._ta_manager
        session_specific_deps['signal_generator'] = self._signal_generator
        
        self._event_processor = EventProcessor_class(session_specific_deps)

        # --- Estado Interno ---
        self._initialized = False
        self._is_running = False
        self._session_start_time: Optional[datetime.datetime] = None
        self._global_stop_loss_event = None

        # --- INICIO DE LA MODIFICACIÓN ---
        # Ahora se llama `_last_known_valid_symbol` para mayor claridad.
        self._last_known_valid_symbol = "BTCUSDT" # Un fallback seguro
        if hasattr(self._config, 'TICKER_SYMBOL'):
            self._last_known_valid_symbol = getattr(self._config, 'TICKER_SYMBOL')
        # --- FIN DE LA MODIFICACIÓN ---

    def initialize(self):
        """
        Prepara la sesión para ser iniciada, inicializando sus componentes hijos
        y manejando un posible símbolo de ticker inválido.
        """
        memory_logger.log("SessionManager: Inicializando nueva sesión...", "INFO")

        symbol = getattr(self._config, 'TICKER_SYMBOL')
        operation_mode = "live_interactive"

        if not self._exchange_adapter.initialize(symbol):
            memory_logger.log(f"SessionManager: Fallo al inicializar adaptador para '{symbol}'. "
                              f"Reintentando con el símbolo de respaldo '{self._last_known_valid_symbol}'.", "WARN")
            
            setattr(self._config, 'TICKER_SYMBOL', self._last_known_valid_symbol)
            symbol = self._last_known_valid_symbol

            if not self._exchange_adapter.initialize(symbol):
                raise RuntimeError(f"SessionManager: Fallo crítico al inicializar adaptador. "
                                   f"Incluso el símbolo de respaldo '{symbol}' falló.")
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # El símbolo ha sido validado, así que lo guardamos como el último válido conocido.
        self._last_known_valid_symbol = symbol
        # --- FIN DE LA MODIFICACIÓN ---

        self._pm.initialize(operation_mode=operation_mode)
        
        leverage = getattr(self._config, 'POSITION_LEVERAGE', None)
        if leverage:
            self._trading_api.set_leverage(symbol=symbol, buy_leverage=str(leverage), sell_leverage=str(leverage))

        self._event_processor.initialize(
            operation_mode=operation_mode,
            pm_instance=self._pm,
            global_stop_loss_event=self._global_stop_loss_event
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
        Construye y devuelve un resumen completo del estado de la sesión actual,
        agregando datos de rendimiento total.
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
            
            total_initial_capital = 0
            total_session_pnl = 0
            
            if long_op:
                total_initial_capital += long_op.capital_inicial_usdt
                total_session_pnl += summary.get('operation_long_pnl', 0.0)
            
            if short_op:
                total_initial_capital += short_op.capital_inicial_usdt
                total_session_pnl += summary.get('operation_short_pnl', 0.0)
                
            summary['total_session_initial_capital'] = total_initial_capital
            summary['total_session_pnl'] = total_session_pnl
            summary['total_session_roi'] = self._utils.safe_division(total_session_pnl, total_initial_capital) * 100
            
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
            
        changed_keys = set()
        for attr, new_value in params.items():
            if hasattr(self._config, attr):
                old_value = getattr(self._config, attr, None)
                if new_value != old_value:
                    # Aplicar el cambio temporalmente para registrarlo
                    setattr(self._config, attr, new_value)
                    changed_keys.add(attr)
        
        if not changed_keys:
            memory_logger.log("SessionManager: No se detectaron cambios en la configuración.", "INFO")
            return
            
        # --- INICIO DE LA MODIFICACIÓN PRINCIPAL ---

        # 1. Manejo especial para el cambio de Ticker Symbol
        if 'TICKER_SYMBOL' in changed_keys:
            new_symbol = getattr(self._config, 'TICKER_SYMBOL')
            memory_logger.log(f"SessionManager: Se detectó cambio de símbolo a '{new_symbol}'. Validando...", "WARN")

            # Usamos el adaptador para verificar si el nuevo símbolo es válido
            is_new_symbol_valid = self._exchange_adapter.get_instrument_info(new_symbol) is not None
            
            if is_new_symbol_valid:
                memory_logger.log(f"SessionManager: Símbolo '{new_symbol}' validado con éxito.", "INFO")
                # Actualizamos nuestro respaldo al nuevo símbolo válido
                self._last_known_valid_symbol = new_symbol
                # Forzamos un reinicio completo, ya que un nuevo símbolo lo requiere
                changed_keys.add('TICKER_INTERVAL_SECONDS') # Añadimos esto para asegurar que el ticker se reinicie
                for k in STRATEGY_AFFECTING_KEYS: changed_keys.add(k) # Forzamos reinicio de la estrategia
            else:
                memory_logger.log(f"SessionManager: ERROR - El símbolo '{new_symbol}' es INVÁLIDO. Revertiendo a '{self._last_known_valid_symbol}'.", "ERROR")
                # Revertimos el cambio en el objeto config
                setattr(self._config, 'TICKER_SYMBOL', self._last_known_valid_symbol)
                # Eliminamos la clave de los cambios para que no active ninguna otra acción
                changed_keys.remove('TICKER_SYMBOL')
        
        # Loggear los cambios que SÍ se van a aplicar
        for key in changed_keys:
            memory_logger.log(f"SessionManager: Aplicando config '{key}' -> '{getattr(self._config, key)}'", "WARN")

        # 2. Lógica de reinicio basada en los cambios finales y validados
        strategy_needs_reset = any(key in STRATEGY_AFFECTING_KEYS for key in changed_keys)
        if strategy_needs_reset:
            memory_logger.log("SessionManager: Cambios en parámetros de estrategia detectados. Reiniciando componentes de TA y Señal...", "WARN")
            if self._ta_manager: self._ta_manager.initialize()
            if self._signal_generator: self._signal_generator.initialize()

        if 'TICKER_INTERVAL_SECONDS' in changed_keys:
            memory_logger.log("SessionManager: Parámetros del Ticker actualizados. Reiniciando el hilo del Ticker...", "WARN")
            self.stop()
            self.start()

        # 3. Lógica para límites de sesión (sin cambios)
        if any(key in ['SESSION_STOP_LOSS_ROI_PCT', 'SESSION_ROI_SL_ENABLED'] for key in changed_keys):
            sl_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT') if getattr(self._config, 'SESSION_ROI_SL_ENABLED', False) else 0
            self._pm_api.set_global_stop_loss_pct(sl_pct)
            
        if any(key in ['SESSION_TAKE_PROFIT_ROI_PCT', 'SESSION_ROI_TP_ENABLED'] for key in changed_keys):
            tp_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT') if getattr(self._config, 'SESSION_ROI_TP_ENABLED', False) else 0
            self._pm_api.set_global_take_profit_pct(tp_pct)
        # --- FIN DE LA MODIFICACIÓN PRINCIPAL ---

    def is_running(self) -> bool:
        """Indica si la sesión está actualmente en ejecución (ticker activo)."""
        return self._is_running