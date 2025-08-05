# ./core/strategy/sm/_manager.py

"""
Módulo Gestor de Sesión (SessionManager).

v6.0 (Refactor de Configuración):
- Adaptado para leer la configuración desde los nuevos diccionarios anidados
  en `config.py` (BOT_CONFIG, SESSION_CONFIG, OPERATION_DEFAULTS).

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
import numpy as np # Importado para cálculos de promedio

# --- Dependencias del Proyecto (inyectadas a través de __init__) ---
try:
    from core.logging import memory_logger
    from core.strategy.ep.event_processor import GlobalStopLossException, EventProcessor
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

# --- INICIO DE LA CORRECCIÓN: Claves que afectan la estrategia actualizadas ---
# Estas son ahora las claves dentro de SESSION_CONFIG que, si cambian,
# requieren un reinicio de los componentes de análisis.
STRATEGY_AFFECTING_KEYS = {
    'EMA_WINDOW',
    'WEIGHTED_INC_WINDOW',
    'WEIGHTED_DEC_WINDOW',
    'PRICE_CHANGE_BUY_PERCENTAGE',
    'PRICE_CHANGE_SELL_PERCENTAGE',
    'WEIGHTED_DECREMENT_THRESHOLD',
    'WEIGHTED_INCREMENT_THRESHOLD',
    'ENABLED' # Clave genérica para sub-diccionarios como TA y SIGNAL
}
# --- FIN DE LA CORRECCIÓN ---


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
        self._ta_manager = TAManager_class(self._config)
        self._signal_generator = SignalGenerator_class(dependencies)
        session_specific_deps['ta_manager'] = self._ta_manager
        session_specific_deps['signal_generator'] = self._signal_generator
        
        self._event_processor = EventProcessor_class(session_specific_deps)

        # --- Estado Interno ---
        self._initialized = False
        self._is_running = False
        self._session_start_time: Optional[datetime.datetime] = None
        self._global_stop_loss_event = None
        # --- INICIO DE LA CORRECCIÓN ---
        self._last_known_valid_symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
        # --- FIN DE LA CORRECCIÓN ---


    def initialize(self):
        """
        Prepara la sesión para ser iniciada, inicializando sus componentes hijos
        y manejando un posible símbolo de ticker inválido.
        """
        memory_logger.log("SessionManager: Inicializando nueva sesión...", "INFO")
        # --- INICIO DE LA CORRECCIÓN ---
        symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
        # --- FIN DE LA CORRECCIÓN ---

        operation_mode = "live_interactive"

        if not self._exchange_adapter.initialize(symbol):
            memory_logger.log(f"SessionManager: Fallo al inicializar adaptador para '{symbol}'. "
                              f"Reintentando con el símbolo de respaldo '{self._last_known_valid_symbol}'.", "WARN")
            # --- INICIO DE LA CORRECCIÓN ---
            self._config.BOT_CONFIG["TICKER"]["SYMBOL"] = self._last_known_valid_symbol
            # --- FIN DE LA CORRECCIÓN ---
            symbol = self._last_known_valid_symbol

            if not self._exchange_adapter.initialize(symbol):
                raise RuntimeError(f"SessionManager: Fallo crítico al inicializar adaptador. "
                                   f"Incluso el símbolo de respaldo '{symbol}' falló.")
        
        self._last_known_valid_symbol = symbol

        self._pm.initialize(operation_mode=operation_mode)
        # --- INICIO DE LA CORRECCIÓN ---
        leverage = self._config.OPERATION_DEFAULTS["CAPITAL"].get('LEVERAGE')
        # --- FIN DE LA CORRECCIÓN ---
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
                summary['comisiones_totales_usdt_long'] = long_op.comisiones_totales_usdt
                long_positions = summary.get('open_long_positions', [])
                if long_positions:
                    entry_prices = [p.get('entry_price', 0) for p in long_positions]
                    summary['avg_entry_price_long'] = np.mean(entry_prices) if entry_prices else 'N/A'
                else:
                    summary['avg_entry_price_long'] = 'N/A'

            if short_op:
                total_initial_capital += short_op.capital_inicial_usdt
                total_session_pnl += summary.get('operation_short_pnl', 0.0)
                summary['comisiones_totales_usdt_short'] = short_op.comisiones_totales_usdt
                short_positions = summary.get('open_short_positions', [])
                if short_positions:
                    entry_prices = [p.get('entry_price', 0) for p in short_positions]
                    summary['avg_entry_price_short'] = np.mean(entry_prices) if entry_prices else 'N/A'
                else:
                    summary['avg_entry_price_short'] = 'N/A'
                
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
        changed_keys = set(params.keys())
        
        if not changed_keys:
            memory_logger.log("SessionManager: No se detectaron cambios en la configuración.", "INFO")
            return
            
        # El editor de config general ya no pasa 'TICKER_SYMBOL', pero se mantiene la lógica
        if 'TICKER_SYMBOL' in changed_keys:
            new_symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
            memory_logger.log(f"SessionManager: Se detectó cambio de símbolo a '{new_symbol}'. Validando...", "WARN")

            is_new_symbol_valid = self._exchange_adapter.get_instrument_info(new_symbol) is not None
            
            if is_new_symbol_valid:
                memory_logger.log(f"SessionManager: Símbolo '{new_symbol}' validado con éxito.", "INFO")
                self._last_known_valid_symbol = new_symbol
                changed_keys.add('TICKER_INTERVAL_SECONDS') # Forzar reinicio del Ticker
            else:
                memory_logger.log(f"SessionManager: ERROR - El símbolo '{new_symbol}' es INVÁLIDO. Revertiendo a '{self._last_known_valid_symbol}'.", "ERROR")
                self._config.BOT_CONFIG["TICKER"]["SYMBOL"] = self._last_known_valid_symbol
                changed_keys.discard('TICKER_SYMBOL')
        
        # --- INICIO DE LA CORRECCIÓN: Lógica de detección de cambios actualizada ---
        strategy_needs_reset = any(key in STRATEGY_AFFECTING_KEYS for key in changed_keys)

        if strategy_needs_reset:
            memory_logger.log("SessionManager: Cambios en parámetros de estrategia detectados. Reiniciando componentes de TA y Señal...", "WARN")
            if self._ta_manager: self._ta_manager.initialize()
            if self._signal_generator: self._signal_generator.initialize()
        # --- FIN DE LA CORRECCIÓN ---

        if 'TICKER_INTERVAL_SECONDS' in changed_keys:
            memory_logger.log("SessionManager: Parámetros del Ticker actualizados. Reiniciando el hilo del Ticker...", "WARN")
            self.stop()
            self.start()

        # --- INICIO DE LA CORRECCIÓN: Actualizar límites globales ---
        limits_cfg = self._config.SESSION_CONFIG["SESSION_LIMITS"]
        sl_enabled = limits_cfg["ROI_SL"]["ENABLED"]
        sl_pct = limits_cfg["ROI_SL"]["PERCENTAGE"] if sl_enabled else 0.0
        self._pm_api.set_global_stop_loss_pct(sl_pct)

        tp_enabled = limits_cfg["ROI_TP"]["ENABLED"]
        tp_pct = limits_cfg["ROI_TP"]["PERCENTAGE"] if tp_enabled else 0.0
        self._pm_api.set_global_take_profit_pct(tp_pct)
        # --- FIN DE LA CORRECCIÓN ---

    def is_running(self) -> bool:
        """Indica si la sesión está actualmente en ejecución (ticker activo)."""
        return self._is_running