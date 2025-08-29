"""
Módulo para capturar y almacenar logs en memoria.

Permite que diferentes partes de la aplicación registren mensajes sin
imprimirlos directamente en la consola, para luego ser consultados
bajo demanda por la TUI.
"""
import collections
import datetime
from datetime import timezone
from typing import List, Tuple
import sys  # <--- IMPORTACIÓN AÑADIDA

# --- Estado del Módulo ---
# Se mantiene el tamaño máximo de 1000 entradas para el historial de la TUI.
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
    # --- INICIO DE LA MODIFICACIÓN ---
    # Se genera el timestamp en UTC y se formatea para incluir la zona horaria.
    timestamp = datetime.datetime.now(timezone.utc).strftime('%H:%M:%S (UTC)')
    # --- FIN DE LA MODIFICACIÓN ---
    log_entry = (timestamp, level, message)
    _log_deque.append(log_entry)

    # Imprimir solo si estamos en modo "verboso"
    if _is_verbose_mode:
        # --- LÍNEA 33 CORREGIDA ---
        # Se redirige la impresión a sys.stderr para que no interfiera con la TUI.
        print(f"[{timestamp}][{level}] {message}", file=sys.stderr)

def get_logs() -> List[Tuple[str, str, str]]:
    """Devuelve una copia de todos los logs almacenados."""
    return list(_log_deque)