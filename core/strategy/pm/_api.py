"""
Interfaz Pública del Position Manager (PM API).

Este módulo contiene todas las funciones que los consumidores externos, como la TUI,
utilizan para controlar y consultar el estado del Position Manager en tiempo real.
Separa la interfaz de control de la lógica de orquestación principal.
"""
import sys
import os
import datetime
import time
from typing import Optional, Dict, Any, Tuple

# --- Guardián de sys.path para importaciones robustas ---
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# --- Dependencias Externas y Módulos Internos ---
try:
    import config
    from core import utils
    # --- SOLUCIÓN: Corregir la importación de 'api' ---
    from core import api as live_operations
    # --- FIN DE LA SOLUCIÓN ---
    from core.logging import memory_logger
    from connection import ticker as connection_ticker
    
    from . import _state
    from . import _actions
    from . import _balance
    from . import _position_state
    from . import _helpers
except ImportError as e:
    print(f"ERROR CRÍTICO [PM API]: Falló importación de dependencias: {e}")
    # Definir dummies para evitar fallos catastróficos
    config=None; utils=None; live_operations=None; memory_logger=None; connection_ticker=None;
    _state=None; _actions=None; _balance=None; _position_state=None; _helpers=None;


# --- Funciones de Acceso y Resumen de Estado ---

def is_initialized() -> bool:
    """Verifica si el Position Manager ha sido inicializado."""
    return _state.is_initialized() if _state else False

def get_position_summary() -> dict:
    """Obtiene un resumen completo del estado actual del Position Manager."""
    if not is_initialized(): return {"error": "PM no inicializado"}
    
    open_longs = _position_state.get_open_logical_positions('long')
    open_shorts = _position_state.get_open_logical_positions('short')
    
    summary_dict = {
        "initialized": True,
        "operation_mode": _state.get_operation_mode(),
        "manual_mode_status": _state.get_manual_state(),
        "trend_status": _state.get_trend_state(),
        "leverage": _state.get_leverage(),
        "max_logical_positions": _state.get_max_logical_positions(),
        "initial_base_position_size_usdt": _state.get_initial_base_position_size(),
        "dynamic_base_size_long": _state.get_dynamic_base_size('long'),
        "dynamic_base_size_short": _state.get_dynamic_base_size('short'),
        "bm_balances": _balance.get_balances(),
        "open_long_positions_count": len(open_longs),
        "open_short_positions_count": len(open_shorts),
        "open_long_positions": [_helpers.format_pos_for_summary(p, utils) for p in open_longs],
        "open_short_positions": [_helpers.format_pos_for_summary(p, utils) for p in open_shorts],
        "total_realized_pnl_session": _state.get_total_pnl_realized(),
        "initial_total_capital": _balance.get_initial_total_capital(),
        "real_account_balances": {},
        "session_limits": {
            "time_limit": _state.get_session_time_limit(),
            "trade_limit": _state.get_manual_state().get("limit"),
            "trades_executed": _state.get_manual_state().get("executed")
        },
        "active_triggers": _state.get_active_triggers()
    }

    if _state.is_live_mode():
        if _balance:
            summary_dict["real_account_balances"] = _balance.get_real_balances_cache()
        else:
            summary_dict["real_account_balances"] = {"error": "balance_manager no disponible"}

    return summary_dict

def get_unrealized_pnl(current_price: float) -> float:
    """Calcula el PNL no realizado total de todas las posiciones abiertas."""
    if not is_initialized(): return 0.0
    total_unrealized_pnl = 0.0
    for side in ['long', 'short']:
        for pos in _position_state.get_open_logical_positions(side):
            entry = pos.get('entry_price', 0.0)
            size = pos.get('size_contracts', 0.0)
            if side == 'long': total_unrealized_pnl += (current_price - entry) * size
            else: total_unrealized_pnl += (entry - current_price) * size
    return total_unrealized_pnl

def get_manual_state() -> Dict[str, Any]:
    """Obtiene el estado del modo manual."""
    return _state.get_manual_state() if _state else {}

def get_session_start_time() -> Optional[datetime.datetime]:
    """Obtiene la hora de inicio de la sesión."""
    return _state.get_session_start_time() if _state else None

def get_global_tp_pct() -> Optional[float]:
    """Obtiene el umbral de Take Profit Global por ROI."""
    return _state.get_global_tp_pct() if _state else None

def is_session_tp_hit() -> bool:
    """Verifica si se ha alcanzado el TP global de la sesión."""
    return _state.is_session_tp_hit() if _state else False

def get_individual_stop_loss_pct() -> float:
    """Obtiene el SL individual para nuevas posiciones."""
    return _state.get_individual_stop_loss_pct() if _state else 0.0

