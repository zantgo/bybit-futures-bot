"""
Paquete del BotController.

Este paquete encapsula toda la lógica relacionada con el ciclo de vida de la
aplicación del bot en su conjunto.

Este archivo `__init__.py` actúa como la fachada pública para el paquete,
exponiendo la interfaz de control (`api`) que otras partes del sistema,
como el `main_controller` de la TUI, utilizarán para interactuar con el
BotController.
"""

# --- Exposición de la API Pública ---
# Se importa el módulo `_api` y se le da un alias público y corto `api`.
# Esto permite a otros módulos acceder a las funciones del BotController
# de forma limpia y desacoplada, por ejemplo: `from core.bot_controller import api`.
from . import _api as api

# --- Control de lo que se exporta con 'from core.bot_controller import *' ---
# Es una buena práctica definir `__all__` para declarar explícitamente la
# interfaz pública del paquete. En este caso, solo queremos exponer el
# módulo `api`.
__all__ = [
    'api',
]