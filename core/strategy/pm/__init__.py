# core/strategy/pm/__init__.py

"""
Fachada Pública y Orquestador de Alto Nivel para el Position Manager.

Este módulo es el único punto de entrada para el resto del sistema.
Delega la gestión del estado a `_state`, las reglas a `_rules` y las
acciones a `_actions`, manteniendo este archivo limpio y enfocado en la orquestación.
"""
import sys
import os
import datetime
import time
import traceback
from typing import Optional, Dict, Any, Tuple

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias externas al paquete PM
try:
    import config
    from core import utils
    from core import api as live_operations # Usa el nuevo paquete api
    from core.logging import memory_logger, closed_position_logger
    from connection import manager as live_manager
except ImportError as e:
    print(f"ERROR CRÍTICO [PM Facade Import]: Falló importación de dependencias externas: {e}")
    # Definir dummies
    config=None; utils=None; live_operations=None; memory_logger=None;
    closed_position_logger=None; live_manager=None

# Importar módulos internos del paquete PM usando importaciones relativas y alias
try:
    from . import _state as pm_state
    from . import _rules as pm_rules
    from . import _actions as pm_actions
    from . import _balance as balance_manager
    from . import _position_state as position_state
    from ._executor import PositionExecutor
    from . import _helpers as position_helpers
    from . import _calculations as position_calculations
except ImportError as e:
    print(f"ERROR CRÍTICO [PM Facade Import]: Falló importación de módulos internos del PM: {e}")
    # Definir dummies
    pm_state=None; pm_rules=None; pm_actions=None; balance_manager=None;
    position_state=None; PositionExecutor=None; position_helpers=None;
    position_calculations=None

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


def initialize(
    operation_mode: str,
    initial_real_state: Optional[Dict[str, Dict[str, Any]]] = None,
    base_position_size_usdt_param: Optional[float] = None,
    initial_max_logical_positions_param: Optional[int] = None,
    stop_loss_event: Optional[Any] = None
):
    """Inicializa todos los componentes del Position Manager."""
    if not getattr(config, 'POSITION_MANAGEMENT_ENABLED', False):
        print("[PM Facade] Init omitida (Gestión Desactivada).")
        return

    memory_logger.log("PM Facade: Inicializando Orquestador...", level="INFO")
    
    pm_state.reset_all_states()
    is_live = operation_mode == "live_interactive"

    base_size = base_position_size_usdt_param or getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0)
    max_pos = initial_max_logical_positions_param or getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1)
    
    executor = PositionExecutor(
        is_live_mode=is_live, config=config, utils=utils,
        balance_manager=balance_manager, position_state=position_state,
        position_calculations=position_calculations, live_operations=live_operations,
        closed_position_logger=closed_position_logger, position_helpers=position_helpers,
        live_manager=live_manager
    )

    pm_state.set_initial_config(
        op_mode=operation_mode, live_mode=is_live, exec_instance=executor,
        lev=getattr(config, 'POSITION_LEVERAGE', 1.0), max_pos=max_pos,
        base_size=base_size, stop_event=stop_loss_event
    )

    real_balances_for_init = initial_real_state
    if is_live and not real_balances_for_init and live_manager:
        memory_logger.log("PM Facade: Obteniendo balances reales para inicialización...", level="DEBUG")
        real_balances_for_init = {}
        for acc_name in live_manager.get_initialized_accounts():
            real_balances_for_init[acc_name] = {'unified_balance': live_operations.get_unified_account_balance_info(acc_name)}

    balance_manager.initialize(operation_mode, real_balances_for_init, base_size, max_pos)
    position_state.initialize_state(
        is_live_mode=is_live,
        config_dependency=config,
        utils_dependency=utils,
        live_ops_dependency=live_operations
    )
    
    pm_state.set_initialized(True)
    memory_logger.log("PM Facade: Orquestador Inicializado.", level="INFO")

def handle_low_level_signal(signal: str, entry_price: float, timestamp: datetime.datetime):
    """Punto de entrada para señales. Filtra y actúa según el modo de operación."""
    if not pm_state.is_initialized(): return
    
    manual_mode = pm_state.get_manual_state()["mode"]
    side_to_open = 'long' if signal == "BUY" else 'short'
    
    side_allowed = (side_to_open == 'long' and manual_mode in ["LONG_ONLY", "LONG_SHORT"]) or \
                   (side_to_open == 'short' and manual_mode in ["SHORT_ONLY", "LONG_SHORT"])
    
    if side_allowed and pm_rules.can_open_new_position(side_to_open):
        pm_actions.open_logical_position(side_to_open, entry_price, timestamp)

