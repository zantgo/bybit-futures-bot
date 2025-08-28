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
    params_changed_in_submenu = False
    while True:
        clear_screen()
        print_tui_header("Editor de Condiciones de Salida")

        print("\nCondiciones Actuales (Se ejecutará la PRIMERA que se cumpla):")
        if not temp_op.condiciones_salida_precio and not temp_op.tiempo_maximo_min and not temp_op.max_comercios:
            print("  - Ningún límite de salida configurado.")
        
        for c in temp_op.condiciones_salida_precio:
            op = '>' if c['tipo'] == 'PRICE_ABOVE' else '<'
            print(f"  - Precio {op} {c['valor']:.4f} (Acción: {c['accion']})")
        
        print(f"  - Límite de Duración: {temp_op.tiempo_maximo_min or 'Ilimitado'} min (Acción: {temp_op.accion_por_limite_tiempo})")
        print(f"  - Límite de Trades: {temp_op.max_comercios or 'Ilimitado'} (Acción: {temp_op.accion_por_limite_trades})")
        
        menu_items = [
            "[1] Gestionar condiciones de precio",
            "[2] Configurar límite de duración",
            "[3] Configurar límite de trades",
            None,
            "[b] Volver al menú anterior"
        ]

        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()

        if choice is None or choice == 4: break
        
        try:
            if choice == 0:
                while True:
                    price_cond_items = [f"[{i+1}] Eliminar: Precio {'>' if c['tipo'] == 'PRICE_ABOVE' else '<'} {c['valor']:.4f} (Acción: {c['accion']})" for i, c in enumerate(temp_op.condiciones_salida_precio)]
                    price_cond_items.extend([None, "[a] Añadir nueva condición de precio", "[d] Eliminar TODAS las condiciones de precio", "[b] Volver"])
                    
                    price_menu_options = MENU_STYLE.copy(); price_menu_options['clear_screen'] = False
                    price_menu_choice = TerminalMenu(price_cond_items, title="\nGestionar condiciones de precio:", **price_menu_options).show()
                    
                    if price_menu_choice is None or price_menu_choice == len(price_cond_items) - 1: break
                    elif price_menu_choice == len(price_cond_items) - 3: # Añadir
                        add_menu = TerminalMenu(["[1] Salir si precio SUPERIOR a", "[2] Salir si precio INFERIOR a"], title="\nTipo de condición:").show()
                        if add_menu is not None:
                            tipo = 'PRICE_ABOVE' if add_menu == 0 else 'PRICE_BELOW'
                            op = '>' if tipo == 'PRICE_ABOVE' else '<'
                            valor = get_input(f"Salir si precio {op}", float, context_info="Añadir Condición de Salida")
                            accion = get_action_menu("Acción al alcanzar este precio", 'PAUSAR')
                            temp_op.condiciones_salida_precio.append({'tipo': tipo, 'valor': valor, 'accion': accion})
                            params_changed_in_submenu = True
                    elif price_menu_choice == len(price_cond_items) - 2: # Eliminar Todas
                        if temp_op.condiciones_salida_precio:
                            temp_op.condiciones_salida_precio.clear(); params_changed_in_submenu = True
                    elif price_menu_choice < len(temp_op.condiciones_salida_precio): # Eliminar una
                        temp_op.condiciones_salida_precio.pop(price_menu_choice); params_changed_in_submenu = True

            elif choice == 1:
                new_val = get_input("Límite de Duración (min)", int, temp_op.tiempo_maximo_min, min_val=1, is_optional=True, context_info="Límites de Salida")
                if new_val != temp_op.tiempo_maximo_min:
                    temp_op.tiempo_maximo_min = new_val
                    if temp_op.tiempo_maximo_min is not None:
                        temp_op.accion_por_limite_tiempo = get_action_menu("Acción al alcanzar el tiempo máximo", temp_op.accion_por_limite_tiempo)
                    params_changed_in_submenu = True
            
            elif choice == 2:
                new_val = get_input("Límite de Trades", int, temp_op.max_comercios, min_val=1, is_optional=True, context_info="Límites de Salida")
                if new_val != temp_op.max_comercios:
                    temp_op.max_comercios = new_val
                    if temp_op.max_comercios is not None:
                        temp_op.accion_por_limite_trades = get_action_menu("Acción al alcanzar el máximo de trades", temp_op.accion_por_limite_trades)
                    params_changed_in_submenu = True

        except UserInputCancelled:
            print("\nEdición de campo cancelada."); time.sleep(1)
            
    return params_changed_in_submenu