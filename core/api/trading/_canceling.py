# core/api/trading/_canceling.py

"""
Módulo para la Cancelación de Órdenes.

Su única responsabilidad es contener la lógica para enviar solicitudes de
cancelación de órdenes a la API de Bybit.
"""
import traceback
from typing import Optional, Dict

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
            
# Importar helper de la capa superior de la API
from .._helpers import _handle_api_error_generic

def cancel_order(
    symbol: str,
    order_id: Optional[str] = None,
    order_link_id: Optional[str] = None,
    account_name: Optional[str] = None
) -> Optional[dict]:
    """
    Cancela una orden específica en Bybit (v5 API).

    Se puede cancelar usando `order_id` o `order_link_id`.

    Args:
        symbol (str): El símbolo del instrumento.
        order_id (Optional[str]): El ID de la orden de Bybit.
        order_link_id (Optional[str]): El ID personalizado de la orden.
        account_name (Optional[str]): Nombre de la cuenta específica donde se encuentra la orden.

    Returns:
        Optional[dict]: La respuesta de la API, ya sea de éxito o de error.
                         Devuelve None si ocurre un error antes de la llamada a la API.
    """
    if not connection_manager or not config:
        print("ERROR [Cancel Order]: Dependencias no disponibles.")
        return None
    if not order_id and not order_link_id:
        print("ERROR [Cancel Order]: Debe proporcionar order_id o order_link_id.")
        return None
        
    # 1. Obtener la sesión API correcta para la operación
    session, target_account = connection_manager.get_session_for_operation(
        purpose='general',  # Cancelar es una operación general
        specific_account=account_name
    )
    if not session:
        print(f"ERROR [Cancel Order]: No se pudo obtener sesión API válida (solicitada: {account_name}).")
        return None
        
    # 2. Construir los parámetros
    params = {"category": getattr(config, 'CATEGORY_LINEAR', 'linear'), "symbol": symbol}
    id_type = ""
    if order_id:
        params["orderId"] = order_id
        id_type = f"ID={order_id}"
    elif order_link_id:
        params["orderLinkId"] = order_link_id
        id_type = f"LinkID={order_link_id}"
        
    memory_logger.log(f"Intentando cancelar orden {id_type} para {symbol} en '{target_account}'...", level="INFO")
    
    # 3. Ejecutar la llamada a la API
    try:
        if not hasattr(session, 'cancel_order'):
            memory_logger.log(f"ERROR Fatal [Cancel Order]: La sesión para '{target_account}' no tiene el método 'cancel_order'.", level="ERROR")
            return None
            
        response = session.cancel_order(**params)
        
        if not _handle_api_error_generic(response, f"Cancel Order {id_type}"):
            canceled_id = response.get('result', {}).get('orderId') or response.get('result', {}).get('orderLinkId', 'N/A')
            memory_logger.log(f"ÉXITO [Cancel Order]: Cancelación aceptada para orden {canceled_id}.", level="INFO")
        elif response and response.get('retCode') == 110001:
            memory_logger.log(f"INFO [Cancel Order]: Orden {id_type} no encontrada o ya finalizada (110001).", level="WARN")

        # Devuelve la respuesta de la API en todos los casos (éxito o error API)
        return response
            
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Cancel Order]: {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Cancel Order]: {e}")
        traceback.print_exc()
        return None