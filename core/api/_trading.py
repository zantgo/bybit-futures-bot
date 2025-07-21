# core/api/_trading.py

"""
Módulo para ejecutar acciones de trading a través de la API de Bybit.

Responsabilidades:
- Colocar y cancelar órdenes.
- Establecer apalancamiento.
- Cerrar posiciones de forma programática.
"""
import sys
import os
import traceback
from typing import Optional, Union, Dict, Any, List
from decimal import Decimal, ROUND_DOWN, InvalidOperation

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias con rutas absolutas desde la raíz del proyecto
try:
    import config
    from connection import manager as connection_manager
    from core.logging import memory_logger
    
    # Importar dependencias relativas dentro del mismo paquete `api`
    from ._helpers import _handle_api_error_generic, _get_qty_precision_from_step
    
    # Importar el paquete api completo para usar su fachada en llamadas internas
    from core import api

    try:
        from pybit.exceptions import InvalidRequestError, FailedRequestError
    except ImportError:
        print("WARN [Trading API Import]: pybit exceptions not found. Using fallback.")
        class InvalidRequestError(Exception): pass
        class FailedRequestError(Exception):
             def __init__(self, message, status_code=None): super().__init__(message); self.status_code = status_code
except ImportError as e:
    print(f"ERROR [Trading API Import]: No se pudo importar módulo necesario: {e}")
    config = type('obj', (object,), {'DEFAULT_QTY_PRECISION': 3, 'DEFAULT_MIN_ORDER_QTY': 0.001, 'ACCOUNT_MAIN': 'main', 'CATEGORY_LINEAR': 'linear', 'BYBIT_HEDGE_MODE_ENABLED': True})()
    connection_manager = None
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    def _get_qty_precision_from_step(step_str): return 3
    def _handle_api_error_generic(response, tag): return True
    api = None
    class InvalidRequestError(Exception): pass
    class FailedRequestError(Exception):
        def __init__(self, message, status_code=None): super().__init__(message); self.status_code = status_code

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Funciones de Operaciones de Trading ---

