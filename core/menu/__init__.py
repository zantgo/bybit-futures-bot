# =============== INICIO ARCHIVO: core/menu/__init__.py ===============
"""
Paquete de la Interfaz de Usuario de Terminal (TUI) para el Bot de Trading.

Este archivo `__init__.py` actúa como la fachada del paquete `menu`.
Exporta las funciones públicas y principales que serán utilizadas por el resto
de la aplicación, como `main.py` y los `runners`.

Funciones Públicas Exportadas:
- run_trading_assistant_wizard: Lanza el asistente de configuración inicial.
- run_tui_menu_loop: Lanza el bucle del menú interactivo principal.
- main_cli: El objeto de grupo de comandos de `click` para el lanzador.
- clear_screen: Función de ayuda para limpiar la terminal.
"""

# --- Importar y Exponer Funciones Públicas ---

# Desde el módulo del asistente de configuración (_wizard)
try:
    from ._wizard import run_trading_assistant_wizard
except ImportError as e:
    print(f"ADVERTENCIA [menu/__init__]: No se pudo importar el asistente de configuración: {e}")
    # Definir una función dummy para que las importaciones en otros archivos no fallen
    def run_trading_assistant_wizard(*args, **kwargs):
        print("ERROR: El asistente de configuración no está disponible.")
        return None, None

# Desde el módulo del bucle principal (_main_loop)
try:
    from ._main_loop import run_tui_menu_loop
except ImportError as e:
    print(f"ADVERTENCIA [menu/__init__]: No se pudo importar el bucle del menú principal: {e}")
    def run_tui_menu_loop(*args, **kwargs):
        print("ERROR: El menú principal no está disponible.")

# Desde el módulo de la CLI (_cli)
try:
    from ._cli import main_cli
except ImportError as e:
    print(f"ADVERTENCIA [menu/__init__]: No se pudo importar la CLI: {e}")
    # click.group es un objeto, por lo que un dummy simple es más difícil.
    # Si esto falla, el programa probablemente no pueda iniciarse de todos modos.
    main_cli = None

# Desde el módulo de helpers (_helpers)
try:
    from ._helpers import clear_screen
except ImportError as e:
     print(f"ADVERTENCIA [menu/__init__]: No se pudo importar helpers del menú: {e}")
     def clear_screen():
         pass

# --- Control de lo que se exporta con 'from core.menu import *' ---
# Es una buena práctica definir __all__ para controlar las importaciones públicas.
__all__ = [
    'run_trading_assistant_wizard',
    'run_tui_menu_loop',
    'main_cli',
    'clear_screen'
]

# =============== FIN ARCHIVO: core/menu/__init__.py ===============