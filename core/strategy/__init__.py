# core/strategy/__init__.py

"""
Paquete de Estrategia de Trading.

Este paquete contiene toda la lógica relacionada con la toma de decisiones,
desde el análisis técnico de bajo nivel hasta la gestión de posiciones de alto nivel.

Se organiza en los siguientes componentes públicos:
- event_processor: El orquestador que procesa cada tick de precio.
- ta: Fachada para el módulo de Análisis Técnico.
- signal: Fachada para el módulo de Generación de Señales.
- pm: Fachada para el Position Manager, que gestiona el capital y las posiciones.
"""

# --- Importar y Exponer Módulos y Sub-Paquetes ---

# Importar el procesador de eventos
from . import _event_processor as event_processor

# Importar las fachadas de los sub-paquetes
from . import ta
from . import signal
from . import pm

__all__ = [
    'event_processor',
    'ta',
    'signal',
    'pm',
]
