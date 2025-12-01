"""
Paquete de la Interfaz de Usuario de Terminal (TUI) para el Bot de Trading.

Este archivo __init__.py actúa como la fachada y el punto de entrada principal
para todo el paquete `menu`. Exporta las funciones clave que serán utilizadas
por el resto de la aplicación, como `main.py`.
"""
# --- Importar y Exponer Funciones Públicas Clave ---

from ._main_controller import launch_bot
from ._helpers import clear_screen

__all__ = [
    'launch_bot',
    'clear_screen',
]
