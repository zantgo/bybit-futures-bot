# =============== INICIO ARCHIVO: core/strategy/pm_state.py (CORREGIDO Y COMPLETO) ===============
"""
Módulo para gestionar y encapsular TODO el estado interno del Position Manager.

Este módulo actúa como la "única fuente de verdad" para el estado del PM.
Ninguna otra parte del sistema debe modificar estas variables directamente. El acceso
se realiza a través de las funciones getter y setter proporcionadas.
"""
import threading
import datetime
from typing import Optional, Dict, Any
import config

# --- Estado General y de Configuración ---
_initialized: bool = False
_operation_mode: str = "unknown"
_is_live_mode: bool = False
_executor: Optional[Any] = None # Referencia a la instancia de PositionExecutor
_leverage: float = 1.0
_max_logical_positions: int = 1
_initial_base_position_size_usdt: float = 0.0
_current_dynamic_base_size_long: float = 0.0
_current_dynamic_base_size_short: float = 0.0
_stop_loss_event: Optional[threading.Event] = None
_global_stop_loss_roi_pct: Optional[float] = None
_global_take_profit_roi_pct: Optional[float] = None
_session_tp_hit: bool = False # Flag para saber si ya se alcanzó el TP de la sesión

# <<< INICIO DE NUEVAS VARIABLES DE ESTADO PARA RIESGO DINÁMICO >>>
_individual_stop_loss_pct: float = 0.0
_trailing_stop_activation_pct: float = 0.0
_trailing_stop_distance_pct: float = 0.0
# <<< FIN DE NUEVAS VARIABLES DE ESTADO >>>

# --- Estado de Límites de Sesión ---
_session_start_time: Optional[datetime.datetime] = None
_session_max_duration_minutes: int = 0
_session_time_limit_action: str = "NEUTRAL"

# --- Estado de PNL y Transferencias ---
_total_realized_pnl_long: float = 0.0
_total_realized_pnl_short: float = 0.0
_total_transferred_profit: float = 0.0

# --- Estado para Modo Automático ---
_current_trend_side: Optional[str] = None
_trades_in_current_trend: int = 0
_initial_pnl_at_trend_start: float = 0.0
_trend_take_profit_hit: bool = False

# --- Estado para Modo Live Interactivo ---
_manual_mode: str = "NEUTRAL"
_manual_trade_limit: Optional[int] = None
_manual_trades_executed: int = 0

# --- Getters (para leer el estado) ---

def is_initialized() -> bool: return _initialized
def get_operation_mode() -> str: return _operation_mode
def is_live_mode() -> bool: return _is_live_mode
def get_executor() -> Optional[Any]: return _executor
def get_leverage() -> float: return _leverage
def get_max_logical_positions() -> int: return _max_logical_positions
def get_initial_base_position_size() -> float: return _initial_base_position_size_usdt
def get_dynamic_base_size(side: str) -> float: return _current_dynamic_base_size_long if side == 'long' else _current_dynamic_base_size_short
def get_total_pnl_realized(side: Optional[str] = None) -> float:
    if side == 'long': return _total_realized_pnl_long
    if side == 'short': return _total_realized_pnl_short
    return _total_realized_pnl_long + _total_realized_pnl_short
def get_total_transferred_profit() -> float: return _total_transferred_profit
def get_trend_state() -> Dict[str, Any]:
    return {
        "side": _current_trend_side,
        "trades_count": _trades_in_current_trend,
        "initial_pnl": _initial_pnl_at_trend_start,
        "tp_hit": _trend_take_profit_hit
    }
def get_manual_state() -> Dict[str, Any]:
    return {
        "mode": _manual_mode,
        "limit": _manual_trade_limit,
        "executed": _manual_trades_executed
    }
