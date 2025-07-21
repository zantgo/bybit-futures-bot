# core/strategy/workflow/__init__.py

"""
Paquete del Flujo de Trabajo del Event Processor.

Este paquete encapsula y organiza las diferentes etapas lógicas que componen
el procesamiento de un único evento de precio (tick).

Cada módulo interno tiene una responsabilidad única, y este archivo __init__.py
actúa como una fachada pública para exponer esas funcionalidades al orquestador
principal (_event_processor.py).
"""

# --- Importar y Exponer Funciones Públicas del Flujo de Trabajo ---

# Desde el módulo de gestión de triggers
from ._triggers import check_conditional_triggers

# Desde el módulo de procesamiento de datos y generación de señal
from ._data_processing import process_tick_and_generate_signal

# Desde el módulo de interacción con el Position Manager
from ._pm_interaction import (
    update_pm_with_tick,
    send_signal_to_pm
)

# Desde el módulo de comprobación de límites y disyuntores
from ._limit_checks import (
    check_trend_limits,
    check_session_limits,
    GlobalStopLossException
)


# --- Control de lo que se exporta con 'from . import *' ---
__all__ = [
    'check_conditional_triggers',
    'process_tick_and_generate_signal',
    'update_pm_with_tick',
    'send_signal_to_pm',
    'check_trend_limits',
    'check_session_limits',
    'GlobalStopLossException',
]