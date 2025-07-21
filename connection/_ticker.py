# connection/_ticker.py

"""
Gestiona el hilo ticker en vivo, llama a core.strategy._event_processor.

Módulo interno del paquete 'connection'.
"""
import threading
import time
import datetime
import traceback
import os
import sys

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Importar dependencias core y de configuración desde su nueva ubicación.
# Usamos un try-except para robustez.
try:
    # 1. Ajustar el sys.path para encontrar la raíz del proyecto.
    #    La raíz ahora está dos niveles por encima de `connection/`.
    if __name__ != "__main__":
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir) # Raíz del proyecto
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    # 2. Importar dependencias con rutas absolutas desde la raíz.
    import config
    from core import utils
    from core.logging import memory_logger

    # 3. Importar el manager de forma relativa DENTRO del mismo paquete.
    from . import _manager as client

except ImportError as e:
    # Fallback si las importaciones fallan
    print(f"ERROR CRITICO [Ticker Import]: No se pudo importar un módulo esencial. Detalle: {e}")
    # Definir dummies mínimos.
    config = type('obj', (object,), {
        'TICKER_SYMBOL': 'N/A', 'CATEGORY_LINEAR': 'linear',
        'TICKER_INTERVAL_SECONDS': 30, 'RAW_PRICE_TICK_INTERVAL': 2,
        'TICKER_SOURCE_ACCOUNT': 'main', 'ACCOUNT_MAIN': 'main'
    })()
    utils = type('obj', (object,), {'safe_float_convert': float, 'format_datetime': str})()
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    client = None

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Module State ---
_latest_price_info = {"price": None, "timestamp": None, "symbol": None}
_ticker_stop_event = threading.Event()
_ticker_thread = None
_tick_counter = 0
_raw_event_callback = None
_intermediate_ticks_buffer = []

# --- Public Accessor ---
def get_latest_price() -> dict:
    """Devuelve una copia de la información del último precio."""
    return _latest_price_info.copy()

# --- Internal Loop (Executed in Background Thread) ---
def _fetch_price_loop(session):
    """Bucle interno ejecutado por el hilo del ticker."""
    global _latest_price_info, _tick_counter, _raw_event_callback, _intermediate_ticks_buffer

    symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
    category = getattr(config, 'CATEGORY_LINEAR', 'linear')
    fetch_interval = getattr(config, 'TICKER_INTERVAL_SECONDS', 30)
    raw_event_interval_ticks = getattr(config, 'RAW_PRICE_TICK_INTERVAL', 2)

    if not utils or not client:
        memory_logger.log("Ticker ERROR FATAL: Faltan dependencias utils o client (manager). Saliendo.", level="ERROR")
        return
    if symbol == 'N/A':
        memory_logger.log("Ticker ERROR FATAL: TICKER_SYMBOL no definido en config. Saliendo.", level="ERROR")
        return

    memory_logger.log(f"Ticker iniciado para {symbol} (Fetch: {fetch_interval}s, Callback cada: {raw_event_interval_ticks} ticks)", level="INFO")
    if not callable(_raw_event_callback):
        memory_logger.log("Ticker ERROR FATAL: No se proporcionó callback. Saliendo.", level="ERROR")
        return

    _latest_price_info["symbol"] = symbol

    while not _ticker_stop_event.is_set():
        fetch_start_time = datetime.datetime.now()
        current_price_info = None
        price_updated_this_tick = False

        # --- 1. Obtener Precio ---
        response = client.get_tickers(session, category=category, symbol=symbol)
        fetch_timestamp = datetime.datetime.now()

        if response:
            try:
                ticker_data_list = response.get('result', {}).get('list', [])
                if ticker_data_list:
                    ticker_data = ticker_data_list[0]
                    price_str = ticker_data.get('lastPrice')
                    price = utils.safe_float_convert(price_str, default=None)
                    if price is not None and price > 0:
                        current_price_info = {"price": price, "timestamp": fetch_timestamp}
                        _latest_price_info["price"] = price
                        _latest_price_info["timestamp"] = fetch_timestamp
                        price_updated_this_tick = True
            except Exception as e:
                memory_logger.log(f"Ticker: Error procesando respuesta API: {e}", level="WARN")
        
        # --- 2. Lógica de Conteo y Llamada al Callback ---
        if price_updated_this_tick and current_price_info:
            _tick_counter += 1

            if _tick_counter < raw_event_interval_ticks:
                 _intermediate_ticks_buffer.append(current_price_info)
            else:
                 if callable(_raw_event_callback):
                     try:
                         _raw_event_callback( _intermediate_ticks_buffer.copy(),
                             final_price_info={ "price": current_price_info["price"],
                                                "timestamp": current_price_info["timestamp"],
                                                "symbol": symbol } )
                     except Exception as cb_err:
                         memory_logger.log(f"Ticker: ERROR ejecutando callback: {cb_err}", level="ERROR")
                         memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")
                 _intermediate_ticks_buffer.clear()
                 _tick_counter = 0
        
        # --- 3. Esperar para el próximo ciclo ---
        elapsed_time = (datetime.datetime.now() - fetch_start_time).total_seconds()
        wait_time = fetch_interval - elapsed_time
        _ticker_stop_event.wait(timeout=max(0.1, wait_time))

    # --- Limpieza al detener ---
    memory_logger.log("Ticker: Bucle detenido.", level="INFO")
    _latest_price_info = {"price": None, "timestamp": None, "symbol": None}
    _tick_counter = 0
    _intermediate_ticks_buffer.clear()
    memory_logger.log("Ticker: Estado limpiado.", level="INFO")

