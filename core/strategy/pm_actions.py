# =============== INICIO ARCHIVO: core/strategy/pm_actions.py (COMPLETO) ===============
"""
Módulo de Acciones del Position Manager.

Contiene las funciones que ejecutan las operaciones de apertura y cierre,
actuando como un wrapper de alto nivel alrededor del PositionExecutor.
También actualiza el estado del PM después de cada acción.
"""
import datetime
from typing import Optional

# Dependencias del ecosistema PM y del Bot
from . import pm_state
from . import position_state
from . import balance_manager
import config
from core import utils

def open_logical_position(side: str, entry_price: float, timestamp: datetime.datetime):
    """
    Orquesta la apertura de una posición, incluyendo filtros finales y actualización de estado.
    """
    if not pm_state.is_initialized(): return
    
    executor = pm_state.get_executor()
    if not executor:
        print("ERROR [PM Actions]: PositionExecutor no está disponible.")
        return
    
    # Filtro de diferencia de precio mínimo (lógica original)
    open_positions = position_state.get_open_logical_positions(side)
    if open_positions:
        last_entry = utils.safe_float_convert(open_positions[-1].get('entry_price'), 0.0)
        if last_entry > 1e-9:
            diff_pct = utils.safe_division(entry_price - last_entry, last_entry) * 100.0
            long_thresh = getattr(config, 'POSITION_MIN_PRICE_DIFF_LONG_PCT', -1.0)
            short_thresh = getattr(config, 'POSITION_MIN_PRICE_DIFF_SHORT_PCT', 1.0)
            
            if (side == 'long' and diff_pct > long_thresh) or \
               (side == 'short' and diff_pct < short_thresh):
                if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
                    print(f"DEBUG [PM Actions]: Apertura ignorada por filtro de diferencia de precio ({diff_pct:.2f}%).")
                return
    
    margin_to_use = pm_state.get_dynamic_base_size(side)
    
    result = executor.execute_open(
        side=side, 
        entry_price=entry_price, 
        timestamp=timestamp, 
        margin_to_use=margin_to_use
    )
    
    if result and result.get('success'):
        if pm_state.get_operation_mode() == "live_interactive":
            pm_state.increment_manual_trades()

def close_logical_position(side: str, position_index: int, exit_price: float, timestamp: datetime.datetime, reason: str = "TP") -> bool:
    """
    Orquesta el cierre de una posición, actualiza contadores y maneja PNL.
    """
    if not pm_state.is_initialized(): return False
    
    executor = pm_state.get_executor()
    if not executor: 
        print("ERROR [PM Actions]: PositionExecutor no está disponible.")
        return False
    
    result = executor.execute_close(
        side=side, 
        position_index=position_index, 
        exit_price=exit_price, 
        timestamp=timestamp,
        exit_reason=reason # Pasar la razón del cierre al executor
    )
    
    success = result.get('success', False)
    if success:
        # Actualizar contadores y PNL
        pm_state.add_realized_pnl(side, result.get('pnl_net_usdt', 0.0))
        
        if pm_state.get_operation_mode() != "live_interactive":
            trend_state = pm_state.get_trend_state()
            if trend_state["side"] == side:
                pm_state.increment_trend_trades()
                print(f"INFO [PM Trend]: Trade #{pm_state.get_trend_state()['trades_count']} cerrado en tendencia {trend_state['side'].upper()}.")
        
        # Lógica de transferencia de PNL
        transfer_amount = result.get('amount_transferable_to_profit', 0.0)
        min_transfer = getattr(config, 'POSITION_MIN_TRANSFER_AMOUNT_USDT', 0.1)
        if transfer_amount >= min_transfer:
            transferred = executor.execute_transfer(transfer_amount, side)
            if transferred > 0:
                pm_state.add_transferred_profit(transferred)
                if pm_state.is_live_mode():
                    balance_manager.record_real_profit_transfer_logically(side, transferred)
    
    return success
# =============== FIN ARCHIVO: core/strategy/pm_actions.py (COMPLETO) ===============