"""
Módulo del Panel de Control de Operación.

Este __init__.py actúa como la fachada pública para el módulo, exponiendo la
función principal de la pantalla e inyectando las dependencias necesarias
en todos los submódulos que lo componen.
"""
from typing import Dict, Any

# 1. Importar la función principal desde el submódulo _main para exponerla
#    públicamente. Se le da un nombre más claro y consistente.
from ._main import show_operation_manager_screen

# --- Inyección de Dependencias ---

def init(dependencies: Dict[str, Any]):
    """
    Inyecta las dependencias necesarias en todos los submódulos de este paquete.
    Este patrón permite que los submódulos permanezcan desacoplados y sean
    fáciles de probar.
    """
    # Importar los submódulos aquí para evitar dependencias circulares a nivel de paquete
    from . import _main
    from . import _displayers
    from . import _wizards
    
    # Inyectar las dependencias en cada submódulo que las necesite
    if hasattr(_main, 'init'):
        _main.init(dependencies)
    
    if hasattr(_displayers, 'init'):
        _displayers.init(dependencies)
        
    if hasattr(_wizards, 'init'):
        _wizards.init(dependencies)

# --- Control de lo que se exporta con 'from . import *' ---
# Define la API pública de este módulo. Solo se debe poder acceder a 'init' y
# a la función que muestra la pantalla.
__all__ = [
    'init',
    'show_operation_manager_screen',
]