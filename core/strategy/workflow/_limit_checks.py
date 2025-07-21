# core/strategy/workflow/_limit_checks.py

"""
Módulo para la Comprobación de Límites y Disyuntores.

Responsabilidad: Verificar en cada tick si se han alcanzado los límites
globales de la sesión (ej. SL/TP por ROI) o los límites de una tendencia
manual activa. Actúa como el sistema de "disyuntores" del bot.
"""
import sys
import os
import datetime
import traceback
import threading
from typing import Dict, Any, Optional

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias con rutas absolutas desde la raíz del proyecto
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

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Excepción Personalizada ---
class GlobalStopLossException(Exception):
    """Excepción para ser lanzada cuando se activa el Global Stop Loss."""
    pass


# --- Estado del Módulo ---
_trend_limit_hit_reported = False
_global_stop_loss_triggered = False

def initialize_limit_checks():
    """Resetea el estado interno del módulo de comprobación de límites."""
    global _trend_limit_hit_reported, _global_stop_loss_triggered
    _trend_limit_hit_reported = False
    _global_stop_loss_triggered = False

def has_global_stop_loss_triggered() -> bool:
    """Informa si el SL global ya se ha activado en esta sesión."""
    return _global_stop_loss_triggered


# --- Lógica de Comprobación de Límites ---

def check_trend_limits(current_price: float, current_timestamp: datetime.datetime, operation_mode: str):
    """Comprueba si se han alcanzado los límites para una tendencia manual activa."""
    global _trend_limit_hit_reported
    if not (position_manager and position_manager.is_initialized() and utils):
        return
    if operation_mode != "live_interactive":
        return

    manual_state = position_manager.get_manual_state()
    current_mode = manual_state.get("mode")
    if current_mode == "NEUTRAL" or _trend_limit_hit_reported:
        if current_mode == "NEUTRAL" and _trend_limit_hit_reported:
            # Resetea el flag si el modo vuelve a ser neutral manualmente
            _trend_limit_hit_reported = False
        return

    limit_reason = None
    trend_limits = position_manager.get_trend_limits()

    # 1. Comprobar límite de trades
    trade_limit = manual_state.get("limit")
    if trade_limit is not None and manual_state.get("executed", 0) >= trade_limit:
        limit_reason = f"Límite de {trade_limit} trades alcanzado"

    # 2. Comprobar límite de duración
    duration_limit = trend_limits.get("duration_minutes")
    if duration_limit and not limit_reason:
        trend_start_time = trend_limits.get("start_time")
        if trend_start_time:
            elapsed_minutes = (current_timestamp - trend_start_time).total_seconds() / 60.0
            if elapsed_minutes >= duration_limit:
                limit_reason = f"Límite de duración de {duration_limit} min alcanzado"

    # 3. Comprobar límites de ROI de tendencia
    tp_roi_limit = trend_limits.get("tp_roi_pct")
    sl_roi_limit = trend_limits.get("sl_roi_pct")
    if (tp_roi_limit is not None or sl_roi_limit is not None) and not limit_reason:
        summary = position_manager.get_position_summary()
        initial_capital = summary.get('initial_total_capital', 0.0)
        
        if initial_capital > 1e-9:
            # Reutiliza la lógica de PNL no realizado del PM
            unrealized_pnl = position_manager.get_unrealized_pnl(current_price)
            realized_pnl = summary.get('total_realized_pnl_session', 0.0)
            
            # (Esta lógica podría simplificarse si el PM proveyera PNL de tendencia)
            total_pnl_trend = (realized_pnl + unrealized_pnl) - position_manager.get_trend_state()["initial_pnl"]
            current_trend_roi = utils.safe_division(total_pnl_trend, initial_capital) * 100
            
            if tp_roi_limit is not None and current_trend_roi >= tp_roi_limit:
                limit_reason = f"Límite de TP por ROI de +{tp_roi_limit:.2f}% alcanzado (actual: {current_trend_roi:+.2f}%)"
            elif sl_roi_limit is not None and current_trend_roi <= sl_roi_limit:
                limit_reason = f"Límite de SL por ROI de {sl_roi_limit:.2f}% alcanzado (actual: {current_trend_roi:+.2f}%)"

    if limit_reason:
        memory_logger.log(f"!!! LÍMITE DE TENDENCIA ALCANZADO: {limit_reason} !!!", level="INFO")
        memory_logger.log("Revirtiendo modo a NEUTRAL. No se abrirán más posiciones en esta tendencia.", level="INFO")
        _trend_limit_hit_reported = True
        position_manager.end_current_trend_and_ask()


