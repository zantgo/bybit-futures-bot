# core/menu/screens/__init__.py

"""
Paquete de Pantallas de la TUI.

Este paquete organiza y contiene la lógica para cada pantalla individual
del menú interactivo del bot.

Este archivo __init__.py actúa como una fachada, importando todas las funciones
de pantalla públicas desde sus módulos internos y exponiéndolas de forma
unificada para que otros módulos (como _main_loop) puedan utilizarlas.
"""

# --- Importar y Exponer Funciones Públicas de cada Pantalla ---

# Desde el módulo de la pantalla de estado
from ._status import show_status_screen

# Desde el módulo de la pantalla de modo de trading
from ._mode import show_mode_menu

# Desde el módulo de la pantalla de gestión de riesgo
from ._risk import show_risk_menu

# Desde el módulo de la pantalla de gestión de capital
from ._capital import show_capital_menu

# Desde el módulo de la pantalla de gestión de posiciones
from ._positions import show_positions_menu

# Desde el módulo de la pantalla de automatización y triggers
from ._automation import show_automation_menu

# Desde el módulo de la pantalla del visor de logs
from ._log_viewer import show_log_viewer


# --- Control de lo que se exporta con 'from . import *' ---
# Definir __all__ es una buena práctica para una API pública limpia.
__all__ = [
    'show_status_screen',
    'show_mode_menu',
    'show_risk_menu',
    'show_capital_menu',
    'show_positions_menu',
    'show_automation_menu',
    'show_log_viewer',
]