# =============== INICIO ARCHIVO: core/strategy/pm_facade.py (COMPLETO Y MODIFICADO) ===============
"""
Fachada Pública y Orquestador de Alto Nivel para el Position Manager (v16.0).

Este módulo es el único punto de entrada para el resto del sistema.
Delega la gestión del estado a `pm_state`, las reglas a `pm_rules` y las
acciones a `pm_actions`, manteniendo este archivo limpio y enfocado en la orquestación.
"""
import datetime
import time
import traceback
from typing import Optional, Dict, Any, Tuple

from core.strategy import position_calculations

# --- Dependencias del Ecosistema PM ---
from . import pm_state
from . import pm_rules
from . import pm_actions

# --- Dependencias Externas del Bot ---
from . import balance_manager
from . import position_state
from .position_executor import PositionExecutor
from . import _position_helpers
from core import utils, live_operations
import config

try:
    from core.logging import closed_position_logger
except ImportError:
    closed_position_logger = None

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

    print("[PM Facade v16.0] Inicializando Orquestador...")
    
    pm_state.reset_all_states()

    is_live = operation_mode.startswith("live") or operation_mode.startswith("automatic")

    # Configuración inicial
    base_size = base_position_size_usdt_param or getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0)
    max_pos = initial_max_logical_positions_param or getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1)
    
    # Dependencias
    try:
        from live.connection import manager as live_manager
    except ImportError:
        live_manager = None
    
    # Crear executor
    executor = PositionExecutor(
        is_live_mode=is_live,
        config=config,
        utils=utils,
        balance_manager=balance_manager,
        position_state=position_state,
        position_calculations=position_calculations,
        live_operations=live_operations,
        closed_position_logger=closed_position_logger,
        position_helpers=_position_helpers,
        live_manager=live_manager
    )

    # Establecer el estado inicial en pm_state
    pm_state.set_initial_config(
        op_mode=operation_mode,
        live_mode=is_live,
        exec_instance=executor,
        lev=getattr(config, 'POSITION_LEVERAGE', 1.0),
        max_pos=max_pos,
        base_size=base_size,
        stop_event=stop_loss_event
    )

    # Inicializar módulos dependientes
    balance_manager.initialize(operation_mode, initial_real_state, base_size, max_pos)
    position_state.initialize_state(is_live_mode=is_live)

    # Calcular tamaños dinámicos iniciales
    long_size = max(base_size, utils.safe_division(balance_manager.get_available_margin('long'), max_pos))
    short_size = max(base_size, utils.safe_division(balance_manager.get_available_margin('short'), max_pos))
    pm_state.set_dynamic_base_size(long_size, short_size)

    pm_state.set_initialized(True)
    print("[PM Facade] Orquestador Inicializado.")

def handle_low_level_signal(signal: str, entry_price: float, timestamp: datetime.datetime, market_context: str = "UNKNOWN"):
    """Punto de entrada para señales. Filtra y actúa según el modo de operación."""
    if not pm_state.is_initialized(): return
    
    operation_mode = pm_state.get_operation_mode()

    if operation_mode == "live_interactive":
        manual_mode = pm_state.get_manual_state()["mode"]
        side_to_open = 'long' if signal == "BUY" else 'short'
        
        side_allowed = False
        if side_to_open == 'long' and manual_mode in ["LONG_ONLY", "LONG_SHORT"]: side_allowed = True
        if side_to_open == 'short' and manual_mode in ["SHORT_ONLY", "LONG_SHORT"]: side_allowed = True
        
        if side_allowed and pm_rules.can_open_new_position(side_to_open):
            pm_actions.open_logical_position(side_to_open, entry_price, timestamp)
    else: # Modo automático
        current_trend = pm_state.get_trend_state()["side"]
        new_trend = None
        if "TREND_UP" in market_context: new_trend = 'long'
        elif "TREND_DOWN" in market_context: new_trend = 'short'
        
        if new_trend and new_trend != current_trend: pm_state.start_new_trend(new_trend)
        elif not new_trend and current_trend: pm_state.end_trend()
        
        if signal == "BUY" and pm_state.get_trend_state()["side"] == 'long' and "NEAR_SUPPORT" in market_context:
            if pm_rules.can_open_new_position('long'):
                pm_actions.open_logical_position('long', entry_price, timestamp)
        elif signal == "SELL" and pm_state.get_trend_state()["side"] == 'short' and "NEAR_RESISTANCE" in market_context:
            if pm_rules.can_open_new_position('short'):
                pm_actions.open_logical_position('short', entry_price, timestamp)

