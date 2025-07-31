"""
Orquestador Principal del Procesamiento de Eventos.

v7.2 (Corrección de Imports y ROI):
- Se corrige la importación de `om_api` y `pm_api` para que apunten a los
  módulos de API (`.api`) en lugar de a los paquetes, solucionando el
  AttributeError en `is_initialized`.
- Se refactoriza la lógica de salida en `_check_operation_triggers` para
  calcular el ROI de cada operación (side) de forma independiente, asegurando
  que los límites de TP/SL por operación funcionen correctamente.
"""
import sys
import os
import datetime
import traceback
import pandas as pd
import numpy as np
import threading
from typing import Optional, Dict, Any, TYPE_CHECKING, Tuple

# --- Dependencias de Tipado ---
if TYPE_CHECKING:
    from core.strategy.pm import PositionManager
    from core.strategy.om._entities import Operacion

# --- Importaciones Adaptadas ---
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

try:
    import config
    from core import utils
    from core.logging import memory_logger, signal_logger
    # --- IMPORTACIÓN CORREGIDA ---
    from core.strategy.pm import api as pm_api
    from core.strategy.om import api as om_api
    from core.strategy import ta, signal
except ImportError as e:
    print(f"ERROR CRÍTICO [Event Proc Import]: Falló importación: {e}")
    # Definir stubs para que el resto del archivo se pueda analizar
    config=utils=memory_logger=signal_logger=pm_api=om_api=ta=signal=None
    traceback.print_exc()
    sys.exit(1)


# ==============================================================================
# --- ESTADO Y LÓGICA ABSORBIDOS DE WORKFLOW ---
# ==============================================================================

class GlobalStopLossException(Exception):
    """Excepción para ser lanzada cuando se activa el Global Stop Loss."""
    pass

_global_stop_loss_triggered = False

def initialize_limit_checks():
    global _global_stop_loss_triggered
    _global_stop_loss_triggered = False

def has_global_stop_loss_triggered() -> bool:
    return _global_stop_loss_triggered

_previous_raw_event_price = np.nan
_is_first_event = True

def initialize_data_processing():
    global _previous_raw_event_price, _is_first_event
    _previous_raw_event_price = np.nan
    _is_first_event = True

# ==============================================================================
# --- ESTADO PRINCIPAL DEL EVENT PROCESSOR ---
# ==============================================================================
_operation_mode = "unknown"
_global_stop_loss_event: Optional[threading.Event] = None
_pm_instance: Optional['PositionManager'] = None


# ==============================================================================
# --- FUNCIONES PRINCIPALES DEL MÓDULO ---
# ==============================================================================

def initialize(
    operation_mode: str,
    pm_instance: 'PositionManager',
    global_stop_loss_event: Optional[threading.Event] = None
):
    """
    Inicializa el orquestador de eventos y sus componentes lógicos internos.
    """
    global _operation_mode, _global_stop_loss_event, _pm_instance

    if not all([config, utils, ta, signal, memory_logger, pm_api, om_api]):
        raise RuntimeError("Event Processor no pudo inicializarse por dependencias faltantes.")

    memory_logger.log("Event Processor: Inicializando orquestador...", level="INFO")
    _operation_mode = operation_mode
    _global_stop_loss_event = global_stop_loss_event
    _pm_instance = pm_instance
    
    initialize_data_processing()
    initialize_limit_checks()
    ta.initialize()
    
    memory_logger.log("Event Processor: Orquestador inicializado.", level="INFO")


