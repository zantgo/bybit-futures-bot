# =============== INICIO ARCHIVO: core/strategy/pm_facade.py (CORREGIDO Y COMPLETO) ===============
"""
Fachada Pública y Orquestador de Alto Nivel para el Position Manager (v18.0).

Este módulo es el único punto de entrada para el resto del sistema.
Delega la gestión del estado a `pm_state`, las reglas a `pm_rules` y las
acciones a `pm_actions`, manteniendo este archivo limpio y enfocado en la orquestación.

v18.0:
- Eliminado el paso de `pm_state` al constructor de `PositionExecutor` para
  resolver el problema de orden de dependencias.
- Modificado get_position_summary para incluir balances reales en modo live.
"""
import datetime
import time
import traceback
from typing import Optional, Dict, Any, Tuple
from core.logging import _memory_logger # <-- AÑADIDO

from core.strategy import position_calculations

# --- Dependencias del Ecosistema PM ---
from . import _state
from . import _rules
from . import _actions

# --- Dependencias Externas del Bot ---
from . import _balance
from . import _position_state
from ._executor import PositionExecutor
from . import _helpers
from core import _utils, live_operations
import config as config

try:
    from core.logging import _close_position_logger
except ImportError:
    _close_position_logger = None

def initialize(
    operation_mode: str,
    initial_real_state: Optional[Dict[str, Dict[str, Any]]] = None,
    base_position_size_usdt_param: Optional[float] = None,
    initial_max_logical_positions_param: Optional[int] = None,
    stop_loss_event: Optional[Any] = None
):
    """Inicializa todos los componentes del Position Manager."""
    if not getattr(config, 'POSITION_MANAGEMENT_ENABLED', False):
        # Usamos print aquí porque es un mensaje de inicialización de bajo nivel.
        print("[PM Facade] Init omitida (Gestión Desactivada).")
        return

    _memory_logger.log("PM Facade v18.0: Inicializando Orquestador...", level="INFO")
    
    _state.reset_all_states()
    is_live = operation_mode.startswith("live") or operation_mode == "automatic"

    # Configuración inicial
    base_size = base_position_size_usdt_param or getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0)
    max_pos = initial_max_logical_positions_param or getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1)
    
    # Dependencias
    try:
        from live.connection import manager as live_manager
    except ImportError:
        live_manager = None
    
    executor = PositionExecutor(
        is_live_mode=is_live, config=config, utils=_utils,
        balance_manager=_balance, position_state=_position_state,
        position_calculations=position_calculations, live_operations=live_operations,
        closed_position_logger=_close_position_logger, position_helpers=_helpers,
        live_manager=live_manager
    )

    # Establecer el estado inicial en pm_state
    _state.set_initial_config(
        op_mode=operation_mode, live_mode=is_live, exec_instance=executor,
        lev=getattr(config, 'POSITION_LEVERAGE', 1.0), max_pos=max_pos,
        base_size=base_size, stop_event=stop_loss_event
    )

    # Inicializar Balance Manager con balances reales si es posible
    real_balances_for_init = initial_real_state
    if is_live and not real_balances_for_init and live_manager:
        _memory_logger.log("PM Facade: Obteniendo balances reales para inicialización...", level="INFO")
        real_balances_for_init = {}
        for acc_name in live_manager.get_initialized_accounts():
            real_balances_for_init[acc_name] = {'unified_balance': live_operations.get_unified_account_balance_info(acc_name)}

    _balance.initialize(operation_mode, real_balances_for_init, base_size, max_pos)
    _position_state.initialize_state(is_live_mode=is_live)
    
    _state.set_initialized(True)
    _memory_logger.log("PM Facade: Orquestador Inicializado.", level="INFO")