def check_and_close_positions(current_price: float, timestamp: datetime.datetime):
    """Revisa SL y TS para todas las posiciones abiertas."""
    if not pm_state.is_initialized(): return
    
    for side in ['long', 'short']:
        open_positions = position_state.get_open_logical_positions(side)
        if not open_positions: continue
        
        indices_to_close = []
        reasons_for_close = {} # Guarda la razón del cierre por índice
        for i, pos in enumerate(open_positions):
            entry_price = pos.get('entry_price')
            if not pos.get('id') or not entry_price: continue
            
            sl_price = pos.get('stop_loss_price')
            if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                indices_to_close.append(i)
                reasons_for_close[i] = "SL"
                continue
            
            is_ts_active = pos.get('ts_is_active', False)
            if not is_ts_active:
                activation_pct = getattr(config, 'TRAILING_STOP_ACTIVATION_PCT', 0.5)
                activation_price = entry_price * (1 + activation_pct / 100.0) if side == 'long' else entry_price * (1 - activation_pct / 100.0)
                if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                    pos['ts_is_active'] = True; pos['ts_peak_price'] = current_price
                    distance_pct = getattr(config, 'TRAILING_STOP_DISTANCE_PCT', 0.15)
                    pos['ts_stop_price'] = current_price * (1 - distance_pct / 100.0) if side == 'long' else current_price * (1 + distance_pct / 100.0)
                    position_state.update_logical_position_details(side, pos.get('id'), pos)
            else:
                peak_price = pos.get('ts_peak_price'); stop_price = pos.get('ts_stop_price')
                if peak_price is None or stop_price is None: continue
                if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                    pos['ts_peak_price'] = current_price
                    distance_pct = getattr(config, 'TRAILING_STOP_DISTANCE_PCT', 0.15)
                    pos['ts_stop_price'] = current_price * (1 - distance_pct / 100.0) if side == 'long' else current_price * (1 + distance_pct / 100.0)
                    position_state.update_logical_position_details(side, pos.get('id'), pos)
                if (side == 'long' and current_price <= stop_price) or (side == 'short' and current_price >= stop_price):
                    indices_to_close.append(i)
                    reasons_for_close[i] = "TS"
        
        for index in sorted(list(set(indices_to_close)), reverse=True):
            reason = reasons_for_close.get(index, "UNKNOWN")
            pm_actions.close_logical_position(side, index, current_price, timestamp, reason=reason)

# --- Funciones de Control Manual ---
def set_manual_trading_mode(mode: str, trade_limit: Optional[int] = None, close_open: bool = False) -> Tuple[bool, str]:
    if not pm_state.is_initialized() or pm_state.get_operation_mode() != "live_interactive":
        return False, "Función solo disponible en modo live interactivo."
    
    current_manual_mode = pm_state.get_manual_state()["mode"]
    
    if close_open:
        print("INFO [PM Facade]: Solicitud de cierre de posiciones abiertas por cambio de modo...")
        if current_manual_mode in ["LONG_ONLY", "LONG_SHORT"] and mode not in ["LONG_ONLY", "LONG_SHORT"]:
            close_all_logical_positions('long', "Cierre manual por cambio de modo")
        if current_manual_mode in ["SHORT_ONLY", "LONG_SHORT"] and mode not in ["SHORT_ONLY", "LONG_SHORT"]:
            close_all_logical_positions('short', "Cierre manual por cambio de modo")
            
    pm_state.set_manual_mode(mode.upper(), trade_limit)
    return True, f"Modo actualizado a {mode.upper()} con límite de {trade_limit or 'infinito'} trades."

def manual_close_logical_position_by_index(side: str, index: int) -> Tuple[bool, str]:
    price = get_current_price_for_exit()
    if not price: return False, "No se pudo obtener el precio de mercado actual."
    
    success = pm_actions.close_logical_position(side, index, price, datetime.datetime.now(), reason="MANUAL")
    if success:
        return True, f"Orden de cierre para {side.upper()} #{index} enviada."
    return False, f"Fallo al enviar orden de cierre para {side.upper()} #{index}."

def add_max_logical_position_slot() -> Tuple[bool, str]:
    new_max = pm_state.get_max_logical_positions() + 1
    pm_state.set_max_logical_positions(new_max)
    balance_manager.update_operational_margins_based_on_slots(new_max)
    return True, f"Slots incrementados a {new_max}."

def remove_max_logical_position_slot() -> Tuple[bool, str]:
    current_max = pm_state.get_max_logical_positions()
    if current_max <= 1: return False, "Mínimo 1 slot."
    
    open_count = max(len(position_state.get_open_logical_positions(l)) for l in ['long', 'short'])
    if (current_max - 1) < open_count:
        return False, "No se puede remover, hay más posiciones abiertas que el nuevo límite."
        
    new_max = current_max - 1
    pm_state.set_max_logical_positions(new_max)
    balance_manager.update_operational_margins_based_on_slots(new_max)
    return True, f"Slots decrementados a {new_max}."

