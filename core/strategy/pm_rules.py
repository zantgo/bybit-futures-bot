# =============== INICIO ARCHIVO: core/strategy/pm_rules.py (COMPLETO Y MODIFICADO) ===============
"""
Módulo para el motor de reglas del Position Manager.

Contiene la función guardiana `can_open_new_position`, que centraliza toda la
lógica y las reglas que determinan si se puede abrir una nueva posición.
"""
import traceback
from typing import Optional

# Dependencias del ecosistema PM y del Bot
from . import pm_state
from . import balance_manager
from . import position_state
from . import _position_helpers
from core import utils, live_operations
import config

def can_open_new_position(side: str) -> bool:
    """
    Función guardiana que centraliza TODAS las reglas para abrir una nueva posición.
    """
    if not pm_state.is_initialized(): return False
    
    # Justo al inicio de la función, después de la guarda de inicialización
    if pm_state.is_session_tp_hit():
        if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
            print(f"DEBUG [PM Rules]: Apertura bloqueada, TP global de la sesión ya fue alcanzado.")
        return False

    operation_mode = pm_state.get_operation_mode()

    # --- REGLAS PARA MODO LIVE INTERACTIVO ---
    if operation_mode == "live_interactive":
        manual_state = pm_state.get_manual_state()
        manual_mode = manual_state["mode"]
        
        # Regla Manual 1: ¿El modo permite abrir en este lado?
        if manual_mode == 'NEUTRAL':
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
                print(f"DEBUG [PM Rules]: Apertura bloqueada, modo manual en NEUTRAL.")
            return False
        if side == 'long' and manual_mode == 'SHORT_ONLY': return False
        if side == 'short' and manual_mode == 'LONG_ONLY': return False

        # Regla Manual 2: ¿Hemos alcanzado el límite de trades?
        if manual_state["limit"] is not None:
            if manual_state["executed"] >= manual_state["limit"]:
                print(f"INFO [PM Rules]: Límite manual de trades ({manual_state['limit']}) alcanzado. No se abrirá posición.")
                return False

    # --- REGLAS PARA MODO AUTOMÁTICO ---
    else:
        trend_state = pm_state.get_trend_state()
        if trend_state["tp_hit"]:
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
                 print(f"DEBUG [PM Rules]: Apertura ignorada, TP de tendencia {side.upper()} ya alcanzado.")
            return False

        if getattr(config, 'AUTOMATIC_TRADE_LIMIT_ENABLED', False):
            limit = getattr(config, 'AUTOMATIC_MAX_TRADES_PER_TREND', 5)
            if trend_state["trades_count"] >= limit:
                print(f"INFO [PM Rules]: Límite de trades ({limit}) para tendencia {side.upper()} alcanzado.")
                pm_state.set_trend_tp_hit(True)
                return False
        
        if getattr(config, 'AUTOMATIC_ROI_PROFIT_TAKING_ENABLED', False):
            pnl_in_trend = pm_state.get_total_pnl_realized() - trend_state["initial_pnl"]
            initial_capital = balance_manager.get_initial_total_capital()
            if initial_capital > 1e-9:
                roi_pct = (pnl_in_trend / initial_capital) * 100
                target_roi = getattr(config, 'AUTOMATIC_ROI_PROFIT_TARGET_PCT', 0.1)
                if roi_pct >= target_roi:
                    print(f"INFO [PM Rules]: ROI Target ({target_roi}%) para tendencia {side.upper()} alcanzado.")
                    pm_state.set_trend_tp_hit(True)
                    return False

    # --- REGLAS COMUNES A AMBOS MODOS ---
    try:
        # Regla Común 1: Límite de slots
        open_positions = position_state.get_open_logical_positions(side)
        if len(open_positions) >= pm_state.get_max_logical_positions():
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
                print(f"DEBUG [PM Rules]: Límite de slots ({pm_state.get_max_logical_positions()}) para {side.upper()} alcanzado.")
            return False
        
        # Regla Común 2: Margen Lógico
        margin_needed = pm_state.get_dynamic_base_size(side)
        if balance_manager.get_available_margin(side) < margin_needed - 1e-6:
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
                print(f"DEBUG [PM Rules]: Margen lógico insuficiente para {side.upper()}.")
            return False
        
        # Regla Común 3: Chequeo de Sincronización Real (si es modo live)
        if pm_state.is_live_mode() and getattr(config, 'POSITION_PRE_OPEN_SYNC_CHECK', True):
            from live.connection import manager as live_manager # Importación local
            
            symbol = getattr(config, 'TICKER_SYMBOL', '')
            target_account = getattr(config, f'ACCOUNT_{side.upper()}S', None) or getattr(config, 'ACCOUNT_MAIN', 'main')
            
            if target_account in live_manager.get_initialized_accounts():
                balance_info = live_operations.get_unified_account_balance_info(target_account)
                real_balance = utils.safe_float_convert(balance_info.get('usdt_balance')) if balance_info else 0.0
                
                if real_balance < margin_needed - 1e-6:
                    print(f"WARN [PM Rules]: Chequeo Pre-Apertura falló: Margen REAL en '{target_account}' ({real_balance:.4f}) es insuficiente.")
                    return False
                
                physical_raw = live_operations.get_active_position_details_api(symbol, target_account)
                physical_state = _position_helpers.extract_physical_state_from_api(physical_raw, symbol, side, utils)
                physical_size = physical_state['total_size_contracts'] if physical_state else 0.0
                logical_size = sum(utils.safe_float_convert(p.get('size_contracts'), 0.0) for p in open_positions)

                if abs(physical_size - logical_size) > 1e-9:
                    print(f"WARN [PM Rules]: Chequeo Pre-Apertura falló: Desincronización de tamaño en '{target_account}'.")
                    return False
            
    except Exception as e:
        print(f"ERROR [PM Rules]: Excepción en `can_open_new_position`: {e}")
        traceback.print_exc()
        return False

    # Si todas las reglas pasan, se puede abrir la posición.
    return True
# =============== FIN ARCHIVO: core/strategy/pm_rules.py (COMPLETO Y MODIFICADO) ===============