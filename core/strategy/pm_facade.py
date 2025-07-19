# =============== INICIO ARCHIVO: core/strategy/pm_facade.py (MODIFICADO) ===============
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

    print("[PM Facade v18.0] Inicializando Orquestador...")
    
    pm_state.reset_all_states()
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
        is_live_mode=is_live, config=config, utils=utils,
        balance_manager=balance_manager, position_state=position_state,
        position_calculations=position_calculations, live_operations=live_operations,
        closed_position_logger=closed_position_logger, position_helpers=_position_helpers,
        live_manager=live_manager
    )

    # Establecer el estado inicial en pm_state
    pm_state.set_initial_config(
        op_mode=operation_mode, live_mode=is_live, exec_instance=executor,
        lev=getattr(config, 'POSITION_LEVERAGE', 1.0), max_pos=max_pos,
        base_size=base_size, stop_event=stop_loss_event
    )

    # Inicializar Balance Manager con balances reales si es posible
    real_balances_for_init = initial_real_state
    if is_live and not real_balances_for_init and live_manager:
        print("[PM Facade] Obteniendo balances reales para inicialización...")
        real_balances_for_init = {}
        for acc_name in live_manager.get_initialized_accounts():
            real_balances_for_init[acc_name] = {'unified_balance': live_operations.get_unified_account_balance_info(acc_name)}

    balance_manager.initialize(operation_mode, real_balances_for_init, base_size, max_pos)
    position_state.initialize_state(is_live_mode=is_live)
    
    pm_state.set_initialized(True)
    print("[PM Facade] Orquestador Inicializado.")

def handle_low_level_signal(signal: str, entry_price: float, timestamp: datetime.datetime, market_context: str = "UNKNOWN"):
    """Punto de entrada para señales. Filtra y actúa según el modo de operación."""
    if not pm_state.is_initialized(): return
    
    operation_mode = pm_state.get_operation_mode()

    if operation_mode == "live_interactive":
        manual_mode = pm_state.get_manual_state()["mode"]
        side_to_open = 'long' if signal == "BUY" else 'short'
        
        side_allowed = (side_to_open == 'long' and manual_mode in ["LONG_ONLY", "LONG_SHORT"]) or \
                       (side_to_open == 'short' and manual_mode in ["SHORT_ONLY", "LONG_SHORT"])
        
        if side_allowed and pm_rules.can_open_new_position(side_to_open):
            pm_actions.open_logical_position(side_to_open, entry_price, timestamp)
    else: # Modo automático
        current_trend = pm_state.get_trend_state()["side"]
        new_trend = 'long' if "TREND_UP" in market_context else 'short' if "TREND_DOWN" in market_context else None
        
        if new_trend and new_trend != current_trend: pm_state.start_new_trend(new_trend)
        elif not new_trend and current_trend: pm_state.end_trend()
        
        if (signal == "BUY" and pm_state.get_trend_state()["side"] == 'long' and "NEAR_SUPPORT" in market_context and pm_rules.can_open_new_position('long')):
            pm_actions.open_logical_position('long', entry_price, timestamp)
        elif (signal == "SELL" and pm_state.get_trend_state()["side"] == 'short' and "NEAR_RESISTANCE" in market_context and pm_rules.can_open_new_position('short')):
            pm_actions.open_logical_position('short', entry_price, timestamp)

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
            
            # 1. Comprobar Stop Loss Fijo
            sl_price = pos.get('stop_loss_price')
            if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                indices_to_close.append(i); reasons_for_close[i] = "SL"; continue
            
            # 2. Comprobar Trailing Stop
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

# --- Funciones de Control Manual ---
def set_manual_trading_mode(mode: str, trade_limit: Optional[int] = None, close_open: bool = False) -> Tuple[bool, str]:
    if not pm_state.is_initialized() or pm_state.get_operation_mode() != "live_interactive":
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
    pm_state._initial_base_position_size_usdt = new_size_usdt # Acceso directo justificado para el valor "de referencia"
    
    # Recalcular tamaños dinámicos
    balance_manager.recalculate_dynamic_base_sizes()
    return True, f"Tamaño base actualizado de {old_size:.2f} a {new_size_usdt:.2f} USDT."