def set_base_position_size(new_size_usdt: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    if not isinstance(new_size_usdt, (int, float)) or new_size_usdt <= 0: return False, f"Tamaño inválido."
    
    old_size = pm_state.get_initial_base_position_size()
    pm_state._initial_base_position_size_usdt = new_size_usdt # Acceso directo justificado aquí
    
    # Recalcular tamaños dinámicos
    max_pos = pm_state.get_max_logical_positions()
    long_size = max(new_size_usdt, utils.safe_division(balance_manager.get_available_margin('long'), max_pos))
    short_size = max(new_size_usdt, utils.safe_division(balance_manager.get_available_margin('short'), max_pos))
    pm_state.set_dynamic_base_size(long_size, short_size)
    
    return True, f"Tamaño base actualizado de {old_size:.2f} a {new_size_usdt:.2f} USDT."

def set_global_stop_loss_pct(value: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    pm_state.set_global_sl_pct(value)
    msg = f"Stop Loss Global actualizado a -{value}%." if value > 0 else "Stop Loss Global desactivado."
    return True, msg

def set_global_take_profit_pct(value: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    pm_state.set_global_tp_pct(value)
    msg = f"Take Profit Global actualizado a +{value}%." if value > 0 else "Take Profit Global desactivado."
    # Si se establece un nuevo TP, reseteamos el flag por si ya se había alcanzado
    pm_state.set_session_tp_hit(False) 
    return True, msg

def get_session_time_limit() -> Dict[str, Any]:
    """Devuelve la configuración actual del límite de tiempo."""
    if not pm_state.is_initialized(): return {}
    return pm_state.get_session_time_limit()

def set_session_time_limit(duration: int, action: str) -> Tuple[bool, str]:
    """Establece el límite de tiempo y la acción para la sesión."""
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    pm_state.set_session_time_limit(duration, action)
    msg = f"Límite de tiempo actualizado a {duration} minutos, acción: {action.upper()}." if duration > 0 else "Límite de tiempo desactivado."
    return True, msg

def get_position_summary() -> dict:
    if not pm_state.is_initialized(): return {"error": "PM no inicializado"}
    
    open_longs = position_state.get_open_logical_positions('long')
    open_shorts = position_state.get_open_logical_positions('short')
    
    return {
        "initialized": True,
        "operation_mode": pm_state.get_operation_mode(),
        "manual_mode_status": pm_state.get_manual_state(),
        "trend_status": pm_state.get_trend_state(),
        "leverage": pm_state.get_leverage(),
        "max_logical_positions": pm_state.get_max_logical_positions(),
        "initial_base_position_size_usdt": pm_state.get_initial_base_position_size(),
        "dynamic_base_size_long": pm_state.get_dynamic_base_size('long'),
        "dynamic_base_size_short": pm_state.get_dynamic_base_size('short'),
        "bm_balances": balance_manager.get_balances(),
        "open_long_positions_count": len(open_longs),
        "open_short_positions_count": len(open_shorts),
        "open_long_positions": [_position_helpers.format_pos_for_summary(p, utils) for p in open_longs],
        "open_short_positions": [_position_helpers.format_pos_for_summary(p, utils) for p in open_shorts],
        "total_realized_pnl_session": pm_state.get_total_pnl_realized(),
        "initial_total_capital": balance_manager.get_initial_total_capital(),
    }

def display_logical_positions():
    if not pm_state.is_initialized(): return
    position_state.display_logical_table('long')
    position_state.display_logical_table('short')

# --- Funciones de Ayuda y Cierre Forzoso ---
def get_current_price_for_exit() -> Optional[float]:
    try:
        from live.connection import ticker
        price_info = ticker.get_latest_price()
        return price_info.get('price')
    except Exception: return None

def close_all_logical_positions(side: str, reason: str = "MANUAL_ALL") -> bool:
    price = get_current_price_for_exit()
    if not price:
        print(f"ERROR: No se pudo cerrar todo en {side}, sin precio de mercado.")
        return False
    
    open_positions = position_state.get_open_logical_positions(side)
    print(f"--- Solicitud de cierre forzoso de {len(open_positions)} posiciones {side.upper()} ---")
    
    for i in sorted(range(len(open_positions)), reverse=True):
        pm_actions.close_logical_position(side, i, price, datetime.datetime.now(), reason=reason)
        time.sleep(0.1) # Pequeña pausa entre cierres
        
    return len(position_state.get_open_logical_positions(side)) == 0
# =============== FIN ARCHIVO: core/strategy/pm_facade.py (COMPLETO Y MODIFICADO) ===============