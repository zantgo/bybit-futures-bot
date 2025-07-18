# =============== INICIO ARCHIVO: core/strategy/event_processor.py (COMPLETO Y MODIFICADO) ===============
"""
Procesa un único evento de precio (tick).
Calcula TA, genera señal y delega la gestión de posiciones al pm_facade.

v16.0 (Control Dual):
- Adaptado a la nueva arquitectura de Position Manager (pm_facade).
- Diferencia la llamada a `handle_low_level_signal` según si el modo es
  'live_interactive' (sin contexto) o 'automatic' (con contexto).
v14.0 (Orquestador de Régimen):
- Modificado para obtener el contexto de mercado del MarketRegimeController.
- Pasa el market_context a position_manager.handle_low_level_signal.
v13.3 - Añadido chequeo de Global Stop Loss.
"""
import datetime
import traceback
import pandas as pd
import numpy as np
import json
import sys
import threading
from typing import Optional, Dict, Any, List

# --- Importaciones Core y Strategy ---
try:
    import config
    from core import utils
    from . import ta_manager
    from . import signal_generator
    from . import position_state

    # <<< INICIO MODIFICACIÓN: Importar la fachada con el alias original >>>
    position_manager = None
    _pm_enabled_in_config = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    if _pm_enabled_in_config:
        try:
            from . import pm_facade as position_manager
            print("DEBUG [Event Proc Import]: Fachada de Position Manager (pm_facade) importada.")
        except ImportError as e_pm:
            print(f"ERROR CRITICO [Event Proc Import]: Import relativo de pm_facade falló: {e_pm}")
        except Exception as e_pm_other:
            print(f"WARN [Event Proc Import]: Excepción inesperada cargando pm_facade: {e_pm_other}")
    else:
        print("INFO [Event Proc Import]: Position Management desactivado en config, PM no importado.")
    # <<< FIN MODIFICACIÓN >>>

    signal_logger = None
    if getattr(config, 'LOG_SIGNAL_OUTPUT', False):
        try:
            from core.logging import signal_logger
            print("DEBUG [Event Proc Import]: Signal Logger importado.")
        except ImportError:
            print("WARN [Event Proc Import]: No se pudo cargar signal_logger (habilitado en config).")
        except Exception as e_log_other:
             print(f"WARN [Event Proc Import]: Excepción inesperada cargando signal_logger: {e_log_other}")

except ImportError as e:
    print(f"ERROR CRÍTICO [Event Proc Import]: Falló importación base (config/utils/core?): {e}")
    config=None; utils=None; ta_manager=None; signal_generator=None; position_manager=None; signal_logger=None; position_state = None
    traceback.print_exc(); sys.exit(1)
except Exception as e_imp:
    print(f"ERROR CRÍTICO [Event Proc Import]: Excepción inesperada durante imports: {e_imp}")
    config=None; utils=None; ta_manager=None; signal_generator=None; position_manager=None; signal_logger=None; position_state = None
    traceback.print_exc(); sys.exit(1)

class GlobalStopLossException(Exception):
    """Excepción para ser lanzada cuando se activa el Global Stop Loss en backtest."""
    pass

# --- Estado del Módulo ---
_previous_raw_event_price = np.nan
_is_first_event = True
_operation_mode = "unknown"
_market_regime_controller_instance: Optional[Any] = None # Renombrado para claridad
_global_stop_loss_event: Optional[threading.Event] = None
_global_stop_loss_triggered: bool = False

