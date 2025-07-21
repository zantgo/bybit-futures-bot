# core/strategy/signal/__init__.py

"""
Paquete de Generación de Señales.

Este __init__.py actúa como la fachada pública para el paquete `signal`.
Expone la función principal `generate_signal` desde el módulo orquestador `_generator.py`,
ocultando los detalles de implementación del manejo de datos y las reglas.
"""

# Importar y exponer la interfaz pública desde el módulo generador
from ._generator import generate_signal

# Definir __all__ para una API de paquete limpia y explícita
__all__ = [
    'generate_signal',
]