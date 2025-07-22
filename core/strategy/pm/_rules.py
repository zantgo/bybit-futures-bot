# core/strategy/pm/_rules.py

"""
Módulo para el motor de reglas del Position Manager.

Contiene la función guardiana `can_open_new_position`, que centraliza toda la
lógica y las reglas que determinan si se puede abrir una nueva posición.
"""
import traceback
from typing import Optional

# Dependencias del ecosistema PM y del Bot
from . import _state
from . import _balance
from . import _position_state
from . import _helpers
from core import utils
from core import api as live_operations
import config

def can_open_new_position(side: str) -> bool:
    """
    Función guardiana que centraliza TODAS las reglas para abrir una nueva posición.
    """
    if not _state.is_initialized(): return False
    
    # Regla Global 0: ¿Se alcanzó el TP/Límite de la sesión?
    if _state.is_session_tp_hit():
        if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
            print(f"DEBUG [PM Rules]: Apertura bloqueada, TP global/Límite de la sesión ya fue alcanzado.")
        return False

    operation_mode = _state.get_operation_mode()

    # --- REGLAS PARA MODO LIVE INTERACTIVO ---
    if operation_mode == "live_interactive":
        manual_state = _state.get_manual_state()
        manual_mode = manual_state["mode"]
        
        # Regla Manual 1: ¿El modo de trading permite abrir en este lado?
        if manual_mode == 'NEUTRAL':
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
                print(f"DEBUG [PM Rules]: Apertura bloqueada, modo manual en NEUTRAL.")
            return False
        if side == 'long' and manual_mode == 'SHORT_ONLY':
            return False
        if side == 'short' and manual_mode == 'LONG_ONLY':
            return False

        trade_limit = manual_state.get("limit")
        if trade_limit is not None:
            if manual_state["executed"] >= trade_limit:
                if not _state.is_session_tp_hit():
                    print(f"INFO [PM Rules]: Límite de trades de sesión ({trade_limit}) alcanzado. No se abrirán más posiciones.")
                    _state.set_session_tp_hit(True)
                return False

    # --- REGLAS PARA MODO AUTOMÁTICO (Mantenidas por si se reactivan) ---
    else: 
        trend_state = _state.get_trend_state()
        if trend_state["tp_hit"]:
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
                 print(f"DEBUG [PM Rules]: Apertura ignorada, TP de tendencia {side.upper()} ya alcanzado.")
            return False

        if getattr(config, 'AUTOMATIC_TRADE_LIMIT_ENABLED', False):
            limit = getattr(config, 'AUTOMATIC_MAX_TRADES_PER_TREND', 5)
            if trend_state["trades_count"] >= limit:
                print(f"INFO [PM Rules]: Límite de trades ({limit}) para tendencia {side.upper()} alcanzado.")
                _state.set_trend_tp_hit(True)
                return False
        
        if getattr(config, 'AUTOMATIC_ROI_PROFIT_TAKING_ENABLED', False):
            pnl_in_trend = _state.get_total_pnl_realized() - trend_state["initial_pnl"]
            initial_capital = _balance.get_initial_total_capital()
            if initial_capital > 1e-9:
                roi_pct = (pnl_in_trend / initial_capital) * 100
                target_roi = getattr(config, 'AUTOMATIC_ROI_PROFIT_TARGET_PCT', 0.1)
                if roi_pct >= target_roi:
                    print(f"INFO [PM Rules]: ROI Target ({target_roi}%) para tendencia {side.upper()} alcanzado.")
                    _state.set_trend_tp_hit(True)
                    return False

    # --- REGLAS COMUNES A AMBOS MODOS ---
    try:
        # Regla Común 1: Límite de slots (posiciones simultáneas)
        open_positions = _position_state.get_open_logical_positions(side)
        if len(open_positions) >= _state.get_max_logical_positions():
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
                print(f"DEBUG [PM Rules]: Límite de slots ({_state.get_max_logical_positions()}) para {side.upper()} alcanzado.")
            return False
        
        # Regla Común 2: Margen Lógico disponible
        margin_needed = _state.get_dynamic_base_size(side)
        if _balance.get_available_margin(side) < margin_needed - 1e-6:
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
                print(f"DEBUG [PM Rules]: Margen lógico insuficiente para {side.upper()}.")
            return False
            
    except Exception as e:
        print(f"ERROR [PM Rules]: Excepción en `can_open_new_position`: {e}")
        traceback.print_exc()
        return False

    # Si todas las reglas pasan, se puede abrir la posición.
    return True