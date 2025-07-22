# core/menu/__init__.py

"""
Paquete de la Interfaz de Usuario de Terminal (TUI) para el Bot de Trading.

Este archivo __init__.py actúa como la fachada y el punto de entrada principal
para todo el paquete `menu`. Exporta las funciones clave que serán utilizadas
por el resto de la aplicación, como `main.py`.
"""
from typing import Dict, Any

# --- Importar y Exponer Funciones Públicas Clave ---

# Importar la función de lanzamiento principal desde el controlador.
from ._main_controller import launch_bot

# Importar helpers comunes que podrían ser útiles externamente.
from ._helpers import clear_screen

def initialize_menu_system(dependencies: Dict[str, Any]):
    """
    [OBSOLETO] Esta función se mantiene por compatibilidad hacia atrás si fuera necesario.
    La nueva forma de iniciar es llamar directamente a `launch_bot`.
    """
    print("ADVERTENCIA: initialize_menu_system está obsoleto. Llama a launch_bot(dependencies) directamente.")
    launch_bot(dependencies)

# --- Control de lo que se exporta ---
__all__ = [
    'launch_bot',
    'clear_screen',
]