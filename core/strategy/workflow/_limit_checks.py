# core/strategy/workflow/_limit_checks.py

"""
Módulo para la Comprobación de Límites y Disyuntores.

v3.0 (Refactor de Hitos):
- `check_trend_limits` se ha adaptado para leer los límites de finalización
  directamente desde la configuración de la tendencia activa en el Position Manager.

v4.0 (Modelo de Operaciones):
- La lógica de `check_trend_limits` ha sido movida a `_triggers.py`, ya que los
  límites de una operación son ahora condiciones de un Hito de Finalización.
  La función original se ha comentado para mantener la compatibilidad.
"""
import sys
import os
import datetime
import traceback
import threading
from typing import Dict, Any, Optional

if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

try:
    import config
    from core import utils
    from core.strategy import pm as position_manager
    from core.logging import memory_logger
except ImportError as e:
    print(f"ERROR [Workflow Limit Checks Import]: Falló importación de dependencias: {e}")
    config = None; utils = None; position_manager = None
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

class GlobalStopLossException(Exception):
    """Excepción para ser lanzada cuando se activa el Global Stop Loss."""
    pass

# _trend_limit_hit_reported = False # Comentado
_global_stop_loss_triggered = False

def initialize_limit_checks():
    """Resetea el estado interno del módulo de comprobación de límites."""
    # global _trend_limit_hit_reported, _global_stop_loss_triggered # Comentado
    global _global_stop_loss_triggered
    # _trend_limit_hit_reported = False # Comentado
    _global_stop_loss_triggered = False

def has_global_stop_loss_triggered() -> bool:
    """Informa si el SL global ya se ha activado en esta sesión."""
    return _global_stop_loss_triggered

# --- Lógica de Comprobación de Límites ---

# --- (COMENTADO) check_trend_limits ---
# La lógica de esta función ha sido absorbida por `_evaluate_milestone_conditions` en `_triggers.py`
# como parte de las condiciones de los Hitos de Finalización.
# def check_trend_limits(current_price: float, current_timestamp: datetime.datetime, operation_mode: str):
#     """Comprueba si se han alcanzado los límites de finalización de la tendencia activa."""
#     global _trend_limit_hit_reported
    
#     if not (position_manager and position_manager.api.is_initialized() and utils):
#         return

#     # Obtenemos el estado completo de la tendencia activa.
#     trend_state = position_manager.api.get_trend_state()
#     trend_mode = trend_state.get("mode")

#     # Si no hay tendencia activa (modo NEUTRAL) o el límite ya fue reportado, no hacemos nada.
#     if trend_mode == "NEUTRAL" or _trend_limit_hit_reported:
#         if trend_mode == "NEUTRAL" and _trend_limit_hit_reported:
#             _trend_limit_hit_reported = False # Reseteamos si vuelve a NEUTRAL
#         return

#     limit_reason = None
    
#     # Extraemos los límites de la configuración de la tendencia.
#     trend_config = trend_state.get('config', {})
#     trade_limit = trend_config.get("limit_trade_count")
#     duration_limit = trend_config.get("limit_duration_minutes")
#     tp_roi_limit = trend_config.get("limit_tp_roi_pct")
#     sl_roi_limit = trend_config.get("limit_sl_roi_pct")

#     # 1. Comprobar límite de trades
#     if trade_limit is not None and trend_state.get("trades_executed", 0) >= trade_limit:
#         limit_reason = f"Límite de {trade_limit} trades alcanzado"

#     # 2. Comprobar límite de duración
#     if duration_limit and not limit_reason:
#         trend_start_time = trend_state.get("start_time")
#         if trend_start_time:
#             elapsed_minutes = (current_timestamp - trend_start_time).total_seconds() / 60.0
#             if elapsed_minutes >= duration_limit:
#                 limit_reason = f"Límite de duración de {duration_limit} min alcanzado"

#     # 3. Comprobar límites de ROI de tendencia
#     if (tp_roi_limit is not None or sl_roi_limit is not None) and not limit_reason:
#         summary = position_manager.api.get_position_summary()
#         initial_capital = summary.get('initial_total_capital', 0.0)
        
#         if initial_capital > 1e-9:
#             unrealized_pnl = position_manager.api.get_unrealized_pnl(current_price)
#             realized_pnl = summary.get('total_realized_pnl_session', 0.0)
            
#             initial_pnl_at_trend_start = trend_state.get("initial_pnl", 0.0)
#             total_pnl_trend = (realized_pnl + unrealized_pnl) - initial_pnl_at_trend_start
            
#             current_trend_roi = utils.safe_division(total_pnl_trend, initial_capital) * 100
            
#             if tp_roi_limit is not None and current_trend_roi >= tp_roi_limit:
#                 limit_reason = f"Límite de TP por ROI de +{tp_roi_limit:.2f}% alcanzado (actual: {current_trend_roi:+.2f}%)"
#             elif sl_roi_limit is not None and current_trend_roi <= sl_roi_limit:
#                 limit_reason = f"Límite de SL por ROI de {sl_roi_limit:.2f}% alcanzado (actual: {current_trend_roi:+.2f}%)"

#     if limit_reason:
#         memory_logger.log(f"!!! LÍMITE DE TENDENCIA ALCANZADO: {limit_reason} !!!", level="INFO")
#         memory_logger.log("Finalizando tendencia y revirtiendo a modo NEUTRAL.", level="INFO")
#         _trend_limit_hit_reported = True
#         position_manager.api.end_current_trend_and_ask()