def handle_low_level_signal(signal: str, entry_price: float, timestamp: datetime.datetime, market_context: str = "UNKNOWN"):
    """Punto de entrada para señales. Filtra y actúa según el modo de operación."""
    if not _state.is_initialized(): return
    
    operation_mode = _state.get_operation_mode()

    if operation_mode == "live_interactive":
        manual_mode = _state.get_manual_state()["mode"]
        side_to_open = 'long' if signal == "BUY" else 'short'
        
        side_allowed = (side_to_open == 'long' and manual_mode in ["LONG_ONLY", "LONG_SHORT"]) or \
                       (side_to_open == 'short' and manual_mode in ["SHORT_ONLY", "LONG_SHORT"])
        
        if side_allowed and _rules.can_open_new_position(side_to_open):
            _actions.open_logical_position(side_to_open, entry_price, timestamp)
    else: # Modo automático
        current_trend = _state.get_trend_state()["side"]
        new_trend = 'long' if "TREND_UP" in market_context else 'short' if "TREND_DOWN" in market_context else None
        
        if new_trend and new_trend != current_trend: _state.start_new_trend(new_trend)
        elif not new_trend and current_trend: _state.end_trend()
        
        if (signal == "BUY" and _state.get_trend_state()["side"] == 'long' and "NEAR_SUPPORT" in market_context and _rules.can_open_new_position('long')):
            _actions.open_logical_position('long', entry_price, timestamp)
        elif (signal == "SELL" and _state.get_trend_state()["side"] == 'short' and "NEAR_RESISTANCE" in market_context and _rules.can_open_new_position('short')):
            _actions.open_logical_position('short', entry_price, timestamp)

def check_and_close_positions(current_price: float, timestamp: datetime.datetime):
    """Revisa SL y TS para todas las posiciones abiertas."""
    if not _state.is_initialized(): return
    
    for side in ['long', 'short']:
        open_positions = _position_state.get_open_logical_positions(side)
        if not open_positions: continue
        
        indices_to_close = []
        reasons_for_close = {}
        for i, pos in enumerate(open_positions):
            entry_price, pos_id = pos.get('entry_price'), pos.get('id')
            if not pos_id or not entry_price: continue
            
            # 1. Comprobar Stop Loss Fijo
            sl_price = pos.get('stop_loss_price')
            if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                indices_to_close.append(i); reasons_for_close[i] = "SL"; continue
            
            # 2. Comprobar Trailing Stop
            is_ts_active = pos.get('ts_is_active', False)
            ts_params = _state.get_trailing_stop_params()
            activation_pct = ts_params['activation']
            distance_pct = ts_params['distance']

            if not is_ts_active:
                if activation_pct > 0:
                    activation_price = entry_price * (1 + activation_pct / 100.0) if side == 'long' else entry_price * (1 - activation_pct / 100.0)
                    if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                        pos['ts_is_active'], pos['ts_peak_price'] = True, current_price
                        pos['ts_stop_price'] = current_price * (1 - distance_pct / 100.0) if side == 'long' else current_price * (1 + distance_pct / 100.0)
                        _position_state.update_logical_position_details(side, pos_id, pos)
            else:
                peak_price, stop_price = pos.get('ts_peak_price'), pos.get('ts_stop_price')
                if peak_price is None or stop_price is None: continue
                if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                    pos['ts_peak_price'] = current_price
                    pos['ts_stop_price'] = current_price * (1 - distance_pct / 100.0) if side == 'long' else current_price * (1 + distance_pct / 100.0)
                    _position_state.update_logical_position_details(side, pos_id, pos)
                if (side == 'long' and current_price <= stop_price) or (side == 'short' and current_price >= stop_price):
                    indices_to_close.append(i); reasons_for_close[i] = "TS"
        
        for index in sorted(list(set(indices_to_close)), reverse=True):
            _actions.close_logical_position(side, index, current_price, timestamp, reason=reasons_for_close.get(index, "UNKNOWN"))

# --- Funciones de Control Manual ---
def set_manual_trading_mode(mode: str, trade_limit: Optional[int] = None, close_open: bool = False) -> Tuple[bool, str]:
    if not _state.is_initialized() or _state.get_operation_mode() != "live_interactive":
        return False, "Función solo disponible en modo live interactivo."
    
    current_manual_mode = _state.get_manual_state()["mode"]
    
    if close_open:
        if current_manual_mode in ["LONG_ONLY", "LONG_SHORT"] and mode not in ["LONG_ONLY", "LONG_SHORT"]:
            close_all_logical_positions('long', "Cierre manual por cambio de modo")
        if current_manual_mode in ["SHORT_ONLY", "LONG_SHORT"] and mode not in ["SHORT_ONLY", "LONG_SHORT"]:
            close_all_logical_positions('short', "Cierre manual por cambio de modo")
            
    _state.set_manual_mode(mode.upper(), trade_limit)
    return True, f"Modo actualizado a {mode.upper()}."

