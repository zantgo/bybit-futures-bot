# core/api/trading/_helpers.py

"""
Módulo de Ayuda para las Operaciones de Trading.

Contiene funciones auxiliares específicas para el sub-paquete de trading,
como la validación y el redondeo de cantidades de órdenes según las reglas
del instrumento.
"""
from typing import Optional, Union
from decimal import Decimal, ROUND_DOWN, InvalidOperation

# --- Dependencias del Proyecto ---
import config
from core.logging import memory_logger
from .._market_data import get_instrument_info
from .._helpers import _get_qty_precision_from_step

def _validate_and_round_quantity(
    quantity: Union[float, str],
    symbol: str,
    reduce_only: bool
) -> Optional[str]:
    """
    Valida y redondea la cantidad de una orden según las reglas del instrumento.

    Esta función centraliza la lógica de consultar la información del instrumento
    para obtener la precisión y la cantidad mínima, y luego formatea la
    cantidad para que sea compatible con la API de Bybit.

    Args:
        quantity: La cantidad deseada, como float o string.
        symbol: El símbolo del instrumento (ej. 'BTCUSDT').
        reduce_only: Flag que indica si la orden es de solo reducción.

    Returns:
        Un string con la cantidad formateada lista para la API, o None si la
        validación falla (ej. la cantidad es demasiado pequeña).
    """
    # Obtener la precisión y la cantidad mínima, con fallbacks a config
    instrument_info = get_instrument_info(symbol)
    qty_precision = config.PRECISION_FALLBACKS["QTY_PRECISION"]
    min_qty = config.PRECISION_FALLBACKS["MIN_ORDER_QTY"]

    if instrument_info:
        qty_step_str = instrument_info.get('qtyStep')
        min_qty_str = instrument_info.get('minOrderQty')
        if qty_step_str:
            try:
                # Utiliza el helper de la capa superior de la API para consistencia
                qty_precision = _get_qty_precision_from_step(qty_step_str)
            except Exception as e:
                memory_logger.log(f"WARN [_validate_and_round_quantity]: Error procesando qtyStep ({e}). Usando default.", level="WARN")
        if min_qty_str:
            try:
                min_qty = float(min_qty_str)
            except (ValueError, TypeError):
                 memory_logger.log(f"WARN [_validate_and_round_quantity]: minOrderQty inválido ({min_qty_str}). Usando default.", level="WARN")
    else:
        memory_logger.log(f"WARN [_validate_and_round_quantity]: No se pudo obtener instrument info. Usando defaults.", level="WARN")

    # Realizar el redondeo y la validación
    try:
        qty_float = float(quantity)
        if qty_float <= 1e-9:
            memory_logger.log(f"ERROR [_validate_and_round_quantity]: Cantidad debe ser positiva '{quantity}'.", level="ERROR")
            return None
            
        qty_decimal = Decimal(str(qty_float))
        rounding_factor = Decimal('1e-' + str(qty_precision))
        qty_rounded = qty_decimal.quantize(rounding_factor, rounding=ROUND_DOWN)
        
        # Validar contra la cantidad mínima de la orden
        if qty_rounded < Decimal(str(min_qty)):
            if not reduce_only:
                memory_logger.log(f"ERROR [_validate_and_round_quantity]: Cantidad redondeada ({qty_rounded}) es menor que el mínimo requerido ({min_qty}).", level="ERROR")
                return None
            else:
                # Se permite para órdenes de cierre, incluso si son muy pequeñas
                memory_logger.log(f"WARN [_validate_and_round_quantity]: Cantidad de cierre ({qty_rounded}) < mínimo ({min_qty}), permitido por reduce_only=True.", level="WARN")
        
        # Devolver el string formateado final
        return str(qty_rounded)

    except (ValueError, TypeError, InvalidOperation) as e:
        memory_logger.log(f"ERROR [_validate_and_round_quantity]: Cantidad inválida o error de redondeo para '{quantity}': {e}.", level="ERROR")
        return None
