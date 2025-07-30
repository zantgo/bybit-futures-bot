"""
Módulo para la Pantalla de Edición de Configuración General del Bot.
"""
from typing import Any, Dict
import time
import copy

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen,
    print_tui_header,
    get_input,
    MENU_STYLE,
    show_help_popup,
    UserInputCancelled
)

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- LÓGICA PRINCIPAL ---

def show_general_config_editor_screen(config_module: Any) -> bool:
    """
    Muestra la pantalla de edición de configuración general y devuelve True si se guardaron cambios.
    """
    logger = _deps.get("memory_logger_module")
    if not TerminalMenu:
        if logger: logger.log("Error: 'simple-term-menu' no está instalado.", level="ERROR")
        return False

    class TempConfig: pass
    temp_config = TempConfig()
    for attr in dir(config_module):
        if attr.isupper() and not attr.startswith('_'):
            setattr(temp_config, attr, copy.deepcopy(getattr(config_module, attr)))

    changes_made = _show_general_config_menu(temp_config)

    if changes_made:
        _apply_changes_to_real_config(temp_config, config_module, logger)
        return True
    
    return False

# --- Lógica de Aplicación de Cambios ---

def _apply_changes_to_real_config(temp_cfg: Any, real_cfg: Any, logger: Any):
    """Compara la config temporal con la real, aplica los cambios y los loguea."""
    if not logger: return
    logger.log("Aplicando cambios de configuración general...", "WARN")
    for attr in dir(temp_cfg):
        if attr.isupper() and not attr.startswith('_'):
            new_value = getattr(temp_cfg, attr)
            if hasattr(real_cfg, attr) and new_value != getattr(real_cfg, attr):
                logger.log(f"  -> {attr}: '{getattr(real_cfg, attr)}' -> '{new_value}'", "WARN")
                setattr(real_cfg, attr, new_value)

# --- MENÚ DE EDICIÓN ---

def _show_general_config_menu(temp_cfg: Any) -> bool:
    """Muestra el menú interactivo para editar la configuración general."""
    while True:
        clear_screen()
        print_tui_header("Editor de Configuración General")

        modo_actual = "Paper Trading" if getattr(temp_cfg, 'PAPER_TRADING_MODE', False) else "Live Trading"
        testnet_actual = "ON" if getattr(temp_cfg, 'UNIVERSAL_TESTNET_MODE', False) else "OFF"
        
        print("\nValores Actuales:")
        print("┌" + "─" * 40 + "┐")
        print(f"│ {'Exchange':<15}: {getattr(temp_cfg, 'EXCHANGE_NAME', 'N/A').upper():<21} │")
        print(f"│ {'Modo':<15}: {modo_actual:<21} │")
        print(f"│ {'Testnet':<15}: {testnet_actual:<21} │")
        print("└" + "─" * 40 + "┘")

        menu_items = [
            "[1] Exchange", "[2] Modo", "[3] Testnet", None,
            "[s] Guardar y Volver", "[c] Cancelar (Descartar Cambios)"
        ]
        action_map = {0: 'exchange', 1: 'mode', 2: 'testnet', 4: 'save', 5: 'cancel'}
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        
        menu = TerminalMenu(menu_items, title="\nSelecciona una opción para editar:", **menu_options)
        
        # --- INICIO DE LA CORRECCIÓN ---
        # La variable debe llamarse 'action' para que el bloque if/elif funcione.
        action = action_map.get(menu.show())
        # --- FIN DE LA CORRECCIÓN ---

        if action == 'exchange':
            sub_choice = TerminalMenu(["Bybit", None, "[c] Cancelar"], title="\nSelecciona el Exchange:", **MENU_STYLE).show()
            if sub_choice == 0: setattr(temp_cfg, 'EXCHANGE_NAME', 'bybit')
        
        elif action == 'mode':
            sub_choice = TerminalMenu(["Live Trading", "Paper Trading", None, "[c] Cancelar"], title="\nSelecciona el Modo de Trading:", **MENU_STYLE).show()
            if sub_choice == 0: setattr(temp_cfg, 'PAPER_TRADING_MODE', False)
            elif sub_choice == 1: setattr(temp_cfg, 'PAPER_TRADING_MODE', True)

        elif action == 'testnet':
            sub_choice = TerminalMenu(["ON", "OFF", None, "[c] Cancelar"], title="\nActivar Modo Testnet:", **MENU_STYLE).show()
            if sub_choice == 0: setattr(temp_cfg, 'UNIVERSAL_TESTNET_MODE', True)
            elif sub_choice == 1: setattr(temp_cfg, 'UNIVERSAL_TESTNET_MODE', False)

        elif action == 'save':
            print("\nCambios guardados."); time.sleep(1.5); return True
            
        elif action == 'cancel' or action is None:
            print("\nCambios descartados."); time.sleep(1.5); return False