def get_trailing_stop_params() -> Dict[str, float]:
    """Obtiene los parámetros del Trailing Stop."""
    return _state.get_trailing_stop_params() if _state else {'activation': 0.0, 'distance': 0.0}

def get_trend_limits() -> Dict[str, Any]:
    """Obtiene los límites configurados para la tendencia actual/próxima."""
    return _state.get_trend_limits() if _state else {}
    
def get_trend_state() -> Dict[str, Any]:
    """Obtiene el estado de la tendencia actual."""
    return _state.get_trend_state() if _state else {}
    
def get_all_triggers() -> list:
    """Obtiene todos los triggers condicionales (activos e inactivos)."""
    return _state.get_all_triggers() if _state else []

def get_global_sl_pct() -> Optional[float]:
    """Obtiene el umbral de Stop Loss Global por ROI."""
    return _state.get_global_sl_pct() if is_initialized() else None


# --- Funciones de Control Manual (TUI) ---

def set_manual_trading_mode(mode: str, trade_limit: Optional[int] = None, close_open: bool = False) -> Tuple[bool, str]:
    """Establece el modo de trading manual."""
    if not is_initialized(): return False, "PM no está inicializado."
    
    current_manual_mode = _state.get_manual_state()["mode"]
    
    if close_open:
        if current_manual_mode in ["LONG_ONLY", "LONG_SHORT"] and mode not in ["LONG_ONLY", "LONG_SHORT"]:
            close_all_logical_positions('long', "Cierre manual por cambio de modo")
        if current_manual_mode in ["SHORT_ONLY", "LONG_SHORT"] and mode not in ["SHORT_ONLY", "LONG_SHORT"]:
            close_all_logical_positions('short', "Cierre manual por cambio de modo")
            
    _state.set_manual_mode(mode.upper(), trade_limit)
    return True, f"Modo actualizado a {mode.upper()}."

def manual_close_logical_position_by_index(side: str, index: int) -> Tuple[bool, str]:
    """Cierra una posición lógica específica por su índice."""
    price = get_current_price_for_exit()
    if not price: return False, "No se pudo obtener el precio de mercado actual."

    success = _actions.close_logical_position(side, index, price, datetime.datetime.now(), reason="MANUAL")
    return (True, f"Orden de cierre para {side.upper()} #{index} enviada.") if success else (False, f"Fallo al enviar orden de cierre.")

def close_all_logical_positions(side: str, reason: str = "MANUAL_ALL") -> bool:
    """Cierra TODAS las posiciones lógicas de un lado de forma robusta."""
    price = get_current_price_for_exit()
    if not price:
        memory_logger.log(f"CIERRE TOTAL FALLIDO: Sin precio de mercado para {side.upper()}.", level="ERROR")
        return False
    
    initial_count = len(_position_state.get_open_logical_positions(side))
    if initial_count == 0: return True
        
    memory_logger.log(f"Iniciando cierre total de {initial_count} posiciones {side.upper()}.", level="INFO")
    
    attempts, max_attempts = 0, initial_count + 3
    while len(_position_state.get_open_logical_positions(side)) > 0 and attempts < max_attempts:
        success = _actions.close_logical_position(side, 0, price, datetime.datetime.now(), reason=reason)
        if not success:
            memory_logger.log(f"Fallo al cerrar posición {side.upper()} en índice 0.", level="WARN")
        attempts += 1
        time.sleep(0.2)

    remaining = len(_position_state.get_open_logical_positions(side))
    if remaining == 0:
        memory_logger.log(f"ÉXITO: Todas las posiciones {side.upper()} cerradas lógicamente.", level="INFO")
        return True
    else:
        memory_logger.log(f"FALLO: Quedan {remaining} posiciones {side.upper()} tras {attempts} intentos.", level="ERROR")
        return False


# --- Funciones de Ajuste de Parámetros (TUI) ---

def add_max_logical_position_slot() -> Tuple[bool, str]:
    """Incrementa el número máximo de posiciones simultáneas."""
    if not is_initialized(): return False, "PM no está inicializado."
    new_max = _state.get_max_logical_positions() + 1
    _state.set_max_logical_positions(new_max)
    _balance.update_operational_margins_based_on_slots(new_max)
    return True, f"Slots incrementados a {new_max}."

def remove_max_logical_position_slot() -> Tuple[bool, str]:
    """Decrementa el número máximo de posiciones, si es seguro hacerlo."""
    if not is_initialized(): return False, "PM no está inicializado."
    current_max = _state.get_max_logical_positions()
    if current_max <= 1: return False, "Mínimo 1 slot."
    
    open_count = max(len(_position_state.get_open_logical_positions('long')),
                     len(_position_state.get_open_logical_positions('short')))

    if (current_max - 1) < open_count:
        return False, "No se puede remover, hay más posiciones abiertas que el nuevo límite."
        
    new_max = current_max - 1
    _state.set_max_logical_positions(new_max)
    _balance.update_operational_margins_based_on_slots(new_max)
    return True, f"Slots decrementados a {new_max}."

