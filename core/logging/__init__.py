# core/logging/__init__.py

"""
Paquete de Logging del Bot.

Este paquete centraliza todos los módulos relacionados con el registro de eventos,
incluyendo logs en memoria para la TUI y logs persistentes en archivos para
señales, posiciones cerradas y snapshots.
"""
import os
import time
import collections
import threading
import queue
from typing import List

# --- Importar y Exponer Módulos de Logging ---
from . import _memory_logger as memory_logger
from . import _signal_logger as signal_logger
from . import _close_position_logger as closed_position_logger
from . import _open_position_logger as open_position_logger

# --- INICIO DE LA MODIFICACIÓN: Lógica del Gestor de Logs Asíncrono ---

class FileLogManager:
    """
    Gestiona la escritura de logs a un archivo en un hilo separado de forma asíncrona.
    Mantiene un límite de líneas en el archivo y escribe por lotes para eficiencia.
    """
    def __init__(self, filepath: str, max_lines: int = 1000, batch_size: int = 10, flush_interval: int = 30, overwrite: bool = False):
        self.filepath = filepath
        self.max_lines = max_lines
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.overwrite = overwrite # True para el snapshot, False para logs continuos

        self._log_queue = queue.Queue()
        self._log_deque = collections.deque(maxlen=self.max_lines)
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._is_prepared = False

    def _prepare(self):
        """Lee el archivo existente en el deque. Se ejecuta una sola vez."""
        if self._is_prepared:
            return
        
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            if not self.overwrite and os.path.exists(self.filepath):
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    # Carga las líneas existentes, el deque se encargará del límite.
                    self._log_deque.extend(line.strip() for line in f if line.strip())
        except Exception as e:
            print(f"ERROR [FileLogManager]: No se pudo preparar el archivo {self.filepath}: {e}")
        finally:
            self._is_prepared = True

    def start(self):
        """Inicia el hilo trabajador del logger."""
        self._prepare()
        self._worker_thread.start()

    def stop(self):
        """Señala al trabajador que debe detenerse y vacía la cola final."""
        self._log_queue.put(None) # Señal de parada
        self._stop_event.set()
        self._worker_thread.join(timeout=5)

    def log(self, message: str):
        """Método público para añadir un mensaje de log a la cola."""
        if not self._stop_event.is_set():
            self._log_queue.put(message)

    def _worker(self):
        """
        Bucle del trabajador que se ejecuta en segundo plano.
        Recoge logs de la cola y los escribe en el archivo.
        """
        batch: List[str] = []
        last_flush = time.time()
        
        while not self._stop_event.is_set():
            try:
                # Esperar por un nuevo mensaje, con un timeout para permitir el flush periódico
                log_message = self._log_queue.get(timeout=1)
                
                if log_message is None: # Señal de parada
                    break
                
                batch.append(log_message)
                
                time_since_flush = time.time() - last_flush
                
                # Escribir si el lote está lleno o si ha pasado suficiente tiempo
                if len(batch) >= self.batch_size or time_since_flush >= self.flush_interval:
                    self._flush(batch)
                    batch.clear()
                    last_flush = time.time()

            except queue.Empty:
                # Timeout alcanzado, no hay nuevos mensajes. Comprobar si hay algo que escribir.
                if batch and (time.time() - last_flush) >= self.flush_interval:
                    self._flush(batch)
                    batch.clear()
                    last_flush = time.time()
        
        # Vaciado final al detener el bot
        if batch:
            self._flush(batch)
        # Recoger cualquier mensaje restante en la cola
        final_batch = []
        while not self._log_queue.empty():
            msg = self._log_queue.get_nowait()
            if msg: final_batch.append(msg)
        if final_batch:
            self._flush(final_batch)

    def _flush(self, batch: List[str]):
        """Añade un lote de mensajes al deque y escribe el contenido al archivo."""
        try:
            # Añadir todos los mensajes nuevos al deque
            for msg in batch:
                self._log_deque.append(msg)
            
            # Preparar contenido para escribir
            lines_to_write = [line + '\n' for line in self._log_deque]
            
            # Determinar el modo de escritura
            write_mode = 'w' if self.overwrite else 'w' # Siempre sobrescribimos con el contenido del deque
            
            with open(self.filepath, write_mode, encoding='utf-8') as f:
                f.writelines(lines_to_write)
        except Exception as e:
            print(f"ERROR [FileLogManager]: No se pudo escribir en el archivo {self.filepath}: {e}")

# Instancias globales para los gestores
_signal_manager = None
_closed_pos_manager = None
_open_pos_manager = None

def initialize_loggers():
    """
    Crea, configura e inicia los gestores de logging de archivos.
    """
    global _signal_manager, _closed_pos_manager, _open_pos_manager
    import config # Importación local para asegurar que config esté cargado

    # Configuración para el logger de señales
    if getattr(config, 'LOG_SIGNAL_OUTPUT', False):
        _signal_manager = FileLogManager(
            filepath=getattr(config, 'SIGNAL_LOG_FILE'),
            max_lines=1000,
            batch_size=10,
            flush_interval=30
        )
        signal_logger.setup(_signal_manager)
        _signal_manager.start()

    # Configuración para el logger de posiciones cerradas
    if getattr(config, 'POSITION_LOG_CLOSED_POSITIONS', False):
        _closed_pos_manager = FileLogManager(
            filepath=getattr(config, 'POSITION_CLOSED_LOG_FILE'),
            max_lines=1000
        )
        closed_position_logger.setup(_closed_pos_manager)
        _closed_pos_manager.start()
        
    # Configuración para el logger de snapshot de posiciones abiertas
    if getattr(config, 'POSITION_LOG_OPEN_SNAPSHOT', False):
        _open_pos_manager = FileLogManager(
            filepath=getattr(config, 'POSITION_OPEN_SNAPSHOT_FILE'),
            max_lines=1, # Solo nos interesa la última instantánea
            overwrite=True # Siempre sobrescribir
        )
        open_position_logger.setup(_open_pos_manager)
        _open_pos_manager.start()
    
    memory_logger.log("Sistema de logging asíncrono inicializado.", "INFO")

def shutdown_loggers():
    """Detiene todos los hilos de los gestores de logs de forma ordenada."""
    if _signal_manager: _signal_manager.stop()
    if _closed_pos_manager: _closed_pos_manager.stop()
    if _open_pos_manager: _open_pos_manager.stop()
    memory_logger.log("Sistema de logging asíncrono detenido.", "INFO")

# --- FIN DE LA MODIFICACIÓN ---


# --- Control de lo que se exporta con 'from core.logging import *' ---
# Es una buena práctica definir __all__ para una API pública limpia.
__all__ = [
    'memory_logger',
    'signal_logger',
    'closed_position_logger',
    'open_position_logger',
    'initialize_loggers', # Exponer la nueva función de inicialización
    'shutdown_loggers',   # Exponer la nueva función de apagado
]