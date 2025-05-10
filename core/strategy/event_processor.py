# =============== INICIO ARCHIVO: core/strategy/event_processor.py (v8.7.x - Nueva Lógica Capital) ===============
"""
Procesa un único evento de precio (tick).
Calcula TA, genera señal, gestiona posiciones (live/backtest), y loguea/imprime.

v8.7.x: Modificada la inicialización para aceptar y pasar base_position_size e initial_slots a PM.
v8.7.8: Corrige firma de initialize para aceptar initial_real_state.
v8.5.5: Acepta instance_capital y lo pasa a PM.initialize.
"""
import datetime
import traceback
import pandas as pd
import numpy as np
import json
import sys # Para sys.exit en caso de error crítico de importación
from typing import Optional, Dict, Any, List

# --- Importaciones Core y Strategy ---
try:
    # Importar config desde la raíz y utils desde core
    import config 
    from core import utils
    # Imports relativos dentro de strategy (asumiendo que este archivo está en core/strategy)
    from . import ta_manager
    from . import signal_generator
    position_manager = None # Inicializar a None
    _pm_enabled_in_config = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    if _pm_enabled_in_config:
        try:
            from . import position_manager 
            print("DEBUG [Event Proc Import]: Position Manager importado.")
        except ImportError as e_pm:
            print(f"ERROR CRITICO [Event Proc Import]: Import relativo de position_manager falló: {e_pm}")
        except Exception as e_pm_other:
            print(f"WARN [Event Proc Import]: Excepción inesperada cargando position_manager: {e_pm_other}")
    else:
        print("INFO [Event Proc Import]: Position Management desactivado en config, PM no importado.")

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
    config=None; utils=None; ta_manager=None; signal_generator=None; position_manager=None; signal_logger=None
    traceback.print_exc(); sys.exit(1)
except Exception as e_imp:
    print(f"ERROR CRÍTICO [Event Proc Import]: Excepción inesperada durante imports: {e_imp}")
    config=None; utils=None; ta_manager=None; signal_generator=None; position_manager=None; signal_logger=None
    traceback.print_exc(); sys.exit(1)

# --- Estado del Módulo ---
_previous_raw_event_price = np.nan
_is_first_event = True
_operation_mode = "unknown"

# --- Inicialización ---
def initialize(
    operation_mode: str,
    initial_real_state: Optional[Dict[str, Dict[str, Any]]] = None,
    # instance_capital_override: Optional[float] = None, # Eliminado
    # Nuevos parámetros para la configuración de posiciones
    base_position_size_usdt: Optional[float] = None,
    initial_max_logical_positions: Optional[int] = None
):
    """
    Inicializa el procesador, loggers y position manager, pasando la nueva configuración de posiciones.
    """
    global _previous_raw_event_price, _is_first_event, _operation_mode
    global position_manager 

    if not config or not utils or not ta_manager or not signal_generator:
        print("ERROR CRITICO [EP Init]: Faltan dependencias esenciales (config, utils, TA, SignalGen).")
        raise RuntimeError("Event Processor no pudo inicializarse por dependencias faltantes.")

    print("[Event Processor] Inicializando...")
    _previous_raw_event_price = np.nan; _is_first_event = True
    _operation_mode = operation_mode

    if signal_logger and getattr(config, 'LOG_SIGNAL_OUTPUT', False) and hasattr(signal_logger, 'initialize_logger'):
        try: signal_logger.initialize_logger()
        except Exception as e: print(f"ERROR [Event Proc]: Inicializando signal_logger: {e}")
    elif getattr(config, 'LOG_SIGNAL_OUTPUT', False) and not signal_logger: print("WARN [Event Proc]: LOG_SIGNAL_OUTPUT=True pero signal_logger no disponible.")

    # --- Inicializar Position Manager ---
    pm_enabled = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    if pm_enabled:
        if position_manager and hasattr(position_manager, 'initialize'):
             try:
                 # Preparar mensaje de debug con los nuevos parámetros
                 debug_msg_pm_init = (
                     f"DEBUG [EP Init]: Llamando a position_manager.initialize -> "
                     f"mode='{operation_mode}', "
                     f"initial_real_state={'Presente' if initial_real_state else 'None'}, "
                     f"base_pos_size={base_position_size_usdt if base_position_size_usdt is not None else 'Default_PM'}, "
                     f"initial_slots={initial_max_logical_positions if initial_max_logical_positions is not None else 'Default_PM'}"
                 )
                 print(debug_msg_pm_init)
                 
                 # Pasar los nuevos parámetros a PM initialize
                 position_manager.initialize(
                     operation_mode=operation_mode,
                     initial_real_state=initial_real_state,
                     # instance_capital_override ya no se pasa
                     base_position_size_usdt_param=base_position_size_usdt,
                     initial_max_logical_positions_param=initial_max_logical_positions
                 )
                 print("  -> Position Manager inicializado vía Event Processor.")
             except Exception as e_pm_init:
                 print(f"ERROR CRÍTICO [Event Proc]: Falló la inicialización de position_manager: {e_pm_init}")
                 traceback.print_exc()
                 print("  -> Desactivando gestión de posiciones debido a error de inicialización.")
                 setattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
                 pm_enabled = False
        elif not position_manager:
             print("ERROR CRÍTICO [Event Proc]: POSITION_MANAGEMENT_ENABLED=True pero position_manager no importado."); setattr(config, 'POSITION_MANAGEMENT_ENABLED', False); pm_enabled = False
        elif not hasattr(position_manager, 'initialize'):
             print("ERROR CRÍTICO [Event Proc]: position_manager cargado pero sin método 'initialize'."); setattr(config, 'POSITION_MANAGEMENT_ENABLED', False); pm_enabled = False
    else: print("INFO [Event Proc]: Gestión de posiciones desactivada. No se inicializará PM.")

    print("[Event Processor] Inicializado.")


