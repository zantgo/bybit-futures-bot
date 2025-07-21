# core/strategy/ta/__init__.py

"""
Paquete de Análisis Técnico (TA).

Este __init__.py actúa como la fachada pública para todo el paquete de TA.
Expone las funciones del gestor (`_manager.py`), ocultando los detalles
de implementación del almacenamiento de datos (`_data_store.py`) y los
cálculos (`_calculator.py`).
"""

# Importar y exponer la interfaz pública desde el módulo gestor
from ._manager import (
    initialize,
    process_raw_price_event,
    get_latest_indicators,
)

# Definir __all__ para una API de paquete limpia y explícita
__all__ = [
    'initialize',
    'process_raw_price_event',
    'get_latest_indicators',
]