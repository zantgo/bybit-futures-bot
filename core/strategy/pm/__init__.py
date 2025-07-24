"""
Paquete del Position Manager (PM).

Este archivo __init__.py actúa como la fachada pública para el paquete `pm`.
Su principal responsabilidad es exponer la interfaz de control (`api`) y las
clases principales del dominio a otras partes del sistema.

La lógica de orquestación que antes residía aquí ha sido migrada a la clase
`PositionManager` en `_manager.py` para seguir los principios de Clean Architecture.
"""

# --- Exposición de la API Pública ---
# La TUI y otros consumidores externos interactuarán con el PM a través de esta API.
# Esta API actúa como un proxy a la instancia activa de PositionManager.
from . import _api as api

# --- Exposición de las Clases Principales ---
# Se exponen las clases para que puedan ser instanciadas por el 'runner' o el
# ensamblador de dependencias en una capa superior.
from ._balance import BalanceManager
from ._position_state import PositionState
from ._executor import PositionExecutor
from .manager import PositionManager

# --- Control de lo que se exporta con 'from core.strategy.pm import *' ---
# Definir __all__ para una API de paquete limpia y explícita.
__all__ = [
    'api',
    'PositionManager',
    'BalanceManager',
    'PositionState',
    'PositionExecutor',
]