def process_event(intermediate_ticks_info: list, final_price_info: dict):
    """
    Orquesta el flujo de trabajo completo para procesar un único evento de precio.
    """
    if not _pm_instance or has_global_stop_loss_triggered():
        return

    if not final_price_info:
        memory_logger.log("Evento de precio final vacío, saltando tick.", level="WARN")
        return

    current_timestamp = final_price_info.get("timestamp")
    current_price = utils.safe_float_convert(final_price_info.get("price"), default=np.nan)
    if not isinstance(current_timestamp, (datetime.datetime, pd.Timestamp)) or pd.isna(current_price) or current_price <= 0:
        memory_logger.log(f"Timestamp/Precio inválido. Saltando. TS:{current_timestamp}, P:{current_price}", level="WARN")
        return

    try:
        # 1. Comprobar Triggers de la Operación (lógica de activación/desactivación automática)
        _check_operation_triggers(current_price)

        # 2. Procesar datos y generar señal de bajo nivel
        signal_data = _process_tick_and_generate_signal(current_timestamp, current_price)
        
        # 3. Interacción con el Position Manager
        if _pm_instance:
            _pm_instance.check_and_close_positions(current_price, current_timestamp)
            _pm_instance.handle_low_level_signal(
                signal=signal_data.get("signal", "HOLD"),
                entry_price=current_price,
                timestamp=current_timestamp
            )

        # 4. Comprobar Límites de Sesión (Disyuntores Globales)
        _check_session_limits(current_price, current_timestamp, _operation_mode, _global_stop_loss_event)
        
        # 5. Imprimir estado en consola
        _print_tick_status_to_console(signal_data, current_timestamp, current_price)

    except GlobalStopLossException as e:
        memory_logger.log(f"GlobalStopLossException capturada en Event Processor: {e}", level="ERROR")
    except Exception as e:
        memory_logger.log(f"ERROR INESPERADO en el flujo de trabajo de process_event: {e}", level="ERROR")
        memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")


# ==============================================================================
# --- LÓGICA DE WORKFLOW AHORA INTEGRADA LOCALMENTE ---
# ==============================================================================

