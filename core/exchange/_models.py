"""
Define los Modelos de Datos Estandarizados para la Interfaz de Exchange.

Estas `dataclasses` representan conceptos de trading de forma agnóstica
a cualquier exchange. La lógica de negocio del bot operará exclusivamente
con estos objetos, en lugar de los diccionarios específicos de cada API.
"""
from dataclasses import dataclass
from typing import Optional
import datetime

@dataclass
class StandardInstrumentInfo:
    """Información normalizada de un instrumento."""
    symbol: str
    price_precision: int      # Número de decimales para el precio
    quantity_precision: int   # Número de decimales para la cantidad
    min_order_size: float
    max_order_size: float
    qty_step: float

@dataclass
class StandardBalance:
    """Balance normalizado de una cuenta."""
    total_equity_usd: float
    available_balance_usd: float

@dataclass
class StandardPosition:
    """Posición normalizada."""
    symbol: str
    side: str                   # 'long' o 'short'
    size_contracts: float
    avg_entry_price: float
    liquidation_price: Optional[float]
    unrealized_pnl: float
    margin_usd: float

@dataclass
class StandardOrder:
    """Orden normalizada para ser enviada al exchange."""
    symbol: str
    side: str                   # 'buy' o 'sell'
    order_type: str             # 'market' o 'limit'
    quantity_contracts: float
    price: Optional[float] = None  # Para órdenes límite
    reduce_only: bool = False

@dataclass
class StandardTicker:
    """Información normalizada de un tick de precio."""
    timestamp: datetime.datetime
    symbol: str
    price: float