def set_leverage(
    symbol: str,
    buy_leverage: Union[float, str],
    sell_leverage: Union[float, str],
    account_name: Optional[str] = None
) -> bool:
    """Establece el apalancamiento para un símbolo específico (v5 API)."""
    if not connection_manager or not config:
        print("ERROR [Set Leverage]: Dependencias no disponibles.")
        return False
        
    target_account = account_name
    if not target_account:
         acc_longs = getattr(config, 'ACCOUNT_LONGS', None)
         acc_shorts = getattr(config, 'ACCOUNT_SHORTS', None)
         main_acc = getattr(config, 'ACCOUNT_MAIN', 'main')
         if acc_longs and connection_manager.get_client(acc_longs):
             target_account = acc_longs
         elif acc_shorts and connection_manager.get_client(acc_shorts):
             target_account = acc_shorts
         else:
             target_account = main_acc
             
    session = connection_manager.get_client(target_account)
    if not session:
        print(f"ERROR [Set Leverage]: Sesión API no válida para '{target_account}'.")
        return False
        
    try:
        buy_lev_str = str(float(buy_leverage))
        sell_lev_str = str(float(sell_leverage))
    except (ValueError, TypeError):
        print(f"ERROR [Set Leverage]: Apalancamiento inválido ({buy_leverage}, {sell_leverage}).")
        return False
        
    params = {
        "category": getattr(config, 'CATEGORY_LINEAR', 'linear'),
        "symbol": symbol,
        "buyLeverage": buy_lev_str,
        "sellLeverage": sell_lev_str,
    }
    memory_logger.log(f"Intentando establecer leverage para {symbol} en '{target_account}': Buy={buy_lev_str}x, Sell={sell_lev_str}x", level="INFO")
    
    try:
        if not hasattr(session, 'set_leverage'):
            print("ERROR Fatal [Set Leverage]: Sesión API no tiene método 'set_leverage'.")
            return False
            
        response = session.set_leverage(**params)
        
        if not _handle_api_error_generic(response, "Set Leverage"):
            memory_logger.log(f"ÉXITO [Set Leverage]: Apalancamiento establecido para {symbol}.", level="INFO")
            return True
        elif response and response.get('retCode') == 110043:
            memory_logger.log(f"INFO [Set Leverage]: Apalancamiento no modificado (ya estaba) - Código 110043.", level="INFO")
            return True
        else:
            return False
            
    except InvalidRequestError as invalid_req_err:
        error_message = str(invalid_req_err)
        if "110043" in error_message or "leverage not modified" in error_message.lower():
            memory_logger.log(f"INFO [Set Leverage]: Apalancamiento no modificado (ya estaba) - InvalidRequestError(110043).", level="INFO")
            return True
        else:
            print(f"ERROR API [Set Leverage] - Invalid Request: {invalid_req_err}")
            return False
    except FailedRequestError as api_err:
        status_code = getattr(api_err, 'status_code', None)
        if status_code == 503:
            print(f"WARN [Set Leverage]: Received HTTP 503. Leverage MAY already be set. Continuing.")
            return True
        else:
            print(f"ERROR API [Set Leverage]: {api_err} (Status: {status_code})")
            return False
    except Exception as e:
        print(f"ERROR Inesperado [Set Leverage]: {e}")
        traceback.print_exc()
        return False

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
    Obtiene precisión y mínimo de la API y redondea/valida la cantidad.
    """
    if not connection_manager or not config or not api:
        print("ERROR [Place Order]: Dependencias no disponibles.")
        return None
    if side not in ["Buy", "Sell"]:
        print(f"ERROR [Place Order]: Lado inválido '{side}'.")
        return None

    instrument_info = api.get_instrument_info(symbol)
    qty_precision = getattr(config, 'DEFAULT_QTY_PRECISION', 3)
    min_qty = getattr(config, 'DEFAULT_MIN_ORDER_QTY', 0.001)
    
    if instrument_info:
        qty_step_str = instrument_info.get('qtyStep')
        min_qty_str = instrument_info.get('minOrderQty')
        if qty_step_str and min_qty_str:
            try:
                qty_precision = _get_qty_precision_from_step(qty_step_str)
                min_qty = float(min_qty_str)
            except (ValueError, TypeError) as e:
                print(f"WARN [Place Order]: Error procesando instrument info ({e}). Usando defaults.")
        else:
            print(f"WARN [Place Order]: Faltan datos en instrument info. Usando defaults.")
    else:
        print(f"WARN [Place Order]: No se pudo obtener instrument info. Usando defaults.")

    try:
        qty_float = float(quantity)
        if qty_float <= 1e-9:
            print(f"ERROR [Place Order]: Cantidad debe ser positiva '{quantity}'.")
            return None
        qty_decimal = Decimal(str(qty_float))
        rounding_factor = Decimal('1e-' + str(qty_precision))
        qty_rounded = qty_decimal.quantize(rounding_factor, rounding=ROUND_DOWN)
        qty_str_api = str(qty_rounded)
        if qty_rounded < Decimal(str(min_qty)):
            if not reduce_only:
                print(f"ERROR [Place Order]: Cantidad redondeada ({qty_str_api}) < mínimo ({min_qty}).")
                return None
            else:
                print(f"WARN [Place Order]: Cantidad de cierre ({qty_str_api}) < mínimo ({min_qty}), pero permitido por reduce_only=True.")
    except (ValueError, TypeError, InvalidOperation) as e:
        print(f"ERROR [Place Order]: Cantidad inválida o error de redondeo '{quantity}': {e}.")
        return None

    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main')
    session = connection_manager.get_client(target_account)
    if not session:
        print(f"ERROR [Place Order]: No se pudo obtener sesión API válida para '{target_account}'.")
        return None

    params = {
        "category": getattr(config, 'CATEGORY_LINEAR', 'linear'),
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": qty_str_api,
        "reduceOnly": bool(reduce_only)
    }
    
    is_hedge_mode = getattr(config, 'BYBIT_HEDGE_MODE_ENABLED', True)
    if is_hedge_mode:
        if position_idx is None:
            position_idx = 1 if side == "Buy" else 2
        elif position_idx not in [1, 2]:
            print(f"ERROR [Place Order]: position_idx ({position_idx}) inválido para modo Hedge (debe ser 1 o 2).")
            return None
        params["positionIdx"] = position_idx
    else:
        params["positionIdx"] = 0

    memory_logger.log(f"Enviando orden MARKET a cuenta '{target_account}': {params}", level="INFO")
    
    try:
        if not hasattr(session, 'place_order'):
            print("ERROR Fatal [Place Order]: Sesión API no tiene método 'place_order'.")
            return None
            
        response = session.place_order(**params)
        
        if not _handle_api_error_generic(response, "Place Order"):
            order_id = response.get('result', {}).get('orderId', 'N/A')
            memory_logger.log(f"ÉXITO [Place Order]: Orden aceptada por API. OrderID: {order_id}", level="INFO")
            return response
        else:
            return response
            
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Place Order]: {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Place Order]: {e}")
        traceback.print_exc()
        return None

def cancel_order( symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None, account_name: Optional[str] = None) -> Optional[dict]:
    """Cancela una orden específica en Bybit (v5 API)."""
    if not connection_manager or not config:
        print("ERROR [Cancel Order]: Dependencias no disponibles.")
        return None
    if not order_id and not order_link_id:
        print("ERROR [Cancel Order]: Debe proporcionar order_id o order_link_id.")
        return None
        
    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main')
    session = connection_manager.get_client(target_account)
    if not session:
        print(f"ERROR [Cancel Order]: Sesión API no válida para '{target_account}'.")
        return None
        
    params = {"category": getattr(config, 'CATEGORY_LINEAR', 'linear'), "symbol": symbol}
    id_type = ""
    if order_id:
        params["orderId"] = order_id
        id_type = f"ID={order_id}"
    elif order_link_id:
        params["orderLinkId"] = order_link_id
        id_type = f"LinkID={order_link_id}"
        
    memory_logger.log(f"Intentando cancelar orden {id_type} para {symbol} en '{target_account}'...", level="INFO")
    
    try:
        if not hasattr(session, 'cancel_order'):
            print("ERROR Fatal [Cancel Order]: Sesión API no tiene método 'cancel_order'.")
            return None
            
        response = session.cancel_order(**params)
        
        if not _handle_api_error_generic(response, f"Cancel Order {id_type}"):
            canceled_id = response.get('result', {}).get('orderId') or response.get('result', {}).get('orderLinkId', 'N/A')
            memory_logger.log(f"ÉXITO [Cancel Order]: Cancelación aceptada para orden {canceled_id}.", level="INFO")
            return response
        elif response and response.get('retCode') == 110001:
            memory_logger.log(f"INFO [Cancel Order]: Orden {id_type} no encontrada o ya finalizada (110001).", level="WARN")
            return None
        else:
            return response
            
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Cancel Order]: {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Cancel Order]: {e}")
        traceback.print_exc()
        return None

def close_all_symbol_positions(symbol: str, account_name: Optional[str] = None) -> bool:
    """
    Intenta cerrar todas las posiciones activas (Long y Short) para un símbolo específico
    en una cuenta determinada.
    """
    if not connection_manager or not config or not api:
        print("ERROR [Close All Positions]: Dependencias no disponibles.")
        return False
        
    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main')
    session = connection_manager.get_client(target_account)
    if not session:
        print(f"ERROR [Close All Positions]: Sesión API no válida para '{target_account}'.")
        return False
        
    memory_logger.log(f"Intentando cerrar TODAS las posiciones para {symbol} en cuenta '{target_account}'...", level="INFO")

    active_positions = api.get_active_position_details_api(symbol=symbol, account_name=target_account)
    if active_positions is None:
        print(f"  ERROR [Close All Positions]: No se pudieron obtener posiciones.")
        return False
    if not active_positions:
        memory_logger.log(f"INFO [Close All Positions]: No hay posiciones activas para {symbol}.", level="INFO")
        return True

    all_close_attempts_successful = True
    for pos in active_positions:
        pos_side = pos.get('side')
        pos_size_str = pos.get('size', '0')
        pos_idx = pos.get('positionIdx', 0)
        
        if not pos_side or float(pos_size_str) <= 1e-9:
            continue

        close_order_side = "Sell" if pos_side == "Buy" else "Buy"
        
        memory_logger.log(f"-> Intentando cerrar {pos_side} PosIdx={pos_idx} (Tamaño: {pos_size_str})...", level="DEBUG")
        close_response = place_market_order(
            symbol=symbol,
            side=close_order_side,
            quantity=pos_size_str,
            reduce_only=True,
            position_idx=pos_idx,
            account_name=target_account
        )
        if not close_response or close_response.get('retCode') != 0:
            print(f"  -> FALLO al intentar cerrar {pos_side} PosIdx={pos_idx}.")
            all_close_attempts_successful = False

    if all_close_attempts_successful:
        memory_logger.log(f"ÉXITO [Close All Positions]: Órdenes de cierre enviadas para todas las posiciones de {symbol} en '{target_account}'.", level="INFO")
    else:
        print(f"WARN [Close All Positions]: Fallaron algunos intentos de cierre para {symbol}. Verifica logs.")
        
    return all_close_attempts_successful

def close_position_by_side(symbol: str, side_to_close: str, account_name: Optional[str] = None) -> bool:
    """
    Intenta cerrar la posición activa para un lado específico (Buy para Long, Sell para Short).
    """
    if not connection_manager or not config or not api:
        print("ERROR [Close Position By Side]: Dependencias no disponibles.")
        return False
    if side_to_close not in ["Buy", "Sell"]:
        print(f"ERROR [Close Position By Side]: Lado inválido '{side_to_close}'.")
        return False
        
    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main')
    session = connection_manager.get_client(target_account)
    if not session:
        print(f"ERROR [Close Position By Side]: Sesión API no válida para '{target_account}'.")
        return False
        
    memory_logger.log(f"Buscando posición {side_to_close} para {symbol} en cuenta '{target_account}'...", level="INFO")

    active_positions = api.get_active_position_details_api(symbol=symbol, account_name=target_account)
    if active_positions is None:
        print(f"  ERROR [Close Position By Side]: No se pudieron obtener posiciones.")
        return False

    position_to_close = next((pos for pos in active_positions if pos.get('side') == side_to_close), None)
    
    if not position_to_close:
        memory_logger.log(f"INFO [Close Position By Side]: No se encontró posición activa del lado '{side_to_close}'.", level="INFO")
        return True

    pos_size_str = position_to_close.get('size', '0')
    pos_idx = position_to_close.get('positionIdx', 0)
    close_order_side = "Sell" if side_to_close == "Buy" else "Buy"

    memory_logger.log(f"-> Intentando cerrar {side_to_close} PosIdx={pos_idx} (Tamaño: {pos_size_str})...", level="DEBUG")
    close_response = place_market_order(
        symbol=symbol,
        side=close_order_side,
        quantity=pos_size_str,
        reduce_only=True,
        position_idx=pos_idx,
        account_name=target_account
    )
    
    if close_response and close_response.get('retCode') == 0:
        memory_logger.log(f"ÉXITO [Close Position By Side]: Orden de cierre para {side_to_close} enviada.", level="INFO")
        return True
    else:
        print(f"  FALLO [Close Position By Side]: No se pudo enviar orden de cierre para {side_to_close}.")
        return False