# --- Procesamiento Principal de Evento ---
def process_event(intermediate_ticks_info: list, final_price_info: dict):
    """
    Función principal: TA -> Señal -> Gestión Posiciones (Live/BT) -> Log/Print -> Incr Cooldown.
    (El cuerpo de esta función se mantiene igual que la versión anterior que me proporcionaste,
     ya que los cambios de lógica de capital afectan la inicialización y cómo PM decide
     el tamaño de la posición, no cómo EP procesa el tick en sí).
    """
    global _previous_raw_event_price, _is_first_event
    global position_manager

    if not ta_manager or not signal_generator or not utils or not config:
        print("ERROR CRÍTICO [EP Process]: Faltan módulos esenciales. Imposible procesar evento."); return

    if not final_price_info: print("WARN [EP Process]: Evento final vacío."); return
    current_timestamp = final_price_info.get("timestamp")
    current_price = utils.safe_float_convert(final_price_info.get("price"), default=np.nan)
    if not isinstance(current_timestamp, (datetime.datetime, pd.Timestamp)) or pd.isna(current_price) or current_price <= 0:
        print(f"WARN [EP Process]: Timestamp/Precio inválido. Saltando. TS:{current_timestamp}, P:{current_price}"); return

    increment = 0; decrement = 0
    if not _is_first_event and pd.notna(_previous_raw_event_price):
        if current_price > _previous_raw_event_price + 1e-9: increment = 1
        elif current_price < _previous_raw_event_price - 1e-9: decrement = 1
    _is_first_event = False

    raw_price_event = {'timestamp': current_timestamp, 'price': current_price, 'increment': increment, 'decrement': decrement}
    if getattr(config, 'PRINT_RAW_EVENT_ALWAYS', False): print(f"DEBUG [Raw Event]: {raw_price_event}")

    processed_data = None
    if getattr(config, 'TA_CALCULATE_PROCESSED_DATA', True):
        try: processed_data = ta_manager.process_raw_price_event(raw_price_event.copy())
        except Exception as e_ta: print(f"ERROR [TA Call]: {e_ta}"); traceback.print_exc()

    signal_data = None; price_fmt_config = f".{config.PRICE_PRECISION}f" if hasattr(config, 'PRICE_PRECISION') else ".8f"; price_fmt = f"{current_price:{price_fmt_config}}"; ts_fmt = utils.format_datetime(current_timestamp); nan_fmt = "NaN"
    base_signal_dict = {"timestamp": ts_fmt, "price_float": current_price, "price": price_fmt, "ema": nan_fmt, "inc_price_change_pct": nan_fmt, "dec_price_change_pct": nan_fmt, "weighted_increment": nan_fmt, "weighted_decrement": nan_fmt}
    try:
        if getattr(config, 'STRATEGY_ENABLED', True):
            if processed_data: signal_data = signal_generator.generate_signal(processed_data.copy())
            else: signal_data = {**base_signal_dict, "signal": "HOLD_NO_TA", "signal_reason": "No TA data"}
        else: signal_data = {**base_signal_dict, "signal": "HOLD_STRATEGY_DISABLED", "signal_reason": "Strategy disabled"}
    except Exception as e_signal: print(f"ERROR [Signal Gen Call]: {e_signal}"); traceback.print_exc(); signal_data = {**base_signal_dict, "signal": "HOLD_SIGNAL_ERROR", "signal_reason": f"Error: {e_signal}"}

    pm_enabled_runtime = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    if pm_enabled_runtime:
        if position_manager:
            pm_initialized_runtime = getattr(position_manager, '_initialized', False)
            if pm_initialized_runtime:
                try:
                    if hasattr(position_manager, 'check_and_close_positions'): position_manager.check_and_close_positions(current_price, current_timestamp)
                    else: print("ERROR CRÍTICO [EP Process]: PM sin 'check_and_close_positions'.")
                    if signal_data and hasattr(position_manager, 'open_logical_position'):
                        signal = signal_data.get("signal")
                        if signal == "BUY": position_manager.open_logical_position('long', current_price, current_timestamp)
                        elif signal == "SELL": position_manager.open_logical_position('short', current_price, current_timestamp)
                    elif signal_data and not hasattr(position_manager, 'open_logical_position'): print("ERROR CRÍTICO [EP Process]: PM sin 'open_logical_position'.")
                except Exception as pm_err: print(f"ERROR [PM Call]: {pm_err}"); traceback.print_exc()
            else: print("WARN [EP Process]: PM habilitado pero no inicializado.")
        else: print("ERROR CRÍTICO [EP Process]: PM habilitado pero instancia es None.")

    if signal_data:
        if signal_logger and getattr(config, 'LOG_SIGNAL_OUTPUT', False):
            try:
                if hasattr(signal_logger, 'log_signal_event'): signal_logger.log_signal_event(signal_data.copy());
                else: print("WARN [EP Process]: signal_logger sin 'log_signal_event'.")
            except Exception as e_log_write: print(f"ERROR [Signal Log Write]: {e_log_write}")
        if getattr(config, 'PRINT_SIGNAL_OUTPUT', False):
            try: print(json.dumps(signal_data, indent=2));
            except Exception as e_print_signal: print(f"ERROR [Print Signal]: {e_print_signal}\nData: {signal_data}")

    _previous_raw_event_price = current_price

    pm_initialized_runtime_cooldown = getattr(position_manager, '_initialized', False) if position_manager else False
    if pm_enabled_runtime and position_manager and pm_initialized_runtime_cooldown and getattr(config, 'POSITION_SIGNAL_COOLDOWN_ENABLED', False):
        try:
            if hasattr(position_manager, 'increment_event_counters'): position_manager.increment_event_counters()
            else: print("ERROR [EP Process]: PM sin 'increment_event_counters'.")
        except Exception as cd_err: print(f"ERROR incrementando cooldown: {cd_err}"); traceback.print_exc()

    pm_initialized_runtime_print = getattr(position_manager, '_initialized', False) if position_manager else False
    if _operation_mode.startswith('live') and getattr(config, 'PRINT_TICK_LIVE_STATUS', False):
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
            if pm_enabled_runtime and position_manager and pm_initialized_runtime_print and hasattr(position_manager, 'get_position_summary'):
                summary = position_manager.get_position_summary()
                if summary and 'error' not in summary:
                    max_p = summary.get('max_logical_positions',0); lc = summary.get('open_long_positions_count', 0); sc = summary.get('open_short_positions_count', 0); al = summary.get('available_long_margin', 0.0); ul = summary.get('used_long_margin_logical', 0.0); as_val = summary.get('available_short_margin', 0.0); us_val = summary.get('used_short_margin_logical', 0.0); pb = summary.get('profit_balance', 0.0); pnl_l = summary.get('total_realized_pnl_long', 0.0); pnl_s = summary.get('total_realized_pnl_short', 0.0); tf = summary.get('total_transferred_profit', 0.0);
                    print(f"    Longs: {lc}/{max_p} Shorts: {sc}/{max_p}"); print(f"    Margen Disp(L): {al:<15.4f} Usado(L): {ul:<15.4f}"); print(f"    Margen Disp(S): {as_val:<15.4f} Usado(S): {us_val:<15.4f}"); print(f"    Balance Profit: {pb:<15.4f} PNL Neto(L): {pnl_l:<+15.4f}"); print(f"    Transferido:    {tf:<15.4f} PNL Neto(S): {pnl_s:<+15.4f}");
                    
                    liq_price_fmt_str = f".{config.PRICE_PRECISION}f" if hasattr(config, 'PRICE_PRECISION') else ".2f"
                    qty_fmt_str = f".{config.DEFAULT_QTY_PRECISION}f" if hasattr(config, 'DEFAULT_QTY_PRECISION') else ".3f"

                    # --- Para LONGS ---
                    open_longs = summary.get('open_long_positions', [])
                    avg_liq_price_long_str = "N/A"
                    if lc > 0 and open_longs:
                        pos_details = []
                        total_liq_price_weighted_sum_long = 0.0
                        total_size_long = 0.0
                        valid_liq_prices_long = 0
                        for p in open_longs:
                            pos_id_short = "..." + str(p.get('id', 'N/A'))[-6:]
                            entry_p_val = utils.safe_float_convert(p.get('entry_price'))
                            entry_p_str = f"{entry_p_val:{liq_price_fmt_str}}" if pd.notna(entry_p_val) else "N/A"
                            liq_p_val = utils.safe_float_convert(p.get('liq_price'))
                            liq_p_str = f"{liq_p_val:{liq_price_fmt_str}}" if pd.notna(liq_p_val) else "N/A"
                            pos_size_val = utils.safe_float_convert(p.get('size_contracts'))
                            size_str_print = f"{pos_size_val:{qty_fmt_str}}" if pd.notna(pos_size_val) else "N/A"
                            pos_details.append(f"ID:{pos_id_short}(Ent:{entry_p_str} LiqP:{liq_p_str} Sz:{size_str_print})")
                            if pd.notna(liq_p_val) and pd.notna(pos_size_val) and pos_size_val > 0:
                                total_liq_price_weighted_sum_long += liq_p_val * pos_size_val
                                total_size_long += pos_size_val
                                valid_liq_prices_long += 1
                        print(f"    Open Longs Det: {', '.join(pos_details)}")
                        if total_size_long > 0:
                            avg_liq_price_long = total_liq_price_weighted_sum_long / total_size_long
                            avg_liq_price_long_str = f"{avg_liq_price_long:{liq_price_fmt_str}}"
                        elif valid_liq_prices_long > 0: avg_liq_price_long_str = "Error Promedio (Tamaño 0)"
                    elif lc > 0: print(f"    Open Longs    : {lc} (Detalles no disponibles)")
                    print(f"    Avg LiqP Long : {avg_liq_price_long_str}")

                    # --- Para SHORTS ---
                    open_shorts = summary.get('open_short_positions', [])
                    avg_liq_price_short_str = "N/A"
                    if sc > 0 and open_shorts:
                        pos_details_short = []
                        total_liq_price_weighted_sum_short = 0.0
                        total_size_short = 0.0
                        valid_liq_prices_short = 0
                        for p_short in open_shorts:
                            pos_id_short_s = "..." + str(p_short.get('id', 'N/A'))[-6:]
                            entry_p_val_s = utils.safe_float_convert(p_short.get('entry_price'))
                            entry_p_str_s = f"{entry_p_val_s:{liq_price_fmt_str}}" if pd.notna(entry_p_val_s) else "N/A"
                            liq_p_val_s = utils.safe_float_convert(p_short.get('liq_price'))
                            liq_p_str_s = f"{liq_p_val_s:{liq_price_fmt_str}}" if pd.notna(liq_p_val_s) else "N/A"
                            pos_size_val_s = utils.safe_float_convert(p_short.get('size_contracts'))
                            size_str_print_s = f"{pos_size_val_s:{qty_fmt_str}}" if pd.notna(pos_size_val_s) else "N/A"
                            pos_details_short.append(f"ID:{pos_id_short_s}(Ent:{entry_p_str_s} LiqP:{liq_p_str_s} Sz:{size_str_print_s})")
                            if pd.notna(liq_p_val_s) and pd.notna(pos_size_val_s) and pos_size_val_s > 0:
                                total_liq_price_weighted_sum_short += liq_p_val_s * pos_size_val_s
                                total_size_short += pos_size_val_s
                                valid_liq_prices_short +=1
                        print(f"    Open Shorts Det: {', '.join(pos_details_short)}")
                        if total_size_short > 0:
                            avg_liq_price_short = total_liq_price_weighted_sum_short / total_size_short
                            avg_liq_price_short_str = f"{avg_liq_price_short:{liq_price_fmt_str}}"
                        elif valid_liq_prices_short > 0 : avg_liq_price_short_str = "Error Promedio (Tamaño 0)"
                    elif sc > 0: print(f"    Open Shorts   : {sc} (Detalles no disponibles)")
                    print(f"    Avg LiqP Short: {avg_liq_price_short_str}")

                elif summary and 'error' in summary: print(f"    Error resumen PM: {summary.get('error', 'N/A')}")
                else: print(f"    Error resumen PM (Respuesta inválida).")
            elif pm_enabled_runtime and position_manager and not pm_initialized_runtime_print: print("    (PM no inicializado)")
            else: print("    (Gestión desactivada o PM no disponible)")
            print("=" * len(hdr))
        except Exception as e_print: print(f"ERROR [Print Tick Status]: {e_print}"); traceback.print_exc()

# =============== FIN ARCHIVO: core/strategy/event_processor.py (v8.7.x - Nueva Lógica Capital) ===============