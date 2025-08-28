# core/menu/screens/operation_manager/_wizards.py

import time
from typing import Any, Dict

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from ..._helpers import (
    clear_screen,
    print_tui_header,
    press_enter_to_continue,
    MENU_STYLE
)

# Importar el nuevo asistente unificado desde su propio paquete
from . import wizard_setup 

_deps: Dict[str, Any] = {}

# --- INICIO DE LA MODIFICACIÓN ---
def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias e inicializa los submódulos de asistentes."""
    global _deps
    _deps = dependencies
    
    # Se asegura de que las dependencias se pasen al nuevo paquete refactorizado.
    if hasattr(wizard_setup, 'init'):
        wizard_setup.init(dependencies)
# --- FIN DE LA MODIFICACIÓN ---

def operation_setup_wizard(om_api: Any, side: str, is_modification: bool = False):
    """
    Actúa como un despachador que llama al asistente unificado para
    crear o modificar una operación.
    """
    wizard_setup.operation_setup_wizard(om_api, side, is_modification)

def force_close_all_wizard(pm_api: Any, side: str):
    """Asistente para el cierre de pánico de todas las posiciones de un lado."""
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return
        
    summary = pm_api.get_position_summary()
    position_count = summary.get(f'open_{side}_positions_count', 0)

    if position_count == 0:
        print(f"\nNo hay posiciones {side.upper()} para cerrar.")
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