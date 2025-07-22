"""
Gestiona el hilo que obtiene los precios del mercado en tiempo real.

Su única responsabilidad es gestionar un hilo que periódicamente obtiene el precio
más reciente a través de la Interfaz de Exchange y notifica al `event_processor`
a través de un callback.
"""
import threading
import time
import datetime
import traceback
import sys
import os
from typing import Optional, Dict, Any, Callable

# --- Importaciones Adaptadas ---
try:
    if __name__ != "__main__":
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(script_dir))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    # Dependencias de la aplicación
    import config
    from core.logging import memory_logger
    from core.exchange import AbstractExchange, StandardTicker # <-- CAMBIO CLAVE

except ImportError as e:
    print(f"ERROR CRITICO [Ticker Import]: No se pudo importar un módulo esencial: {e}")
    # Fallbacks
    config = type('obj', (object,), {})()
    memory_logger = type('obj', (object,), {'log': print})()
    AbstractExchange = type('obj', (object,), {})
    StandardTicker = type('obj', (object,), {})


# --- Estado del Módulo ---
_latest_price_info: Dict[str, Any] = {"price": None, "timestamp": None, "symbol": None}
_ticker_stop_event = threading.Event()
_ticker_thread: Optional[threading.Thread] = None
_tick_counter: int = 0
_raw_event_callback: Optional[Callable] = None
_intermediate_ticks_buffer: list = []
_exchange_adapter: Optional[AbstractExchange] = None # <-- CAMBIO CLAVE

# --- Interfaz Pública ---

def get_latest_price() -> dict:
    """Devuelve una copia de la información del último precio almacenado en caché."""
    with threading.Lock():
        return _latest_price_info.copy()

def start_ticker_thread(exchange_adapter: AbstractExchange, raw_event_callback: Callable):
    """
    Inicia el hilo del ticker en segundo plano.
    
    Args:
        exchange_adapter (AbstractExchange): La instancia del adaptador del exchange a usar.
        raw_event_callback (Callable): La función a llamar con cada nuevo tick.
    """
    global _ticker_thread, _raw_event_callback, _exchange_adapter

    if not isinstance(exchange_adapter, AbstractExchange):
        memory_logger.log("Ticker ERROR FATAL: El objeto proporcionado no es una instancia de AbstractExchange.", level="ERROR")
        return

    if _ticker_thread and _ticker_thread.is_alive():
        memory_logger.log("Ticker: Advertencia: Ticker ya en ejecución.", level="WARN")
        return

    memory_logger.log(f"Ticker: Iniciando con adaptador '{type(exchange_adapter).__name__}'.", level="INFO")

    # Resetear estado y crear el hilo
    _raw_event_callback = raw_event_callback
    _exchange_adapter = exchange_adapter
    _ticker_stop_event.clear()
    
    with threading.Lock():
        _latest_price_info.clear()
        _intermediate_ticks_buffer.clear()
    
    _ticker_thread = threading.Thread(
        target=_fetch_price_loop,
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

def _fetch_price_loop():
    """Bucle interno que se ejecuta en el hilo para obtener precios."""
    global _tick_counter
    
    if not _exchange_adapter:
        memory_logger.log("Ticker ERROR FATAL: Adaptador de exchange no disponible en el hilo.", "ERROR")
        return

    symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
    fetch_interval = getattr(config, 'TICKER_INTERVAL_SECONDS', 1)

    if symbol == 'N/A' or not callable(_raw_event_callback):
        memory_logger.log(f"Ticker ERROR FATAL: Símbolo '{symbol}' o callback inválido. Saliendo del hilo.", level="ERROR")
        return

    raw_event_ticks = getattr(config, 'RAW_PRICE_TICK_INTERVAL', 1)
    memory_logger.log(f"Ticker: Bucle iniciado para {symbol} (Intervalo: {fetch_interval}s, Evento cada: {raw_event_ticks} ticks)", level="INFO")
    
    with threading.Lock():
        _latest_price_info["symbol"] = symbol

    while not _ticker_stop_event.is_set():
        start_time = time.monotonic()
        
        # 1. Obtener el ticker estandarizado desde el adaptador
        standard_ticker = _exchange_adapter.get_ticker(symbol)
        
        # 2. Gestionar el tick si es válido
        if standard_ticker and isinstance(standard_ticker, StandardTicker):
            _handle_new_price(standard_ticker)

        # 3. Esperar de forma precisa para el siguiente ciclo
        elapsed = time.monotonic() - start_time
        wait_time = max(0, fetch_interval - elapsed)
        _ticker_stop_event.wait(timeout=wait_time)

    memory_logger.log("Ticker: Bucle de obtención de precios detenido.", level="INFO")

def _handle_new_price(ticker_data: StandardTicker):
    """Actualiza el estado interno con el nuevo precio y dispara el callback si corresponde."""
    global _tick_counter, _intermediate_ticks_buffer, _latest_price_info
    
    price = ticker_data.price
    timestamp = ticker_data.timestamp
    symbol = ticker_data.symbol
    
    with threading.Lock():
        _latest_price_info.update({"price": price, "timestamp": timestamp})
        
        current_tick_info = {"price": price, "timestamp": timestamp}
        _intermediate_ticks_buffer.append(current_tick_info)
        _tick_counter += 1
        
        raw_event_ticks = getattr(config, 'RAW_PRICE_TICK_INTERVAL', 1)
        if _tick_counter >= raw_event_ticks:
            try:
                final_info = {"price": price, "timestamp": timestamp, "symbol": symbol}
                if callable(_raw_event_callback):
                    # Pasamos una copia para seguridad entre hilos
                    _raw_event_callback(_intermediate_ticks_buffer.copy(), final_info)
            except Exception as e:
                memory_logger.log(f"Ticker: ERROR CRÍTICO ejecutando callback: {e}", level="ERROR")
                memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")
            finally:
                _intermediate_ticks_buffer.clear()
                _tick_counter = 0