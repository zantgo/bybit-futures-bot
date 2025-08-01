"""
Paquete de Conexión.

v2.0 (Refactor a Clases):
- Se actualiza el __init__.py para exponer directamente las CLASES
  `ConnectionManager` y `Ticker`, en lugar de los módulos.
- Esto permite importaciones más limpias y directas como:
  `from connection import ConnectionManager`.
"""

# --- Importar y Exponer las Clases Principales ---
# Importamos las clases desde sus módulos privados para exponerlas públicamente.
from ._manager import ConnectionManager
from ._ticker import Ticker

# Definir __all__ para una API de paquete limpia y explícita.
# Ahora, `from connection import *` importará estas clases.
__all__ = [
    'ConnectionManager',
    'Ticker',
]