# # --- CÓDIGO ANTIGUO COMENTADO POR SOLICITUD ---
# def manual_close_logical_position_by_index(side: str, index: int) -> Tuple[bool, str]:
#     price = get_current_price_for_exit()
#     if not price: return False, "No se pudo obtener el precio de mercado actual."
#
#     success = pm_actions.close_logical_position(side, index, price, datetime.datetime.now(), reason="MANUAL")
#     return (True, f"Orden de cierre para {side.upper()} #{index} enviada.") if success else (False, f"Fallo al enviar orden de cierre.")

# REEMPLAZO de manual_close_logical_position_by_index
def manual_close_logical_position_by_index(side: str, index: int) -> Tuple[bool, str]:
    """
    Cierra una posición lógica específica por su índice.
    Devuelve un feedback inmediato sobre el éxito de la operación.
    """
    price = get_current_price_for_exit()
    if not price:
        return False, "No se pudo obtener el precio de mercado actual para el cierre."
    
    # pm_actions.close_logical_position devuelve True/False indicando el éxito
    success = _actions.close_logical_position(side, index, price, datetime.datetime.now(), reason="MANUAL")
    
    if success:
        return True, f"Orden de cierre para {side.upper()} #{index} enviada y procesada lógicamente con éxito."
    else:
        return False, f"FALLO al cerrar {side.upper()} #{index}. La API pudo haber rechazado la orden. Revisa los logs."

def add_max_logical_position_slot() -> Tuple[bool, str]:
    new_max = _state.get_max_logical_positions() + 1
    _state.set_max_logical_positions(new_max)
    _balance.update_operational_margins_based_on_slots(new_max)
    return True, f"Slots incrementados a {new_max}."

def remove_max_logical_position_slot() -> Tuple[bool, str]:
    current_max = _state.get_max_logical_positions()
    if current_max <= 1: return False, "Mínimo 1 slot."
    
    open_long_count = len(_position_state.get_open_logical_positions('long'))
    open_short_count = len(_position_state.get_open_logical_positions('short'))
    open_count = max(open_long_count, open_short_count)

    if (current_max - 1) < open_count:
        return False, "No se puede remover, hay más posiciones abiertas que el nuevo límite."
        
    new_max = current_max - 1
    _state.set_max_logical_positions(new_max)
    _balance.update_operational_margins_based_on_slots(new_max)
    return True, f"Slots decrementados a {new_max}."

def set_base_position_size(new_size_usdt: float) -> Tuple[bool, str]:
    if not _state.is_initialized(): return False, "PM no inicializado."
    if not isinstance(new_size_usdt, (int, float)) or new_size_usdt <= 0: return False, "Tamaño inválido."
    
    old_size = _state.get_initial_base_position_size()
    _state._initial_base_position_size_usdt = new_size_usdt # Acceso directo justificado para el valor "de referencia"
    
    # Recalcular tamaños dinámicos
    _balance.recalculate_dynamic_base_sizes()
    return True, f"Tamaño base actualizado de {old_size:.2f} a {new_size_usdt:.2f} USDT."

def set_global_stop_loss_pct(value: float) -> Tuple[bool, str]:
    if not _state.is_initialized(): return False, "PM no inicializado."
    _state.set_global_sl_pct(value)
    return True, f"Stop Loss Global actualizado a -{value}%." if value > 0 else "Stop Loss Global desactivado."

def set_global_take_profit_pct(value: float) -> Tuple[bool, str]:
    if not _state.is_initialized(): return False, "PM no inicializado."
    _state.set_global_tp_pct(value)
    _state.set_session_tp_hit(False) # Si se cambia, se resetea el flag de "alcanzado"
    return True, f"Take Profit Global actualizado a +{value}%." if value > 0 else "Take Profit Global desactivado."

def get_session_time_limit() -> Dict[str, Any]:
    return _state.get_session_time_limit() if _state.is_initialized() else {}

def set_session_time_limit(duration: int, action: str) -> Tuple[bool, str]:
    if not _state.is_initialized(): return False, "PM no inicializado."
    _state.set_session_time_limit(duration, action)
    return True, f"Límite de tiempo a {duration} min, acción: {action.upper()}." if duration > 0 else "Límite de tiempo desactivado."