# --- Thread Control Functions ---
def start_ticker_thread(raw_event_callback=None):
    """Inicia el hilo del ticker en segundo plano."""
    global _ticker_thread, _ticker_stop_event, _tick_counter, _raw_event_callback, _intermediate_ticks_buffer

    if not client:
        memory_logger.log("Ticker ERROR FATAL: Módulo client (manager) no disponible. No se puede iniciar.", level="ERROR")
        return
    if not config:
         memory_logger.log("Ticker ERROR FATAL: Módulo config no disponible. No se puede iniciar.", level="ERROR")
         return

    if _ticker_thread and _ticker_thread.is_alive():
        memory_logger.log("Ticker: Advertencia: Ticker ya en ejecución.", level="WARN")
        return

    # Obtener Sesión API (con fallback)
    source_account = getattr(config, 'TICKER_SOURCE_ACCOUNT', 'profit')
    session = client.get_client(source_account)
    if not session:
        memory_logger.log(f"Ticker: Advertencia: Fuente primaria '{source_account}' no disponible.", level="WARN")
        initialized_accounts = client.get_initialized_accounts()
        alt_source = next((acc for acc in initialized_accounts if acc != getattr(config, 'ACCOUNT_MAIN', 'main') and acc != source_account), None)
        if not alt_source:
            alt_source = next((acc for acc in initialized_accounts if acc != source_account), None)

        if alt_source:
            memory_logger.log(f"Ticker: Usando fuente alternativa '{alt_source}'...", level="INFO")
            session = client.get_client(alt_source)
            if not session:
                memory_logger.log(f"Ticker Error Fatal: Fuente alternativa '{alt_source}' falló.", level="ERROR")
                return
            else:
                memory_logger.log(f"Ticker: Conexión alternativa '{alt_source}' OK.", level="INFO")
        else:
            memory_logger.log(f"Ticker Error Fatal: No hay cuentas API válidas disponibles.", level="ERROR")
            return

    # Resetear Estado y Crear/Iniciar Hilo
    memory_logger.log("Ticker: Usando sesión API para obtener precios.", level="INFO")
    _tick_counter = 0
    _intermediate_ticks_buffer.clear()
    _raw_event_callback = raw_event_callback
    _ticker_stop_event.clear()
    _ticker_thread = threading.Thread( target=_fetch_price_loop, args=(session,), daemon=True )
    _ticker_thread.name = "PriceTickerThread"
    _ticker_thread.start()
    memory_logger.log("Ticker: Hilo iniciado.", level="INFO")

def stop_ticker_thread():
    """Detiene el hilo del ticker."""
    global _ticker_stop_event, _ticker_thread
    if _ticker_thread and _ticker_thread.is_alive():
        memory_logger.log("Ticker: Solicitando parada...", level="INFO")
        _ticker_stop_event.set()
    else:
        memory_logger.log("Ticker: Info: Ticker no estaba en ejecución.", level="INFO")
    _ticker_thread = None