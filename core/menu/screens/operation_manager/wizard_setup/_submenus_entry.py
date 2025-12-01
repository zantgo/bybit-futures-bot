# core/menu/screens/operation_manager/wizard_setup/_submenus_entry.py

import time
from typing import Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from ...._helpers import (
    clear_screen,
    print_tui_header,
    get_input,
    MENU_STYLE,
    UserInputCancelled,
)
from core.strategy.entities import Operacion

def _edit_entry_conditions_submenu(temp_op: Operacion):
    """
    Submenú para gestionar las condiciones de entrada de la operación con una UI simplificada.
    """
    from ...._helpers import show_help_popup
    params_changed_in_submenu = False
    
    while True:
        clear_screen()
        print_tui_header("Editor de Condiciones de Entrada")

        above_val = temp_op.cond_entrada_above
        below_val = temp_op.cond_entrada_below
        timer_val = temp_op.tiempo_espera_minutos

        above_str = f"{above_val:.4f}" if above_val is not None else "Desactivado"
        below_str = f"{below_val:.4f}" if below_val is not None else "Desactivado"
        timer_str = f"{timer_val} min" if timer_val is not None else "Desactivado"

        print("\nCondiciones Actuales (Se activará con CUALQUIERA que se cumpla):")
        if all(v is None for v in [above_val, below_val, timer_val]):
            print("  - Inmediata (Market)")
        else:
            print(f"  - Precio SUPERIOR a: {above_str}")
            print(f"  - Precio INFERIOR a: {below_str}")
            print(f"  - Temporizador:      {timer_str}")

        menu_items = [
            f"[1] Editar Condición 'Precio SUPERIOR a'",
            f"[2] Editar Condición 'Precio INFERIOR a'",
            f"[3] Editar Temporizador",
            None,
            "[d] Desactivar TODAS las condiciones (Activar en Market)",
            "[h] Ayuda",
            "[b] Volver al menú anterior"
        ]

        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()

        if choice is None or choice == 6:
            break
        try:
            if choice == 0:
                new_val = get_input("Activar si precio >", float, temp_op.cond_entrada_above, is_optional=True, context_info="Deja vacío para desactivar")
                if new_val != temp_op.cond_entrada_above:
                    temp_op.cond_entrada_above = new_val
                    params_changed_in_submenu = True
            
            elif choice == 1:
                new_val = get_input("Activar si precio <", float, temp_op.cond_entrada_below, is_optional=True, context_info="Deja vacío para desactivar")
                if new_val != temp_op.cond_entrada_below:
                    temp_op.cond_entrada_below = new_val
                    params_changed_in_submenu = True
            
            elif choice == 2:
                new_val = get_input("Activar después de (minutos)", int, temp_op.tiempo_espera_minutos, min_val=1, is_optional=True, context_info="Deja vacío para desactivar")
                if new_val != temp_op.tiempo_espera_minutos:
                    temp_op.tiempo_espera_minutos = new_val
                    params_changed_in_submenu = True
            
            elif choice == 4:
                if temp_op.cond_entrada_above is not None or temp_op.cond_entrada_below is not None or temp_op.tiempo_espera_minutos is not None:
                    temp_op.cond_entrada_above = None
                    temp_op.cond_entrada_below = None
                    temp_op.tiempo_espera_minutos = None
                    params_changed_in_submenu = True
                    print("\nTodas las condiciones de entrada han sido desactivadas."); time.sleep(1.5)

            elif choice == 5: # Índice de Ayuda
                show_help_popup('wizard_entry_conditions')

        except UserInputCancelled:
            print("\nEdición cancelada."); time.sleep(1)
            
    return params_changed_in_submenu