def check_and_close_positions(current_price: float, timestamp: datetime.datetime):
    """Revisa SL y TS para todas las posiciones abiertas."""
    if not pm_state.is_initialized(): return
    
    for side in ['long', 'short']:
        open_positions = position_state.get_open_logical_positions(side)
        if not open_positions: continue
        
        indices_to_close = []
        reasons_for_close = {}
        for i, pos in enumerate(open_positions):
            entry_price, pos_id = pos.get('entry_price'), pos.get('id')
            if not pos_id or not entry_price: continue
            
            sl_price = pos.get('stop_loss_price')
            if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                indices_to_close.append(i); reasons_for_close[i] = "SL"; continue
            
            is_ts_active = pos.get('ts_is_active', False)
            ts_params = pm_state.get_trailing_stop_params()
            activation_pct = ts_params['activation']
            distance_pct = ts_params['distance']

            if not is_ts_active:
                if activation_pct > 0:
                    activation_price = entry_price * (1 + activation_pct / 100.0) if side == 'long' else entry_price * (1 - activation_pct / 100.0)
                    if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                        pos['ts_is_active'], pos['ts_peak_price'] = True, current_price
                        pos['ts_stop_price'] = current_price * (1 - distance_pct / 100.0) if side == 'long' else current_price * (1 + distance_pct / 100.0)
                        position_state.update_logical_position_details(side, pos_id, pos)
            else:
                peak_price, stop_price = pos.get('ts_peak_price'), pos.get('ts_stop_price')
                if peak_price is None or stop_price is None: continue
                if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                    pos['ts_peak_price'] = current_price
                    pos['ts_stop_price'] = current_price * (1 - distance_pct / 100.0) if side == 'long' else current_price * (1 + distance_pct / 100.0)
                    position_state.update_logical_position_details(side, pos_id, pos)
                if (side == 'long' and current_price <= stop_price) or (side == 'short' and current_price >= stop_price):
                    indices_to_close.append(i); reasons_for_close[i] = "TS"
        
        for index in sorted(list(set(indices_to_close)), reverse=True):
            pm_actions.close_logical_position(side, index, current_price, timestamp, reason=reasons_for_close.get(index, "UNKNOWN"))

def set_manual_trading_mode(mode: str, trade_limit: Optional[int] = None, close_open: bool = False) -> Tuple[bool, str]:
    if not pm_state.is_initialized():
        return False, "Función solo disponible en modo live interactivo."
    
    current_manual_mode = pm_state.get_manual_state()["mode"]
    
    if close_open:
        if current_manual_mode in ["LONG_ONLY", "LONG_SHORT"] and mode not in ["LONG_ONLY", "LONG_SHORT"]:
            close_all_logical_positions('long', "Cierre manual por cambio de modo")
        if current_manual_mode in ["SHORT_ONLY", "LONG_SHORT"] and mode not in ["SHORT_ONLY", "LONG_SHORT"]:
            close_all_logical_positions('short', "Cierre manual por cambio de modo")
            
    pm_state.set_manual_mode(mode.upper(), trade_limit)
    return True, f"Modo actualizado a {mode.upper()}."

def manual_close_logical_position_by_index(side: str, index: int) -> Tuple[bool, str]:
    price = get_current_price_for_exit()
    if not price: return False, "No se pudo obtener el precio de mercado actual."

    success = pm_actions.close_logical_position(side, index, price, datetime.datetime.now(), reason="MANUAL")
    return (True, f"Orden de cierre para {side.upper()} #{index} enviada.") if success else (False, f"Fallo al enviar orden de cierre.")

def add_max_logical_position_slot() -> Tuple[bool, str]:
    new_max = pm_state.get_max_logical_positions() + 1
    pm_state.set_max_logical_positions(new_max)
    balance_manager.update_operational_margins_based_on_slots(new_max)
    return True, f"Slots incrementados a {new_max}."

def remove_max_logical_position_slot() -> Tuple[bool, str]:
    current_max = pm_state.get_max_logical_positions()
    if current_max <= 1: return False, "Mínimo 1 slot."
    
    open_long_count = len(position_state.get_open_logical_positions('long'))
    open_short_count = len(position_state.get_open_logical_positions('short'))
    open_count = max(open_long_count, open_short_count)

    if (current_max - 1) < open_count:
        return False, "No se puede remover, hay más posiciones abiertas que el nuevo límite."
        
    new_max = current_max - 1
    pm_state.set_max_logical_positions(new_max)
    balance_manager.update_operational_margins_based_on_slots(new_max)
    return True, f"Slots decrementados a {new_max}."