def set_base_position_size(new_size_usdt: float) -> Tuple[bool, str]:
    """Establece el tamaño base de las nuevas posiciones."""
    if not is_initialized(): return False, "PM no inicializado."
    if not isinstance(new_size_usdt, (int, float)) or new_size_usdt <= 0: return False, "Tamaño inválido."
    
    old_size = _state.get_initial_base_position_size()
    # Accedemos directamente a la variable global de _state para actualizarla, una alternativa sería un setter específico.
    _state._initial_base_position_size_usdt = new_size_usdt
    _balance.recalculate_dynamic_base_sizes()
    return True, f"Tamaño base actualizado de {old_size:.2f} a {new_size_usdt:.2f} USDT."

def set_leverage(new_leverage: float) -> Tuple[bool, str]:
    """Establece el apalancamiento para futuras operaciones."""
    if not is_initialized(): return False, "PM no está inicializado."
    if not isinstance(new_leverage, (int, float)) or not (1 <= new_leverage <= 100):
        return False, "Apalancamiento inválido. Debe ser un número entre 1 y 100."

    _state.set_leverage(new_leverage)
    
    if _state.is_live_mode():
        symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
        success = live_operations.set_leverage(symbol, str(new_leverage), str(new_leverage))
        if success:
            return True, f"Apalancamiento actualizado a {new_leverage}x (afecta a nuevas posiciones)."
        else:
            return False, f"Error al aplicar apalancamiento de {new_leverage}x en el exchange."
    
    return True, f"Apalancamiento de backtest actualizado a {new_leverage}x (afecta a nuevas posiciones)."

def set_individual_stop_loss_pct(value: float) -> Tuple[bool, str]:
    """Establece el SL para nuevas posiciones."""
    if not is_initialized(): return False, "PM no inicializado."
    if not isinstance(value, (int, float)) or value < 0: return False, "Valor de SL inválido."
    _state.set_individual_stop_loss_pct(value)
    return True, f"Stop Loss individual para nuevas posiciones ajustado a {value:.2f}%."

def set_trailing_stop_params(activation_pct: float, distance_pct: float) -> Tuple[bool, str]:
    """Ajusta los parámetros del Trailing Stop."""
    if not is_initialized(): return False, "PM no inicializado."
    if not all(isinstance(v, (int, float)) and v >= 0 for v in [activation_pct, distance_pct]):
        return False, "Valores de TS inválidos."
    _state.set_trailing_stop_params(activation_pct, distance_pct)
    return True, f"Trailing Stop ajustado (Activación: {activation_pct:.2f}%, Distancia: {distance_pct:.2f}%)."


# --- Funciones de Gestión de Límites y Triggers (TUI) ---

def set_global_stop_loss_pct(value: float) -> Tuple[bool, str]:
    """Establece el disyuntor de SL global por ROI."""
    if not is_initialized(): return False, "PM no inicializado."
    _state.set_global_sl_pct(value)
    return True, f"Stop Loss Global actualizado a -{value}%." if value > 0 else "Stop Loss Global desactivado."

def set_global_take_profit_pct(value: float) -> Tuple[bool, str]:
    """Establece el disyuntor de TP global por ROI."""
    if not is_initialized(): return False, "PM no inicializado."
    _state.set_global_tp_pct(value)
    _state.set_session_tp_hit(False)
    return True, f"Take Profit Global actualizado a +{value}%." if value > 0 else "Take Profit Global desactivado."

def set_session_time_limit(duration: int, action: str) -> Tuple[bool, str]:
    """Establece el límite de duración de la sesión."""
    if not is_initialized(): return False, "PM no inicializado."
    _state.set_session_time_limit(duration, action)
    return True, f"Límite de tiempo a {duration} min, acción: {action.upper()}." if duration > 0 else "Límite de tiempo desactivado."

def set_manual_trade_limit(limit: Optional[int]) -> Tuple[bool, str]:
    """Establece un límite al número de trades para la sesión manual."""
    if not is_initialized(): return False, "PM no está inicializado."
    if limit is not None and (not isinstance(limit, int) or limit < 0): return False, "Límite inválido."
    
    new_limit = limit if limit is not None and limit > 0 else None
    _state.set_manual_mode(_state.get_manual_state()["mode"], new_limit)
    limit_str = f"{new_limit} trades" if new_limit is not None else "ilimitados"
    return True, f"Límite de sesión establecido a {limit_str}."

