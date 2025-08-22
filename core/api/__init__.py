# core/api/__init__.py

"""
Paquete de la Interfaz de la API.

Este paquete actúa como una fachada pública que abstrae y organiza todas las
interacciones con la API del exchange (Bybit). Expone funciones para:
- Obtener datos de mercado.
- Consultar información de la cuenta.
- Ejecutar operaciones de trading.

La lógica interna está separada en submódulos y sub-paquetes para mejorar la
mantenibilidad y claridad del código.
"""

# --- Importar y Exponer Funciones Públicas ---

# Desde el módulo de datos de mercado (_market_data.py)
from ._market_data import (
    get_instrument_info,
)

# Desde el módulo de gestión de cuenta (_account.py)
from ._account import (
    get_unified_account_balance_info,
    get_funding_account_balance_info,
    get_order_status,
    get_active_position_details_api,
    get_order_execution_history,
    get_position_info_api,
)

# Se actualiza la importación para apuntar al nuevo sub-paquete 'trading'.
# La palabra clave 'trading' ahora representa la fachada 'core/api/trading/__init__.py'
from . import trading

# --- Control de lo que se exporta con 'from core.api import *' ---
# Es una buena práctica definir __all__ para una API pública limpia.
__all__ = [
    # Funciones de datos de mercado
    'get_instrument_info',

    # Funciones de información de cuenta
    'get_unified_account_balance_info',
    'get_funding_account_balance_info',
    'get_order_status',
    'get_active_position_details_api',
    'get_order_execution_history',
    'get_position_info_api',
    'set_leverage',
    'place_market_order',
    'cancel_order',
    'close_all_symbol_positions',
    'close_position_by_side',
]
set_leverage = trading.set_leverage
place_market_order = trading.place_market_order
cancel_order = trading.cancel_order
close_all_symbol_positions = trading.close_all_symbol_positions
close_position_by_side = trading.close_position_by_side