def check_session_limits(
    current_price: float,
    current_timestamp: datetime.datetime,
    operation_mode: str,
    global_stop_loss_event: Optional[threading.Event] = None
):
    """Comprueba si se han alcanzado los límites globales de la sesión."""
    global _global_stop_loss_triggered
    if not (position_manager and position_manager.is_initialized() and utils and config):
        return
    if _global_stop_loss_triggered:
        return

    # 1. Comprobar límite de duración de la sesión
    start_time = position_manager.get_session_start_time()
    if start_time:
        time_limit_config = position_manager.get_session_time_limit()
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
                        position_manager.close_all_logical_positions('long', reason="TIME_LIMIT_STOP")
                        position_manager.close_all_logical_positions('short', reason="TIME_LIMIT_STOP")
                        if global_stop_loss_event:
                            global_stop_loss_event.set()
                        raise GlobalStopLossException("Límite de tiempo de sesión alcanzado (STOP)")
                    return
                elif not position_manager.is_session_tp_hit(): # NEUTRAL
                    memory_logger.log("!!! LÍMITE DE TIEMPO DE SESIÓN ALCANZADO (ACCIÓN: NEUTRAL) !!!", level="INFO")
                    memory_logger.log(f"Tiempo ({elapsed_minutes:.2f} min) >= Límite ({max_minutes} min). Pasando a modo neutral.", level="INFO")
                    position_manager.set_session_tp_hit(True)
                    if operation_mode == "live_interactive":
                        position_manager.set_manual_trading_mode("NEUTRAL")

    # 2. Comprobar límites de ROI de la sesión
    sl_threshold_pct = position_manager.get_global_sl_pct()
    tp_threshold_pct = position_manager.get_global_tp_pct()

    if (sl_threshold_pct is None or sl_threshold_pct == 0.0) and (tp_threshold_pct is None or tp_threshold_pct == 0.0):
        return

    summary = position_manager.get_position_summary()
    if not summary or 'error' in summary: return
    initial_capital = summary.get('initial_total_capital', 0.0)
    if initial_capital < 1e-6: return
    
    total_realized_pnl = summary.get('total_realized_pnl_session', 0.0)
    total_unrealized_pnl = position_manager.get_unrealized_pnl(current_price)
    
    current_roi_pct = utils.safe_division(total_realized_pnl + total_unrealized_pnl, initial_capital) * 100.0
    
    # Comprobar TP
    if tp_threshold_pct and tp_threshold_pct > 0 and not position_manager.is_session_tp_hit():
        if current_roi_pct >= tp_threshold_pct:
            memory_logger.log("!!! INFO: GLOBAL TAKE PROFIT DE LA SESIÓN ALCANZADO !!!", level="INFO")
            memory_logger.log(f"ROI Total ({current_roi_pct:.2f}%) >= Umbral ({tp_threshold_pct:.2f}%)", level="INFO")
            position_manager.set_session_tp_hit(True)
            if operation_mode == "live_interactive":
                position_manager.set_manual_trading_mode("NEUTRAL") 
            
    # Comprobar SL
    stop_loss_comparison_pct = -abs(sl_threshold_pct) if sl_threshold_pct else 0.0
    if stop_loss_comparison_pct != 0 and current_roi_pct <= stop_loss_comparison_pct:
        _global_stop_loss_triggered = True
        memory_logger.log("!!! ALERTA DE EMERGENCIA: GLOBAL STOP LOSS POR ROI ACTIVADO !!!", level="ERROR")
        memory_logger.log(f"ROI Total ({current_roi_pct:.2f}%) <= Umbral ({stop_loss_comparison_pct:.2f}%)", level="ERROR")
        
        position_manager.close_all_logical_positions('long', reason="GLOBAL_SL_ROI")
        position_manager.close_all_logical_positions('short', reason="GLOBAL_SL_ROI")
        
        if global_stop_loss_event:
            global_stop_loss_event.set()
        raise GlobalStopLossException(f"Global Stop Loss por ROI activado: {current_roi_pct:.2f}%")