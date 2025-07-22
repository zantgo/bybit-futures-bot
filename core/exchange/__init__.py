"""
Paquete de la Interfaz de Exchange.

Este paquete define el protocolo de comunicación abstracto entre el bot
y cualquier exchange de criptomonedas, logrando la independencia de la plataforma.

Componentes Clave:
- _interface.py: Define la clase base abstracta `AbstractExchange`.
- _models.py: Define los modelos de datos estandarizados (`StandardOrder`, etc.).
- bybit_adapter.py: Una implementación concreta del `AbstractExchange` para Bybit.
"""

# Exponer la interfaz principal y los modelos de datos
from ._interface import AbstractExchange
from ._models import (
    StandardInstrumentInfo,
    StandardBalance,
    StandardPosition,
    StandardOrder,
    StandardTicker
)

__all__ = [
    'AbstractExchange',
    'StandardInstrumentInfo',
    'StandardBalance',
    'StandardPosition',
    'StandardOrder',
    'StandardTicker'
]