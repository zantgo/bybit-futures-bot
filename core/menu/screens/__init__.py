"""
Paquete de Pantallas de la TUI.
"""
from typing import Dict, Any

# --- Importar y Exponer Funciones Públicas de cada Pantalla ---
from ._welcome import show_welcome_screen
from ._dashboard import show_dashboard_screen
from ._position_viewer import show_position_viewer_screen
from ._log_viewer import show_log_viewer
from .operation_manager import show_operation_manager_screen
from ._general_config_editor import show_general_config_editor_screen
from ._session_config_editor import show_session_config_editor_screen

def init_screens(dependencies: Dict[str, Any]):
    """
    Inyecta las dependencias necesarias en los módulos de pantalla que las requieran.
    """
    from . import _dashboard, _welcome, operation_manager
    from . import _general_config_editor, _session_config_editor
    if hasattr(_dashboard, 'init'): _dashboard.init(dependencies)
    if hasattr(_welcome, 'init'): _welcome.init(dependencies)
    if hasattr(operation_manager, 'init'): operation_manager.init(dependencies)
    if hasattr(_general_config_editor, 'init'): _general_config_editor.init(dependencies)
    if hasattr(_session_config_editor, 'init'): _session_config_editor.init(dependencies)

__all__ = [
    'init_screens',
    'show_welcome_screen',
    'show_dashboard_screen',
    'show_position_viewer_screen',
    'show_log_viewer',
    'show_operation_manager_screen',
    'show_general_config_editor_screen',
    'show_session_config_editor_screen',
]