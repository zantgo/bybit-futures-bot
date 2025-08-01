"""
Módulo para la gestión del Apalancamiento.
 
Su única responsabilidad es contener la lógica para establecer el apalancamiento
en las cuentas de trading relevantes a través de la API de Bybit.
"""
import traceback
from typing import Optional, Union

# --- Dependencias del Proyecto ---
import config
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
# --- INICIO DE LA CORRECCIÓN: Usar importación absoluta ---
from connection._manager import get_connection_manager_instance
connection_manager = get_connection_manager_instance()
# --- FIN DE LA CORRECCIÓN ---

def set_leverage(
    symbol: str,
    buy_leverage: Union[float, str],
    sell_leverage: Union[float, str],
    account_name: Optional[str] = None
) -> bool:
    """
    Establece el apalancamiento para un símbolo específico en las cuentas de trading relevantes.

    Si se proporciona `account_name`, solo se intentará en esa cuenta. De lo contrario,
    se aplicará a las cuentas designadas para operaciones LONG y SHORT en la configuración.

    Args:
        symbol (str): El símbolo del instrumento (ej. 'BTCUSDT').
        buy_leverage (Union[float, str]): El apalancamiento para posiciones largas.
        sell_leverage (Union[float, str]): El apalancamiento para posiciones cortas.
        account_name (Optional[str]): Nombre de una cuenta específica para configurar.

    Returns:
        bool: True si la operación fue exitosa para todas las cuentas objetivo, False si alguna falló.
    """
    if not connection_manager or not config:
        memory_logger.log("ERROR [Set Leverage]: Dependencias no disponibles.", level="ERROR")
        return False
        
    accounts_to_configure = []
    if account_name:
        accounts_to_configure.append(account_name)
    else:
        # Obtener las cuentas de trading para long y short desde el gestor centralizado
        _, long_acc = connection_manager.get_session_for_operation('trading', side='long')
        _, short_acc = connection_manager.get_session_for_operation('trading', side='short')
        if long_acc: accounts_to_configure.append(long_acc)
        if short_acc: accounts_to_configure.append(short_acc)

    if not accounts_to_configure:
        memory_logger.log("ERROR [Set Leverage]: No se encontraron cuentas de trading válidas para configurar.", level="ERROR")
        return False

    all_successful = True
    # Usar set() para evitar configurar la misma cuenta dos veces
    for acc_name in set(accounts_to_configure):
        session = connection_manager.get_client(acc_name)
        if not session:
            memory_logger.log(f"ERROR [Set Leverage]: Sesión API no encontrada para la cuenta '{acc_name}'.", level="ERROR")
            all_successful = False
            continue
            
        try:
            buy_lev_str = str(float(buy_leverage))
            sell_lev_str = str(float(sell_leverage))
        except (ValueError, TypeError):
            memory_logger.log(f"ERROR [Set Leverage]: Valor de apalancamiento inválido ({buy_leverage}, {sell_leverage}).", level="ERROR")
            return False # Es un error de entrada, fallar inmediatamente.
            
        params = {
            "category": getattr(config, 'CATEGORY_LINEAR', 'linear'),
            "symbol": symbol,
            "buyLeverage": buy_lev_str,
            "sellLeverage": sell_lev_str,
        }
        
        if not _execute_leverage_call(session, params, acc_name):
            all_successful = False
            
    return all_successful

def _execute_leverage_call(session, params: dict, account_name: str) -> bool:
    """Función de ayuda para encapsular la llamada a la API y el manejo de errores."""
    symbol = params.get("symbol")
    memory_logger.log(f"Intentando establecer leverage para {symbol} en '{account_name}'...", level="INFO")
    
    try:
        if not hasattr(session, 'set_leverage'):
            memory_logger.log(f"ERROR Fatal [Set Leverage]: La sesión para '{account_name}' no tiene el método 'set_leverage'.", level="ERROR")
            return False
            
        response = session.set_leverage(**params)
        
        if not _handle_api_error_generic(response, f"Set Leverage on {account_name}"):
            memory_logger.log(f"ÉXITO [Set Leverage]: Apalancamiento establecido para {symbol} en '{account_name}'.", level="INFO")
            return True
        elif response and response.get('retCode') == 110043:
            memory_logger.log(f"INFO [Set Leverage]: Apalancamiento para {symbol} en '{account_name}' no modificado (ya estaba establecido).", level="INFO")
            return True
        else:
            return False
            
    except InvalidRequestError as e:
        if "110043" in str(e) or "leverage not modified" in str(e).lower():
            memory_logger.log(f"INFO [Set Leverage]: Apalancamiento para {symbol} en '{account_name}' no modificado (excepción de ya establecido).", level="INFO")
            return True
        else:
            memory_logger.log(f"ERROR API (Invalid Request) [Set Leverage] en '{account_name}': {e}", level="ERROR")
            return False
    except FailedRequestError as e:
        status_code = getattr(e, 'status_code', 'N/A')
        memory_logger.log(f"ERROR API (Failed Request) [Set Leverage] en '{account_name}': {e} (Status: {status_code})", level="ERROR")
        return False
    except Exception as e:
        memory_logger.log(f"ERROR Inesperado [Set Leverage] en '{account_name}': {e}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")
        return False