# core/api/_account.py

"""
Módulo para consultar información de la cuenta desde la API de Bybit.

Responsabilidades:
- Obtener balances de diferentes tipos de cuenta (Unificada, Fondos).
- Consultar el estado de órdenes.
- Obtener detalles de posiciones activas.
- Obtener historial de ejecuciones de órdenes.
"""
import sys
import os
import traceback
from typing import Optional, Dict, Any, List

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---
# (Esta sección se mantiene igual, es correcta)
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

try:
    import config
    from core import utils
    from connection import manager as connection_manager
    from core.logging import memory_logger
    from ._helpers import _handle_api_error_generic
    from pybit.exceptions import InvalidRequestError, FailedRequestError
except ImportError as e:
    print(f"ERROR [Account API Import]: No se pudo importar módulo necesario: {e}")
    config = type('obj', (object,), {})()
    utils = None; connection_manager = None
    memory_logger = type('obj', (object,), {'log': print})()
    def _handle_api_error_generic(response: Optional[Dict], operation_tag: str) -> bool: return True
    class InvalidRequestError(Exception): pass
    class FailedRequestError(Exception): pass
# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Funciones para Obtener Balances ---

def get_unified_account_balance_info(account_name: str) -> Optional[dict]:
    """Obtiene detalles del balance de la Cuenta Unificada (UTA)."""
    if not connection_manager or not config or not utils:
        print("ERROR [Get Unified Balance]: Dependencias no disponibles.")
        return None
        
    # --- MODIFICACIÓN: Usar selección de sesión específica ---
    session, account_used = connection_manager.get_session_for_operation(
        purpose='general', specific_account=account_name
    )
    if not session:
        print(f"ERROR [Get Unified Balance]: Sesión API no válida para '{account_name}'.")
        return None
    # --- FIN DE LA MODIFICACIÓN ---
        
    memory_logger.log(f"Obteniendo balance UNIFIED para '{account_used}'...", level="DEBUG")
    
    try:
        if not hasattr(session, 'get_wallet_balance'):
            print("ERROR Fatal [Get Unified Balance]: Sesión API no tiene método 'get_wallet_balance'.")
            return None
            
        response = session.get_wallet_balance(accountType="UNIFIED")
        
        if _handle_api_error_generic(response, f"Get Unified Balance for {account_used}"):
            return None
        else:
            result_list = response.get('result', {}).get('list', [])
            if not result_list:
                memory_logger.log(f"INFO [Get Unified Balance]: Sin datos de balance para '{account_used}'.", level="WARN")
                return {'totalEquity': 0.0, 'totalAvailableBalance': 0.0, 'totalWalletBalance': 0.0, 'usdt_balance': 0.0, 'usdt_available': 0.0}
                
            account_data = result_list[0]
            balance_info = {
                'totalEquity': utils.safe_float_convert(account_data.get('totalEquity'), 0.0),
                'totalAvailableBalance': utils.safe_float_convert(account_data.get('totalAvailableBalance'), 0.0),
                'totalWalletBalance': utils.safe_float_convert(account_data.get('totalWalletBalance'), 0.0),
                'usdt_balance': 0.0,
                'usdt_available': 0.0
            }
            
            coins_data = account_data.get('coin', [])
            usdt_data = next((coin for coin in coins_data if coin.get('coin') == 'USDT'), None)
            if usdt_data:
                balance_info['usdt_balance'] = utils.safe_float_convert(usdt_data.get('walletBalance'), 0.0)
                balance_info['usdt_available'] = utils.safe_float_convert(usdt_data.get('availableToWithdraw', usdt_data.get('walletBalance')), 0.0)
            
            memory_logger.log(f"ÉXITO [Get Unified Balance]: Balance obtenido para '{account_used}'.", level="DEBUG")
            return balance_info
            
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Get Unified Balance] para '{account_used}': {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Get Unified Balance] para '{account_used}': {e}")
        traceback.print_exc()
        return None

