"""
Paquete del Operation Manager (OM).

Este archivo __init__.py actúa como la fachada pública para el paquete `om`.
Su responsabilidad es exponer la interfaz de control (`api`) y las clases
principales del dominio a otras partes del sistema, como el `runner` o la TUI.
"""

from . import _api as api
from ._manager import OperationManager
from ..entities import Operacion

__all__ = [
    'api',
    'OperationManager',
    'Operacion',
]
