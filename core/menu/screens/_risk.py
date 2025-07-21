# core/menu/screens/_risk.py

"""
Módulo para la pantalla de "Ajustar Parámetros de Riesgo" de la TUI.

Esta pantalla permite al usuario modificar en tiempo real los parámetros
clave de gestión de riesgo, como el apalancamiento, el Stop Loss individual
y los parámetros del Trailing Stop.
"""
import sys
import os
import time
from typing import Dict, Any, Optional

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias
try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

try:
    from core.strategy import pm as position_manager
    from .._helpers import (
        get_input,
        MENU_STYLE
    )
except ImportError as e:
    print(f"ERROR [TUI Risk Screen]: Falló importación de dependencias: {e}")
    position_manager = None
    MENU_STYLE = {}
    def get_input(prompt, type_func, default, min_val=None, max_val=None): return default

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Pantalla de Gestión de Riesgo ---

def show_risk_menu():
    """Muestra el menú para ajustar parámetros de riesgo en un bucle."""
    if not TerminalMenu or not position_manager:
        print("\nError: Dependencias de menú no disponibles (TerminalMenu o PositionManager).")
        time.sleep(2)
        return

    while True:
        summary = position_manager.get_position_summary()
        if not summary or summary.get('error'):
            print(f"Error al obtener resumen del bot: {summary.get('error', 'Desconocido')}")
            time.sleep(2)
            break
            
        leverage = summary.get('leverage', 0.0)
        sl_ind = position_manager.get_individual_stop_loss_pct()
        ts_params = position_manager.get_trailing_stop_params()
        
        menu_items = [
            f"[1] Ajustar Apalancamiento (Actual: {leverage:.1f}x)",
            f"[2] Ajustar Stop Loss Individual (Actual: {sl_ind:.2f}%)",
            f"[3] Ajustar Trailing Stop (Actual: Act {ts_params['activation']:.2f}% / Dist {ts_params['distance']:.2f}%)",
            None,
            "[b] Volver al menú principal"
        ]
        
        title = "Ajustar Parámetros de Riesgo"
        
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            new_lev = get_input("\nNuevo Apalancamiento (afecta a nuevas posiciones)", float, leverage, min_val=1.0, max_val=100.0)
            success, msg = position_manager.set_leverage(new_lev)
            print(f"\n{msg}")
            time.sleep(2.0)
        elif choice_index == 1:
            new_sl = get_input("\nNuevo % de Stop Loss Individual (0 para desactivar)", float, sl_ind, min_val=0.0)
            success, msg = position_manager.set_individual_stop_loss_pct(new_sl)
            print(f"\n{msg}")
            time.sleep(1.5)
        elif choice_index == 2:
            print("\n--- Ajustar Trailing Stop (para todas las posiciones) ---")
            new_act = get_input("Nuevo % de Activación (0 para desactivar)", float, ts_params['activation'], min_val=0.0)
            new_dist = get_input("Nuevo % de Distancia", float, ts_params['distance'], min_val=0.0)
            success, msg = position_manager.set_trailing_stop_params(new_act, new_dist)
            print(f"\n{msg}")
            time.sleep(1.5)
        else: # Si el usuario presiona 'b', ESC o elige una opción nula
            break