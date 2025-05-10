# live/connection/ticker.py
"""
Gestiona el hilo ticker en vivo, llama a core.strategy.event_processor (v5.4.7).
v5.4.7: Elimina referencia a config.PRINT_TICK_ALWAYS que no existe.
"""
import threading
import time
import datetime
import traceback

# Use absolute imports for core modules
# <<< Importar utils y config (aunque no usemos PRINT_TICK_ALWAYS, se usan otras configs) >>>
try:
    import os
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path: sys.path.insert(0, project_root)
    from core import utils
    import config
except ImportError as e_core:
    print(f"ERROR CRITICO [Ticker Import]: Falló importación core ({e_core.name}).")
    # Dummies mínimos para evitar más errores si es posible
    config = type('obj', (object,), {
        'TICKER_SYMBOL': 'N/A', 'CATEGORY_LINEAR': 'linear',
        'TICKER_INTERVAL_SECONDS': 30, 'RAW_PRICE_TICK_INTERVAL': 2,
        'TICKER_SOURCE_ACCOUNT': 'profit', 'ACCOUNT_MAIN': 'main'
    })()
    utils = type('obj', (object,), {'safe_float_convert': float, 'format_datetime': str})()
    # Salir es probablemente lo mejor
    # sys.exit(1)
except Exception as e_imp:
    print(f"ERROR CRITICO [Ticker Import]: Excepción inesperada: {e_imp}")
    config = type('obj', (object,), {})()
    utils = None
    # sys.exit(1)


# Use relative import for manager within the same package
try:
    from . import manager as client # 'client' es un alias para live.connection.manager
except ImportError as e_rel:
    print(f"ERROR CRITICO [Ticker Import]: Falló importación relativa de manager: {e_rel}")
    client = None # Indicar que no está disponible
    # sys.exit(1)

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

    # Acceder a config de forma segura con getattr
    symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
    category = getattr(config, 'CATEGORY_LINEAR', 'linear')
    fetch_interval = getattr(config, 'TICKER_INTERVAL_SECONDS', 30)
    raw_event_interval_ticks = getattr(config, 'RAW_PRICE_TICK_INTERVAL', 2)

    # Verificar dependencias críticas para el bucle
    if not utils or not client:
        print("[Ticker] ERROR FATAL: Faltan dependencias utils o client (manager). Saliendo.")
        return
    if symbol == 'N/A':
        print("[Ticker] ERROR FATAL: TICKER_SYMBOL no definido en config. Saliendo.")
        return

    print(f"[Ticker] Iniciado para {symbol} (Fetch: {fetch_interval}s, Callback cada: {raw_event_interval_ticks} ticks)")
    if not callable(_raw_event_callback):
        print("[Ticker] ERROR FATAL: No se proporcionó callback. Saliendo.")
        return

    _latest_price_info["symbol"] = symbol # Establecer símbolo inicial

    while not _ticker_stop_event.is_set():
        fetch_start_time = datetime.datetime.now()
        current_price_info = None
        price_updated_this_tick = False

        # --- 1. Obtener Precio ---
        # Usar client (manager) para obtener tickers
        response = client.get_tickers(session, category=category, symbol=symbol)
        fetch_timestamp = datetime.datetime.now() # Timestamp de cuando se obtuvo la respuesta

        if response:
            try:
                ticker_data_list = response.get('result', {}).get('list', [])
                if ticker_data_list:
                    ticker_data = ticker_data_list[0]
                    price_str = ticker_data.get('lastPrice')
                    # Usar utils para conversión segura
                    price = utils.safe_float_convert(price_str, default=None)
                    if price is not None and price > 0:
                        # Guardar precio y timestamp si son válidos
                        current_price_info = {"price": price, "timestamp": fetch_timestamp}
                        _latest_price_info["price"] = price
                        _latest_price_info["timestamp"] = fetch_timestamp
                        price_updated_this_tick = True
                # else: Lista vacía, no se actualiza precio
            except Exception as e:
                print(f"[Ticker] Error procesando respuesta API: {e}")
        # else: No hubo respuesta, no se actualiza precio

        # --- 2. Lógica de Conteo y Llamada al Callback ---
        if price_updated_this_tick and current_price_info: # Asegurar que tenemos info válida
            _tick_counter += 1

            # <<< BLOQUE ELIMINADO: Referencia a config.PRINT_TICK_ALWAYS >>>
            # if config.PRINT_TICK_ALWAYS:
            #      if current_price_info: # Seguridad adicional
            #          price_fmt = f"{current_price_info.get('price', 0.0):.4f}"
            #          ts_fmt = utils.format_datetime(current_price_info.get('timestamp'), '%H:%M:%S.%f')
            #          if '.' in ts_fmt: ts_fmt = ts_fmt[:-3] # Recortar microsegundos
            #          print(f"DEBUG [Ticker Tick] {_tick_counter}/{raw_event_interval_ticks} -> Precio: {price_fmt} @ {ts_fmt}")
            #      else:
            #          print("DEBUG [Ticker Tick] Intento de imprimir pero current_price_info es None.")

            # Guardar en buffer si no es el tick final
            if _tick_counter < raw_event_interval_ticks:
                 _intermediate_ticks_buffer.append(current_price_info)
            # Si ES el tick final
            else:
                 if callable(_raw_event_callback):
                     try:
                         # Pasar copia del buffer y los datos finales
                         _raw_event_callback( _intermediate_ticks_buffer.copy(),
                             final_price_info={ "price": current_price_info["price"],
                                                "timestamp": current_price_info["timestamp"],
                                                "symbol": symbol } )
                     except Exception as cb_err:
                         print(f"[Ticker] ERROR ejecutando callback: {cb_err}"); traceback.print_exc()
                 # Limpiar buffer y resetear contador después de llamar al callback
                 _intermediate_ticks_buffer.clear()
                 _tick_counter = 0
        # else: Si no se actualizó el precio este tick, no hacer nada con el contador/buffer

        # --- 3. Esperar para el próximo ciclo ---
        elapsed_time = (datetime.datetime.now() - fetch_start_time).total_seconds()
        wait_time = fetch_interval - elapsed_time
        # Esperar el tiempo restante o un mínimo de 0.1s para evitar spin-wait
        _ticker_stop_event.wait(timeout=max(0.1, wait_time))

    # --- Limpieza al detener ---
    print("[Ticker] Bucle detenido.");
    _latest_price_info = {"price": None, "timestamp": None, "symbol": None} # Resetear
    _tick_counter = 0
    _intermediate_ticks_buffer.clear()
    print("[Ticker] Estado limpiado.")

