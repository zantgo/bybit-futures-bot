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
from . import _api as api

__all__ = [
    'api',
]
