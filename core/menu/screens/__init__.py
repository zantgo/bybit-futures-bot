# core/menu/screens/__init__.py

"""
Paquete de Pantallas de la TUI.

Este paquete organiza y contiene la lógica para cada pantalla individual
del menú interactivo del bot.

Este __init__.py actúa como una fachada, importando todas las funciones
de pantalla públicas y proporcionando una función de inicialización para
inyectar las dependencias necesarias en cada una.
"""
from typing import Dict, Any

# --- Importar y Exponer Funciones Públicas de cada Pantalla ---
# Ahora importamos las funciones de las pantallas que hemos creado.
from ._welcome import show_welcome_screen
from ._config_editor import show_config_editor_screen
from ._dashboard import show_dashboard_screen
from ._manual_mode import show_manual_mode_screen
from ._auto_mode import show_auto_mode_screen
from ._position_viewer import show_position_viewer_screen
from ._log_viewer import show_log_viewer

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
    # Añadir inicializadores para otras pantallas si los necesitan en el futuro.
    # --- INICIO DE LA SOLUCIÓN ---
    # Añadimos la inicialización para el editor de configuración.
    if hasattr(_config_editor, 'init'):
        _config_editor.init(dependencies)
    # --- FIN DE LA SOLUCIÓN ---
# --- Control de lo que se exporta con 'from . import *' ---
__all__ = [
    'init_screens',
    'show_welcome_screen',
    'show_config_editor_screen',
    'show_dashboard_screen',
    'show_manual_mode_screen',
    'show_auto_mode_screen',
    'show_position_viewer_screen',
    'show_log_viewer',
]