def set_individual_stop_loss_pct(value: float) -> Tuple[bool, str]:
    """Ajusta el SL individual para las NUEVAS posiciones que se abran."""
    if not _state.is_initialized(): return False, "PM no inicializado."
    if not isinstance(value, (int, float)) or value < 0: return False, "Valor de SL inválido."
    _state.set_individual_stop_loss_pct(value)
    return True, f"Stop Loss individual para nuevas posiciones ajustado a {value:.2f}%."

def set_trailing_stop_params(activation_pct: float, distance_pct: float) -> Tuple[bool, str]:
    """Ajusta los parámetros del Trailing Stop para TODAS las posiciones."""
    if not _state.is_initialized(): return False, "PM no inicializado."
    if not all(isinstance(v, (int, float)) and v >= 0 for v in [activation_pct, distance_pct]):
        return False, "Valores de TS inválidos."
    _state.set_trailing_stop_params(activation_pct, distance_pct)
    return True, f"Trailing Stop ajustado (Activación: {activation_pct:.2f}%, Distancia: {distance_pct:.2f}%)."

def get_unrealized_pnl(current_price: float) -> float:
    """Calcula el PNL no realizado total de todas las posiciones abiertas."""
    if not _state.is_initialized(): return 0.0
    total_unrealized_pnl = 0.0
    for side in ['long', 'short']:
        for pos in _position_state.get_open_logical_positions(side):
            entry = pos.get('entry_price', 0.0)
            size = pos.get('size_contracts', 0.0)
            if side == 'long': total_unrealized_pnl += (current_price - entry) * size
            else: total_unrealized_pnl += (entry - current_price) * size
    return total_unrealized_pnl

# <<< INICIO DE NUEVAS FUNCIONES PARA CONTROL AVANZADO >>>

def set_leverage(new_leverage: float) -> Tuple[bool, str]:
    """
    Establece el apalancamiento para futuras operaciones y lo aplica en el exchange.
    """
    if not _state.is_initialized(): return False, "PM no está inicializado."
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

def set_manual_trade_limit(limit: Optional[int]) -> Tuple[bool, str]:
    """
    Establece un límite al número de trades para la sesión manual actual.
    """
    if not _state.is_initialized(): return False, "PM no está inicializado."
    if limit is not None and (not isinstance(limit, int) or limit < 0):
        return False, "Límite de trades inválido. Debe ser un número entero positivo o 0."
    
    new_limit = limit if limit is not None and limit > 0 else None
    current_mode = _state.get_manual_state()["mode"]
    # Re-aplica el modo para resetear el contador de trades con el nuevo límite
    _state.set_manual_mode(current_mode, new_limit)
    
    limit_str = f"{new_limit} trades" if new_limit is not None else "ilimitados"
    return True, f"Límite de sesión establecido a {limit_str}."

def get_rrr_potential() -> Optional[float]:
    """
    Calcula el Risk/Reward Ratio Potencial hasta la activación del Trailing Stop.
    """
    if not _state.is_initialized(): return None
    
    sl_pct = _state.get_individual_stop_loss_pct()
    ts_activation_pct = _state.get_trailing_stop_params()['activation']
    
    if sl_pct > 0 and ts_activation_pct > 0:
        return _utils.safe_division(ts_activation_pct, sl_pct)
    return None

def add_conditional_trigger(condition: Dict[str, Any], action: Dict[str, Any], one_shot: bool = True) -> Tuple[bool, str]:
    """
    Añade una nueva regla de trigger condicional.
    """
    if not _state.is_initialized(): return False, "PM no está inicializado."
    
    # Validación básica (se puede expandir)
    if not all(k in condition for k in ["type", "value"]) or not all(k in action for k in ["type", "params"]):
        return False, "Estructura de trigger inválida."
        
    trigger_id = f"trigger_{int(time.time() * 1000)}_{action['params'].get('mode', action.get('type', 'action'))}"
    
    trigger_data = {
        "id": trigger_id,
        "condition": condition,
        "action": action,
        "is_active": True,
        "one_shot": one_shot
    }
    
    _state.add_trigger(trigger_data)
    return True, f"Trigger '{trigger_id}' añadido con éxito."

