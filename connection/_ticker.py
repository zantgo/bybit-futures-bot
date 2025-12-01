# connection/_ticker.py

import threading
import time
import traceback
import sys
import os
from typing import Optional, Dict, Any, Callable
import datetime

try:
    import requests
except ImportError:
    requests = None

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
    print(f"ERROR CRITICO [Ticker Class Import]: No se pudo importar un módulo esencial: {e}")
    config = type('obj', (object,), {})()
    memory_logger = type('obj', (object,), {'log': print})()
    AbstractExchange = type
    StandardTicker = type


class Ticker:
    """
    Gestiona un hilo para obtener precios de mercado o ejecutar ticks de simulación.
    """

    def __init__(self, dependencies: Dict[str, Any]):
        self._config = dependencies.get('config_module', config)
        self._memory_logger = dependencies.get('memory_logger_module', memory_logger)
        
        self._latest_price_info: Dict[str, Any] = {"price": None, "timestamp": None, "symbol": None}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._tick_counter: int = 0
        self._raw_event_callback: Optional[Callable] = None
        self._intermediate_ticks_buffer: list = []
        self._exchange_adapter: Optional[AbstractExchange] = None
        self._lock = threading.Lock()

    def get_latest_price(self) -> dict:
        with self._lock:
            return self._latest_price_info.copy()

    def start(self, exchange_adapter: AbstractExchange, raw_event_callback: Callable):
        if not isinstance(exchange_adapter, AbstractExchange):
            self._memory_logger.log("Ticker ERROR FATAL: El objeto proporcionado no es una instancia de AbstractExchange.", level="ERROR")
            return

        if self._thread and self._thread.is_alive():
            self._memory_logger.log("Ticker: Advertencia: Ticker ya en ejecución.", level="WARN")
            return

        self._memory_logger.log(f"Ticker: Iniciando con adaptador '{type(exchange_adapter).__name__}'.", level="INFO")

        self._raw_event_callback = raw_event_callback
        self._exchange_adapter = exchange_adapter
        self._stop_event.clear()
        
        with self._lock:
            self._latest_price_info = {"price": None, "timestamp": None, "symbol": None}
            self._intermediate_ticks_buffer.clear()
            self._tick_counter = 0
        
        self._thread = threading.Thread(target=self._fetch_price_loop, daemon=True)
        self._thread.name = "PriceTickerThread"
        self._thread.start()
        self._memory_logger.log("Ticker: Hilo iniciado.", level="INFO")
    
    def signal_stop(self):
        """Solamente establece el evento de parada para que el hilo termine su bucle."""
        self._stop_event.set()

    def stop(self):
        """Señaliza la parada y espera a que el hilo termine (join)."""
        if self._thread and self._thread.is_alive():
            self._memory_logger.log("Ticker: Solicitando parada y esperando finalización...", level="INFO")
            self.signal_stop()
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                self._memory_logger.log("WARN [Ticker]: El hilo no terminó de forma limpia.", level="WARN")
        
        self._thread = None

    def run_simulation_tick(self, new_price: float):
        if not callable(self._raw_event_callback):
            self._memory_logger.log("Ticker Sim: Callback no configurado. No se puede ejecutar el tick.", "ERROR")
            return

        symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
        
        simulated_ticker = StandardTicker(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            symbol=symbol,
            price=new_price
        )
        
        self._handle_new_price(simulated_ticker)
        self._memory_logger.log(f"Ticker Sim: Tick ejecutado con precio simulado: {new_price}", "DEBUG")

    def run_single_real_tick(self):
        if not self._exchange_adapter:
            self._memory_logger.log("Ticker Sim: Adaptador de exchange no disponible. No se puede ejecutar tick real.", level="ERROR")
            return

        if not callable(self._raw_event_callback):
            self._memory_logger.log("Ticker Sim: Callback no configurado. No se puede ejecutar el tick.", level="ERROR")
            return

        symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
        self._memory_logger.log(f"Ticker: Ejecutando consulta puntual para '{symbol}'...", level="DEBUG")
        
        standard_ticker = self._exchange_adapter.get_ticker(symbol)
        
        if standard_ticker and isinstance(standard_ticker, StandardTicker):
            self._handle_new_price(standard_ticker)
            self._memory_logger.log(f"Ticker: Tick puntual ejecutado con precio real: {standard_ticker.price}", level="INFO")
        else:
            self._memory_logger.log(f"Ticker: Fallo al obtener precio en la consulta puntual.", level="WARN")

    def _fetch_price_loop(self):
        if not self._exchange_adapter:
            self._memory_logger.log("Ticker ERROR FATAL: Adaptador de exchange no disponible en el hilo.", "ERROR")
            return

        if not callable(self._raw_event_callback):
            self._memory_logger.log(f"Ticker ERROR FATAL: Callback inválido. Saliendo del hilo.", level="ERROR")
            return

        fetch_interval = self._config.SESSION_CONFIG["TICKER_INTERVAL_SECONDS"]
        self._memory_logger.log(f"Ticker: Bucle iniciado (Intervalo: {fetch_interval}s)", level="INFO")
        
        last_symbol_used = ""

        while not self._stop_event.is_set():
            start_time = time.monotonic()
            
            try:
                fetch_interval = self._config.SESSION_CONFIG["TICKER_INTERVAL_SECONDS"]
                symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]

                if not symbol:
                    time.sleep(fetch_interval)
                    continue
                
                if symbol != last_symbol_used:
                    self._memory_logger.log(f"Ticker: Símbolo actualizado a '{symbol}'.", level="INFO")
                    last_symbol_used = symbol
                    with self._lock:
                        self._latest_price_info = {"price": None, "timestamp": None, "symbol": symbol}

                standard_ticker = None
                try:
                    standard_ticker = self._exchange_adapter.get_ticker(symbol)
                except requests.exceptions.RequestException as e:
                    self._memory_logger.log(f"Ticker WARN: Error de red al obtener precio: {type(e).__name__}", level="WARN")
                    time.sleep(2)
                except Exception as e:
                    self._memory_logger.log(f"Ticker ERROR: Excepción en get_ticker: {e}", level="ERROR")
                    self._memory_logger.log(traceback.format_exc(), level="ERROR")
                    time.sleep(5) 

                if standard_ticker and isinstance(standard_ticker, StandardTicker):
                    self._handle_new_price(standard_ticker)

            except Exception as e_outer:
                self._memory_logger.log(f"Ticker FATAL: Error crítico en el bucle principal: {e_outer}", level="ERROR")
                self._memory_logger.log(traceback.format_exc(), level="ERROR")
                time.sleep(10)

            elapsed = time.monotonic() - start_time
            wait_time = max(0, fetch_interval - elapsed)
            self._stop_event.wait(timeout=wait_time)

        self._memory_logger.log("Ticker: Bucle de obtención de precios detenido.", level="INFO")

    def _handle_new_price(self, ticker_data: StandardTicker):
        final_info = None
        with self._lock:
            self._latest_price_info.update({
                "price": ticker_data.price,
                "timestamp": ticker_data.timestamp,
                "symbol": ticker_data.symbol
            })
            
            current_tick_info = {"price": ticker_data.price, "timestamp": ticker_data.timestamp}
            self._intermediate_ticks_buffer.append(current_tick_info)
            self._tick_counter += 1
            
            raw_event_ticks = 1 

            if self._tick_counter >= raw_event_ticks:
                final_info = self._latest_price_info.copy()
                intermediate_info = self._intermediate_ticks_buffer.copy()
                self._intermediate_ticks_buffer.clear()
                self._tick_counter = 0
        
        if final_info and callable(self._raw_event_callback):
            try:
                self._raw_event_callback(
                    intermediate_ticks_info=intermediate_info,
                    final_price_info=final_info
                )
            except Exception as e:
                self._memory_logger.log(f"Ticker: ERROR CRÍTICO ejecutando callback: {e}", level="ERROR")
                self._memory_logger.log(traceback.format_exc(), level="ERROR")
