"""
Define la Interfaz Abstracta de Exchange.
v2.0: Añadido soporte para cuentas con propósito y transferencias.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Callable

from ._models import (
    StandardOrder,
    StandardPosition,
    StandardBalance,
    StandardInstrumentInfo,
    StandardTicker
)

class AbstractExchange(ABC):
    """
    Define la interfaz (el protocolo) que toda implementación de exchange debe seguir.
    Esta clase es agnóstica al exchange y opera con modelos de datos estandarizados.
    """

    @abstractmethod
    def initialize(self, symbol: str) -> bool:
        """Inicializa el adaptador y verifica la conexión a las cuentas necesarias."""
        pass
        
    @abstractmethod
    def get_instrument_info(self, symbol: str) -> Optional[StandardInstrumentInfo]:
        """Obtiene información estandarizada del instrumento."""
        pass

    @abstractmethod
    def get_balance(self, account_purpose: str) -> Optional[StandardBalance]:
        """
        Obtiene el balance estandarizado de una cuenta con un propósito específico
        (ej: 'longs', 'shorts', 'profit', 'main').
        """
        pass

    @abstractmethod
    def get_positions(self, symbol: str, account_purpose: str) -> List[StandardPosition]:
        """
        Obtiene una lista de posiciones abiertas estandarizadas de una cuenta con propósito.
        """
        pass
    
    @abstractmethod
    def get_ticker(self, symbol: str) -> Optional[StandardTicker]:
        """Obtiene el último precio (ticker) para un símbolo."""
        pass

    @abstractmethod
    def place_order(self, order: StandardOrder, account_purpose: str) -> Tuple[bool, str]:
        """
        Coloca una orden basada en un objeto de orden estandarizado en una cuenta con propósito.
        Devuelve (éxito, id_de_la_orden_o_mensaje_de_error).
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str, account_purpose: str) -> bool:
        """Cancela una orden por su ID en una cuenta con propósito."""
        pass

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: float, account_purpose: str) -> bool:
        """
        Establece el apalancamiento para un símbolo en una cuenta con propósito.
        """
        pass
        
    @abstractmethod
    def transfer_funds(self, amount: float, from_purpose: str, to_purpose: str, coin: str = "USDT") -> bool:
        """
        Transfiere fondos entre dos cuentas con propósito.
        """
        pass
        
    @abstractmethod
    def get_latest_price(self) -> Optional[float]:
        """Devuelve el último precio conocido del ticker, como un simple float."""
        pass