# --- Thread Control Functions ---
def start_ticker_thread(raw_event_callback=None):
    """Inicia el hilo del ticker en segundo plano."""
    global _ticker_thread, _ticker_stop_event, _tick_counter, _raw_event_callback, _intermediate_ticks_buffer

    # Verificar dependencias
    if not client:
        print("[Ticker] ERROR FATAL: Módulo client (manager) no disponible. No se puede iniciar.")
        return
    if not config:
         print("[Ticker] ERROR FATAL: Módulo config no disponible. No se puede iniciar.")
         return

    if _ticker_thread and _ticker_thread.is_alive():
        print("[Ticker] Advertencia: Ticker ya en ejecución."); return

    # Obtener Sesión API (con fallback)
    source_account = getattr(config, 'TICKER_SOURCE_ACCOUNT', 'profit')
    session = client.get_client(source_account)
    if not session:
        print(f"[Ticker] Advertencia: Fuente primaria '{source_account}' no disponible.");
        initialized_accounts = client.get_initialized_accounts()
        # Intentar con cuentas que no sean ni main ni la fuente primaria
        alt_source = next((acc for acc in initialized_accounts if acc != getattr(config, 'ACCOUNT_MAIN', 'main') and acc != source_account), None)
        # Si no hay, intentar con cualquiera que no sea la fuente primaria
        if not alt_source:
            alt_source = next((acc for acc in initialized_accounts if acc != source_account), None)

        if alt_source:
            print(f"[Ticker] Usando fuente alternativa '{alt_source}'...");
            session = client.get_client(alt_source)
            if not session:
                print(f"[Ticker] Error Fatal: Fuente alternativa '{alt_source}' falló."); return
            else:
                print(f"[Ticker] Conexión alternativa '{alt_source}' OK.")
        else:
            print(f"[Ticker] Error Fatal: No hay cuentas API válidas disponibles."); return

    # Resetear Estado y Crear/Iniciar Hilo
    print(f"[Ticker] Usando sesión API para obtener precios.");
    _tick_counter = 0
    _intermediate_ticks_buffer.clear()
    _raw_event_callback = raw_event_callback # Guardar referencia al callback
    _ticker_stop_event.clear() # Asegurar que el evento de parada esté limpio
    _ticker_thread = threading.Thread( target=_fetch_price_loop, args=(session,), daemon=True )
    _ticker_thread.name = "PriceTickerThread"
    _ticker_thread.start()
    print("[Ticker] Hilo iniciado.")

def stop_ticker_thread():
    """Detiene el hilo del ticker."""
    global _ticker_stop_event, _ticker_thread
    if _ticker_thread and _ticker_thread.is_alive():
        print("[Ticker] Solicitando parada...");
        _ticker_stop_event.set() # Señalizar al hilo que debe detenerse
        # Opcional: Esperar a que el hilo termine realmente
        # _ticker_thread.join(timeout=config.TICKER_INTERVAL_SECONDS + 2) # Esperar un poco más que el intervalo
        # if _ticker_thread.is_alive():
        #    print("[Ticker] Advertencia: El hilo no se detuvo después del timeout.")
    else:
        print("[Ticker] Info: Ticker no estaba en ejecución.")
    _ticker_thread = None # Limpiar la referencia al hilo

# --- Limpieza del módulo (si es necesario en el futuro) ---
# def cleanup():
#     global _raw_event_callback
#     stop_ticker_thread()
#     _raw_event_callback = None
#     print("[Ticker] Módulo limpiado.")