def get_funding_account_balance_info(account_name: str) -> Optional[Dict[str, Dict[str, float]]]:
    """Obtiene detalles del balance de la Cuenta de Fondos (FUND)."""
    if not connection_manager or not config or not utils:
        print("ERROR [Get Funding Balance]: Dependencias no disponibles.")
        return None
        
    # --- MODIFICACIÓN: Usar selección de sesión específica ---
    session, account_used = connection_manager.get_session_for_operation(
        purpose='general', specific_account=account_name
    )
    if not session:
        print(f"ERROR [Get Funding Balance]: Sesión API no válida para '{account_name}'.")
        return None
    # --- FIN DE LA MODIFICACIÓN ---
        
    memory_logger.log(f"Obteniendo balance FUND para '{account_used}'...", level="DEBUG")
    
    try:
        if not hasattr(session, 'get_coins_balance'):
            print("ERROR Fatal [Get Funding Balance]: Sesión API no tiene método 'get_coins_balance'.")
            return None
            
        response = session.get_coins_balance(accountType="FUND")
        funding_balances = {}
        
        if _handle_api_error_generic(response, f"Get Funding Balance for {account_used}"):
            return None
        else:
            balance_list = response.get('result', {}).get('balance', [])
            if balance_list:
                for coin_data in balance_list:
                    coin_symbol = coin_data.get('coin')
                    wallet_balance = utils.safe_float_convert(coin_data.get('walletBalance'), 0.0)
                    if coin_symbol and wallet_balance > 1e-9:
                        funding_balances[coin_symbol] = {'walletBalance': wallet_balance}
                memory_logger.log(f"ÉXITO [Get Funding Balance]: Balances obtenidos para '{account_used}'. {len(funding_balances)} activo(s).", level="DEBUG")
            else:
                memory_logger.log(f"INFO [Get Funding Balance]: Sin datos de balance para '{account_used}'.", level="WARN")
            return funding_balances
            
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Get Funding Balance] para '{account_used}': {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Get Funding Balance] para '{account_used}': {e}")
        traceback.print_exc()
        return None

# --- Funciones para Órdenes y Posiciones ---

def get_order_status( symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None, account_name: Optional[str] = None) -> Optional[dict]:
    """Obtiene el estado de una orden específica usando get_order_history (v5 API)."""
    if not connection_manager or not config:
        print("ERROR [Get Order Status]: Dependencias no disponibles.")
        return None
    if not order_id and not order_link_id:
        print("ERROR [Get Order Status]: Debe proporcionar order_id o order_link_id.")
        return None
        
    # --- MODIFICACIÓN: Usar selección de sesión centralizada ---
    session, account_used = connection_manager.get_session_for_operation(
        purpose='general', specific_account=account_name
    )
    if not session:
        print(f"ERROR [Get Order Status]: No se pudo obtener una sesión API válida (solicitada: {account_name}).")
        return None
    # --- FIN DE LA MODIFICACIÓN ---
        
    params = {"category": getattr(config, 'CATEGORY_LINEAR', 'linear'), "limit": 1}
    id_type = ""
    if order_id:
        params["orderId"] = order_id
        id_type = f"ID={order_id}"
    elif order_link_id:
        params["orderLinkId"] = order_link_id
        id_type = f"LinkID={order_link_id}"
        
    memory_logger.log(f"Buscando estado orden {id_type} en '{account_used}'...", level="DEBUG")
    
    try:
        if not hasattr(session, 'get_order_history'):
            print("ERROR Fatal [Get Order Status]: Sesión API no tiene método 'get_order_history'.")
            return None
            
        response = session.get_order_history(**params)
        
        if _handle_api_error_generic(response, f"Get Order Status {id_type}"):
            return None
        else:
            order_list = response.get('result', {}).get('list', [])
            if order_list:
                order_details = order_list[0]
                found_id = order_details.get('orderId')
                found_link_id = order_details.get('orderLinkId')
                if (order_id and found_id == order_id) or (order_link_id and found_link_id == order_link_id):
                    memory_logger.log(f"ÉXITO [Get Order Status]: Orden {id_type} encontrada. Estado: {order_details.get('orderStatus', 'N/A')}", level="DEBUG")
                    return order_details
                else:
                    memory_logger.log(f"INFO [Get Order Status]: Orden encontrada ({found_id}/{found_link_id}) no coincide con buscada ({id_type}).", level="WARN")
                    return None
            else:
                memory_logger.log(f"INFO [Get Order Status]: Orden {id_type} no encontrada.", level="INFO")
                return None
                
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Get Order Status]: {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Get Order Status]: {e}")
        traceback.print_exc()
        return None

