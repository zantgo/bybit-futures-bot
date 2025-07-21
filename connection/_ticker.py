# connection/_ticker.py

"""
Gestiona el hilo que obtiene los precios del mercado en tiempo real.

Su única responsabilidad es gestionar un hilo que periódicamente obtiene el precio
más reciente a través de la capa `core.api` y notifica al `event_processor`
a través de un callback.
"""
import threading
import time
import datetime
import traceback
import sys
import os
from typing import Optional, Dict, Any # <-- SOLUCIÓN: Añadir 'Optional' a la importación

# --- Importaciones Adaptadas ---
try:
    if __name__ != "__main__":
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
    
    # Dependencias de la aplicación
    import config
    from core import utils
    from core.logging import memory_logger
    from core import api as live_operations
    from . import _manager as connection_manager
except ImportError as e:
    print(f"ERROR CRITICO [Ticker Import]: No se pudo importar un módulo esencial: {e}")
    # Fallbacks
    config = type('obj', (object,), {})()
    utils = type('obj', (object,), {})()
    memory_logger = type('obj', (object,), {'log': print})()
    live_operations = None
    connection_manager = None

# --- Estado del Módulo ---
_latest_price_info: Dict[str, Any] = {"price": None, "timestamp": None, "symbol": None}
_ticker_stop_event = threading.Event()
_ticker_thread: Optional[threading.Thread] = None
_tick_counter: int = 0
_raw_event_callback: Optional[callable] = None
_intermediate_ticks_buffer: list = []

# --- Interfaz Pública ---
def get_latest_price() -> dict:
    """Devuelve una copia de la información del último precio almacenado en caché."""
    return _latest_price_info.copy()

def start_ticker_thread(raw_event_callback: callable):
    """
    Inicia el hilo del ticker en segundo plano.
    Utiliza el gestor de conexiones para obtener la sesión API apropiada.
    """
    global _ticker_thread, _raw_event_callback
    
    if not connection_manager or not live_operations:
        memory_logger.log("Ticker ERROR FATAL: Módulos 'connection_manager' o 'live_operations' no disponibles.", level="ERROR")
        return

    if _ticker_thread and _ticker_thread.is_alive():
        memory_logger.log("Ticker: Advertencia: Ticker ya en ejecución.", level="WARN")
        return

    # 1. Obtener la sesión correcta de forma centralizada
    session, account_used = connection_manager.get_session_for_operation('ticker')
    if not session:
        memory_logger.log("Ticker ERROR FATAL: No se pudo obtener una sesión API para el ticker.", level="ERROR")
        return
    
    memory_logger.log(f"Ticker: Usando sesión de la cuenta '{account_used}' para obtener precios.", level="INFO")

    # 2. Resetear estado y crear el hilo
    _raw_event_callback = raw_event_callback
    _ticker_stop_event.clear()
    _latest_price_info.clear()
    _intermediate_ticks_buffer.clear()
    
    _ticker_thread = threading.Thread(
        target=_fetch_price_loop,
        args=(session,),
        daemon=True
    )
    _ticker_thread.name = "PriceTickerThread"
    _ticker_thread.start()
    memory_logger.log("Ticker: Hilo iniciado.", level="INFO")

def stop_ticker_thread():
    """Detiene el hilo del ticker de forma segura."""
    global _ticker_thread
    if _ticker_thread and _ticker_thread.is_alive():
        memory_logger.log("Ticker: Solicitando parada...", level="INFO")
        _ticker_stop_event.set()
        _ticker_thread.join(timeout=5)
        if _ticker_thread.is_alive():
            memory_logger.log("WARN [Ticker]: El hilo del ticker no terminó de forma limpia.", level="WARN")
    else:
        memory_logger.log("Ticker: Info: Ticker no estaba en ejecución.", level="INFO")
    _ticker_thread = None

# --- Bucle Interno del Hilo (Privado) ---
def _fetch_price_loop(session):
    """Bucle interno que se ejecuta en el hilo para obtener precios."""
    global _latest_price_info, _tick_counter, _intermediate_ticks_buffer

    symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
    category = getattr(config, 'CATEGORY_LINEAR', 'linear')
    fetch_interval = getattr(config, 'TICKER_INTERVAL_SECONDS', 1)

    if symbol == 'N/A' or not callable(_raw_event_callback):
        memory_logger.log(f"Ticker ERROR FATAL: Símbolo '{symbol}' o callback inválido. Saliendo del hilo.", level="ERROR")
        return

    raw_event_ticks = getattr(config, 'RAW_PRICE_TICK_INTERVAL', 1)
    memory_logger.log(f"Ticker: Bucle iniciado para {symbol} (Intervalo: {fetch_interval}s, Evento cada: {raw_event_ticks} ticks)", level="INFO")
    _latest_price_info["symbol"] = symbol

    while not _ticker_stop_event.is_set():
        start_time = time.monotonic()
        
        # 1. Obtener el precio
        response = session.get_tickers(category=category, symbol=symbol)
        
        # 2. Procesar la respuesta
        price = _process_api_response(response)
        
        # 3. Gestionar el tick y el callback si el precio es válido
        if price is not None:
            _handle_new_price(price, symbol)

        # 4. Esperar de forma precisa para el siguiente ciclo
        elapsed = time.monotonic() - start_time
        wait_time = max(0, fetch_interval - elapsed)
        _ticker_stop_event.wait(timeout=wait_time)

    memory_logger.log("Ticker: Bucle de obtención de precios detenido.", level="INFO")

def _process_api_response(response: Optional[dict]) -> Optional[float]:
    """Procesa la respuesta de la API y extrae el precio."""
    if not response or response.get('retCode') != 0:
        msg = response.get('retMsg', 'No response') if response else 'No response'
        # Evitar spam de logs si la API está temporalmente caída
        # (se podría implementar un contador para loguear solo cada N errores)
        # memory_logger.log(f"Ticker: Error en respuesta API de precios: {msg}", level="WARN")
        return None
    try:
        ticker_data = response.get('result', {}).get('list', [])[0]
        price = utils.safe_float_convert(ticker_data.get('lastPrice'))
        return price if price and price > 0 else None
    except (IndexError, TypeError, KeyError) as e:
        memory_logger.log(f"Ticker: Error al parsear respuesta de precios: {e}", level="WARN")
        return None

def _handle_new_price(price: float, symbol: str):
    """Actualiza el estado interno con el nuevo precio y dispara el callback si corresponde."""
    global _tick_counter, _intermediate_ticks_buffer, _latest_price_info
    
    timestamp = datetime.datetime.now(datetime.timezone.utc)
    _latest_price_info.update({"price": price, "timestamp": timestamp})
    
    current_tick_info = {"price": price, "timestamp": timestamp}
    _intermediate_ticks_buffer.append(current_tick_info)
    _tick_counter += 1
    
    raw_event_ticks = getattr(config, 'RAW_PRICE_TICK_INTERVAL', 1)
    if _tick_counter >= raw_event_ticks:
        try:
            final_info = {"price": price, "timestamp": timestamp, "symbol": symbol}
            if callable(_raw_event_callback):
                _raw_event_callback(_intermediate_ticks_buffer.copy(), final_info)
        except Exception as e:
            memory_logger.log(f"Ticker: ERROR CRÍTICO ejecutando callback: {e}", level="ERROR")
            memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")
        finally:
            _intermediate_ticks_buffer.clear()
            _tick_counter = 0