def remove_conditional_trigger(trigger_id: str) -> Tuple[bool, str]:
    """
    Elimina un trigger condicional por su ID.
    """
    if not _state.is_initialized(): return False, "PM no está inicializado."
    
    success = _state.remove_trigger_by_id(trigger_id)
    if success:
        return True, f"Trigger '{trigger_id}' eliminado."
    else:
        return False, f"No se encontró el trigger con ID '{trigger_id}'."

def get_active_triggers() -> list:
    """
    Obtiene la lista de todos los triggers condicionales.
    """
    if not _state.is_initialized(): return []
    return _state.get_all_triggers()

# <<< FIN DE NUEVAS FUNCIONES PARA CONTROL AVANZADO >>>

# <<< INICIO DE MODIFICACIONES PARA CONTROL DE TENDENCIA >>>

def set_trend_limits(
    duration: Optional[int], 
    tp_roi_pct: Optional[float], 
    sl_roi_pct: Optional[float],
    trade_limit: Optional[int] = None
) -> Tuple[bool, str]:
    """
    Establece los límites (duración, TP/SL ROI, trades) para la PRÓXIMA tendencia manual.
    """
    if not _state.is_initialized(): return False, "PM no está inicializado."
    
    # El límite de trades se asocia al modo, así que se gestiona a través de set_manual_trade_limit.
    if trade_limit is not None:
        set_manual_trade_limit(trade_limit)

    # La acción al finalizar se mantiene como "ASK", ya que el TUI lo gestionará.
    _state.set_trend_limits(duration, tp_roi_pct, sl_roi_pct, "ASK")
    
    msg_parts = []
    if duration: msg_parts.append(f"Duración: {duration} min")
    if tp_roi_pct is not None and tp_roi_pct > 0: msg_parts.append(f"TP ROI: +{tp_roi_pct:.2f}%")
    if sl_roi_pct is not None and sl_roi_pct < 0: msg_parts.append(f"SL ROI: {sl_roi_pct:.2f}%")
    if trade_limit is not None: msg_parts.append(f"Trades: {trade_limit if trade_limit > 0 else 'Ilimitados'}")

    if not msg_parts:
        return True, "Límites de tendencia para la próxima sesión han sido desactivados."
    
    return True, f"Límites para la próxima tendencia establecidos: {', '.join(msg_parts)}."

# --- CÓDIGO ANTERIOR (COMENTADO) ---
# def set_trend_limits(duration: Optional[int], roi: Optional[float], action_on_end: str = "ASK") -> Tuple[bool, str]:
#     """Establece los límites para la próxima tendencia que se active."""
#     if not pm_state.is_initialized(): return False, "PM no está inicializado."
#     
#     pm_state.set_trend_limits(duration, roi, action_on_end)
#     
#     msg_parts = []
#     if duration: msg_parts.append(f"Duración: {duration} min")
#     if roi: msg_parts.append(f"ROI: {roi:.2f}%")
#     if not msg_parts:
#         return True, "Límites de tendencia desactivados."
#     
#     return True, f"Límites para la próxima tendencia establecidos: {', '.join(msg_parts)}."

def start_manual_trend(
    mode: str, 
    trade_limit: Optional[int], 
    duration_limit: Optional[int], 
    tp_roi_limit: Optional[float],
    sl_roi_limit: Optional[float]
) -> Tuple[bool, str]:
    """
    Inicia una nueva tendencia manual con límites específicos.
    Esta función está diseñada para ser llamada por un trigger.
    """
    if not _state.is_initialized() or _state.get_operation_mode() != "live_interactive":
        return False, "Función solo disponible en modo live interactivo."
    
    # 1. Establecer los límites de duración y ROI para la tendencia que vamos a iniciar.
    _state.set_trend_limits(duration_limit, tp_roi_limit, sl_roi_limit, "ASK")
    
    # 2. Cambiar al modo de trading deseado, aplicando el límite de trades.
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
    """
    Finaliza la tendencia actual, cambia el modo a NEUTRAL y pregunta al usuario
    qué hacer con las posiciones abiertas.
    NOTA: La "pregunta" se gestiona en la TUI, esta función prepara el estado.
    """
    if not _state.is_initialized() or _state.get_operation_mode() != "live_interactive":
        return
    
    _state._manual_mode = "NEUTRAL"
    
# <<< FIN DE MODIFICACIONES PARA CONTROL DE TENDENCIA >>>

