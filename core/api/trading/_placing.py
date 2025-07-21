# core/api/trading/_placing.py

"""
Módulo para la Colocación de Órdenes.

Su única responsabilidad es contener la lógica para enviar nuevas órdenes
de mercado a la API de Bybit.
"""
import traceback
from typing import Optional, Union, Dict

# --- Dependencias del Proyecto ---
import config
from connection import manager as connection_manager
from core.logging import memory_logger

# Importar excepciones específicas con fallbacks
try:
    from pybit.exceptions import InvalidRequestError, FailedRequestError
except ImportError:
    class InvalidRequestError(Exception): pass
    class FailedRequestError(Exception):
        def __init__(self, message, status_code=None):
            super().__init__(message)
            self.status_code = status_code
            
# Importar helpers del paquete y del sub-paquete
from .._helpers import _handle_api_error_generic
from ._helpers import _validate_and_round_quantity

def place_market_order(
    symbol: str,
    side: str,
    quantity: Union[float, str],
    reduce_only: bool = False,
    position_idx: Optional[int] = None,
    account_name: Optional[str] = None
) -> Optional[dict]:
    """
    Coloca una orden de mercado en Bybit (v5 API).

    Delega la validación y redondeo de la cantidad al helper y utiliza
    la lógica centralizada para seleccionar la cuenta de trading correcta.

    Args:
        symbol (str): El símbolo del instrumento.
        side (str): 'Buy' o 'Sell'.
        quantity (Union[float, str]): La cantidad deseada de la orden.
        reduce_only (bool): Flag para órdenes de solo reducción.
        position_idx (Optional[int]): Índice de posición para Hedge Mode.
        account_name (Optional[str]): Nombre de una cuenta específica a usar (override).

    Returns:
        Optional[dict]: La respuesta de la API si la orden es aceptada, o None si hay un error previo.
    """
    if not (connection_manager and config):
        print("ERROR [Place Order]: Dependencias no disponibles.")
        return None
    if side not in ["Buy", "Sell"]:
        print(f"ERROR [Place Order]: Lado inválido '{side}'.")
        return None

    # 1. Validar y formatear la cantidad usando el helper
    qty_str_api = _validate_and_round_quantity(
        quantity=quantity,
        symbol=symbol,
        reduce_only=reduce_only
    )
    if qty_str_api is None:
        # El helper ya habrá impreso el error específico
        return None

    # 2. Obtener la sesión API correcta para la operación
    op_side = 'long' if side == 'Buy' else 'short'
    session, target_account = connection_manager.get_session_for_operation(
        purpose='trading',
        side=op_side,
        specific_account=account_name
    )
    if not session:
        print("ERROR [Place Order]: No se pudo obtener una sesión API válida para la operación.")
        return None

    # 3. Construir los parámetros de la orden
    params = {
        "category": getattr(config, 'CATEGORY_LINEAR', 'linear'),
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": qty_str_api,
        "reduceOnly": bool(reduce_only)
    }
    
    # Añadir lógica de positionIdx para Hedge Mode
    is_hedge_mode = getattr(config, 'BYBIT_HEDGE_MODE_ENABLED', True)
    if is_hedge_mode:
        if position_idx is None:
            # Por defecto: 1 para Long (Buy), 2 para Short (Sell)
            position_idx = 1 if side == "Buy" else 2
        params["positionIdx"] = position_idx
    else:
        params["positionIdx"] = 0

    # 4. Ejecutar la llamada a la API
    memory_logger.log(f"Enviando orden MARKET a cuenta '{target_account}': {params}", level="INFO")
    
    try:
        if not hasattr(session, 'place_order'):
            memory_logger.log(f"ERROR Fatal [Place Order]: La sesión para '{target_account}' no tiene el método 'place_order'.", level="ERROR")
            return None
            
        response = session.place_order(**params)
        
        if not _handle_api_error_generic(response, "Place Market Order"):
            order_id = response.get('result', {}).get('orderId', 'N/A')
            memory_logger.log(f"ÉXITO [Place Order]: Orden aceptada por API. OrderID: {order_id}", level="INFO")

        # Se devuelve la respuesta completa (con éxito o con error de la API)
        return response
            
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Place Order]: {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Place Order]: {e}")
        traceback.print_exc()
        return None