def _check_operation_triggers(current_price: float):
    """
    Evalúa las condiciones de entrada y salida para las operaciones en cada tick
    y llama a los métodos del OM para transicionar el estado.
    """
    if not (om_api and om_api.is_initialized() and pm_api and pm_api.is_initialized()):
        return

    try:
        for side in ['long', 'short']:
            operacion = om_api.get_operation_by_side(side)
            if not operacion:
                continue

            # --- LÓGICA DE ENTRADA (si la operación está esperando) ---
            if operacion.estado == 'EN_ESPERA':
                cond_type = operacion.tipo_cond_entrada
                cond_value = operacion.valor_cond_entrada
                
                entry_condition_met = False
                
                if cond_type == 'MARKET':
                    entry_condition_met = True
                elif cond_value is not None:
                    if cond_type == 'PRICE_ABOVE' and current_price > cond_value:
                        entry_condition_met = True
                    elif cond_type == 'PRICE_BELOW' and current_price < cond_value:
                        entry_condition_met = True
                
                if entry_condition_met:
                    om_api.activar_por_condicion(side)

            # --- LÓGICA DE SALIDA (si la operación está activa) ---
            elif operacion.estado == 'ACTIVA':
                exit_condition_met = False
                reason = ""
                
                summary = pm_api.get_position_summary()
                if summary and 'error' not in summary:
                    unrealized_pnl_side = 0.0
                    open_positions_side = summary.get(f'open_{side}_positions', [])
                    for pos in open_positions_side:
                        entry = pos.get('entry_price', 0.0)
                        size = pos.get('size_contracts', 0.0)
                        if side == 'long': unrealized_pnl_side += (current_price - entry) * size
                        else: unrealized_pnl_side += (entry - current_price) * size
                    
                    realized_pnl_side = operacion.pnl_realizado_usdt
                    total_pnl_side = realized_pnl_side + unrealized_pnl_side
                    initial_capital_side = operacion.capital_inicial_usdt
                    
                    roi = (total_pnl_side / initial_capital_side) * 100 if initial_capital_side > 0 else 0.0

                    # --- INICIO DE LA MODIFICACIÓN: Lógica de TSL por ROI ---
                    if operacion.tsl_roi_activacion_pct is not None and operacion.tsl_roi_distancia_pct is not None:
                        if not operacion.tsl_roi_activo and roi >= operacion.tsl_roi_activacion_pct:
                            operacion.tsl_roi_activo = True
                            operacion.tsl_roi_peak_pct = roi
                            memory_logger.log(
                                f"TSL-ROI para Operación {side.upper()} ACTIVADO. ROI actual: {roi:.2f}%, "
                                f"Pico inicial: {operacion.tsl_roi_peak_pct:.2f}%", "INFO"
                            )
                        if operacion.tsl_roi_activo:
                            if roi > operacion.tsl_roi_peak_pct:
                                operacion.tsl_roi_peak_pct = roi
                            
                            umbral_disparo = operacion.tsl_roi_peak_pct - operacion.tsl_roi_distancia_pct
                            if roi <= umbral_disparo:
                                exit_condition_met = True
                                reason = f"TSL-ROI disparado (Pico: {operacion.tsl_roi_peak_pct:.2f}%, Actual: {roi:.2f}%)"
                    # --- FIN DE LA MODIFICACIÓN ---

                    if not exit_condition_met and operacion.sl_roi_pct is not None and roi <= -abs(operacion.sl_roi_pct):
                        exit_condition_met, reason = True, f"SL-ROI alcanzado ({roi:.2f}%)"

                if not exit_condition_met and operacion.max_comercios is not None and operacion.comercios_cerrados_contador >= operacion.max_comercios:
                    exit_condition_met, reason = True, f"Límite de {operacion.max_comercios} trades"
                
                start_time = operacion.tiempo_inicio_ejecucion
                if not exit_condition_met and operacion.tiempo_maximo_min is not None and start_time:
                    elapsed_min = (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds() / 60.0
                    if elapsed_min >= operacion.tiempo_maximo_min:
                        exit_condition_met, reason = True, f"Límite de tiempo ({operacion.tiempo_maximo_min} min)"

                exit_type, exit_value = operacion.tipo_cond_salida, operacion.valor_cond_salida
                if not exit_condition_met and exit_type and exit_value is not None:
                    if exit_type == 'PRICE_ABOVE' and current_price > exit_value:
                        exit_condition_met, reason = True, f"Precio de salida ({current_price:.4f}) > ({exit_value:.4f})"
                    elif exit_type == 'PRICE_BELOW' and current_price < exit_value:
                        exit_condition_met, reason = True, f"Precio de salida ({current_price:.4f}) < ({exit_value:.4f})"

                if exit_condition_met:
                    accion_final = operacion.accion_al_finalizar
                    log_msg = (
                        f"CONDICIÓN DE SALIDA CUMPLIDA ({side.upper()}): {reason}. "
                        f"Acción configurada: {accion_final.upper()}"
                    )
                    memory_logger.log(log_msg, "WARN")
                    if accion_final == 'PAUSAR':
                        om_api.pausar_operacion(side)
                    elif accion_final == 'DETENER':
                        om_api.detener_operacion(side, forzar_cierre_posiciones=True)
                    else:
                        memory_logger.log(f"WARN: Acción al finalizar '{accion_final}' desconocida. Se PAUSARÁ por seguridad.", "WARN")
                        om_api.pausar_operacion(side)

    except Exception as e:
        memory_logger.log(f"ERROR CRÍTICO [Check Triggers]: {e}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")


def _process_tick_and_generate_signal(timestamp: datetime.datetime, price: float) -> Dict[str, Any]:
    global _previous_raw_event_price, _is_first_event
    increment, decrement = 0, 0
    if not _is_first_event and pd.notna(_previous_raw_event_price):
        if price > _previous_raw_event_price: increment = 1
        elif price < _previous_raw_event_price: decrement = 1
    _is_first_event = False

    raw_event = {'timestamp': timestamp, 'price': price, 'increment': increment, 'decrement': decrement}
    processed_data = ta.process_raw_price_event(raw_event) if getattr(config, 'TA_CALCULATE_PROCESSED_DATA', True) else None
    
    signal_data = signal.generate_signal(processed_data) if processed_data else {"signal": "HOLD_NO_TA"}
    
    if signal_logger and getattr(config, 'LOG_SIGNAL_OUTPUT', False):
        signal_logger.log_signal_event(signal_data.copy())
    
    _previous_raw_event_price = price
    return signal_data


def _check_session_limits(current_price: float, timestamp: datetime.datetime, op_mode: str, stop_event: Optional[threading.Event]):
    global _global_stop_loss_triggered
    if not (pm_api and pm_api.is_initialized()) or _global_stop_loss_triggered: return

    time_limit_cfg = pm_api.get_session_time_limit()
    max_minutes, action = time_limit_cfg.get("duration", 0), time_limit_cfg.get("action", "NEUTRAL").upper()
    start_time = pm_api.get_session_start_time()
    if start_time and max_minutes > 0:
        elapsed_minutes = (timestamp - start_time).total_seconds() / 60.0
        if elapsed_minutes >= max_minutes:
            if action == "STOP":
                _global_stop_loss_triggered = True
                msg = f"LÍMITE DE TIEMPO DE SESIÓN (STOP) ALCANZADO ({elapsed_minutes:.2f} >= {max_minutes} min)"
                memory_logger.log(msg, "ERROR")
                pm_api.close_all_logical_positions('long', "TIME_LIMIT_STOP")
                pm_api.close_all_logical_positions('short', "TIME_LIMIT_STOP")
                if stop_event: stop_event.set()
                raise GlobalStopLossException(msg)
            elif not pm_api.is_session_tp_hit():
                memory_logger.log(f"LÍMITE DE TIEMPO DE SESIÓN (NEUTRAL) ALCANZADO", "INFO")

    summary = pm_api.get_position_summary()
    initial_capital = summary.get('initial_total_capital', 0.0)
    if initial_capital < 1e-9: return

    unrealized_pnl = pm_api.get_unrealized_pnl(current_price)
    realized_pnl = summary.get('total_realized_pnl_session', 0.0)
    current_roi = utils.safe_division(realized_pnl + unrealized_pnl, initial_capital) * 100.0

    if getattr(config, 'SESSION_ROI_TP_ENABLED', False) and not pm_api.is_session_tp_hit():
        tp_pct = pm_api.get_global_tp_pct()
        if tp_pct and tp_pct > 0 and current_roi >= tp_pct:
            memory_logger.log(f"TAKE PROFIT GLOBAL DE SESIÓN ALCANZADO ({current_roi:.2f}% >= {tp_pct}%)", "INFO")

    if getattr(config, 'SESSION_ROI_SL_ENABLED', False):
        sl_pct = pm_api.get_global_sl_pct()
        if sl_pct and sl_pct > 0 and current_roi <= -abs(sl_pct):
            _global_stop_loss_triggered = True
            msg = f"STOP LOSS GLOBAL DE SESIÓN POR ROI ALCANZADO ({current_roi:.2f}% <= {-abs(sl_pct)}%)"
            memory_logger.log(msg, "ERROR")
            pm_api.close_all_logical_positions('long', "GLOBAL_SL_ROI")
            pm_api.close_all_logical_positions('short', "GLOBAL_SL_ROI")
            if stop_event: stop_event.set()
            raise GlobalStopLossException(msg)


def _print_tick_status_to_console(signal_data: Dict, timestamp: datetime.datetime, price: float):
    if _operation_mode.startswith(('live')) and getattr(config, 'PRINT_TICK_LIVE_STATUS', False):
        try:
            ts_str = utils.format_datetime(timestamp)
            price_prec = getattr(config, 'PRICE_PRECISION', 4)
            price_str = f"{price:.{price_prec}f}"
            
            summary = pm_api.get_position_summary()
            
            op_long = om_api.get_operation_by_side('long')
            op_short = om_api.get_operation_by_side('short')
            
            if not op_long or not op_short: return # Safety check

            def get_op_display(op):
                if op.estado == 'ACTIVA': return f"{op.tendencia}"
                return op.estado.upper()

            status_long = f"L: {get_op_display(op_long)}"
            status_short = f"S: {get_op_display(op_short)}"

            hdr = f" TICK @ {ts_str} | Precio: {price_str} | Ops: {status_long}, {status_short} "
            print("\n" + f"{hdr:=^80}")
            print(f"  TA:  EMA={signal_data.get('ema', 'N/A'):<15} W.Inc={signal_data.get('weighted_increment', 'N/A'):<8} W.Dec={signal_data.get('weighted_decrement', 'N/A'):<8}")
            print(f"  SIG: {signal_data.get('signal', 'N/A'):<15} | Razón: {signal_data.get('signal_reason', 'N/A')}")
            if summary and 'error' not in summary:
                max_pos_l = op_long.max_posiciones_logicas if op_long.estado != 'DETENIDA' else 'N/A'
                max_pos_s = op_short.max_posiciones_logicas if op_short.estado != 'DETENIDA' else 'N/A'
                print(f"  POS: Longs={summary.get('open_long_positions_count', 0)}/{max_pos_l} | Shorts={summary.get('open_short_positions_count', 0)}/{max_pos_s} | PNL Sesión: {summary.get('total_realized_pnl_session', 0.0):+.4f} USDT")
            else:
                print(f"  POS: Error obteniendo resumen del PM: {summary.get('error', 'N/A')}")
            print("=" * 80)
        except Exception as e:
            print(f"ERROR [Print Tick Status]: {e}")