# --- Inicialización ---
def initialize(
    operation_mode: str,
    initial_real_state: Optional[Dict[str, Dict[str, Any]]] = None,
    base_position_size_usdt: Optional[float] = None,
    initial_max_logical_positions: Optional[int] = None,
    ut_bot_controller_instance: Optional[Any] = None, # Mantenido por retrocompatibilidad de llamada
    stop_loss_event: Optional[threading.Event] = None,
    global_stop_loss_event: Optional[threading.Event] = None
):
    global _previous_raw_event_price, _is_first_event, _operation_mode, _market_regime_controller_instance
    global position_manager, _global_stop_loss_event, _global_stop_loss_triggered

    if not config or not utils or not ta_manager or not signal_generator:
        raise RuntimeError("Event Processor no pudo inicializarse por dependencias faltantes.")

    print("[Event Processor] Inicializando...")
    _previous_raw_event_price = np.nan
    _is_first_event = True
    _operation_mode = operation_mode
    _market_regime_controller_instance = ut_bot_controller_instance
    _global_stop_loss_event = global_stop_loss_event
    _global_stop_loss_triggered = False

    if signal_logger and getattr(config, 'LOG_SIGNAL_OUTPUT', False) and hasattr(signal_logger, 'initialize_logger'):
        try: signal_logger.initialize_logger()
        except Exception as e: print(f"ERROR [Event Proc]: Inicializando signal_logger: {e}")

    print("[Event Processor] Inicializado.")


