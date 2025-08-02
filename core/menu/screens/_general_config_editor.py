"""
Módulo para la Pantalla de Edición de Configuración General del Bot.

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

# Importamos la API del BotController para poder llamarla
from core.bot_controller import api as bc_api

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

def show_general_config_editor_screen(config_module: Any) -> bool:
    """
    Muestra la pantalla de edición de configuración general.
    """
    logger = _deps.get("memory_logger_module")
    if not TerminalMenu:
        if logger: logger.log("Error: 'simple-term-menu' no está instalado.", level="ERROR")
        return False
    
    _show_general_config_menu(config_module)

    # Devolvemos False porque no hay un "guardado" final, los cambios ya están aplicados.
    return False

def _show_general_config_menu(config_module: Any):
    """Muestra el menú interactivo para editar la configuración general."""
    while True:
        clear_screen()
        print_tui_header("Editor de Configuración General")

        # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
        # --- (COMENTADO) ---
        # # Leemos directamente del config_module
        # modo_actual = "Paper Trading" if getattr(config_module, 'PAPER_TRADING_MODE', False) else "Live Trading"
        # testnet_actual = "ON" if getattr(config_module, 'UNIVERSAL_TESTNET_MODE', False) else "OFF"
        # 
        # print("\nValores Actuales:")
        # print("┌" + "─" * 40 + "┐")
        # print(f"│ {'Exchange':<15}: {getattr(config_module, 'EXCHANGE_NAME', 'N/A').upper():<21} │")
        # print(f"│ {'Modo':<15}: {modo_actual:<21} │")
        # print(f"│ {'Testnet':<15}: {testnet_actual:<21} │")
        # print(f"│ {'Símbolo Ticker':<15}: {getattr(config_module, 'TICKER_SYMBOL', 'N/A'):<21} │")
        # print("└" + "─" * 40 + "┘")
        # --- (CORREGIDO) ---
        modo_actual = "Paper Trading" if config_module.BOT_CONFIG["PAPER_TRADING_MODE"] else "Live Trading"
        testnet_actual = "ON" if config_module.BOT_CONFIG["UNIVERSAL_TESTNET_MODE"] else "OFF"
        
        print("\nValores Actuales:")
        print("┌" + "─" * 40 + "┐")
        print(f"│ {'Exchange':<15}: {config_module.BOT_CONFIG['EXCHANGE_NAME'].upper():<21} │")
        print(f"│ {'Modo':<15}: {modo_actual:<21} │")
        print(f"│ {'Testnet':<15}: {testnet_actual:<21} │")
        print(f"│ {'Símbolo Ticker':<15}: {config_module.BOT_CONFIG['TICKER']['SYMBOL']:<21} │")
        print("└" + "─" * 40 + "┘")
        # --- FIN DE LA MODIFICACIÓN ---

        menu_items = [
            "[1] Exchange", 
            "[2] Modo", 
            "[3] Testnet",
            "[4] Símbolo del Ticker",
            None,
            "[b] Volver al Menú Principal"
        ]
        action_map = {0: 'exchange', 1: 'mode', 2: 'testnet', 3: 'ticker', 5: 'back'}
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        
        menu = TerminalMenu(menu_items, title="\nSelecciona una opción para editar:", **menu_options)
        
        action = action_map.get(menu.show())

        try:
            # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
            # --- (COMENTADO - Lógica antigua) ---
            # if action == 'exchange':
            #     sub_choice = TerminalMenu(["Bybit", None, "[c] Cancelar"], title="\nSelecciona el Exchange:", **MENU_STYLE).show()
            #     if sub_choice == 0: setattr(config_module, 'EXCHANGE_NAME', 'bybit')
            # ... y así para los demás
            
            # --- (CORREGIDO - Nueva lógica) ---
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
            # --- FIN DE LA MODIFICACIÓN ---
                
            elif action == 'back' or action is None:
                return # Salimos del bucle
        
        except UserInputCancelled:
            print("\n\nEdición cancelada."); time.sleep(1)