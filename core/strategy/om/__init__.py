"""
Paquete del Operation Manager (OM).

Este archivo __init__.py actúa como la fachada pública para el paquete `om`.
Su responsabilidad es exponer la interfaz de control (`api`) y las clases
principales del dominio a otras partes del sistema, como el `runner` o la TUI.
"""

# --- Exposición de la API Pública ---
# La TUI y otros componentes (como el PositionManager) interactuarán con el OM
# a través de esta API. Esta API actúa como un proxy a la instancia activa de OperationManager.
from . import _api as api

# --- Exposición de las Clases y Entidades Principales ---
# Se exponen las clases para que puedan ser instanciadas por el 'runner' o el
# ensamblador de dependencias en una capa superior.
from ._manager import OperationManager

# --- INICIO DE LA MODIFICACIÓN ---
# Se corrige la importación para apuntar a la nueva ubicación centralizada.
from ..entities import Operacion
# --- FIN DE LA MODIFICACIÓN ---

# --- Control de lo que se exporta con 'from core.strategy.om import *' ---
# Definir __all__ para una API de paquete limpia y explícita.
__all__ = [
    'api',
    'OperationManager',
    'Operacion',
]