# --- Procesamiento Principal de Evento ---
def process_event(intermediate_ticks_info: list, final_price_info: dict):
    global _previous_raw_event_price, _is_first_event, _global_stop_loss_triggered
    global position_manager, _market_regime_controller_instance

    if _global_stop_loss_triggered:
        return

    if not all([ta_manager, signal_generator, utils, config]):
        print("ERROR CRÍTICO [EP Process]: Faltan módulos esenciales. Imposible procesar evento."); return

    if not final_price_info:
        print("WARN [EP Process]: Evento final vacío."); return

    current_timestamp = final_price_info.get("timestamp")
    current_price = utils.safe_float_convert(final_price_info.get("price"), default=np.nan)

    if not isinstance(current_timestamp, (datetime.datetime, pd.Timestamp)) or pd.isna(current_price) or current_price <= 0:
        print(f"WARN [EP Process]: Timestamp/Precio inválido. Saltando. TS:{current_timestamp}, P:{current_price}"); return

    if _market_regime_controller_instance and hasattr(_market_regime_controller_instance, 'add_tick'):
        try:
            _market_regime_controller_instance.add_tick(current_price, current_timestamp)
        except Exception as e_ut_tick:
            print(f"ERROR [EP Process]: Falló al pasar tick al Controller de Alto Nivel: {e_ut_tick}")

    increment = 0
    decrement = 0
    if not _is_first_event and pd.notna(_previous_raw_event_price):
        if current_price > _previous_raw_event_price + 1e-9: increment = 1
        elif current_price < _previous_raw_event_price - 1e-9: decrement = 1
    _is_first_event = False

    raw_price_event = {'timestamp': current_timestamp, 'price': current_price, 'increment': increment, 'decrement': decrement}
    if getattr(config, 'PRINT_RAW_EVENT_ALWAYS', False): print(f"DEBUG [Raw Event]: {raw_price_event}")

    processed_data = None
    if getattr(config, 'TA_CALCULATE_PROCESSED_DATA', True):
        try:
            processed_data = ta_manager.process_raw_price_event(raw_price_event.copy())
        except Exception as e_ta:
            print(f"ERROR [TA Call]: {e_ta}"); traceback.print_exc()

    signal_data = None
    nan_fmt = "NaN"
    base_signal_dict = {
        "timestamp": utils.format_datetime(current_timestamp),
        "price_float": current_price,
        "price": f"{current_price:.{getattr(config, 'PRICE_PRECISION', 4)}f}",
        "ema": nan_fmt, "inc_price_change_pct": nan_fmt, "dec_price_change_pct": nan_fmt,
        "weighted_increment": nan_fmt, "weighted_decrement": nan_fmt
    }

    try:
        if getattr(config, 'STRATEGY_ENABLED', True):
            if processed_data:
                signal_data = signal_generator.generate_signal(processed_data.copy())
            else:
                signal_data = {**base_signal_dict, "signal": "HOLD_NO_TA", "signal_reason": "No TA data"}
        else:
            signal_data = {**base_signal_dict, "signal": "HOLD_STRATEGY_DISABLED", "signal_reason": "Strategy disabled"}
    except Exception as e_signal:
        print(f"ERROR [Signal Gen Call]: {e_signal}"); traceback.print_exc()
        signal_data = {**base_signal_dict, "signal": "HOLD_SIGNAL_ERROR", "signal_reason": f"Error: {e_signal}"}

    pm_enabled_runtime = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    if pm_enabled_runtime and position_manager and getattr(position_manager.pm_state, 'is_initialized', lambda: False)():
        try:
            position_manager.check_and_close_positions(current_price, current_timestamp)
            
            if signal_data:
                if _operation_mode == "live_interactive":
                    position_manager.handle_low_level_signal(
                        signal=signal_data.get("signal"),
                        entry_price=current_price,
                        timestamp=current_timestamp
                    )
                else:
                    market_regime = {}
                    if _market_regime_controller_instance and hasattr(_market_regime_controller_instance, 'get_market_regime'):
                        market_regime = _market_regime_controller_instance.get_market_regime()

                    position_manager.handle_low_level_signal(
                        signal=signal_data.get("signal"),
                        entry_price=current_price,
                        timestamp=current_timestamp,
                        market_context=market_regime.get("context", "UNKNOWN")
                    )

        except Exception as pm_err:
            print(f"ERROR [PM Call from EP]: {pm_err}"); traceback.print_exc()

    # Chequea si se han alcanzado los límites de la sesión (tiempo, TP, SL)
    _check_session_limits(current_price, current_timestamp)

    if signal_data:
        if signal_logger and getattr(config, 'LOG_SIGNAL_OUTPUT', False):
            try:
                if hasattr(signal_logger, 'log_signal_event'): signal_logger.log_signal_event(signal_data.copy());
                else: print("WARN [EP Process]: signal_logger sin 'log_signal_event'.")
            except Exception as e_log_write:
                print(f"ERROR [Signal Log Write]: {e_log_write}")
        if getattr(config, 'PRINT_SIGNAL_OUTPUT', False):
            try: print(json.dumps(signal_data, indent=2));
            except Exception as e_print_signal: print(f"ERROR [Print Signal]: {e_print_signal}\nData: {signal_data}")

    _previous_raw_event_price = current_price

    if pm_enabled_runtime and position_manager and getattr(position_manager.pm_state, 'is_initialized', lambda: False)():
        if getattr(config, 'POSITION_SIGNAL_COOLDOWN_ENABLED', False):
            pass
    
    if _operation_mode.startswith(('live', 'automatic')) and getattr(config, 'PRINT_TICK_LIVE_STATUS', False):
        try:
            ts_str_fmt = utils.format_datetime(current_timestamp)
            current_price_fmt_str = f"{current_price:.{config.PRICE_PRECISION}f}" if hasattr(config, 'PRICE_PRECISION') else f"{current_price:.8f}"
            hdr = "="*25 + f" TICK STATUS @ {ts_str_fmt} " + "="*25; print("\n" + hdr)
            print(f"  Precio Actual : {current_price_fmt_str:<15}")
            print("  Indicadores TA:");
            if processed_data:
                 ema_precision_fmt = f".{config.PRICE_PRECISION}f" if hasattr(config, 'PRICE_PRECISION') else ".8f"
                 ema_val = processed_data.get('ema', np.nan); winc_val = processed_data.get('weighted_increment', np.nan); wdec_val = processed_data.get('weighted_decrement', np.nan); inc_pct_val = processed_data.get('inc_price_change_pct', np.nan); dec_pct_val = processed_data.get('dec_price_change_pct', np.nan);
                 ema_str = f"{ema_val:<15{ema_precision_fmt}}" if pd.notna(ema_val) else f"{nan_fmt:<15}"; winc_str = f"{winc_val:<8.4f}" if pd.notna(winc_val) else f"{nan_fmt:<8}"; wdec_str = f"{wdec_val:<8.4f}" if pd.notna(wdec_val) else f"{nan_fmt:<8}"; inc_pct_str = f"{inc_pct_val:<15.4f}%" if pd.notna(inc_pct_val) and np.isfinite(inc_pct_val) else f"{nan_fmt:<15} %"; dec_pct_str = f"{dec_pct_val:<8.4f}%" if pd.notna(dec_pct_val) and np.isfinite(dec_pct_val) else f"{nan_fmt:<8} %";
                 print(f"    EMA       : {ema_str} W.Inc : {winc_str} W.Dec : {wdec_str}")
                 print(f"    Inc %     : {inc_pct_str} Dec % : {dec_pct_str}")
            else: print("    (No disponibles)")
            print("  Señal Generada:");
            if signal_data: print(f"    Signal: {signal_data.get('signal', 'N/A'):<15} Reason: {signal_data.get('signal_reason', 'N/A')}")
            else: print("    (No generada)")
            print("  Estado Posiciones:");
            if pm_enabled_runtime and position_manager and getattr(position_manager.pm_state, 'is_initialized', lambda: False)():
                summary = position_manager.get_position_summary()
                if summary and 'error' not in summary:
                    manual_status = summary.get('manual_mode_status', {})
                    trend_status = summary.get('trend_status', {})
                    balances = summary.get('bm_balances', {})

                    print(f"    Modo Op: {summary.get('operation_mode', 'N/A')}")
                    if summary.get('operation_mode') == 'live_interactive':
                        limit_str = manual_status.get('limit') or 'inf'
                        print(f"    Modo Manual: {manual_status.get('mode', 'N/A')} (Trades: {manual_status.get('executed', 0)}/{limit_str})")
                    else:
                        print(f"    Tendencia Auto: {trend_status.get('side', 'NONE')} (Trades: {trend_status.get('trades_count', 0)})")

                    print(f"    Longs: {summary.get('open_long_positions_count', 0)}/{summary.get('max_logical_positions', 0)} | Shorts: {summary.get('open_short_positions_count', 0)}/{summary.get('max_logical_positions', 0)}")
                    print(f"    PNL Sesión: {summary.get('total_realized_pnl_session', 0.0):+.4f} USDT")

                elif summary and 'error' in summary: print(f"    Error resumen PM: {summary.get('error', 'N/A')}")
                else: print(f"    Error resumen PM (Respuesta inválida).")
            elif pm_enabled_runtime and position_manager: print("    (PM no inicializado)")
            else: print("    (Gestión desactivada o PM no disponible)")
            print("=" * len(hdr))
        except Exception as e_print: print(f"ERROR [Print Tick Status]: {e_print}"); traceback.print_exc()


