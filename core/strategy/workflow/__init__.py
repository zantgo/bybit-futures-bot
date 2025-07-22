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
from ._data_processing import process_tick_and_generate_signal, initialize_data_processing

# Desde el módulo de comprobación de límites y disyuntores
from ._limit_checks import (
    check_trend_limits,
    check_session_limits,
    GlobalStopLossException,
    initialize_limit_checks,
    has_global_stop_loss_triggered
)

# El módulo _pm_interaction.py ha sido eliminado, ya que el event_processor
# ahora interactúa directamente con la instancia del PositionManager.

# --- Control de lo que se exporta con 'from . import *' ---
__all__ = [
    'check_conditional_triggers',
    'process_tick_and_generate_signal',
    'initialize_data_processing',
    'check_trend_limits',
    'check_session_limits',
    'GlobalStopLossException',
    'initialize_limit_checks',
    'has_global_stop_loss_triggered'
]