def set_global_stop_loss_pct(value: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    pm_state.set_global_sl_pct(value)
    return True, f"Stop Loss Global actualizado a -{value}%." if value > 0 else "Stop Loss Global desactivado."

def set_global_take_profit_pct(value: float) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    pm_state.set_global_tp_pct(value)
    pm_state.set_session_tp_hit(False) # Si se cambia, se resetea el flag de "alcanzado"
    return True, f"Take Profit Global actualizado a +{value}%." if value > 0 else "Take Profit Global desactivado."

def get_session_time_limit() -> Dict[str, Any]:
    return pm_state.get_session_time_limit() if pm_state.is_initialized() else {}

def set_session_time_limit(duration: int, action: str) -> Tuple[bool, str]:
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    pm_state.set_session_time_limit(duration, action)
    return True, f"Límite de tiempo a {duration} min, acción: {action.upper()}." if duration > 0 else "Límite de tiempo desactivado."

def set_individual_stop_loss_pct(value: float) -> Tuple[bool, str]:
    """Ajusta el SL individual para las NUEVAS posiciones que se abran."""
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    if not isinstance(value, (int, float)) or value < 0: return False, "Valor de SL inválido."
    pm_state.set_individual_stop_loss_pct(value)
    return True, f"Stop Loss individual para nuevas posiciones ajustado a {value:.2f}%."

def set_trailing_stop_params(activation_pct: float, distance_pct: float) -> Tuple[bool, str]:
    """Ajusta los parámetros del Trailing Stop para TODAS las posiciones."""
    if not pm_state.is_initialized(): return False, "PM no inicializado."
    if not all(isinstance(v, (int, float)) and v >= 0 for v in [activation_pct, distance_pct]):
        return False, "Valores de TS inválidos."
    pm_state.set_trailing_stop_params(activation_pct, distance_pct)
    return True, f"Trailing Stop ajustado (Activación: {activation_pct:.2f}%, Distancia: {distance_pct:.2f}%)."

def get_unrealized_pnl(current_price: float) -> float:
    """Calcula el PNL no realizado total de todas las posiciones abiertas."""
    if not pm_state.is_initialized(): return 0.0
    total_unrealized_pnl = 0.0
    for side in ['long', 'short']:
        for pos in position_state.get_open_logical_positions(side):
            entry = pos.get('entry_price', 0.0)
            size = pos.get('size_contracts', 0.0)
            if side == 'long': total_unrealized_pnl += (current_price - entry) * size
            else: total_unrealized_pnl += (entry - current_price) * size
    return total_unrealized_pnl

def get_position_summary() -> dict:
    if not pm_state.is_initialized(): return {"error": "PM no inicializado"}
    
    open_longs = position_state.get_open_logical_positions('long')
    open_shorts = position_state.get_open_logical_positions('short')
    
    summary_dict = {
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
        # Añadir un campo por defecto para los balances reales
        "real_account_balances": {}
    }

    # <<< INICIO DE LA MODIFICACIÓN >>>
    # Si estamos en modo live, obtener y añadir los balances reales de las cuentas
    if pm_state.is_live_mode():
        try:
            from live.connection import manager as live_manager
            real_balances = {}
            if live_manager:
                accounts_to_check = [
                    config.ACCOUNT_MAIN, config.ACCOUNT_LONGS,
                    config.ACCOUNT_SHORTS, config.ACCOUNT_PROFIT
                ]
                # Usar un set para evitar duplicados si los nombres de cuenta son los mismos
                for acc_name in sorted(list(set(accounts_to_check))):
                    if acc_name in live_manager.get_initialized_accounts():
                        balance_info = live_operations.get_unified_account_balance_info(acc_name)
                        real_balances[acc_name] = balance_info if balance_info else "Error al obtener balance"
            summary_dict["real_account_balances"] = real_balances
        except ImportError:
            summary_dict["real_account_balances"] = {"error": "live_manager no disponible"}
        except Exception as e:
            summary_dict["real_account_balances"] = {"error": f"Excepción obteniendo balances: {e}"}
    # <<< FIN DE LA MODIFICACIÓN >>>

    return summary_dict

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
    if not open_positions: return True # No hay nada que cerrar

    print(f"--- Solicitud de cierre forzoso de {len(open_positions)} posiciones {side.upper()} ---")
    
    for i in sorted(range(len(open_positions)), reverse=True):
        pm_actions.close_logical_position(side, i, price, datetime.datetime.now(), reason=reason)
        time.sleep(0.1) # Pequeña pausa entre cierres
        
    return len(position_state.get_open_logical_positions(side)) == 0

def get_global_sl_pct() -> Optional[float]:
    """Devuelve el umbral de Stop Loss Global por ROI actual."""
    if not pm_state.is_initialized(): return None
    return pm_state.get_global_sl_pct()

# =============== FIN ARCHIVO: core/strategy/pm_facade.py (MODIFICADO) ===============