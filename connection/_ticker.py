"""
Gestiona el hilo que obtiene los precios del mercado en tiempo real.

v2.0: Modificado para leer el TICKER_SYMBOL dinámicamente desde el módulo
config en cada iteración, permitiendo cambios en tiempo real desde la TUI.
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

    import config
    from core.logging import memory_logger
    from core.exchange import AbstractExchange, StandardTicker

except ImportError as e:
    print(f"ERROR CRITICO [Ticker Import]: No se pudo importar un módulo esencial: {e}")
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
_exchange_adapter: Optional[AbstractExchange] = None

# --- Interfaz Pública ---

def get_latest_price() -> dict:
    """Devuelve una copia de la información del último precio almacenado en caché."""
    with threading.Lock():
        return _latest_price_info.copy()

def start_ticker_thread(exchange_adapter: AbstractExchange, raw_event_callback: Callable):
    """Inicia el hilo del ticker en segundo plano."""
    global _ticker_thread, _raw_event_callback, _exchange_adapter

    if not isinstance(exchange_adapter, AbstractExchange):
        memory_logger.log("Ticker ERROR FATAL: El objeto proporcionado no es una instancia de AbstractExchange.", level="ERROR")
        return

    if _ticker_thread and _ticker_thread.is_alive():
        memory_logger.log("Ticker: Advertencia: Ticker ya en ejecución.", level="WARN")
        return

    memory_logger.log(f"Ticker: Iniciando con adaptador '{type(exchange_adapter).__name__}'.", level="INFO")

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

    # No leemos el símbolo aquí
    # symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
    
    fetch_interval = getattr(config, 'TICKER_INTERVAL_SECONDS', 1)
    
    if not callable(_raw_event_callback):
        memory_logger.log(f"Ticker ERROR FATAL: Callback inválido. Saliendo del hilo.", level="ERROR")
        return
        
    memory_logger.log(f"Ticker: Bucle iniciado (Intervalo: {fetch_interval}s)", level="INFO")
    
    last_symbol_used = ""

    while not _ticker_stop_event.is_set():
        start_time = time.monotonic()
        
        # --- INICIO DE LA CORRECCIÓN ---
        # 1. Leer el símbolo desde config DENTRO del bucle.
        #    Esto asegura que siempre usemos el valor más reciente.
        symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')

        if symbol == 'N/A':
            # Si el símbolo no es válido, esperamos y continuamos el bucle.
            time.sleep(fetch_interval)
            continue
            
        # Opcional: Loguear solo si el símbolo ha cambiado
        if symbol != last_symbol_used:
            memory_logger.log(f"Ticker: Símbolo actualizado a '{symbol}'.", level="INFO")
            last_symbol_used = symbol
            with threading.Lock():
                # Reseteamos la info de precio al cambiar de símbolo
                _latest_price_info = {"price": None, "timestamp": None, "symbol": symbol}

        # 2. Obtener el ticker estandarizado desde el adaptador con el símbolo actual
        standard_ticker = _exchange_adapter.get_ticker(symbol)
        # --- FIN DE LA CORRECCIÓN ---
        
        if standard_ticker and isinstance(standard_ticker, StandardTicker):
            _handle_new_price(standard_ticker)

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
        # Actualizamos el símbolo también, para consistencia
        _latest_price_info.update({"price": price, "timestamp": timestamp, "symbol": symbol})
        
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