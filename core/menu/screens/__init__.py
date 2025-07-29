"""
Paquete de Pantallas de la TUI.

Este paquete organiza y contiene la lógica para cada pantalla individual
del menú interactivo del bot.

v3.0 (Refactor de Modularización):
- Se actualiza para reflejar la nueva estructura modular, reemplazando la
  importación directa de `_milestone_manager` por el nuevo módulo `operation_manager`.
"""
# (COMENTARIO) Docstring de la versión anterior (v2.0) para referencia:
# """
# Paquete de Pantallas de la TUI.
# 
# v2.0 (Refactor de Hitos): Se actualiza para reflejar la nueva estructura de
# pantallas, eliminando los modos manual/auto y centralizando la lógica en el
# nuevo `_milestone_manager`.
# """
from typing import Dict, Any

# --- Importar y Exponer Funciones Públicas de cada Pantalla ---
from ._welcome import show_welcome_screen
from ._config_editor import show_config_editor_screen
from ._dashboard import show_dashboard_screen
from ._position_viewer import show_position_viewer_screen
from ._log_viewer import show_log_viewer

# --- INICIO DE LA MODIFICACIÓN: Importar el nuevo módulo ---
# Se importa la función pública expuesta por el __init__.py de operation_manager
from .operation_manager import show_operation_manager_screen

# (COMENTADO) Se elimina la importación del archivo obsoleto.
# from ._milestone_manager import show_milestone_manager_screen
# --- FIN DE LA MODIFICACIÓN ---

# --- Inyección de Dependencias ---

def init_screens(dependencies: Dict[str, Any]):
    """
    Inyecta las dependencias necesarias en los módulos de pantalla que las requieran.
    """
    # Importar los módulos internamente para acceder a sus funciones `init`
    from . import _dashboard, _welcome, _config_editor, operation_manager

    # Este patrón permite que los módulos de pantalla permanezcan desacoplados
    # del resto de la aplicación, ya que reciben sus dependencias en lugar de importarlas.
    if hasattr(_dashboard, 'init'):
        _dashboard.init(dependencies)
    if hasattr(_welcome, 'init'):
        _welcome.init(dependencies)
    if hasattr(_config_editor, 'init'):
        _config_editor.init(dependencies)
    
    # --- INICIO DE LA MODIFICACIÓN: Inyectar dependencias en el nuevo módulo ---
    # Ahora llamamos a la función init del módulo 'operation_manager'
    if hasattr(operation_manager, 'init'):
        operation_manager.init(dependencies)
    
    # (COMENTADO) Se elimina la lógica que apuntaba al archivo obsoleto.
    # from . import _milestone_manager
    # if hasattr(_milestone_manager, 'init'):
    #     _milestone_manager.init(dependencies)
    # --- FIN DE LA MODIFICACIÓN ---

# --- Control de lo que se exporta con 'from . import *' ---
__all__ = [
    'init_screens',
    'show_welcome_screen',
    'show_config_editor_screen',
    'show_dashboard_screen',
    'show_position_viewer_screen',
    'show_log_viewer',
    # --- INICIO DE LA MODIFICACIÓN: Exponer la nueva función ---
    'show_operation_manager_screen',
    # (COMENTADO) Se elimina la exportación de la función obsoleta.
    # 'show_milestone_manager_screen',
    # --- FIN DE LA MODIFICACIÓN ---
]