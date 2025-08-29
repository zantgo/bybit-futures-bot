# core/menu/screens/operation_manager/__init__.py

"""
Módulo del Panel de Control de Operación.

Este __init__.py actúa como la fachada pública para el módulo, exponiendo la
función principal de la pantalla e inyectando las dependencias necesarias
en todos los submódulos que lo componen.
"""
from typing import Dict, Any

from ._main import show_operation_manager_screen

def init(dependencies: Dict[str, Any]):
    """
    Inyecta las dependencias necesarias en todos los submódulos de este paquete.
    """
    # --- INICIO DE LA MODIFICACIÓN (Paso 4 del Plan - Integración) ---
    # Se añade la importación del nuevo módulo y su inicialización.
    from . import _main, _displayers, _wizards, position_editor, manual_position_manager
    
    if hasattr(_main, 'init'): _main.init(dependencies)
    if hasattr(_displayers, 'init'): _displayers.init(dependencies)
    if hasattr(_wizards, 'init'): _wizards.init(dependencies)
    if hasattr(position_editor, 'init'): position_editor.init(dependencies)
    # Se añade la llamada a la función init del nuevo módulo
    if hasattr(manual_position_manager, 'init'): manual_position_manager.init(dependencies)
    # --- FIN DE LA MODIFICACIÓN ---

__all__ = [
    'init',
    'show_operation_manager_screen',
]