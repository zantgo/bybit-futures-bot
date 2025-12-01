"""
Módulo para la Pantalla de Edición de Configuración General del Bot.

v6.1 (Corrección de Adaptabilidad Dinámica):
- Implementado sistema de ancho dinámico basado en el terminal
- Corregido el problema de alineación de la caja de configuración con el menú
- Añadido truncamiento inteligente para valores largos de configuración
- Mantenido todo el funcionamiento original sin cambios

v6.0 (Refactor de Configuración):
- Completamente reescrito para leer y modificar valores dentro del
  diccionario `config.BOT_CONFIG`.
- Los cambios se aplican inmediatamente al objeto `config` en memoria.

v5.1 (Validación de Símbolo en TUI):
- La edición del `TICKER_SYMBOL` ahora llama al BotController para validar
  el símbolo en tiempo real contra el exchange.
- El usuario recibe feedback inmediato si el símbolo es inválido.

v5.0 (Refactor Ticker Symbol):
- Se añade la opción para editar el `TICKER_SYMBOL` en esta pantalla, ya que
  es un parámetro global del bot.
"""
from typing import Any, Dict
import time
import copy
import shutil
import re

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen,
    print_tui_header,
    get_input,
    MENU_STYLE,
    UserInputCancelled
)

from core.bot_controller import api as bc_api

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- Funciones Auxiliares para Adaptabilidad Dinámica ---

def _get_terminal_width():
    """Obtiene el ancho actual del terminal."""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 80  # Ancho por defecto

def _clean_ansi_codes(text: str) -> str:
    """Función de ayuda para eliminar códigos de color ANSI de un string."""
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', str(text))

def _truncate_text(text: str, max_length: int) -> str:
    """Trunca el texto si es muy largo, añadiendo '...' al final."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def _create_config_box_line(content: str, width: int) -> str:
    """Crea una línea de caja de configuración con el contenido alineado correctamente."""
    clean_content = _clean_ansi_codes(content)
    content_len = len(clean_content)
    
    if content_len > width - 2:
        content = _truncate_text(clean_content, width - 5)
        content_len = len(content)
    
    padding = width - content_len - 2
    return f"│ {content}{' ' * (padding - 1)}│"

def show_general_config_editor_screen(config_module: Any) -> bool:
    """
    Muestra la pantalla de edición de configuración general.
    """
    logger = _deps.get("memory_logger_module")
    if not TerminalMenu:
        if logger: logger.log("Error: 'simple-term-menu' no está instalado.", level="ERROR")
        return False
    
    _show_general_config_menu(config_module)

    return False

def _show_general_config_menu(config_module: Any):
    """Muestra el menú interactivo para editar la configuración general."""
    from .._helpers import show_help_popup

    while True:
        clear_screen()
        print_tui_header("Editor de Configuración General")

        modo_actual = "Paper Trading" if config_module.BOT_CONFIG["PAPER_TRADING_MODE"] else "Live Trading"
        testnet_actual = "ON" if config_module.BOT_CONFIG["UNIVERSAL_TESTNET_MODE"] else "OFF"
        
        terminal_width = _get_terminal_width()
        box_width = min(terminal_width - 2, 80)
        
        if box_width < 30:
            box_width = 30

        print("\nValores Actuales:")
        print("┌" + "─" * (box_width - 2) + "┐")
        
        config_items = [
            ("Exchange", config_module.BOT_CONFIG['EXCHANGE_NAME'].upper()),
            ("Modo", modo_actual),
            ("Testnet", testnet_actual),
            ("Símbolo Ticker", config_module.BOT_CONFIG['TICKER']['SYMBOL'])
        ]
        
        max_key_len = min(max(len(item[0]) for item in config_items), box_width - 15)
        
        for key, value in config_items:
            content = f"{key:<{max_key_len}}: {value}"
            print(_create_config_box_line(content, box_width))
        
        print("└" + "─" * (box_width - 2) + "┘")

        menu_items = [
            "[1] Exchange", 
            "[2] Modo", 
            "[3] Testnet",
            "[4] Símbolo del Ticker",
            None,
            "[h] Ayuda",
            "[b] Volver al Menú Principal"
        ]
        action_map = {0: 'exchange', 1: 'mode', 2: 'testnet', 3: 'ticker', 5: 'help', 6: 'back'}
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        
        menu = TerminalMenu(menu_items, title="\nSelecciona una opción para editar:", **menu_options)
        
        action = action_map.get(menu.show())

        try:
            if action == 'exchange':
                sub_choice = TerminalMenu(["Bybit", None, "[c] Cancelar"], title="\nSelecciona el Exchange:", **MENU_STYLE).show()
                if sub_choice == 0:
                    config_module.BOT_CONFIG['EXCHANGE_NAME'] = 'bybit'
            
            elif action == 'mode':
                sub_choice = TerminalMenu(["Live Trading", "Paper Trading", None, "[c] Cancelar"], title="\nSelecciona el Modo de Trading:", **MENU_STYLE).show()
                if sub_choice == 0:
                    config_module.BOT_CONFIG['PAPER_TRADING_MODE'] = False
                elif sub_choice == 1:
                    config_module.BOT_CONFIG['PAPER_TRADING_MODE'] = True

            elif action == 'testnet':
                sub_choice = TerminalMenu(["ON", "OFF", None, "[c] Cancelar"], title="\nActivar Modo Testnet:", **MENU_STYLE).show()
                if sub_choice == 0:
                    config_module.BOT_CONFIG['UNIVERSAL_TESTNET_MODE'] = True
                elif sub_choice == 1:
                    config_module.BOT_CONFIG['UNIVERSAL_TESTNET_MODE'] = False
            
            elif action == 'ticker':
                current_symbol = config_module.BOT_CONFIG['TICKER']['SYMBOL']
                new_symbol = get_input(
                    "\nNuevo Símbolo (ej. ETHUSDT)", 
                    str, 
                    current_symbol
                )
                
                print(f"Validando '{new_symbol.upper()}' con el exchange...")
                success, message = bc_api.validate_and_update_ticker_symbol(new_symbol)
                
                print(f"\nResultado: {message}")
                time.sleep(2.5)
            
            elif action == 'help':
                show_help_popup('general_config_editor')
                
            elif action == 'back' or action is None:
                return
        
        except UserInputCancelled:
            print("\n\nEdición cancelada."); time.sleep(1)
