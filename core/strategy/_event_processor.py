"""
Orquestador Principal del Procesamiento de Eventos.

v4.0 (Arquitectura de Controladores):
- Este módulo ha absorbido toda la lógica del antiguo paquete 'workflow'.
- Ahora contiene de forma cohesiva todo el flujo de procesamiento de un tick:
  1. Comprobación de triggers de la operación.
  2. Procesamiento de datos y generación de señal de bajo nivel.
  3. Interacción con el Position Manager.
  4. Comprobación de los límites globales de la sesión (disyuntores).
- Se elimina la dependencia con el paquete 'workflow', que queda obsoleto.
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
    from core.strategy import pm as pm_api
    from core.strategy import om as om_api
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

# --- Lógica de _limit_checks ---
class GlobalStopLossException(Exception):
    """Excepción para ser lanzada cuando se activa el Global Stop Loss."""
    pass

_global_stop_loss_triggered = False

def initialize_limit_checks():
    global _global_stop_loss_triggered
    _global_stop_loss_triggered = False

def has_global_stop_loss_triggered() -> bool:
    return _global_stop_loss_triggered

# --- Lógica de _data_processing ---
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
    
    # Inicializar estados internos absorbidos de 'workflow'
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
        # 1. Comprobar Triggers de la Operación (lógica de _triggers)
        check_conditional_triggers(current_price, current_timestamp)

        # 2. Procesar datos y generar señal de bajo nivel (lógica de _data_processing)
        signal_data = _process_tick_and_generate_signal(current_timestamp, current_price)
        
        # 3. Interacción con el Position Manager
        _pm_instance.check_and_close_positions(current_price, current_timestamp)
        _pm_instance.handle_low_level_signal(
            signal=signal_data.get("signal", "HOLD"),
            entry_price=current_price,
            timestamp=current_timestamp
        )

        # 4. Comprobar Límites de Sesión (Disyuntores Globales) (lógica de _limit_checks)
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

# --- Funciones de _triggers.py ---
def check_conditional_triggers(current_price: float, timestamp: datetime.datetime):
    if not (pm_api and pm_api.api.is_initialized() and om_api and om_api.api.is_initialized()):
        return

    try:
        operacion = om_api.api.get_operation()
        if not operacion: return

        if operacion.estado == 'EN_ESPERA':
            condition_met, reason = _evaluate_entry_condition(operacion, current_price)
            if condition_met:
                memory_logger.log(f"CONDICIÓN DE ENTRADA CUMPLIDA: {reason}", "INFO")
                om_api.api.force_start_operation()

        elif operacion.estado == 'ACTIVA':
            condition_met, reason = _evaluate_exit_conditions(operacion, current_price)
            if condition_met:
                memory_logger.log(f"CONDICIÓN DE SALIDA CUMPLIDA: {reason}", "INFO")
                om_api.api.force_stop_operation()
    except Exception as e:
        memory_logger.log(f"ERROR CRÍTICO [Check Triggers]: {e}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")

def _evaluate_entry_condition(operacion: 'Operacion', current_price: float) -> Tuple[bool, str]:
    cond_type, cond_value = operacion.tipo_cond_entrada, operacion.valor_cond_entrada
    if cond_type == 'MARKET': return True, "Activación inmediata (Market)"
    if cond_value is None: return False, ""
    if cond_type == 'PRICE_ABOVE' and current_price > cond_value: return True, f"Precio ({current_price:.4f}) > ({cond_value:.4f})"
    if cond_type == 'PRICE_BELOW' and current_price < cond_value: return True, f"Precio ({current_price:.4f}) < ({cond_value:.4f})"
    return False, ""

def _evaluate_exit_conditions(operacion: 'Operacion', current_price: float) -> Tuple[bool, str]:
    summary = pm_api.api.get_position_summary()
    if summary and 'error' not in summary:
        roi = summary.get('operation_roi', 0.0)
        if operacion.tp_roi_pct is not None and roi >= operacion.tp_roi_pct: return True, f"TP-ROI alcanzado ({roi:.2f}%)"
        if operacion.sl_roi_pct is not None and roi <= operacion.sl_roi_pct: return True, f"SL-ROI alcanzado ({roi:.2f}%)"
    
    if operacion.max_comercios is not None and operacion.comercios_cerrados_contador >= operacion.max_comercios: return True, f"Límite de {operacion.max_comercios} trades"
    
    start_time = operacion.tiempo_inicio_ejecucion
    if operacion.tiempo_maximo_min is not None and start_time:
        elapsed_min = (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds() / 60.0
        if elapsed_min >= operacion.tiempo_maximo_min: return True, f"Límite de tiempo ({operacion.tiempo_maximo_min} min)"
            
    exit_type, exit_value = operacion.tipo_cond_salida, operacion.valor_cond_salida
    if exit_type and exit_value is not None:
        if exit_type == 'PRICE_ABOVE' and current_price > exit_value: return True, f"Precio de salida ({current_price:.4f}) > ({exit_value:.4f})"
        if exit_type == 'PRICE_BELOW' and current_price < exit_value: return True, f"Precio de salida ({current_price:.4f}) < ({exit_value:.4f})"
    
    return False, ""

# --- Funciones de _data_processing.py ---
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

# --- Funciones de _limit_checks.py ---
def _check_session_limits(current_price: float, timestamp: datetime.datetime, op_mode: str, stop_event: Optional[threading.Event]):
    global _global_stop_loss_triggered
    if not (pm_api and pm_api.api.is_initialized()) or _global_stop_loss_triggered: return

    # Lógica de límite de tiempo de sesión
    time_limit_cfg = pm_api.api.get_session_time_limit()
    max_minutes, action = time_limit_cfg.get("duration", 0), time_limit_cfg.get("action", "NEUTRAL").upper()
    start_time = pm_api.api.get_session_start_time()
    if start_time and max_minutes > 0:
        elapsed_minutes = (timestamp - start_time).total_seconds() / 60.0
        if elapsed_minutes >= max_minutes:
            if action == "STOP":
                _global_stop_loss_triggered = True
                msg = f"LÍMITE DE TIEMPO DE SESIÓN (STOP) ALCANZADO ({elapsed_minutes:.2f} >= {max_minutes} min)"
                memory_logger.log(msg, "ERROR")
                pm_api.api.close_all_logical_positions('long', "TIME_LIMIT_STOP")
                pm_api.api.close_all_logical_positions('short', "TIME_LIMIT_STOP")
                if stop_event: stop_event.set()
                raise GlobalStopLossException(msg)
            elif not pm_api.api.is_session_tp_hit():
                memory_logger.log(f"LÍMITE DE TIEMPO DE SESIÓN (NEUTRAL) ALCANZADO", "INFO")
                # El PM ahora es responsable de cambiar su estado interno a "neutral"
                # pm_api.api.set_session_tp_hit(True)

    # Lógica de límites de ROI de sesión
    summary = pm_api.api.get_position_summary()
    initial_capital = summary.get('initial_total_capital', 0.0)
    if initial_capital < 1e-9: return

    unrealized_pnl = pm_api.api.get_unrealized_pnl(current_price)
    realized_pnl = summary.get('total_realized_pnl_session', 0.0)
    current_roi = utils.safe_division(realized_pnl + unrealized_pnl, initial_capital) * 100.0

    if getattr(config, 'SESSION_ROI_TP_ENABLED', False) and not pm_api.api.is_session_tp_hit():
        tp_pct = pm_api.api.get_global_tp_pct()
        if tp_pct and tp_pct > 0 and current_roi >= tp_pct:
            memory_logger.log(f"TAKE PROFIT GLOBAL DE SESIÓN ALCANZADO ({current_roi:.2f}% >= {tp_pct}%)", "INFO")
            # pm_api.api.set_session_tp_hit(True)

    if getattr(config, 'SESSION_ROI_SL_ENABLED', False):
        sl_pct = pm_api.api.get_global_sl_pct()
        if sl_pct and sl_pct > 0 and current_roi <= -abs(sl_pct):
            _global_stop_loss_triggered = True
            msg = f"STOP LOSS GLOBAL DE SESIÓN POR ROI ALCANZADO ({current_roi:.2f}% <= {-abs(sl_pct)}%)"
            memory_logger.log(msg, "ERROR")
            pm_api.api.close_all_logical_positions('long', "GLOBAL_SL_ROI")
            pm_api.api.close_all_logical_positions('short', "GLOBAL_SL_ROI")
            if stop_event: stop_event.set()
            raise GlobalStopLossException(msg)

# --- Función de Ayuda para Impresión en Consola ---
def _print_tick_status_to_console(signal_data: Dict, timestamp: datetime.datetime, price: float):
    if _operation_mode.startswith(('live')) and getattr(config, 'PRINT_TICK_LIVE_STATUS', False):
        try:
            ts_str = utils.format_datetime(timestamp)
            price_prec = getattr(config, 'PRICE_PRECISION', 4)
            price_str = f"{price:.{price_prec}f}"
            
            summary = pm_api.api.get_position_summary()
            op_status = summary.get('operation_status', {})
            op_tendencia = op_status.get('tendencia', 'NEUTRAL')
            max_pos = op_status.get('max_posiciones_logicas', 'N/A')
            
            hdr = f" TICK @ {ts_str} | Precio: {price_str} | Op: {op_tendencia} "
            print("\n" + f"{hdr:=^80}")
            print(f"  TA:  EMA={signal_data.get('ema', 'N/A'):<15} W.Inc={signal_data.get('weighted_increment', 'N/A'):<8} W.Dec={signal_data.get('weighted_decrement', 'N/A'):<8}")
            print(f"  SIG: {signal_data.get('signal', 'N/A'):<15} | Razón: {signal_data.get('signal_reason', 'N/A')}")
            if summary and 'error' not in summary:
                print(f"  POS: Longs={summary.get('open_long_positions_count', 0)}/{max_pos} | Shorts={summary.get('open_short_positions_count', 0)}/{max_pos} | PNL Sesión: {summary.get('total_realized_pnl_session', 0.0):+.4f} USDT")
            else:
                print(f"  POS: Error obteniendo resumen del PM: {summary.get('error', 'N/A')}")
            print("=" * 80)
        except Exception as e:
            print(f"ERROR [Print Tick Status]: {e}")