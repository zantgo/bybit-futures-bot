# core/logging/_close_position_logger.py

"""
Módulo para escribir detalles de posiciones CERRADAS a un archivo log.
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
    print(f"ERROR [Closed Pos Logger Import]: {e}. Asegúrate que el módulo core sea accesible.")
    # Definir valores dummy o salir si es crítico
    config = type('obj', (object,), {
        'POSITION_MANAGEMENT_ENABLED': False,
        'POSITION_LOG_CLOSED_POSITIONS': False,
        'POSITION_CLOSED_LOG_FILE': None
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
    """
    Prepara el archivo log de posiciones cerradas para escritura y resetea contadores.
    ¡¡USA MODO WRITE ('w') PARA BORRAR CONTENIDO ANTERIOR!!
    """
    global _log_initialized, _log_filepath, _current_line_count, _limit_reached_message_shown

    # Resetear estado de límite
    _current_line_count = 0
    _limit_reached_message_shown = False

    # Verificar si la gestión de posiciones y el logging están habilitados en config
    pos_management_enabled = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    log_closed_pos_enabled = getattr(config, 'POSITION_LOG_CLOSED_POSITIONS', False)

    if not pos_management_enabled or not log_closed_pos_enabled:
        _log_initialized = False
        print("[Closed Pos Logger] Logging de posiciones cerradas desactivado en config.")
        return

    print("[Closed Pos Logger] Inicializando...")
    _log_filepath = getattr(config, 'POSITION_CLOSED_LOG_FILE', None)
    if not _log_filepath:
        print("ERROR [Closed Pos Logger]: Ruta de archivo no definida en config.POSITION_CLOSED_LOG_FILE.")
        _log_initialized = False
        return

    try:
        # Asegurar que el directorio de logs exista
        log_dir = os.path.dirname(_log_filepath)
        os.makedirs(log_dir, exist_ok=True)

        # Usar modo 'w' (write) para sobrescribir el archivo al inicio de la ejecución
        with open(_log_filepath, 'w', encoding='utf-8') as f:
            pass

        _log_initialized = True
        print(f"[Closed Pos Logger] Archivo log '{os.path.basename(_log_filepath)}' preparado (Max Lines: {MAX_LOG_LINES}, contenido anterior borrado).")

    except Exception as e:
        print(f"ERROR [Closed Pos Logger] No se pudo inicializar/abrir el archivo log '{_log_filepath}': {e}")
        _log_initialized = False
        traceback.print_exc()

def log_closed_position(position_data: dict):
    """
    Escribe el diccionario de la posición cerrada como una línea JSON en el archivo log,
    respetando el límite de MAX_LOG_LINES.
    """
    global _current_line_count, _limit_reached_message_shown # Acceder a contadores globales

    # --- Verificaciones Iniciales ---
    if not _log_initialized:
        return

    # --- Verificar Límite de Líneas ---
    if _current_line_count >= MAX_LOG_LINES:
        if not _limit_reached_message_shown:
            print(f"INFO [Closed Pos Logger]: Límite de {MAX_LOG_LINES} líneas alcanzado para '{os.path.basename(_log_filepath)}'. No se añadirán más entradas en esta ejecución.")
            _limit_reached_message_shown = True
        return # No escribir si se alcanzó el límite

    if not isinstance(position_data, dict):
        print("ERROR [Closed Pos Logger]: Se intentó loguear un dato que no es un diccionario.")
        return

    if not utils:
         print("ERROR [Closed Pos Logger]: Módulo 'utils' no disponible para formatear.")
         return

    # --- Escritura (si el límite no se ha alcanzado) ---
    try:
        # Convertir tipos no serializables a formatos compatibles con JSON
        loggable_data = {}
        for key, value in position_data.items():
            if isinstance(value, (datetime.datetime, pd.Timestamp)):
                loggable_data[key] = utils.format_datetime(value)
            elif isinstance(value, (np.float64, np.float32, np.int64, np.int32)):
                loggable_data[key] = value.item()
            elif value is pd.NaT:
                loggable_data[key] = None
            elif pd.isna(value) or value == np.inf or value == -np.inf:
                 loggable_data[key] = str(value)
            elif isinstance(value, (int, float, str, bool)) or value is None:
                 loggable_data[key] = value
            else:
                 try:
                     loggable_data[key] = str(value)
                 except Exception:
                      loggable_data[key] = f"SerializationError:CannotConvert_{type(value)}"

        # Escribir el diccionario procesado como una línea JSON en el archivo log ('a'ppend)
        with open(_log_filepath, 'a', encoding='utf-8') as f:
            json.dump(loggable_data, f, ensure_ascii=False)
            f.write('\n')

        # Incrementar contador DESPUÉS de escribir exitosamente
        _current_line_count += 1

    except Exception as e:
        print(f"ERROR [Closed Pos Logger] No se pudo escribir en el archivo log '{os.path.basename(_log_filepath)}': {e}")
        traceback.print_exc()