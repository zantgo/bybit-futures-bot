# core/menu/screens/_mode.py

"""
Módulo para la pantalla de "Cambiar Modo de Trading" de la TUI.

Esta pantalla permite al usuario cambiar el comportamiento del bot entre
los diferentes modos de operación manual (LONG_SHORT, LONG_ONLY, etc.).
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
    from .._helpers import MENU_STYLE
except ImportError as e:
    print(f"ERROR [TUI Mode Screen]: Falló importación de dependencias: {e}")
    position_manager = None
    MENU_STYLE = {}

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Pantalla de Modo de Trading ---

def show_mode_menu():
    """Muestra el menú para cambiar el modo de trading con opciones de cierre explícitas."""
    if not TerminalMenu or not position_manager:
        print("\nError: Dependencias de menú no disponibles (TerminalMenu o PositionManager).")
        time.sleep(2)
        return

    current_mode = position_manager.get_manual_state().get('mode', 'N/A')
    
    menu_items = [
        "[1] LONG_SHORT (Operar en ambos lados)",
        "[2] LONG_ONLY (Solo compras)",
        "[3] SHORT_ONLY (Solo ventas)",
        "[4] NEUTRAL (Detener nuevas entradas)",
        None,
        "[b] Volver al menú principal"
    ]
    
    title = f"Selecciona el nuevo modo de trading\nModo actual: {current_mode}"
    
    terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
    choice_index = terminal_menu.show()

    if choice_index is not None and choice_index < 4:
        modes = ["LONG_SHORT", "LONG_ONLY", "SHORT_ONLY", "NEUTRAL"]
        new_mode = modes[choice_index]
        
        close_open = False
        incompatible_side_to_close = None
        
        # Lógica para determinar si el cambio de modo es incompatible con posiciones abiertas
        if current_mode in ["LONG_SHORT", "LONG_ONLY"] and new_mode not in ["LONG_SHORT", "LONG_ONLY"]:
            incompatible_side_to_close = "LONG"
        elif current_mode in ["LONG_SHORT", "SHORT_ONLY"] and new_mode not in ["LONG_SHORT", "SHORT_ONLY"]:
            incompatible_side_to_close = "SHORT"

        # Si hay incompatibilidad, preguntar al usuario qué hacer
        if incompatible_side_to_close:
            confirm_title = (
                f"Al cambiar a '{new_mode}', ¿qué hacer con las posiciones {incompatible_side_to_close} abiertas?\n"
                f"----------------------------------------"
            )
            confirm_menu_items = [
                f"[1] Cerrar Inmediatamente Todas las Posiciones {incompatible_side_to_close}",
                f"[2] No Cerrar Nada (dejar que se gestionen hasta su cierre natural)",
                None,
                "[3] Cancelar Cambio de Modo"
            ]
            confirm_menu = TerminalMenu(confirm_menu_items, title=confirm_title, **MENU_STYLE)
            close_choice = confirm_menu.show()
            
            if close_choice == 0:
                close_open = True
            elif close_choice in [None, 2]: # Si cancela o elige la tercera opción
                print("\nCambio de modo cancelado.")
                time.sleep(1.5)
                return 

        success, message = position_manager.set_manual_trading_mode(new_mode, close_open=close_open)
        print(f"\n{message}")
        time.sleep(2)