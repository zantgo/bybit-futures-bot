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
    params_changed_in_submenu = False
    while True:
        clear_screen()
        print_tui_header("Editor de Condiciones de Entrada")

        print("\nCondiciones Actuales (Se activará con CUALQUIERA que se cumpla):")
        if not temp_op.condiciones_entrada and not temp_op.tiempo_espera_minutos:
            print("  - Inmediata (Market)")
        else:
            for c in temp_op.condiciones_entrada:
                op = '>' if c['tipo'] == 'PRICE_ABOVE' else '<'
                print(f"  - Precio {op} {c['valor']:.4f}")
            if temp_op.tiempo_espera_minutos:
                print(f"  - Activar después de {temp_op.tiempo_espera_minutos} min")

        menu_items = []
        for i, c in enumerate(temp_op.condiciones_entrada):
            op = '>' if c['tipo'] == 'PRICE_ABOVE' else '<'
            menu_items.append(f"[{i+1}] Eliminar: Precio {op} {c['valor']:.4f}")
        
        menu_items.extend([
            None,
            "[a] Añadir nueva condición de precio",
            f"[t] Configurar temporizador ({temp_op.tiempo_espera_minutos or 'Desactivado'} min)",
            "[d] Desactivar TODAS las condiciones (Activar en Market)",
            None,
            "[b] Volver al menú anterior"
        ])

        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()

        action_map = {idx: ('delete', idx) for idx in range(len(temp_op.condiciones_entrada))}
        offset = len(temp_op.condiciones_entrada) + 1
        action_map[offset] = ('add', None)
        action_map[offset+1] = ('timer', None)
        action_map[offset+2] = ('deactivate', None)
        action_map[offset+4] = ('back', None)

        action_tuple = action_map.get(choice)
        if action_tuple is None: continue

        action, value = action_tuple
        if action == 'back': break

        try:
            if action == 'delete':
                temp_op.condiciones_entrada.pop(value)
                params_changed_in_submenu = True
            elif action == 'add':
                add_menu = TerminalMenu(["[1] Activar si precio SUPERIOR a", "[2] Activar si precio INFERIOR a"], title="\nTipo de condición:").show()
                if add_menu is not None:
                    tipo = 'PRICE_ABOVE' if add_menu == 0 else 'PRICE_BELOW'
                    op = '>' if tipo == 'PRICE_ABOVE' else '<'
                    valor_input = get_input(f"Activar si precio {op}", float, context_info="Añadir Condición de Entrada")
                    temp_op.condiciones_entrada.append({'tipo': tipo, 'valor': valor_input})
                    params_changed_in_submenu = True
            elif action == 'timer':
                new_val = get_input("Activar después de (minutos)", int, temp_op.tiempo_espera_minutos, min_val=1, is_optional=True)
                if new_val != temp_op.tiempo_espera_minutos:
                    temp_op.tiempo_espera_minutos = new_val
                    params_changed_in_submenu = True
            elif action == 'deactivate':
                temp_op.condiciones_entrada.clear()
                temp_op.tiempo_espera_minutos = None
                params_changed_in_submenu = True
        except UserInputCancelled:
            print("\nEdición cancelada."); time.sleep(1)
            
    return params_changed_in_submenu