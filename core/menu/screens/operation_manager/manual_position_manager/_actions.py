# core/menu/screens/operation_manager/manual_position_manager/_actions.py

import time
from typing import Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from ...._helpers import (
    clear_screen,
    print_tui_header,
    press_enter_to_continue,
    MENU_STYLE,
)
try:
    from core.strategy.om import api as om_api
    from core.strategy.pm import api as pm_api
except ImportError:
    om_api = None
    pm_api = None

def _open_next_pending(side: str):
    """
    Ejecuta la lógica para abrir manualmente la siguiente posición pendiente.
    """
    clear_screen()
    print_tui_header(f"Apertura Manual - {side.upper()}")
    
    operacion = om_api.get_operation_by_side(side)
    pending_positions = operacion.posiciones_pendientes
    
    if not pending_positions:
        print("\nNo hay posiciones pendientes para abrir.")
        time.sleep(2)
        return
        
    pos_to_open = pending_positions[0]
    
    confirm_title = (
        f"Confirmas abrir la siguiente posición pendiente?\n\n"
        f"  - ID:      ...{str(pos_to_open.id)[-6:]}\n"
        f"  - Capital: {pos_to_open.capital_asignado:.2f} USDT\n\n"
        f"Esta acción IGNORARÁ la distancia de promediación."
    )
    confirm_menu = TerminalMenu(["[s] Sí, abrir posición", "[n] No, cancelar"], title=confirm_title)
    if confirm_menu.show() == 0:
        print("\n\033[93mProcesando apertura manual, por favor espere...\033[0m")
        success, msg = pm_api.manual_open_next_pending_position(side)
        
        clear_screen()
        print_tui_header(f"Apertura Manual - Resultado")
        if success:
            print(f"\n\033[92mÉXITO:\033[0m {msg}")
        else:
            print(f"\n\033[91mFALLO:\033[0m {msg}")
        press_enter_to_continue()


def _close_last_open(side: str):
    """
    Ejecuta la lógica para cerrar manualmente la última posición abierta.
    """
    clear_screen()
    print_tui_header(f"Cierre Manual Individual - {side.upper()}")

    operacion = om_api.get_operation_by_side(side)
    open_positions = operacion.posiciones_abiertas

    if not open_positions:
        print("\nNo hay posiciones abiertas para cerrar.")
        time.sleep(2)
        return
    
    # El índice a cerrar es siempre el último de la lista de posiciones abiertas
    index_to_close_in_list = len(open_positions) - 1
    pos_to_close = open_positions[index_to_close_in_list]

    confirm_title = (
        f"Confirmas cerrar la ÚLTIMA posición abierta?\n\n"
        f"  - ID:          ...{str(pos_to_close.id)[-6:]}\n"
        f"  - P. Entrada:  {pos_to_close.entry_price:.4f}\n"
        f"  - Capital:     {pos_to_close.capital_asignado:.2f} USDT\n\n"
        f"Esta acción cerrará la posición a precio de mercado."
    )
    confirm_menu = TerminalMenu(["[s] Sí, cerrar posición", "[n] No, cancelar"], title=confirm_title)
    if confirm_menu.show() == 0:
        print("\n\033[93mEnviando orden de cierre, por favor espere...\033[0m")
        # Pasamos el índice RELATIVO a la lista de posiciones abiertas
        success, msg = pm_api.manual_close_logical_position_by_index(side, index_to_close_in_list)
        
        clear_screen()
        print_tui_header(f"Cierre Manual Individual - Resultado")
        if success:
            print(f"\n\033[92mÉXITO:\033[0m {msg}")
        else:
            print(f"\n\033[91mFALLO:\033[0m {msg}")
        press_enter_to_continue()


# --- INICIO DE LA MODIFICACIÓN: Nueva función añadida ---
def _close_first_open(side: str):
    """
    Ejecuta la lógica para cerrar manualmente la primera posición abierta.
    """
    clear_screen()
    print_tui_header(f"Cierre Manual Individual - {side.upper()}")

    operacion = om_api.get_operation_by_side(side)
    open_positions = operacion.posiciones_abiertas

    if not open_positions:
        print("\nNo hay posiciones abiertas para cerrar.")
        time.sleep(2)
        return
    
    # El índice a cerrar es siempre el primero de la lista (índice 0)
    index_to_close_in_list = 0
    pos_to_close = open_positions[index_to_close_in_list]

    confirm_title = (
        f"Confirmas cerrar la PRIMERA posición abierta?\n\n"
        f"  - ID:          ...{str(pos_to_close.id)[-6:]}\n"
        f"  - P. Entrada:  {pos_to_close.entry_price:.4f}\n"
        f"  - Capital:     {pos_to_close.capital_asignado:.2f} USDT\n\n"
        f"Esta acción cerrará la posición a precio de mercado."
    )
    confirm_menu = TerminalMenu(["[s] Sí, cerrar posición", "[n] No, cancelar"], title=confirm_title)
    if confirm_menu.show() == 0:
        print("\n\033[93mEnviando orden de cierre, por favor espere...\033[0m")
        # Pasamos el índice RELATIVO a la lista de posiciones abiertas (en este caso, 0)
        success, msg = pm_api.manual_close_logical_position_by_index(side, index_to_close_in_list)
        
        clear_screen()
        print_tui_header(f"Cierre Manual Individual - Resultado")
        if success:
            print(f"\n\033[92mÉXITO:\033[0m {msg}")
        else:
            print(f"\n\033[91mFALLO:\033[0m {msg}")
        press_enter_to_continue()
# --- FIN DE LA MODIFICACIÓN ---


def _panic_close_all(side: str):
    """
    Ejecuta la lógica para el cierre de pánico de todas las posiciones.
    """
    operacion = om_api.get_operation_by_side(side)
    position_count = operacion.posiciones_abiertas_count

    if position_count == 0:
        print("\nNo hay posiciones abiertas para un cierre de pánico.")
        time.sleep(2)
        return

    title = f"Esta acción cerrará permanentemente las {position_count} posiciones {side.upper()}.\n¿Estás seguro?"
    confirm_menu_items = [f"[s] Sí, cerrar todas las posiciones {side.upper()}", "[n] No, cancelar"]
    
    if TerminalMenu(confirm_menu_items, title=title, **MENU_STYLE).show() == 0:
        clear_screen()
        print_tui_header(f"CIERRE DE PÁNICO ({side.upper()})")
        print("\n\033[93mENVIANDO ÓRDENES DE CIERRE... POR FAVOR, ESPERE.\033[0m")
        
        try:
            success, message = pm_api.close_all_logical_positions(side, reason="PANIC_CLOSE_ALL")
        except Exception as e:
            success = False
            message = f"Ocurrió una excepción inesperada: {e}"

        clear_screen()
        print_tui_header(f"CIERRE DE PÁNICO ({side.upper()}) - RESULTADO")
        print(f"\n\033[92mÉXITO:\033[0m {message}" if success else f"\n\033[91mERROR:\033[0m {message}")
        press_enter_to_continue()