def get_position_summary() -> dict:
    if not _state.is_initialized(): return {"error": "PM no inicializado"}
    
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
        "open_long_positions": [_helpers.format_pos_for_summary(p, _utils) for p in open_longs],
        "open_short_positions": [_helpers.format_pos_for_summary(p, _utils) for p in open_shorts],
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

def display_logical_positions():
    if not _state.is_initialized(): return
    _position_state.display_logical_table('long')
    _position_state.display_logical_table('short')

# --- Funciones de Ayuda y Cierre Forzoso ---
def get_current_price_for_exit() -> Optional[float]:
    try:
        from live.connection import ticker
        price_info = ticker.get_latest_price()
        return price_info.get('price')
    except Exception: return None

# # --- CÓDIGO ANTIGUO COMENTADO POR SOLICITUD ---
# def close_all_logical_positions(side: str, reason: str = "MANUAL_ALL") -> bool:
#     price = get_current_price_for_exit()
#     if not price:
#         memory_logger.log(f"ERROR: No se pudo cerrar todo en {side}, sin precio de mercado.", level="ERROR")
#         return False
#
#     open_positions = position_state.get_open_logical_positions(side)
#     if not open_positions: return True
#
#     memory_logger.log(f"Solicitud de cierre forzoso de {len(open_positions)} posiciones {side.upper()}", level="INFO")
#
#     for i in sorted(range(len(open_positions)), reverse=True):
#         pm_actions.close_logical_position(side, i, price, datetime.datetime.now(), reason=reason)
#         time.sleep(0.1)
#
#     return len(position_state.get_open_logical_positions(side)) == 0

# REEMPLAZO de close_all_logical_positions con la versión corregida:
def close_all_logical_positions(side: str, reason: str = "MANUAL_ALL") -> bool:
    """
    Cierra TODAS las posiciones lógicas de un lado de forma robusta,
    iterando hasta que la lista de posiciones lógicas esté vacía.
    """
    price = get_current_price_for_exit()
    if not price:
        _memory_logger.log(f"CIERRE TOTAL FALLIDO: No se pudo obtener el precio de mercado para {side.upper()}.", level="ERROR")
        return False
    
    # Bucle 'while' para asegurar que se intentan cerrar todas, incluso si alguna falla
    # y no se elimina de la lista. Se añade un contador para evitar bucles infinitos.
    initial_pos_count = len(_position_state.get_open_logical_positions(side))
    if initial_pos_count == 0:
        return True # No hay nada que cerrar
        
    intentos_maximos = initial_pos_count + 3 # Un margen de seguridad
    intentos = 0
    
    _memory_logger.log(f"Iniciando cierre total de posiciones {side.upper()}. {initial_pos_count} posiciones detectadas.", level="INFO")

    while len(_position_state.get_open_logical_positions(side)) > 0 and intentos < intentos_maximos:
        # Siempre cerramos la posición en el índice 0.
        # Si tiene éxito, la siguiente posición pasará a ser el nuevo índice 0.
        success = _actions.close_logical_position(side, 0, price, datetime.datetime.now(), reason=reason)
        
        if not success:
            _memory_logger.log(f"Fallo en el intento de cierre para la posición {side.upper()} en índice 0. Reintentando si quedan más.", level="WARN")
            # Si el cierre falla, la posición NO se elimina, y en la siguiente iteración
            # se volverá a intentar. Si el problema persiste, el bucle se romperá por `intentos_maximos`.

        intentos += 1
        time.sleep(0.2) # Pequeña pausa entre cada intento de cierre para no saturar la API

    remaining_positions = len(_position_state.get_open_logical_positions(side))
    if remaining_positions == 0:
        _memory_logger.log(f"CIERRE TOTAL ÉXITOSO: Todas las posiciones {side.upper()} han sido cerradas lógicamente.", level="INFO")
        return True
    else:
        _memory_logger.log(f"CIERRE TOTAL FALLIDO: {remaining_positions} posiciones {side.upper()} permanecen abiertas después de {intentos} intentos. Revisa los logs de la API.", level="ERROR")
        return False

def get_global_sl_pct() -> Optional[float]:
    """Devuelve el umbral de Stop Loss Global por ROI actual."""
    if not _state.is_initialized(): return None
    return _state.get_global_sl_pct()

# =============== FIN ARCHIVO: core/strategy/pm_facade.py (CORREGIDO Y COMPLETO) ===============