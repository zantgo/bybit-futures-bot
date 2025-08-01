# core/strategy/ta/__init__.py

"""
Paquete de Análisis Técnico (TA).

Este __init__.py actúa como la fachada pública para todo el paquete de TA.
Expone la clase principal TAManager, que encapsula toda la lógica de TA,
ocultando los detalles de implementación internos.
"""

# Importar y exponer la nueva clase principal como la API pública del paquete
from ._manager import TAManager

# Definir __all__ para una API de paquete limpia y explícita.
# Cualquiera que haga 'from core.strategy.ta import *' solo obtendrá TAManager.
__all__ = [
    'TAManager',
]