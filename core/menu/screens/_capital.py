# core/menu/screens/_capital.py

"""
Módulo para la pantalla de "Ajustar Capital" de la TUI.

Esta pantalla permite al usuario modificar en tiempo real los parámetros
clave de gestión de capital, como el tamaño base de cada posición y
el número máximo de posiciones simultáneas (slots).
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
    print(f"ERROR [TUI Capital Screen]: Falló importación de dependencias: {e}")
    position_manager = None
    MENU_STYLE = {}
    def get_input(prompt, type_func, default, min_val=None, max_val=None): return default

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Pantalla de Gestión de Capital ---

def show_capital_menu():
    """Muestra el menú para ajustar parámetros de capital en un bucle."""
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
            
        slots = summary.get('max_logical_positions', 0)
        base_size = summary.get('initial_base_position_size_usdt', 0.0)

        menu_items = [
            f"[1] Ajustar Slots por Lado (Actual: {slots})",
            f"[2] Ajustar Tamaño Base de Posición (Actual: {base_size:.2f} USDT)",
            None,
            "[b] Volver al menú principal"
        ]
        
        title = "Ajustar Parámetros de Capital"
        
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()

        if choice_index == 0:
            new_slots = get_input("\nNuevo número de slots por lado", int, slots, min_val=1)
            msg = ""
            if new_slots > slots:
                # Bucle para añadir slots uno por uno
                for _ in range(new_slots - slots):
                    success, msg = position_manager.add_max_logical_position_slot()
            elif new_slots < slots:
                # Bucle para remover slots uno por uno, con verificación
                for _ in range(slots - new_slots):
                    success, msg = position_manager.remove_max_logical_position_slot()
                    if not success:
                        break # Detener si no se puede remover más
            else:
                msg = "El número de slots no ha cambiado."
            print(f"\n{msg}")
            time.sleep(1.5)
        elif choice_index == 1:
            new_size = get_input("\nNuevo tamaño base por posición (USDT)", float, base_size, min_val=1.0)
            success, msg = position_manager.set_base_position_size(new_size)
            print(f"\n{msg}")
            time.sleep(1.5)
        else: # Si el usuario presiona 'b', ESC o elige una opción nula
            break