def set_base_position_size(new_size_usdt: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    if not isinstance(new_size_usdt, (int, float)) or new_size_usdt <= 0: return False, "Tamaño inválido."
    
    old_size = pm_state.get_initial_base_position_size()
    pm_state._initial_base_position_size_usdt = new_size_usdt
    
    balance_manager.recalculate_dynamic_base_sizes()
    return True, f"Tamaño base actualizado de {old_size:.2f} a {new_size_usdt:.2f} USDT."

def set_global_stop_loss_pct(value: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    pm_state.set_global_sl_pct(value)
    return True, f"Stop Loss Global actualizado a -{value}%." if value > 0 else "Stop Loss Global desactivado."

def set_global_take_profit_pct(value: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    pm_state.set_global_tp_pct(value)
    pm_state.set_session_tp_hit(False)
    return True, f"Take Profit Global actualizado a +{value}%." if value > 0 else "Take Profit Global desactivado."

def get_session_time_limit() -> Dict[str, Any]:
    return pm_state.get_session_time_limit() if pm_state.is_initialized() else {}

def set_session_time_limit(duration: int, action: str) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    pm_state.set_session_time_limit(duration, action)
    return True, f"Límite de tiempo a {duration} min, acción: {action.upper()}." if duration > 0 else "Límite de tiempo desactivado."

def set_individual_stop_loss_pct(value: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    if not isinstance(value, (int, float)) or value < 0: return False, "Valor de SL inválido."
    pm_state.set_individual_stop_loss_pct(value)
    return True, f"Stop Loss individual para nuevas posiciones ajustado a {value:.2f}%."

def set_trailing_stop_params(activation_pct: float, distance_pct: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    if not all(isinstance(v, (int, float)) and v >= 0 for v in [activation_pct, distance_pct]):
        return False, "Valores de TS inválidos."
    pm_state.set_trailing_stop_params(activation_pct, distance_pct)
    return True, f"Trailing Stop ajustado (Activación: {activation_pct:.2f}%, Distancia: {distance_pct:.2f}%)."

def get_unrealized_pnl(current_price: float) -> float:
    if not pm_state.is_initialized(): return 0.0
    total_unrealized_pnl = 0.0
    for side in ['long', 'short']:
        for pos in position_state.get_open_logical_positions(side):
            entry = pos.get('entry_price', 0.0)
            size = pos.get('size_contracts', 0.0)
            if side == 'long': total_unrealized_pnl += (current_price - entry) * size
            else: total_unrealized_pnl += (entry - current_price) * size
    return total_unrealized_pnl

def set_leverage(new_leverage: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no está inicializado."
    if not isinstance(new_leverage, (int, float)) or not (1 <= new_leverage <= 100):
        return False, "Apalancamiento inválido. Debe ser un número entre 1 y 100."

    pm_state.set_leverage(new_leverage)
    
    if pm_state.is_live_mode():
        symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
        success = live_operations.set_leverage(symbol, str(new_leverage), str(new_leverage))
        if success:
            return True, f"Apalancamiento actualizado a {new_leverage}x (afecta a nuevas posiciones)."
        else:
            return False, f"Error al aplicar apalancamiento de {new_leverage}x en el exchange."
    
    return True, f"Apalancamiento de backtest actualizado a {new_leverage}x (afecta a nuevas posiciones)."

def set_manual_trade_limit(limit: Optional[int]) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no está inicializado."
    if limit is not None and (not isinstance(limit, int) or limit < 0):
        return False, "Límite de trades inválido. Debe ser un número entero positivo o 0."
    
    new_limit = limit if limit is not None and limit > 0 else None
    current_mode = pm_state.get_manual_state()["mode"]
    pm_state.set_manual_mode(current_mode, new_limit)
    
    limit_str = f"{new_limit} trades" if new_limit is not None else "ilimitados"
    return True, f"Límite de sesión establecido a {limit_str}."

def get_rrr_potential() -> Optional[float]:
    if not pm_state.is_initialized(): return None
    
    sl_pct = pm_state.get_individual_stop_loss_pct()
    ts_activation_pct = pm_state.get_trailing_stop_params()['activation']
    
    if sl_pct > 0 and ts_activation_pct > 0:
        return utils.safe_division(ts_activation_pct, sl_pct)
    return None

def add_conditional_trigger(condition: Dict[str, Any], action: Dict[str, Any], one_shot: bool = True) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no está inicializado."
    
    if not all(k in condition for k in ["type", "value"]) or not all(k in action for k in ["type", "params"]):
        return False, "Estructura de trigger inválida."
        
    trigger_id = f"trigger_{int(time.time() * 1000)}_{action['params'].get('mode', action.get('type', 'action'))}"
    
    trigger_data = {
        "id": trigger_id, "condition": condition, "action": action,
        "is_active": True, "one_shot": one_shot
    }
    
    pm_state.add_trigger(trigger_data)
    return True, f"Trigger '{trigger_id}' añadido con éxito."

def remove_conditional_trigger(trigger_id: str) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no está inicializado."
    
    success = pm_state.remove_trigger_by_id(trigger_id)
    return (True, f"Trigger '{trigger_id}' eliminado.") if success else (False, f"No se encontró el trigger con ID '{trigger_id}'.")

def get_active_triggers() -> list:
    if not pm_state.is_initialized(): return []
    return pm_state.get_all_triggers()

def set_trend_limits(
    duration: Optional[int], 
    tp_roi_pct: Optional[float], 
    sl_roi_pct: Optional[float],
    trade_limit: Optional[int] = None
) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no está inicializado."
    
    if trade_limit is not None:
        set_manual_trade_limit(trade_limit)

    pm_state.set_trend_limits(duration, tp_roi_pct, sl_roi_pct, "ASK")
    
    msg_parts = []
    if duration: msg_parts.append(f"Duración: {duration} min")
    if tp_roi_pct is not None and tp_roi_pct > 0: msg_parts.append(f"TP ROI: +{tp_roi_pct:.2f}%")
    if sl_roi_pct is not None and sl_roi_pct < 0: msg_parts.append(f"SL ROI: {sl_roi_pct:.2f}%")
    if trade_limit is not None: msg_parts.append(f"Trades: {trade_limit if trade_limit > 0 else 'Ilimitados'}")

    return (True, f"Límites para la próxima tendencia establecidos: {', '.join(msg_parts)}") if msg_parts else (True, "Límites de tendencia para la próxima sesión han sido desactivados.")

def start_manual_trend(
    mode: str, 
    trade_limit: Optional[int], 
    duration_limit: Optional[int], 
    tp_roi_limit: Optional[float],
    sl_roi_limit: Optional[float]
) -> Tuple[bool, str]:
    if not pm_state.is_initialized() or pm_state.get_operation_mode() != "live_interactive":
        return False, "Función solo disponible en modo live interactivo."
    
    pm_state.set_trend_limits(duration_limit, tp_roi_limit, sl_roi_limit, "ASK")
    
    success, msg = set_manual_trading_mode(mode, trade_limit=trade_limit, close_open=False)
    
    if success:
        limit_parts = []
        if trade_limit is not None: limit_parts.append(f"Trades: {trade_limit or 'inf'}")
        if duration_limit is not None: limit_parts.append(f"Dur: {duration_limit}m")
        if tp_roi_limit is not None: limit_parts.append(f"TP: +{tp_roi_limit}%")
        if sl_roi_limit is not None: limit_parts.append(f"SL: {sl_roi_limit}%")
        limit_str = f"({', '.join(limit_parts)})" if limit_parts else ""

        return True, f"Tendencia manual '{mode}' iniciada con límites {limit_str}."
    else:
        return False, f"Fallo al iniciar tendencia manual: {msg}"

def end_current_trend_and_ask():
    if not pm_state.is_initialized() or pm_state.get_operation_mode() != "live_interactive":
        return
    pm_state._manual_mode = "NEUTRAL"

def get_position_summary() -> dict:
    if not pm_state.is_initialized(): return {"error": "PM no inicializado"}
    
    open_longs = position_state.get_open_logical_positions('long')
    open_shorts = position_state.get_open_logical_positions('short')
    
    summary_dict = {
        "initialized": True, "operation_mode": pm_state.get_operation_mode(),
        "manual_mode_status": pm_state.get_manual_state(), "trend_status": pm_state.get_trend_state(),
        "leverage": pm_state.get_leverage(), "max_logical_positions": pm_state.get_max_logical_positions(),
        "initial_base_position_size_usdt": pm_state.get_initial_base_position_size(),
        "dynamic_base_size_long": pm_state.get_dynamic_base_size('long'),
        "dynamic_base_size_short": pm_state.get_dynamic_base_size('short'),
        "bm_balances": balance_manager.get_balances(), "open_long_positions_count": len(open_longs),
        "open_short_positions_count": len(open_shorts),
        "open_long_positions": [position_helpers.format_pos_for_summary(p, utils) for p in open_longs],
        "open_short_positions": [position_helpers.format_pos_for_summary(p, utils) for p in open_shorts],
        "total_realized_pnl_session": pm_state.get_total_pnl_realized(),
        "initial_total_capital": balance_manager.get_initial_total_capital(),
        "real_account_balances": {},
        "session_limits": {
            "time_limit": pm_state.get_session_time_limit(),
            "trade_limit": pm_state.get_manual_state().get("limit"),
            "trades_executed": pm_state.get_manual_state().get("executed")
        },
        "active_triggers": pm_state.get_active_triggers()
    }

    if pm_state.is_live_mode():
        if balance_manager:
            summary_dict["real_account_balances"] = balance_manager.get_real_balances_cache()
        else:
            summary_dict["real_account_balances"] = {"error": "balance_manager no disponible"}

    return summary_dict

def display_logical_positions():
    if not pm_state.is_initialized(): return
    position_state.display_logical_table('long')
    position_state.display_logical_table('short')

def get_current_price_for_exit() -> Optional[float]:
    try:
        from connection import ticker
        price_info = ticker.get_latest_price()
        return price_info.get('price')
    except Exception: return None

def close_all_logical_positions(side: str, reason: str = "MANUAL_ALL") -> bool:
    price = get_current_price_for_exit()
    if not price:
        memory_logger.log(f"CIERRE TOTAL FALLIDO: No se pudo obtener el precio de mercado para {side.upper()}.", level="ERROR")
        return False
    
    initial_pos_count = len(position_state.get_open_logical_positions(side))
    if initial_pos_count == 0:
        return True
        
    intentos_maximos = initial_pos_count + 3
    intentos = 0
    
    memory_logger.log(f"Iniciando cierre total de posiciones {side.upper()}. {initial_pos_count} posiciones detectadas.", level="INFO")

    while len(position_state.get_open_logical_positions(side)) > 0 and intentos < intentos_maximos:
        success = pm_actions.close_logical_position(side, 0, price, datetime.datetime.now(), reason=reason)
        
        if not success:
            memory_logger.log(f"Fallo en el intento de cierre para la posición {side.upper()} en índice 0. Reintentando si quedan más.", level="WARN")

        intentos += 1
        time.sleep(0.2)

    remaining_positions = len(position_state.get_open_logical_positions(side))
    if remaining_positions == 0:
        memory_logger.log(f"CIERRE TOTAL ÉXITOSO: Todas las posiciones {side.upper()} han sido cerradas lógicamente.", level="INFO")
        return True
    else:
        memory_logger.log(f"CIERRE TOTAL FALLIDO: {remaining_positions} posiciones {side.upper()} permanecen abiertas después de {intentos} intentos.", level="ERROR")
        return False

def get_global_sl_pct() -> Optional[float]:
    if not pm_state.is_initialized(): return None
    return pm_state.get_global_sl_pct()

# --- Nuevas funciones para que la fachada pueda acceder al estado ---
# Esto es mejor que hacer `pm_state.is_initialized()` desde fuera.
def is_initialized() -> bool:
    return pm_state.is_initialized() if pm_state else False

def get_manual_state() -> Dict[str, Any]:
    return pm_state.get_manual_state() if pm_state else {}

def get_session_start_time() -> Optional[datetime.datetime]:
    return pm_state.get_session_start_time() if pm_state else None

def get_global_tp_pct() -> Optional[float]:
    return pm_state.get_global_tp_pct() if pm_state else None

def is_session_tp_hit() -> bool:
    return pm_state.is_session_tp_hit() if pm_state else False

def get_individual_stop_loss_pct() -> float:
    return pm_state.get_individual_stop_loss_pct() if pm_state else 0.0

def get_trailing_stop_params() -> Dict[str, float]:
    return pm_state.get_trailing_stop_params() if pm_state else {'activation': 0.0, 'distance': 0.0}

def get_trend_limits() -> Dict[str, Any]:
    return pm_state.get_trend_limits() if pm_state else {}
    
def get_trend_state() -> Dict[str, Any]:
    return pm_state.get_trend_state() if pm_state else {}
    
def get_all_triggers() -> list:
    return pm_state.get_all_triggers() if pm_state else []

def update_trigger_status(trigger_id: str, is_active: bool):
    if pm_state: pm_state.update_trigger_status(trigger_id, is_active)