def get_active_position_details_api(symbol: str, account_name: Optional[str] = None) -> Optional[List[dict]]:
    """Obtiene detalles de la(s) posición(es) activas para un símbolo (v5 API)."""
    if not connection_manager or not config or not utils:
        print("ERROR [Get Position]: Dependencias no disponibles.")
        return None
        
    # --- MODIFICACIÓN: Usar selección de sesión centralizada ---
    session, account_used = connection_manager.get_session_for_operation(
        purpose='general', specific_account=account_name
    )
    if not session:
        print(f"ERROR [Get Position]: No se pudo obtener una sesión API válida (solicitada: {account_name}).")
        return None
    # --- FIN DE LA MODIFICACIÓN ---
        
    params = {"category": getattr(config, 'CATEGORY_LINEAR', 'linear'), "symbol": symbol}
    memory_logger.log(f"Obteniendo detalles de posición para {symbol} en '{account_used}'...", level="DEBUG")
    
    try:
        if not hasattr(session, 'get_positions'):
            print("ERROR Fatal [Get Position]: Sesión API no tiene método 'get_positions'.")
            return None
            
        response = session.get_positions(**params)
        
        if _handle_api_error_generic(response, f"Get Position for {symbol}"):
            return None
        else:
            position_list = response.get('result', {}).get('list', [])
            if position_list:
                active_positions = [pos for pos in position_list if utils.safe_float_convert(pos.get('size'), 0.0) > 1e-12]
                if active_positions:
                    memory_logger.log(f"ÉXITO [Get Position]: {len(active_positions)} posición(es) activa(s) encontrada(s) para {symbol}.", level="DEBUG")
                    return active_positions
                else:
                    memory_logger.log(f"INFO [Get Position]: No hay posiciones activas para {symbol}.", level="INFO")
                    return []
            else:
                memory_logger.log(f"INFO [Get Position]: Lista de posiciones vacía para {symbol}.", level="INFO")
                return []
                
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Get Position]: {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Get Position]: {e}")
        traceback.print_exc()
        return None

def get_order_execution_history(category: str, symbol: str, order_id: str, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
    """
    Obtiene el historial de ejecuciones (trades) para una orden específica (v5 API).
    """
    if not connection_manager or not config:
        print("ERROR [Get Executions]: Dependencias no disponibles.")
        return None
        
    # --- MODIFICACIÓN: Usar selección de sesión centralizada ---
    session, account_used = connection_manager.get_session_for_operation(purpose='general')
    if not session:
        print("ERROR [Get Executions]: No se pudo obtener sesión API principal.")
        return None
    # --- FIN DE LA MODIFICACIÓN ---
        
    if not hasattr(session, 'get_executions'):
        print("ERROR Fatal [Get Executions]: Sesión API no tiene método 'get_executions'.")
        return None

    params = {
        "category": category,
        "symbol": symbol,
        "orderId": order_id,
        "limit": min(limit, 100)
    }
    memory_logger.log(f"Consultando API para ejecuciones de Orden ID: {order_id} en '{account_used}'...", level="DEBUG")
    
    try:
        response = session.get_executions(**params)
        
        if _handle_api_error_generic(response, f"Get Executions for Order {order_id}"):
            if response and response.get('retCode') == 110001:
                 memory_logger.log(f"INFO [Get Executions]: Orden {order_id} no encontrada (110001).", level="WARN")
                 return []
            return []
        else:
            executions_list = response.get('result', {}).get('list', [])
            memory_logger.log(f"ÉXITO [Get Executions]: {len(executions_list)} ejecuciones encontradas para Orden ID {order_id}.", level="DEBUG")
            return executions_list
            
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Get Executions] para orden {order_id}: {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Get Executions] para orden {order_id}: {e}")
        traceback.print_exc()
        return None