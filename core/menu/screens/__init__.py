"""
Paquete de Pantallas de la TUI.

Este paquete organiza y contiene la lógica para cada pantalla individual
del menú interactivo del bot.

v2.0 (Refactor de Hitos): Se actualiza para reflejar la nueva estructura de
pantallas, eliminando los modos manual/auto y centralizando la lógica en el
nuevo `_milestone_manager`.
"""
from typing import Dict, Any

# --- Importar y Exponer Funciones Públicas de cada Pantalla ---
from ._welcome import show_welcome_screen
from ._config_editor import show_config_editor_screen
from ._dashboard import show_dashboard_screen
from ._position_viewer import show_position_viewer_screen
from ._log_viewer import show_log_viewer
from ._milestone_manager import show_milestone_manager_screen

# --- Inyección de Dependencias ---

def init_screens(dependencies: Dict[str, Any]):
    """
    Inyecta las dependencias necesarias en los módulos de pantalla que las requieran.
    """
    # Este patrón permite que los módulos de pantalla permanezcan desacoplados
    # del resto de la aplicación, ya que reciben sus dependencias en lugar de importarlas.
    if hasattr(_dashboard, 'init'):
        _dashboard.init(dependencies)
    if hasattr(_welcome, 'init'):
        _welcome.init(dependencies)
    if hasattr(_config_editor, 'init'):
        _config_editor.init(dependencies)
    
    # El módulo se llama _milestone_manager, por lo que usamos esa variable.
    from . import _milestone_manager
    if hasattr(_milestone_manager, 'init'):
        _milestone_manager.init(dependencies)

# --- Control de lo que se exporta con 'from . import *' ---
__all__ = [
    'init_screens',
    'show_welcome_screen',
    'show_config_editor_screen',
    'show_dashboard_screen',
    'show_position_viewer_screen',
    'show_log_viewer',
    'show_milestone_manager_screen',
]