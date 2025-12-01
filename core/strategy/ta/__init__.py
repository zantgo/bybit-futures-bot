# core/strategy/ta/__init__.py

"""
Paquete de Análisis Técnico (TA).

Este __init__.py actúa como la fachada pública para todo el paquete de TA.
Expone la clase principal TAManager, que encapsula toda la lógica de TA,
ocultando los detalles de implementación internos.
"""

from ._manager import TAManager

__all__ = [
    'TAManager',
]