def _check_session_limits(current_price: float, current_timestamp: datetime.datetime):
    global _global_stop_loss_triggered
    if not position_manager or not position_state or not utils or not config:
        return
    if not getattr(position_manager.pm_state, 'is_initialized', lambda: False)():
        return
    if _global_stop_loss_triggered:
        return

    # --- 1. CHEQUEO DEL LÍMITE DE TIEMPO DE LA SESIÓN ---
    start_time = position_manager.pm_state.get_session_start_time()
    if not start_time: return # No hacer nada si la sesión no ha empezado formalmente

    time_limit_config = position_manager.pm_state.get_session_time_limit()
    max_minutes = time_limit_config.get("duration", 0)
    time_limit_action = time_limit_config.get("action", "NEUTRAL").upper()

    if max_minutes > 0:
        elapsed_minutes = (current_timestamp - start_time).total_seconds() / 60.0
        if elapsed_minutes >= max_minutes:
            if time_limit_action == "STOP":
                 # La acción es una parada de emergencia. Solo se ejecuta una vez.
                if not _global_stop_loss_triggered:
                    print("\n" + "!"*80)
                    print("!!!   LÍMITE DE TIEMPO DE SESIÓN ALCANZADO (ACCIÓN: STOP)   !!!".center(80))
                    print(f"!!! Tiempo ({elapsed_minutes:.2f} min) >= Límite ({max_minutes} min). Deteniendo el bot. !!!".center(80))
                    print("!"*80 + "\n")
                    _global_stop_loss_triggered = True
                    position_manager.close_all_logical_positions('long', reason="TIME_LIMIT_STOP")
                    position_manager.close_all_logical_positions('short', reason="TIME_LIMIT_STOP")
                    if _global_stop_loss_event:
                        _global_stop_loss_event.set()
                    if _operation_mode != "backtest":
                        raise GlobalStopLossException("Límite de tiempo de sesión alcanzado (STOP)")
                return # Detener más chequeos en este tick.

            else: # NEUTRAL
                # La acción es una parada suave, solo se ejecuta una vez.
                if not position_manager.pm_state.is_session_tp_hit():
                    print("\n" + "*"*80)
                    print("!!!   LÍMITE DE TIEMPO DE SESIÓN ALCANZADO (ACCIÓN: NEUTRAL)   !!!".center(80))
                    print(f"!!! Tiempo ({elapsed_minutes:.2f} min) >= Límite ({max_minutes} min). Pasando a modo neutral. !!!".center(80))
                    print("*"*80 + "\n")
                    position_manager.pm_state.set_session_tp_hit(True)
                    if _operation_mode == "live_interactive":
                        position_manager.set_manual_trading_mode("NEUTRAL")

    # --- 2. CHEQUEO DE LÍMITES DE ROI ---
    sl_threshold_pct = position_manager.pm_state.get_global_sl_pct()
    tp_threshold_pct = position_manager.pm_state.get_global_tp_pct()

    if (sl_threshold_pct is None or sl_threshold_pct == 0.0) and \
       (tp_threshold_pct is None or tp_threshold_pct == 0.0):
        return

    summary = position_manager.get_position_summary()
    if not summary or 'error' in summary: return
    initial_capital = summary.get('initial_total_capital', 0.0)
    if initial_capital < 1e-6: return
    
    total_realized_pnl = summary.get('total_realized_pnl_session', 0.0)
    total_unrealized_pnl = 0.0
    open_longs = position_state.get_open_logical_positions('long')
    for pos in open_longs:
        total_unrealized_pnl += (current_price - pos.get('entry_price', 0.0)) * pos.get('size_contracts', 0.0)
    open_shorts = position_state.get_open_logical_positions('short')
    for pos in open_shorts:
        total_unrealized_pnl += (pos.get('entry_price', 0.0) - current_price) * pos.get('size_contracts', 0.0)
    
    current_roi_pct = utils.safe_division(total_realized_pnl + total_unrealized_pnl, initial_capital) * 100.0
    
    # Lógica de Take Profit por ROI
    if tp_threshold_pct and tp_threshold_pct > 0 and not position_manager.pm_state.is_session_tp_hit():
        if current_roi_pct >= tp_threshold_pct:
            print("\n" + "*"*80)
            print("!!!   INFO: GLOBAL TAKE PROFIT DE LA SESIÓN ALCANZADO   !!!".center(80))
            print(f"!!! ROI Total ({current_roi_pct:.2f}%) >= Umbral ({tp_threshold_pct:.2f}%) !!!".center(80))
            print("*"*80 + "\n")
            position_manager.pm_state.set_session_tp_hit(True)
            if _operation_mode == "live_interactive":
                position_manager.set_manual_trading_mode("NEUTRAL") 
            
    # Lógica de Stop Loss por ROI
    stop_loss_comparison_pct = -abs(sl_threshold_pct) if sl_threshold_pct else 0.0
    if stop_loss_comparison_pct != 0 and current_roi_pct <= stop_loss_comparison_pct:
        _global_stop_loss_triggered = True
        print("\n" + "!"*80)
        print("!!!   ALERTA DE EMERGENCIA: GLOBAL STOP LOSS POR ROI ACTIVADO   !!!".center(80))
        print(f"!!! ROI Total ({current_roi_pct:.2f}%) <= Umbral ({stop_loss_comparison_pct:.2f}%) !!!".center(80))
        print("!"*80 + "\n")
        
        position_manager.close_all_logical_positions('long', reason="GLOBAL_SL_ROI")
        position_manager.close_all_logical_positions('short', reason="GLOBAL_SL_ROI")
        
        if _global_stop_loss_event:
            _global_stop_loss_event.set()
        if _operation_mode != "backtest":
            raise GlobalStopLossException(f"Global Stop Loss por ROI activado: {current_roi_pct:.2f}%")

# =============== FIN ARCHIVO: core/strategy/event_processor.py (COMPLETO Y MODIFICADO) ===============