def get_global_sl_pct() -> Optional[float]: return _global_stop_loss_roi_pct
def get_global_tp_pct() -> Optional[float]: return _global_take_profit_roi_pct
def is_session_tp_hit() -> bool: return _session_tp_hit
def get_session_start_time() -> Optional[datetime.datetime]: return _session_start_time
def get_session_time_limit() -> Dict[str, Any]: return {"duration": _session_max_duration_minutes, "action": _session_time_limit_action}

# <<< INICIO DE NUEVOS GETTERS PARA RIESGO DINÁMICO >>>
def get_individual_stop_loss_pct() -> float:
    """Obtiene el porcentaje de Stop Loss individual actual."""
    return _individual_stop_loss_pct

def get_trailing_stop_params() -> Dict[str, float]:
    """Obtiene los parámetros de Trailing Stop actuales."""
    return {
        "activation": _trailing_stop_activation_pct,
        "distance": _trailing_stop_distance_pct
    }
# <<< FIN DE NUEVOS GETTERS >>>

# --- Setters (para modificar el estado de forma controlada) ---

def set_initialized(status: bool):
    global _initialized
    _initialized = status

def set_initial_config(op_mode: str, live_mode: bool, exec_instance: Any, lev: float, max_pos: int, base_size: float, stop_event: Optional[threading.Event]):
    global _operation_mode, _is_live_mode, _executor, _leverage, _max_logical_positions, _initial_base_position_size_usdt, _stop_loss_event
    global _global_stop_loss_roi_pct, _global_take_profit_roi_pct, _session_tp_hit
    global _session_start_time, _session_max_duration_minutes, _session_time_limit_action
    global _individual_stop_loss_pct, _trailing_stop_activation_pct, _trailing_stop_distance_pct

    _operation_mode, _is_live_mode, _executor, _leverage, _max_logical_positions, _initial_base_position_size_usdt, _stop_loss_event = op_mode, live_mode, exec_instance, lev, max_pos, base_size, stop_event
    
    # Cargar valores iniciales desde el archivo de configuración
    _global_stop_loss_roi_pct = getattr(config, 'GLOBAL_ACCOUNT_STOP_LOSS_ROI_PCT', 0.0)
    _global_take_profit_roi_pct = getattr(config, 'GLOBAL_ACCOUNT_TAKE_PROFIT_ROI_PCT', 0.0)
    _session_tp_hit = False

    _session_start_time = datetime.datetime.now()
    _session_max_duration_minutes = getattr(config, 'SESSION_MAX_DURATION_MINUTES', 0)
    _session_time_limit_action = getattr(config, 'SESSION_TIME_LIMIT_ACTION', "NEUTRAL")
    
    # <<< INICIO: Cargar valores iniciales de riesgo dinámico desde config >>>
    _individual_stop_loss_pct = getattr(config, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', 0.0)
    _trailing_stop_activation_pct = getattr(config, 'TRAILING_STOP_ACTIVATION_PCT', 0.0)
    _trailing_stop_distance_pct = getattr(config, 'TRAILING_STOP_DISTANCE_PCT', 0.0)
    # <<< FIN >>>

def set_dynamic_base_size(long_size: float, short_size: float):
    global _current_dynamic_base_size_long, _current_dynamic_base_size_short
    _current_dynamic_base_size_long, _current_dynamic_base_size_short = long_size, short_size
    
def set_max_logical_positions(new_max_slots: int):
    global _max_logical_positions
    _max_logical_positions = new_max_slots

def add_realized_pnl(side: str, pnl: float):
    global _total_realized_pnl_long, _total_realized_pnl_short
    if side == 'long': _total_realized_pnl_long += pnl
    else: _total_realized_pnl_short += pnl

def add_transferred_profit(amount: float):
    global _total_transferred_profit
    _total_transferred_profit += amount

def set_global_sl_pct(value: float):
    global _global_stop_loss_roi_pct
    _global_stop_loss_roi_pct = value

def set_global_tp_pct(value: float):
    global _global_take_profit_roi_pct
    _global_take_profit_roi_pct = value
    
def set_session_tp_hit(status: bool):
    global _session_tp_hit
    _session_tp_hit = status

def set_session_time_limit(duration: int, action: str):
    global _session_max_duration_minutes, _session_time_limit_action
    _session_max_duration_minutes, _session_time_limit_action = duration, action

# <<< INICIO DE NUEVOS SETTERS PARA RIESGO DINÁMICO >>>
def set_individual_stop_loss_pct(value: float):
    """Establece el nuevo porcentaje para el Stop Loss individual."""
    global _individual_stop_loss_pct
    _individual_stop_loss_pct = value

def set_trailing_stop_params(activation_pct: float, distance_pct: float):
    """Establece los nuevos parámetros para el Trailing Stop."""
    global _trailing_stop_activation_pct, _trailing_stop_distance_pct
    _trailing_stop_activation_pct = activation_pct
    _trailing_stop_distance_pct = distance_pct
# <<< FIN DE NUEVOS SETTERS >>>

# --- Modificadores de Estado de Tendencia (Automático) ---

def start_new_trend(side: str):
    global _current_trend_side, _trades_in_current_trend, _initial_pnl_at_trend_start, _trend_take_profit_hit
    _current_trend_side, _trades_in_current_trend, _initial_pnl_at_trend_start, _trend_take_profit_hit = side, 0, get_total_pnl_realized(), False

def end_trend():
    global _current_trend_side
    _current_trend_side = None

def increment_trend_trades():
    global _trades_in_current_trend
    _trades_in_current_trend += 1

def set_trend_tp_hit(status: bool):
    global _trend_take_profit_hit
    _trend_take_profit_hit = status

# --- Modificadores de Estado de Sesión (Manual) ---

def set_manual_mode(mode: str, limit: Optional[int]):
    global _manual_mode, _manual_trade_limit, _manual_trades_executed
    _manual_mode, _manual_trade_limit, _manual_trades_executed = mode, (limit if limit and limit > 0 else None), 0

def increment_manual_trades():
    global _manual_trades_executed
    _manual_trades_executed += 1

# --- Función de Reseteo ---

def reset_all_states():
    """Resetea todas las variables de estado a sus valores iniciales."""
    global _initialized, _operation_mode, _is_live_mode, _executor, _leverage, _max_logical_positions, _initial_base_position_size_usdt, _stop_loss_event
    global _total_realized_pnl_long, _total_realized_pnl_short, _total_transferred_profit
    global _current_trend_side, _trades_in_current_trend, _initial_pnl_at_trend_start, _trend_take_profit_hit
    global _manual_mode, _manual_trade_limit, _manual_trades_executed
    global _global_stop_loss_roi_pct, _global_take_profit_roi_pct, _session_tp_hit
    global _session_start_time, _session_max_duration_minutes, _session_time_limit_action
    global _individual_stop_loss_pct, _trailing_stop_activation_pct, _trailing_stop_distance_pct
    
    _initialized = False
    _operation_mode = "unknown"
    _is_live_mode = False
    _executor = None
    _leverage = 1.0
    _max_logical_positions = 1
    _initial_base_position_size_usdt = 0.0
    _stop_loss_event = None
    
    _total_realized_pnl_long = 0.0
    _total_realized_pnl_short = 0.0
    _total_transferred_profit = 0.0
    
    _current_trend_side = None
    _trades_in_current_trend = 0
    _initial_pnl_at_trend_start = 0.0
    _trend_take_profit_hit = False
    
    _manual_mode = "NEUTRAL"
    _manual_trade_limit = None
    _manual_trades_executed = 0

    _global_stop_loss_roi_pct = None
    _global_take_profit_roi_pct = None
    _session_tp_hit = False

    _session_start_time = None
    _session_max_duration_minutes = 0
    _session_time_limit_action = "NEUTRAL"

    _individual_stop_loss_pct = 0.0
    _trailing_stop_activation_pct = 0.0
    _trailing_stop_distance_pct = 0.0

# =============== FIN ARCHIVO: core/strategy/pm_state.py (CORREGIDO Y COMPLETO) ===============