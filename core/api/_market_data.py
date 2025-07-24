"""
Módulo para obtener datos de mercado desde la API de Bybit.

Responsabilidades:
- Obtener información de instrumentos (precisión, mínimos, etc.).
- Gestionar una caché para esta información.
"""
import sys
import os
import traceback
from typing import Optional, Dict, Any
import time

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---
# (Esta sección se mantiene igual, es correcta)
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

try:
    import config
    from connection import manager as connection_manager
    from core.logging import memory_logger
    from ._helpers import _handle_api_error_generic
    from pybit.exceptions import InvalidRequestError, FailedRequestError
except ImportError as e:
    # Este print se mantiene ya que el logger podría no estar disponible
    print(f"ERROR [Market Data API Import]: No se pudo importar módulo necesario: {e}")
    config = type('obj', (object,), {})()
    connection_manager = None
    # Usamos un logger de fallback si el principal falla
    memory_logger = type('obj', (object,), {'log': print})()
    def _handle_api_error_generic(response: Optional[Dict], operation_tag: str) -> bool: return True
    class InvalidRequestError(Exception): pass
    class FailedRequestError(Exception): pass
# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Caché Simple para Instrument Info ---
_instrument_info_cache: Dict[str, Dict[str, Any]] = {}
_INSTRUMENT_INFO_CACHE_EXPIRY_SECONDS = 3600


# --- Funciones de Obtención de Información ---

def get_instrument_info(symbol: str, category: str = 'linear', force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """Obtiene información del instrumento (precisión, mínimos) desde la API o caché."""
    global _instrument_info_cache
    if not connection_manager or not config:
        memory_logger.log("ERROR [Get Instrument Info]: Dependencias no disponibles.", level="ERROR")
        return None
        
    cache_key = f"{category}_{symbol}"
    now = time.time()
    if not force_refresh and cache_key in _instrument_info_cache:
        cached_data = _instrument_info_cache[cache_key]
        if (now - cached_data.get('timestamp', 0)) < _INSTRUMENT_INFO_CACHE_EXPIRY_SECONDS:
            return cached_data.get('data')

    # --- INICIO DE LA MODIFICACIÓN ---
    # Se reemplaza la lógica de selección de cuenta manual con la llamada centralizada.
    session, account_used = connection_manager.get_session_for_operation(
        purpose='market_data'
    )
    if not session:
        memory_logger.log("ERROR [Get Instrument Info]: No se pudo obtener una sesión API válida.", level="ERROR")
        return None
    # --- FIN DE LA MODIFICACIÓN ---
        
    # --- INICIO DE LA MODIFICACIÓN ---
    # Comentamos el log de nivel DEBUG para reducir el ruido en la consola y logs.
    # memory_logger.log(f"Consultando API para info de {symbol} ({category}) usando '{account_used}'...", level="DEBUG")
    # --- FIN DE LA MODIFICACIÓN ---
    params = {"category": category, "symbol": symbol}
    
    try:
        if not hasattr(session, 'get_instruments_info'):
            memory_logger.log("ERROR Fatal [Get Instrument Info]: Sesión API no tiene método 'get_instruments_info'.", level="ERROR")
            return None
            
        response = session.get_instruments_info(**params)
        
        if _handle_api_error_generic(response, f"Get Instrument Info for {symbol}"):
            return None
        else:
            result_list = response.get('result', {}).get('list', [])
            if result_list:
                instrument_data = result_list[0]
                lot_size_filter = instrument_data.get('lotSizeFilter', {})
                price_filter = instrument_data.get('priceFilter', {})
                
                extracted_info = {
                    'symbol': instrument_data.get('symbol'),
                    'qtyStep': lot_size_filter.get('qtyStep'),
                    'minOrderQty': lot_size_filter.get('minOrderQty'),
                    'maxOrderQty': lot_size_filter.get('maxOrderQty'),
                    'priceScale': instrument_data.get('priceScale'),
                    'tickSize': price_filter.get('tickSize')
                }
                
                if not extracted_info.get('qtyStep') or not extracted_info.get('minOrderQty'):
                    memory_logger.log(f"WARN [Get Instrument Info]: Datos qtyStep/minOrderQty incompletos para {symbol}.", level="WARN")
                
                memory_logger.log(f"ÉXITO [Get Instrument Info]: Datos obtenidos para {symbol}.", level="INFO")
                _instrument_info_cache[cache_key] = {'timestamp': now, 'data': extracted_info}
                return extracted_info
            else:
                memory_logger.log(f"INFO [Get Instrument Info]: Lista de instrumentos vacía para {symbol}.", level="WARN")
                return None
                
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        memory_logger.log(f"ERROR API [Get Instrument Info] para {symbol}: {api_err} (Status: {status_code})", level="ERROR")
        return None
    except Exception as e:
        memory_logger.log(f"ERROR Inesperado [Get Instrument Info] para {symbol}: {e}", level="ERROR")
        traceback.print_exc()
        return None