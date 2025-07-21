# core/menu/screens/_status.py

"""
Módulo para la pantalla de "Estado Detallado" de la TUI.

Esta pantalla actúa como un dashboard principal, mostrando un resumen completo
del estado actual del bot, incluyendo balances, PNL, parámetros de riesgo y
posiciones abiertas.
"""
import sys
import os
import datetime
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
    from core.strategy import pm as position_manager
    from .._helpers import (
        clear_screen,
        print_tui_header,
        press_enter_to_continue,
        print_section
    )
except ImportError as e:
    print(f"ERROR [TUI Status Screen]: Falló importación de dependencias: {e}")
    position_manager = None
    def clear_screen(): pass
    def print_tui_header(title): print(f"--- {title} ---")
    def press_enter_to_continue(): input("Press Enter...")
    def print_section(title, data, is_account_balance=False): print(f"--- {title} --- \n {data}")

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Pantalla de Estado ---

def show_status_screen():
    """Muestra una pantalla con el estado detallado de la sesión."""
    clear_screen()
    print_tui_header("Estado Detallado de la Sesión")

    if not position_manager:
        print("\nError: El Position Manager no está disponible.")
        press_enter_to_continue()
        return
    
    summary = position_manager.get_position_summary()
    if not summary or summary.get('error'):
        print(f"\nError al obtener el estado del bot: {summary.get('error', 'Desconocido')}")
        press_enter_to_continue()
        return

    real_account_balances = summary.get('real_account_balances', {})
    if real_account_balances:
        print_section("Balances Reales de Cuentas (UTA)", real_account_balances, is_account_balance=True)

    manual_state = summary.get('manual_mode_status', {})
    limit_str = manual_state.get('limit') or 'Ilimitados'
    
    current_price = position_manager.get_current_price_for_exit() or 0.0
    unrealized_pnl = position_manager.get_unrealized_pnl(current_price)
    total_pnl = summary.get('total_realized_pnl_session', 0.0) + unrealized_pnl
    initial_capital = summary.get('initial_total_capital', 0.0)
    current_roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
    
    session_start_time = position_manager.get_session_start_time()
    roi_per_hour = 0.0
    if session_start_time:
        duration_hours = (datetime.datetime.now() - session_start_time).total_seconds() / 3600
        if duration_hours > 0:
            roi_per_hour = current_roi / duration_hours

    print_section("Estado Lógico de la Sesión (Bot)", {
        "Modo Manual Actual": f"{manual_state.get('mode', 'N/A')} (Trades: {manual_state.get('executed', 0)}/{limit_str})",
        "Precio Actual de Mercado": f"{current_price:.4f} USDT",
        "Capital Lógico Inicial": f"{initial_capital:.2f} USDT",
        "PNL Realizado (Sesión)": f"{summary.get('total_realized_pnl_session', 0.0):+.4f} USDT",
        "PNL No Realizado (Actual)": f"{unrealized_pnl:+.4f} USDT",
        "PNL Total (Estimado)": f"{total_pnl:+.4f} USDT",
        "ROI Actual (Estimado)": f"{current_roi:+.2f}%",
        "ROI Promedio por Hora": f"{roi_per_hour:+.2f}%/h",
    })

    rrr_potential = position_manager.get_rrr_potential()
    rrr_str = f"{rrr_potential:.2f}:1" if rrr_potential is not None else "N/A (SL o TS desactivado)"
    
    risk_params = {
        "Apalancamiento Actual": f"{summary.get('leverage', 0.0):.1f}x (para nuevas posiciones)",
        "RRR Potencial (a Activación TS)": rrr_str,
        "Stop Loss Individual": f"{position_manager.get_individual_stop_loss_pct() or 0.0:.2f}%",
        "Trailing Stop": f"Activación: {position_manager.get_trailing_stop_params()['activation']:.2f}% / Distancia: {position_manager.get_trailing_stop_params()['distance']:.2f}%",
    }
    print_section("Parámetros de Riesgo", risk_params)
    
    session_limits = summary.get('session_limits', {})
    time_limit = session_limits.get('time_limit', {})
    duration_str = f"{time_limit.get('duration', 0)} min (Acción: {time_limit.get('action', 'N/A')})" if time_limit.get('duration', 0) > 0 else "Desactivado"
    
    limits_data = {
        "Límite de Duración": duration_str,
        "Límite de Trades": limit_str,
        "SL Global por ROI": f"-{position_manager.get_global_sl_pct():.2f}%" if position_manager.get_global_sl_pct() else "Desactivado",
        "TP Global por ROI": f"+{position_manager.get_global_tp_pct():.2f}%" if position_manager.get_global_tp_pct() else "Desactivado",
    }
    print_section("Límites de Sesión y Disyuntores", limits_data)
    
    active_triggers = summary.get('active_triggers', [])
    if active_triggers:
        triggers_data = {}
        for i, trigger in enumerate(active_triggers):
            cond = trigger.get('condition', {})
            act = trigger.get('action', {})
            key = f"Trigger #{i+1} ({trigger.get('id', 'N/A')[-6:]})"
            value = f"Si Precio {cond.get('type', '').replace('_', ' ')} {cond.get('value')}, entonces {act.get('type', '').replace('_', ' ')} {act.get('params', {})}"
            triggers_data[key] = value
        print_section("Triggers Condicionales Activos", triggers_data)

    print("\n--- Posiciones Lógicas Abiertas ---")
    position_manager.display_logical_positions()
    
    press_enter_to_continue()