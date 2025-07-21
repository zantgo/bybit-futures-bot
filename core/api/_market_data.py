# core/api/_market_data.py

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
    
    # Importar funciones auxiliares compartidas desde el nuevo módulo _helpers
    from ._helpers import _handle_api_error_generic

    try:
        from pybit.exceptions import InvalidRequestError, FailedRequestError
    except ImportError:
        print("WARN [Market Data API Import]: pybit exceptions not found. Using fallback.")
        class InvalidRequestError(Exception): pass
        class FailedRequestError(Exception):
             def __init__(self, message, status_code=None): super().__init__(message); self.status_code = status_code
except ImportError as e:
    print(f"ERROR [Market Data API Import]: No se pudo importar módulo necesario: {e}")
    config = type('obj', (object,), {'ACCOUNT_MAIN': 'main', 'CATEGORY_LINEAR': 'linear'})()
    connection_manager = None
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    def _handle_api_error_generic(response: Optional[Dict], operation_tag: str) -> bool:
        if response and response.get('retCode') == 0: return False
        print(f"  ERROR API [{operation_tag}]: Fallback - Error genérico.")
        return True
    class InvalidRequestError(Exception): pass
    class FailedRequestError(Exception):
        def __init__(self, message, status_code=None): super().__init__(message); self.status_code = status_code

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Caché Simple para Instrument Info ---
_instrument_info_cache: Dict[str, Dict[str, Any]] = {}
_INSTRUMENT_INFO_CACHE_EXPIRY_SECONDS = 3600


# --- Funciones de Obtención de Información ---

def get_instrument_info(symbol: str, category: str = 'linear', force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """Obtiene información del instrumento (precisión, mínimos) desde la API o caché."""
    global _instrument_info_cache
    if not connection_manager or not config:
        print("ERROR [Get Instrument Info]: Dependencias (connection_manager, config) no disponibles.")
        return None
        
    cache_key = f"{category}_{symbol}"
    now = time.time()
    if not force_refresh and cache_key in _instrument_info_cache:
        cached_data = _instrument_info_cache[cache_key]
        if (now - cached_data.get('timestamp', 0)) < _INSTRUMENT_INFO_CACHE_EXPIRY_SECONDS:
            return cached_data.get('data')

    session = None
    account_used = None
    main_account_fallback = getattr(config, 'ACCOUNT_MAIN', 'main')
    
    session = connection_manager.get_client(main_account_fallback)
    if session:
        account_used = main_account_fallback
    else:
        initialized_accounts = connection_manager.get_initialized_accounts()
        if not initialized_accounts:
            print("ERROR [Get Instrument Info]: No hay sesiones API inicializadas.")
            return None
        account_used = initialized_accounts[0]
        session = connection_manager.get_client(account_used)
        if not session:
            print("ERROR [Get Instrument Info]: Falló al obtener sesión API alternativa.")
            return None
        print(f"WARN [Get Instrument Info]: Usando sesión de '{account_used}' (fallback).")
        
    memory_logger.log(f"Consultando API para info de {symbol} ({category}) usando '{account_used}'...", level="DEBUG")
    params = {"category": category, "symbol": symbol}
    
    try:
        if not hasattr(session, 'get_instruments_info'):
            print("ERROR Fatal [Get Instrument Info]: Sesión API no tiene método 'get_instruments_info'.")
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
                    print(f"WARN [Get Instrument Info]: Datos qtyStep/minOrderQty incompletos para {symbol}.")
                
                memory_logger.log(f"ÉXITO [Get Instrument Info]: Datos obtenidos para {symbol}.", level="INFO")
                _instrument_info_cache[cache_key] = {'timestamp': now, 'data': extracted_info}
                return extracted_info
            else:
                memory_logger.log(f"INFO [Get Instrument Info]: Lista de instrumentos vacía para {symbol}.", level="WARN")
                return None
                
    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Get Instrument Info] para {symbol}: {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Get Instrument Info] para {symbol}: {e}")
        traceback.print_exc()
        return None