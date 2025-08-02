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
    # --- INICIO DE LA MODIFICACIÓN ---
    # Obtenemos la instancia JUSTO cuando se necesita.
    connection_manager = get_connection_manager_instance()
    if not (connection_manager and config):
    # --- FIN DE LA MODIFICACIÓN ---
        memory_logger.log("ERROR [Place Order]: Dependencias no disponibles.", level="ERROR")
        return None
    if side not in ["Buy", "Sell"]:
        memory_logger.log(f"ERROR [Place Order]: Lado inválido '{side}'.", level="ERROR")
        return None

    # 1. Validar y formatear la cantidad usando el helper
    qty_str_api = _validate_and_round_quantity(
        quantity=quantity,
        symbol=symbol,
        reduce_only=reduce_only
    )
    if qty_str_api is None:
        # El helper ya habrá logueado el error específico
        return None

    # 2. Obtener la sesión API correcta para la operación
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
    
    # Añadir lógica de positionIdx para Hedge Mode
    is_hedge_mode = config.EXCHANGE_CONSTANTS["BYBIT"]["HEDGE_MODE_ENABLED"]
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
        memory_logger.log(f"ERROR API [Place Order]: {api_err} (Status: {status_code})", level="ERROR")
        return None
    except Exception as e:
        memory_logger.log(f"ERROR Inesperado [Place Order]: {e}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")
        return None