def check_session_limits(
    current_price: float,
    current_timestamp: datetime.datetime,
    operation_mode: str,
    global_stop_loss_event: Optional[threading.Event] = None
):
    """Comprueba si se han alcanzado los límites globales de la sesión."""
    global _global_stop_loss_triggered
    if not (position_manager and position_manager.api.is_initialized() and utils and config):
        return
    if _global_stop_loss_triggered:
        return

    # --- Lógica de Límites de Sesión (se mantiene sin cambios) ---
    start_time = position_manager.api.get_session_start_time()
    if start_time:
        time_limit_config = position_manager.api.get_session_time_limit()
        max_minutes = time_limit_config.get("duration", 0)
        time_limit_action = time_limit_config.get("action", "NEUTRAL").upper()

        if max_minutes > 0:
            elapsed_minutes = (current_timestamp - start_time).total_seconds() / 60.0
            if elapsed_minutes >= max_minutes:
                if time_limit_action == "STOP":
                    if not _global_stop_loss_triggered:
                        memory_logger.log("!!! LÍMITE DE TIEMPO DE SESIÓN ALCANZADO (ACCIÓN: STOP) !!!", level="ERROR")
                        memory_logger.log(f"Tiempo ({elapsed_minutes:.2f} min) >= Límite ({max_minutes} min). Deteniendo el bot.", level="ERROR")
                        _global_stop_loss_triggered = True
                        position_manager.api.close_all_logical_positions('long', reason="TIME_LIMIT_STOP")
                        position_manager.api.close_all_logical_positions('short', reason="TIME_LIMIT_STOP")
                        if global_stop_loss_event:
                            global_stop_loss_event.set()
                        raise GlobalStopLossException("Límite de tiempo de sesión alcanzado (STOP)")
                    return
                elif not position_manager.api.is_session_tp_hit(): # NEUTRAL
                    memory_logger.log("!!! LÍMITE DE TIEMPO DE SESIÓN ALCANZADO (ACCIÓN: NEUTRAL) !!!", level="INFO")
                    memory_logger.log(f"Tiempo ({elapsed_minutes:.2f} min) >= Límite ({max_minutes} min). Pasando a modo neutral.", level="INFO")
                    position_manager.api.set_session_tp_hit(True)
                    # --- (COMENTADO) Lógica de TUI que podría necesitar revisión futura ---
                    # if operation_mode == "live_interactive":
                    #     position_manager.api.set_manual_trading_mode("NEUTRAL", close_open=False)

    sl_roi_enabled = getattr(config, 'SESSION_ROI_SL_ENABLED', False)
    tp_roi_enabled = getattr(config, 'SESSION_ROI_TP_ENABLED', False)

    if not sl_roi_enabled and not tp_roi_enabled:
        return

    summary = position_manager.api.get_position_summary()
    if not summary or 'error' in summary: return
    
    initial_capital = summary.get('initial_total_capital', 0.0)
    if initial_capital < 1e-9: return
    
    total_realized_pnl = summary.get('total_realized_pnl_session', 0.0)
    total_unrealized_pnl = position_manager.api.get_unrealized_pnl(current_price)
    current_roi_pct = utils.safe_division(total_realized_pnl + total_unrealized_pnl, initial_capital) * 100.0
    
    if tp_roi_enabled and not position_manager.api.is_session_tp_hit():
        tp_threshold_pct = position_manager.api.get_global_tp_pct()
        if tp_threshold_pct and tp_threshold_pct > 0 and current_roi_pct >= tp_threshold_pct:
            memory_logger.log("!!! INFO: GLOBAL TAKE PROFIT DE LA SESIÓN ALCANZADO !!!", level="INFO")
            memory_logger.log(f"ROI Total ({current_roi_pct:.2f}%) >= Umbral ({tp_threshold_pct:.2f}%)", level="INFO")
            position_manager.api.set_session_tp_hit(True)
            # --- (COMENTADO) Lógica de TUI que podría necesitar revisión futura ---
            # if operation_mode == "live_interactive":
            #     position_manager.api.set_manual_trading_mode("NEUTRAL", close_open=False)
            
    if sl_roi_enabled:
        sl_threshold_pct = position_manager.api.get_global_sl_pct()
        if sl_threshold_pct and sl_threshold_pct > 0:
            stop_loss_comparison_pct = -abs(sl_threshold_pct)
            if current_roi_pct <= stop_loss_comparison_pct:
                _global_stop_loss_triggered = True
                memory_logger.log("!!! ALERTA DE EMERGENCIA: GLOBAL STOP LOSS POR ROI ACTIVADO !!!", level="ERROR")
                memory_logger.log(f"ROI Total ({current_roi_pct:.2f}%) <= Umbral ({stop_loss_comparison_pct:.2f}%)", level="ERROR")
                
                position_manager.api.close_all_logical_positions('long', reason="GLOBAL_SL_ROI")
                position_manager.api.close_all_logical_positions('short', reason="GLOBAL_SL_ROI")
                
                if global_stop_loss_event:
                    global_stop_loss_event.set()
                raise GlobalStopLossException(f"Global Stop Loss por ROI activado: {current_roi_pct:.2f}%")