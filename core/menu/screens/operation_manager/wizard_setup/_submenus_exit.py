# core/menu/screens/operation_manager/wizard_setup/_submenus_exit.py

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
from ._submenus_risk import get_action_menu

def _edit_exit_conditions_submenu(temp_op: Operacion):
    """
    Submenú para gestionar las condiciones de salida de la operación con una UI simplificada.
    """
    from ...._helpers import show_help_popup
    params_changed_in_submenu = False
    
    while True:
        clear_screen()
        print_tui_header("Editor de Condiciones de Salida")

        above_cond = temp_op.cond_salida_above
        below_cond = temp_op.cond_salida_below
        
        above_str = f"Precio > {above_cond['valor']:.4f} (Acción: {above_cond['accion']})" if above_cond else "Desactivado"
        below_str = f"Precio < {below_cond['valor']:.4f} (Acción: {below_cond['accion']})" if below_cond else "Desactivado"
        time_str = f"{temp_op.tiempo_maximo_min or 'Ilimitado'} min (Acción: {temp_op.accion_por_limite_tiempo})"
        trades_str = f"{temp_op.max_comercios or 'Ilimitado'} (Acción: {temp_op.accion_por_limite_trades})"

        print("\nCondiciones Actuales (Se ejecutará la PRIMERA que se cumpla):")
        print(f"  - Salida por Precio SUPERIOR: {above_str}")
        print(f"  - Salida por Precio INFERIOR: {below_str}")
        print(f"  - Límite de Duración: {time_str}")
        print(f"  - Límite de Trades: {trades_str}")

        menu_items = [
            f"[1] Editar Condición 'Precio SUPERIOR a'",
            f"[2] Editar Condición 'Precio INFERIOR a'",
            "[3] Editar Límite de Duración",
            "[4] Editar Límite de Trades",
            None,
            "[d] Desactivar TODAS las condiciones de salida",
            "[h] Ayuda",
            "[b] Volver al menú anterior"
        ]

        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()

        if choice is None or choice == 7: break
        
        try:
            if choice == 0:
                valor = get_input("Salir si precio >", float, above_cond['valor'] if above_cond else None, is_optional=True, context_info="Deja vacío para desactivar")
                if valor is not None:
                    accion = get_action_menu("Acción al alcanzar este precio", above_cond['accion'] if above_cond else 'PAUSAR')
                    temp_op.cond_salida_above = {'valor': valor, 'accion': accion}
                else:
                    temp_op.cond_salida_above = None
                params_changed_in_submenu = True

            elif choice == 1:
                valor = get_input("Salir si precio <", float, below_cond['valor'] if below_cond else None, is_optional=True, context_info="Deja vacío para desactivar")
                if valor is not None:
                    accion = get_action_menu("Acción al alcanzar este precio", below_cond['accion'] if below_cond else 'PAUSAR')
                    temp_op.cond_salida_below = {'valor': valor, 'accion': accion}
                else:
                    temp_op.cond_salida_below = None
                params_changed_in_submenu = True

            elif choice == 2:
                original_val = temp_op.tiempo_maximo_min
                original_action = temp_op.accion_por_limite_tiempo

                new_val = get_input("Límite de Duración (min)", int, original_val, min_val=1, is_optional=True, context_info="Deja vacío para desactivar")

                new_action = original_action
                if new_val is not None:
                    new_action = get_action_menu("Acción al alcanzar el tiempo máximo", original_action)

                if new_val != original_val or new_action != original_action:
                    temp_op.tiempo_maximo_min = new_val
                    temp_op.accion_por_limite_tiempo = new_action
                    params_changed_in_submenu = True

            elif choice == 3:
                original_val = temp_op.max_comercios
                original_action = temp_op.accion_por_limite_trades

                new_val = get_input("Límite de Trades", int, original_val, min_val=1, is_optional=True, context_info="Deja vacío para desactivar")
                
                new_action = original_action
                if new_val is not None:
                    new_action = get_action_menu("Acción al alcanzar el máximo de trades", original_action)

                if new_val != original_val or new_action != original_action:
                    temp_op.max_comercios = new_val
                    temp_op.accion_por_limite_trades = new_action
                    params_changed_in_submenu = True

            elif choice == 5:
                if temp_op.cond_salida_above or temp_op.cond_salida_below or temp_op.tiempo_maximo_min or temp_op.max_comercios:
                    temp_op.cond_salida_above = None
                    temp_op.cond_salida_below = None
                    temp_op.tiempo_maximo_min = None
                    temp_op.max_comercios = None
                    params_changed_in_submenu = True
                    print("\nTodas las condiciones de salida han sido desactivadas."); time.sleep(1.5)

            elif choice == 6: # Índice de Ayuda
                show_help_popup('wizard_exit_conditions')

        except UserInputCancelled:
            print("\nEdición de campo cancelada."); time.sleep(1)
            
    return params_changed_in_submenu
