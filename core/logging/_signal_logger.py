# core/logging/_signal_logger.py

"""
Módulo simple para escribir el diccionario de señal completo a un archivo log.
Utiliza formato JSON Lines (un objeto JSON por línea).
"""
import json
import os
import traceback
import datetime
import numpy as np
import pandas as pd
import sys

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
    from core import utils
except ImportError as e:
    print(f"ERROR [Signal Logger Import]: {e}. Asegúrate que el módulo core sea accesible.")
    # Definir valores dummy
    config = type('obj', (object,), {
        'LOG_SIGNAL_OUTPUT': False,
        'SIGNAL_LOG_FILE': None
    })()
    utils = None

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Constantes ---
MAX_LOG_LINES = 1000 # Límite máximo de líneas a escribir por ejecución

# --- Estado del Módulo ---
_log_initialized = False
_log_filepath = None
_current_line_count = 0 # Contador de líneas escritas en esta ejecución
_limit_reached_message_shown = False # Para mostrar el mensaje de límite solo una vez

def initialize_logger():
    """Prepara el archivo log para escritura y resetea contadores."""
    global _log_initialized, _log_filepath, _current_line_count, _limit_reached_message_shown
    print("[Signal Logger] Inicializando...")
    # Resetear estado de límite
    _current_line_count = 0
    _limit_reached_message_shown = False

    _log_filepath = getattr(config, 'SIGNAL_LOG_FILE', None) # Acceso seguro
    log_enabled = getattr(config, 'LOG_SIGNAL_OUTPUT', False)

    if not log_enabled:
        _log_initialized = False
        print("[Signal Logger] Logging de señales desactivado en config.")
        return

    if not _log_filepath:
        print("ERROR [Signal Logger]: Ruta de archivo no definida en config.SIGNAL_LOG_FILE.")
        _log_initialized = False
        return

    try:
        # Asegurar que el directorio existe
        log_dir = os.path.dirname(_log_filepath)
        os.makedirs(log_dir, exist_ok=True)
        # Abrir en modo 'w' para borrar contenido anterior al iniciar un nuevo run
        with open(_log_filepath, 'w', encoding='utf-8') as f:
            pass # Simplemente crea/vacía el archivo
        _log_initialized = True
        print(f"[Signal Logger] Archivo log '{os.path.basename(_log_filepath)}' preparado (Max Lines: {MAX_LOG_LINES}, contenido anterior borrado).")
    except Exception as e:
        print(f"ERROR [Signal Logger] No se pudo inicializar el archivo log '{_log_filepath}': {e}")
        _log_initialized = False
        traceback.print_exc()

def log_signal_event(signal_data: dict):
    """
    Escribe el diccionario de señal completo como una línea JSON en el archivo log,
    respetando el límite de MAX_LOG_LINES.
    """
    global _current_line_count, _limit_reached_message_shown # Acceder a contadores globales

    # --- Verificaciones Iniciales ---
    if not _log_initialized:
        return # No loguear si no está inicializado

    # --- Verificar Límite de Líneas ---
    if _current_line_count >= MAX_LOG_LINES:
        if not _limit_reached_message_shown:
            print(f"INFO [Signal Logger]: Límite de {MAX_LOG_LINES} líneas alcanzado para '{os.path.basename(_log_filepath)}'. No se añadirán más entradas en esta ejecución.")
            _limit_reached_message_shown = True
        return # No escribir si se alcanzó el límite

    if not isinstance(signal_data, dict):
        print("ERROR [Signal Logger]: Se intentó loguear un dato que no es un diccionario.")
        return

    if not utils:
         print("ERROR [Signal Logger]: Módulo 'utils' no disponible para formatear.")
         return

    # --- Escritura (si el límite no se ha alcanzado) ---
    try:
        # Convertir tipos no serializables (como datetime o numpy types si existen) a string
        loggable_data = {}
        for key, value in signal_data.items():
            if isinstance(value, (datetime.datetime, pd.Timestamp)):
                # Usa el timestamp del diccionario si existe, si no, formatea el valor
                loggable_data[key] = signal_data.get('timestamp', utils.format_datetime(value))
            elif isinstance(value, (np.float64, np.float32, np.int64, np.int32)):
                loggable_data[key] = value.item()
            elif value is pd.NaT:
                loggable_data[key] = None
            elif pd.isna(value) or value == np.inf or value == -np.inf:
                 loggable_data[key] = str(value)
            else:
                loggable_data[key] = value

        # Escribir el diccionario como una línea JSON
        with open(_log_filepath, 'a', encoding='utf-8') as f:
            json.dump(loggable_data, f, ensure_ascii=False) # Escribe el objeto JSON
            f.write('\n')              # Añade un salto de línea (JSON Lines)

        # Incrementar contador DESPUÉS de escribir exitosamente
        _current_line_count += 1

    except Exception as e:
        print(f"ERROR [Signal Logger] No se pudo escribir en el archivo log '{_log_filepath}': {e}")
        traceback.print_exc()