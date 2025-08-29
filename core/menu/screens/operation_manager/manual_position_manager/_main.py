# core/menu/screens/operation_manager/manual_position_manager/_main.py

import time
from typing import Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from ...._helpers import (
    clear_screen,
    print_tui_header,
    MENU_STYLE,
)
from ..position_editor._displayers import display_positions_table
from . import _actions

try:
    from core.strategy.om import api as om_api
    from core.strategy.pm import api as pm_api
except ImportError:
    om_api = None
    pm_api = None

# Reemplaza la función show_manual_position_manager_screen completa en core/menu/screens/operation_manager/manual_position_manager/_main.py

def show_manual_position_manager_screen(side: str):
    """
    Muestra la pantalla para la gestión manual de apertura y cierre de posiciones.
    """
    from ...._helpers import show_help_popup # Importar la función de ayuda

    if not all([TerminalMenu, om_api, pm_api]):
        print("Error: Dependencias críticas para el gestor manual no disponibles.")
        time.sleep(3)
        return

    while True:
        clear_screen()
        
        operacion = om_api.get_operation_by_side(side)
        if not operacion:
            print(f"Error: No se pudo cargar la operación para el lado {side.upper()}.")
            time.sleep(2)
            break

        current_price = pm_api.get_current_market_price() or 0.0

        print_tui_header(f"Gestor Manual de Posiciones - {side.upper()}", f"Precio Actual: {current_price:.4f} USDT")
        
        display_positions_table(operacion, current_price, side)

        has_pending = operacion.posiciones_pendientes_count > 0
        has_open = operacion.posiciones_abiertas_count > 0

        menu_items = []
        actions = []
        
        if has_pending:
            menu_items.append("[1] Abrir Siguiente Posición Pendiente")
            actions.append('open_next')
        
        if has_open:
            menu_items.append("[2] Cerrar Última Posición Abierta")
            actions.append('close_last')
            
        if has_open:
            menu_items.append(f"[*] CIERRE DE PÁNICO (Cerrar TODAS las {operacion.posiciones_abiertas_count} posiciones)")
            actions.append('panic_close')
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se añade un separador 'None' a ambas listas para mantener la alineación
        # y generar el espacio en el menú.
        menu_items.extend([
            None, # Separador visual añadido
            "[r] Refrescar",
            "[h] Ayuda",
            "[b] Volver al Panel de Operación"
        ])
        actions.extend([
            None, # Acción correspondiente al separador
            'refresh', 
            'help', 
            'back'
        ])
        # --- FIN DE LA MODIFICACIÓN ---

        # Esta parte del código ya maneja correctamente la lista con 'None'
        final_menu_items = [item for item in menu_items if item is not None and not item.startswith("[ ]")]
        final_actions = [action for action in actions if action is not None]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(
            menu_items, # Usamos la lista original que contiene el None
            title="\nAcciones de Gestión Manual:",
            **menu_options
        )
        choice_index = menu.show()
        
        # Mapeo directo usando el índice sobre la lista original de acciones
        action = actions[choice_index] if choice_index is not None else None
        
        if action == 'open_next':
            _actions._open_next_pending(side)
        
        elif action == 'close_last':
            _actions._close_last_open(side)
        
        elif action == 'panic_close':
            _actions._panic_close_all(side)
        
        elif action == 'refresh':
            continue
            
        elif action == 'help':
            show_help_popup('position_viewer')
            
        elif action == 'back' or action is None:
            break