# ./core/menu/screens/_welcome.py

"""
Módulo para la Pantalla de Bienvenida y Configuración Inicial.

v2.2: Implementa la técnica de renderizado del Dashboard para evitar el parpadeo
y funcionar con cualquier versión de simple-term-menu, sin necesidad de 'preface'.
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
    Muestra una única pantalla de bienvenida que incluye la configuración
    y las opciones de menú, hasta que el usuario decide iniciar o salir.

    Returns:
        bool: True si el usuario elige "Iniciar Bot", False si elige "Salir".
    """
    config_module = _deps.get("config_module")
    if not TerminalMenu or not config_module:
        print("ERROR CRÍTICO: Dependencias (TerminalMenu o config) no disponibles.")
        time.sleep(3)
        return False

    while True:
        # --- INICIO DE LA SOLUCIÓN CORRECTA ---
        
        # 1. Limpiamos la pantalla manualmente, una sola vez.
        clear_screen()
        
        # 2. Imprimimos toda la información estática que queremos mostrar.
        print_tui_header("Bienvenido al Asistente de Trading")
        print("\nConfiguración actual para la sesión:")
        
        # Llamamos a la función de impresión de config.py
        if hasattr(config_module, 'print_initial_config'):
             config_module.print_initial_config("live_interactive")
        else:
            # Fallback por si la función no existe, para evitar un crash.
            print("  (Error: No se pudo cargar la función de impresión de config)")

        # 3. Definimos los ítems del menú interactivo.
        menu_items = [
            "[1] Iniciar Bot con esta configuración",
            "[2] Modificar configuración para esta sesión",
            None,
            "[3] Salir"
        ]
        
        # 4. Creamos el menú, diciéndole explícitamente que NO limpie la pantalla.
        #    Esto es el paso clave para que nuestra información manual permanezca visible.
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False # <-- LA MAGIA ESTÁ AQUÍ
        
        terminal_menu = TerminalMenu(
            menu_items,
            title="\n¿Qué deseas hacer?",
            **menu_options
        )
        choice_index = terminal_menu.show()
        
        # --- FIN DE LA SOLUCIÓN CORRECTA ---

        # 5. Manejamos la elección del usuario (la lógica no cambia).
        if choice_index == 0:
            return True  # El usuario quiere iniciar el bot
        
        elif choice_index == 1:
            # Llamar a la pantalla de edición de configuración.
            # El bucle `while True` asegura que volvamos a esta pantalla
            # para ver los cambios y confirmar de nuevo.
            show_config_editor_screen(config_module)
            continue
            
        elif choice_index == 3 or choice_index is None: # Índice 3 es "Salir" en el menú de 4 ítems
            # Si se presiona ESC, choice_index es None.
            # Si se selecciona "Salir", el índice es 3.
            return False # El usuario quiere salir del programa