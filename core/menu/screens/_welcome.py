# core/menu/screens/_welcome.py

"""
Módulo para la Pantalla de Bienvenida y Configuración Inicial.

Esta pantalla es la primera interacción del usuario. Le permite:
1. Ver un resumen de la configuración cargada desde config.py.
2. Iniciar el bot directamente con esa configuración.
3. Entrar a un menú detallado para modificar la configuración para la sesión actual.
4. Salir del programa.
"""
from typing import Dict, Any
import time

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Menú ---
from .._helpers import clear_screen, print_tui_header, MENU_STYLE
from ._config_editor import show_config_editor_screen

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- Lógica de la Pantalla ---

def show_welcome_screen() -> bool:
    """
    Muestra la pantalla de bienvenida en un bucle hasta que el usuario
    decide iniciar el bot o salir.

    Returns:
        bool: True si el usuario elige "Iniciar Bot", False si elige "Salir".
    """
    # --- INICIO DE LA SOLUCIÓN ---
    # Se importa 'config' directamente desde la raíz del proyecto, no desde 'core'.
    try:
        import config as config_module
    except ImportError:
        print("ERROR CRÍTICO: No se pudo encontrar el archivo de configuración 'config.py'.")
        time.sleep(3)
        return False
    # --- FIN DE LA SOLUCIÓN ---

    while True:
        clear_screen()
        print_tui_header("Bienvenido al Asistente de Trading")
        
        # Imprimir un resumen de la configuración actual
        print("\nConfiguración actual para la sesión:")
        config_module.print_initial_config("live_interactive")
        
        menu_items = [
            "[1] Iniciar Bot con esta configuración",
            "[2] Modificar configuración para esta sesión",
            None,
            "[3] Salir"
        ]
        terminal_menu = TerminalMenu(
            menu_items,
            title="\n¿Qué deseas hacer?",
            **MENU_STYLE
        )
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            return True  # El usuario quiere iniciar el bot
        elif choice_index == 1:
            # Llamar a la pantalla de edición de configuración
            show_config_editor_screen(config_module)
            # El bucle `while True` asegura que volvamos a esta pantalla
            # para ver los cambios y confirmar de nuevo.
            continue
        elif choice_index == 2 or choice_index is None:
            return False # El usuario quiere salir del programa