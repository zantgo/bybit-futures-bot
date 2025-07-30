"""
Paquete del SessionManager (SM).

Este paquete encapsula toda la lógica relacionada con el ciclo de vida y la
gestión de una única sesión de trading.

Este archivo `__init__.py` actúa como la fachada pública para el paquete,
exponiendo la interfaz de control (`api`) que otras partes del sistema,
como la pantalla del dashboard, utilizarán para interactuar con la sesión activa.
"""

# --- Exposición de la API Pública ---
# Se importa el módulo `_api` y se le da un alias público `api`.
from . import _api as api

# --- Exposición de Clases Principales ---
# Se expone la clase principal para que pueda ser instanciada por el BotController.
from ._manager import SessionManager

# --- Control de lo que se exporta con 'from core.strategy.sm import *' ---
# Declara explícitamente la interfaz pública del paquete.
__all__ = [
    'api',
    'SessionManager',
]