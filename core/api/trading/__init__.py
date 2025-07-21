# core/api/trading/__init__.py

"""
Fachada Pública para el Sub-paquete de Operaciones de Trading.

Este módulo importa y expone de forma unificada todas las funciones de
alto nivel relacionadas con la ejecución de operaciones de trading,
ocultando la estructura interna de los submódulos.
"""

# Importar funciones desde sus respectivos módulos especializados
from ._leverage import set_leverage
from ._placing import place_market_order
from ._canceling import cancel_order
from ._closing import close_all_symbol_positions, close_position_by_side

# Definir __all__ para una API pública limpia y explícita
__all__ = [
    'set_leverage',
    'place_market_order',
    'cancel_order',
    'close_all_symbol_positions',
    'close_position_by_side',
]