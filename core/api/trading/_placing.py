# ./core/api/trading/_placing.py

"""
Módulo para la Colocación de Órdenes.
 
Su única responsabilidad es contener la lógica para enviar nuevas órdenes
de mercado a la API de Bybit.
"""
import traceback
from typing import Optional, Union, Dict

# --- Dependencias del Proyecto ---
import config
from core.logging import memory_logger

# --- INICIO DE LA MODIFICACIÓN ---
# Solo importar la función, no ejecutarla.
from connection._manager import get_connection_manager_instance
# connection_manager = get_connection_manager_instance() # <-- COMENTADO/ELIMINADO
# --- FIN DE LA MODIFICACIÓN ---

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
    position_idx: Optional[int] = None, # Lo recibimos, pero ya no lo calculamos aquí
    account_name: Optional[str] = None
) -> Optional[dict]:
    """
    Coloca una orden de mercado en Bybit (v5 API).
    """
    connection_manager = get_connection_manager_instance()
    if not (connection_manager and config):
        memory_logger.log("ERROR [Place Order]: Dependencias no disponibles.", level="ERROR")
        return None
    if side not in ["Buy", "Sell"]:
        memory_logger.log(f"ERROR [Place Order]: Lado inválido '{side}'.", level="ERROR")
        return None

    # 1. Validar y formatear la cantidad
    qty_str_api = _validate_and_round_quantity(
        quantity=quantity,
        symbol=symbol,
        reduce_only=reduce_only
    )
    if qty_str_api is None:
        return None

    # 2. Obtener la sesión API correcta
    op_side = 'long' if side == 'Buy' else 'short'
    session, target_account = connection_manager.get_session_for_operation(
        purpose='trading',
        side=op_side,
        specific_account=account_name
    )
    if not session:
        memory_logger.log("ERROR [Place Order]: No se pudo obtener una sesión API válida para la operación.", level="ERROR")
        return None

    # 3. Construir los parámetros de la orden
    params = {
        "category": config.EXCHANGE_CONSTANTS["BYBIT"]["CATEGORY_LINEAR"],
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": qty_str_api,
        "reduceOnly": bool(reduce_only)
    }
    
    # --- INICIO DE LA REVERSIÓN ---
    # La lógica compleja se elimina. Simplemente añadimos el position_idx si se proporciona.
    if position_idx is not None:
        params["positionIdx"] = position_idx
    # --- FIN DE LA REVERSIÓN ---

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

        return response
            
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        memory_logger.log(f"ERROR API [Place Order]: {api_err} (Status: {status_code})", level="ERROR")
        return None
    except Exception as e:
        memory_logger.log(f"ERROR Inesperado [Place Order]: {e}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")
        return None