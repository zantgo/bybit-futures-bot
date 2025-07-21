# core/logging/__init__.py

"""
Paquete de Logging del Bot.

Este paquete centraliza todos los módulos relacionados con el registro de eventos,
incluyendo logs en memoria para la TUI y logs persistentes en archivos para
señales, posiciones cerradas y snapshots.

Módulos Públicos:
- memory_logger: Para capturar logs en una cola en memoria.
- signal_logger: Para registrar cada señal de trading generada.
- closed_position_logger: Para registrar los detalles de cada posición cerrada.
- open_position_logger: Para guardar una instantánea final de las posiciones abiertas.
"""

# --- Importar y Exponer Módulos de Logging ---

# Importar los módulos internos privados con un alias público y más legible.
from . import _memory_logger as memory_logger
from . import _signal_logger as signal_logger
from . import _close_position_logger as closed_position_logger
from . import _open_position_logger as open_position_logger

# --- Control de lo que se exporta con 'from core.logging import *' ---
# Es una buena práctica definir __all__ para una API pública limpia.
__all__ = [
    'memory_logger',
    'signal_logger',
    'closed_position_logger',
    'open_position_logger',
]