def set_trend_limits(duration: Optional[int], tp_roi_pct: Optional[float], sl_roi_pct: Optional[float], trade_limit: Optional[int] = None) -> Tuple[bool, str]:
    """Establece los límites para la PRÓXIMA tendencia manual."""
    if not is_initialized(): return False, "PM no está inicializado."
    if trade_limit is not None: set_manual_trade_limit(trade_limit)

    _state.set_trend_limits(duration, tp_roi_pct, sl_roi_pct, "ASK")
    
    msg_parts = [p for p in [f"Duración: {duration} min" if duration else None,
                             f"Trades: {trade_limit if trade_limit > 0 else 'Ilimitados'}" if trade_limit is not None else None,
                             f"TP ROI: +{tp_roi_pct:.2f}%" if tp_roi_pct and tp_roi_pct > 0 else None,
                             f"SL ROI: {sl_roi_pct:.2f}%" if sl_roi_pct and sl_roi_pct < 0 else None] if p]

    if not msg_parts: return True, "Límites de tendencia desactivados."
    return True, f"Límites para la próxima tendencia: {', '.join(msg_parts)}."

def add_conditional_trigger(condition: Dict[str, Any], action: Dict[str, Any], one_shot: bool = True) -> Tuple[bool, str]:
    """Añade una nueva regla de trigger condicional."""
    if not is_initialized(): return False, "PM no está inicializado."
    
    if not all(k in condition for k in ["type", "value"]) or not all(k in action for k in ["type", "params"]):
        return False, "Estructura de trigger inválida."
        
    trigger_id = f"trigger_{int(time.time() * 1000)}_{action.get('type', 'action')}"
    
    trigger_data = {"id": trigger_id, "condition": condition, "action": action, "is_active": True, "one_shot": one_shot}
    
    _state.add_trigger(trigger_data)
    return True, f"Trigger '{trigger_id}' añadido con éxito."

def remove_conditional_trigger(trigger_id: str) -> Tuple[bool, str]:
    """Elimina un trigger condicional por su ID."""
    if not is_initialized(): return False, "PM no está inicializado."
    
    success = _state.remove_trigger_by_id(trigger_id)
    return (True, f"Trigger '{trigger_id}' eliminado.") if success else (False, f"No se encontró el trigger con ID '{trigger_id}'.")

def update_trigger_status(trigger_id: str, is_active: bool):
    """Activa o desactiva un trigger."""
    if _state: _state.update_trigger_status(trigger_id, is_active)

def start_manual_trend(mode: str, trade_limit: Optional[int], duration_limit: Optional[int], tp_roi_limit: Optional[float], sl_roi_limit: Optional[float]) -> Tuple[bool, str]:
    """Inicia una nueva tendencia manual con límites específicos (usado por triggers)."""
    if not is_initialized() or _state.get_operation_mode() != "live_interactive":
        return False, "Función solo disponible en modo live interactivo."
    
    _state.set_trend_limits(duration_limit, tp_roi_limit, sl_roi_limit, "ASK")
    
    success, msg = set_manual_trading_mode(mode, trade_limit=trade_limit, close_open=False)
    
    if success:
        limit_parts = [p for p in [f"Trades: {trade_limit or 'inf'}" if trade_limit is not None else None,
                                   f"Dur: {duration_limit}m" if duration_limit is not None else None,
                                   f"TP: +{tp_roi_limit}%" if tp_roi_limit is not None else None,
                                   f"SL: {sl_roi_limit}%" if sl_roi_limit is not None else None] if p]
        limit_str = f"({', '.join(limit_parts)})" if limit_parts else ""
        return True, f"Tendencia manual '{mode}' iniciada con límites {limit_str}."
    else:
        return False, f"Fallo al iniciar tendencia manual: {msg}"

def end_current_trend_and_ask():
    """Finaliza la tendencia actual y revierte a modo NEUTRAL."""
    if not is_initialized() or _state.get_operation_mode() != "live_interactive": return
    if hasattr(_state, '_manual_mode'):
        _state._manual_mode = "NEUTRAL"


# --- Funciones de Ayuda y Visualización ---

def get_current_price_for_exit() -> Optional[float]:
    """Obtiene el último precio del ticker para cierres manuales."""
    try:
        price_info = connection_ticker.get_latest_price()
        return price_info.get('price')
    except (ImportError, AttributeError): return None

def display_logical_positions():
    """Imprime en consola las tablas de posiciones lógicas."""
    if not is_initialized(): return
    _position_state.display_logical_table('long')
    _position_state.display_logical_table('short')

def get_rrr_potential() -> Optional[float]:
    """Calcula el Risk/Reward Ratio Potencial hasta la activación del Trailing Stop."""
    if not is_initialized(): return None
    
    sl_pct = _state.get_individual_stop_loss_pct()
    ts_activation_pct = _state.get_trailing_stop_params()['activation']
    
    if sl_pct > 0 and ts_activation_pct > 0:
        return utils.safe_division(ts_activation_pct, sl_pct)
    return None