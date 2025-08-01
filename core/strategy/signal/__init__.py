# core/strategy/signal/__init__.py

"""
Paquete de Generación de Señales.

Este __init__.py actúa como la fachada pública para el paquete.
Expone la clase principal SignalGenerator, que encapsula toda la lógica
de generación de señales, ocultando los detalles de implementación de
los módulos de reglas y manejo de datos.
"""

# Importar y exponer la nueva clase principal como la API pública del paquete
from ._generator import SignalGenerator

# Definir __all__ para una API de paquete limpia y explícita.
# Cualquiera que haga 'from core.strategy.signal import *' solo obtendrá SignalGenerator.
__all__ = [
    'SignalGenerator',
]