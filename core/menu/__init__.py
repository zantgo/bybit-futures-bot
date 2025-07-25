"""
Paquete de la Interfaz de Usuario de Terminal (TUI) para el Bot de Trading.

Este archivo __init__.py actúa como la fachada y el punto de entrada principal
para todo el paquete `menu`. Exporta las funciones clave que serán utilizadas
por el resto de la aplicación, como `main.py`.
"""
# --- Importar y Exponer Funciones Públicas Clave ---

# Importar la función de lanzamiento principal desde el controlador.
# Esta es la única función que el exterior necesita para iniciar la TUI.
from ._main_controller import launch_bot

# Importar helpers comunes que podrían ser útiles externamente.
from ._helpers import clear_screen


# --- Control de lo que se exporta con 'from core.menu import *' ---
# Definir __all__ para una API pública limpia y explícita.
__all__ = [
    'launch_bot',
    'clear_screen',
]