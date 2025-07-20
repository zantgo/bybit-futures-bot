# =============== INICIO ARCHIVO: core/logging/memory_logger.py (ACTUALIZADO) ===============
"""
Módulo para capturar y almacenar logs en memoria.

Permite que diferentes partes de la aplicación registren mensajes sin
imprimirlos directamente en la consola, para luego ser consultados
bajo demanda por la TUI.
"""
import collections
import datetime
from typing import List, Tuple

# --- Estado del Módulo ---
# Aumentado el tamaño máximo para tener más historial en la TUI
_log_deque = collections.deque(maxlen=1000)
_is_verbose_mode = False # Por defecto, no se imprimen logs informativos

def set_verbose_mode(is_verbose: bool):
    """Activa o desactiva la impresión de logs informativos en la consola."""
    global _is_verbose_mode
    _is_verbose_mode = is_verbose

def log(message: str, level: str = "INFO"):
    """
    Registra un mensaje en la cola de memoria y opcionalmente lo imprime.
    """
    global _log_deque, _is_verbose_mode
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    log_entry = (timestamp, level, message)
    _log_deque.append(log_entry)

    # Imprimir solo si estamos en modo "verboso"
    if _is_verbose_mode:
        print(f"[{timestamp}][{level}] {message}")

def get_logs() -> List[Tuple[str, str, str]]:
    """Devuelve una copia de todos los logs almacenados."""
    return list(_log_deque)

# =============== FIN ARCHIVO: core/logging/memory_logger.py (ACTUALIZADO) ===============