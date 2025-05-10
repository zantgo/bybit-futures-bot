
# core/logging/open_position_snapshot_logger.py
"""
Módulo para escribir una instantánea final del estado de las posiciones ABIERTAS.
Utiliza formato JSON Lines (un objeto JSON por línea).
v7.2 - Añadido límite máximo de 1000 líneas por ejecución (aunque normalmente solo escribe 1).
"""
import json
import os
import traceback
import datetime
import numpy as np
import pandas as pd

# Importar config y utils
try:
    import config
    from core import utils
except ImportError as e:
    print(f"ERROR [Open Pos Snapshot Logger Import]: {e}. Asegúrate que el módulo core sea accesible.")
    config = type('obj', (object,), { 'POSITION_MANAGEMENT_ENABLED': False, 'POSITION_LOG_OPEN_SNAPSHOT': False, 'POSITION_OPEN_SNAPSHOT_FILE': None })()
    utils = None

# --- Constantes ---
MAX_LOG_LINES = 1000 # Límite máximo de líneas a escribir por ejecución

# --- Estado del Módulo ---
_log_initialized = False
_log_filepath = None
_current_line_count = 0 # Contador de líneas escritas en esta ejecución
_limit_reached_message_shown = False # Para mostrar el mensaje de límite solo una vez

def initialize_logger():
    """
    Prepara el archivo log de instantáneas para escritura y resetea contadores.
    ¡¡USA MODO WRITE ('w') PARA BORRAR CONTENIDO ANTERIOR!!
    """
    global _log_initialized, _log_filepath, _current_line_count, _limit_reached_message_shown

    # Resetear estado de límite
    _current_line_count = 0
    _limit_reached_message_shown = False

    # Acceder a la configuración de forma segura usando getattr
    pos_management_enabled = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    log_open_snapshot_enabled = getattr(config, 'POSITION_LOG_OPEN_SNAPSHOT', False)

    if not pos_management_enabled or not log_open_snapshot_enabled:
        _log_initialized = False
        print("[Open Pos Snapshot Logger] Logging de snapshot desactivado en config.")
        return

    print("[Open Pos Snapshot Logger] Inicializando...")
    _log_filepath = getattr(config, 'POSITION_OPEN_SNAPSHOT_FILE', None)
    if not _log_filepath:
        print("ERROR [Open Pos Snapshot Logger]: Ruta de archivo no definida en config.POSITION_OPEN_SNAPSHOT_FILE.")
        _log_initialized = False
        return

    try:
        # Asegurar que el directorio de logs exista
        log_dir = os.path.dirname(_log_filepath)
        os.makedirs(log_dir, exist_ok=True)

        # Usar modo 'w' (write) para sobrescribir el archivo al inicio de la ejecución
        with open(_log_filepath, 'w', encoding='utf-8') as f:
            pass # El modo 'w' vacía o crea el archivo

        _log_initialized = True
        print(f"[Open Pos Snapshot Logger] Archivo log '{os.path.basename(_log_filepath)}' preparado (Max Lines: {MAX_LOG_LINES}, contenido anterior borrado).")

    except Exception as e:
        print(f"ERROR [Open Pos Snapshot Logger] No se pudo inicializar/abrir el archivo log '{_log_filepath}': {e}")
        _log_initialized = False
        traceback.print_exc()

def log_open_positions_snapshot(snapshot_data: dict):
    """
    Escribe el diccionario de la instantánea como una línea JSON en el archivo log,
    respetando el límite de MAX_LOG_LINES.
    """
    global _current_line_count, _limit_reached_message_shown # Acceder a contadores globales

    # --- Verificaciones Iniciales ---
    if not _log_initialized:
        return

    # --- Verificar Límite de Líneas ---
    # Aunque este logger usualmente solo escribe una vez, mantenemos la lógica por consistencia.
    if _current_line_count >= MAX_LOG_LINES:
        if not _limit_reached_message_shown:
            print(f"INFO [Open Pos Snapshot Logger]: Límite de {MAX_LOG_LINES} líneas alcanzado para '{os.path.basename(_log_filepath)}'. No se añadirá la snapshot.")
            _limit_reached_message_shown = True
        return # No escribir si se alcanzó el límite

    if not isinstance(snapshot_data, dict):
        print("ERROR [Open Pos Snapshot Logger]: Se intentó loguear un dato que no es un diccionario.")
        return

    if not _log_filepath:
        print("ERROR [Open Pos Snapshot Logger]: Ruta de archivo no disponible (_log_filepath es None).")
        return

    if not utils:
         print("ERROR [Open Pos Snapshot Logger]: Módulo 'utils' no disponible para formatear.")
         return

    # --- Escritura (si el límite no se ha alcanzado) ---
    try:
        loggable_snapshot = snapshot_data.copy()
        loggable_snapshot['snapshot_timestamp'] = utils.format_datetime(datetime.datetime.now())

        # (Función make_serializable sin cambios)
        def make_serializable(obj):
            if isinstance(obj, dict):
                return {k: make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_serializable(elem) for elem in obj]
            elif isinstance(obj, (datetime.datetime, pd.Timestamp)):
                return utils.format_datetime(obj)
            elif isinstance(obj, (np.float64, np.float32, np.int64, np.int32)):
                return obj.item()
            elif obj is pd.NaT:
                return None
            elif pd.isna(obj) or obj == np.inf or obj == -np.inf:
                 return str(obj)
            elif isinstance(obj, (int, float, str, bool)) or obj is None:
                 return obj
            else:
                 try:
                     return str(obj)
                 except Exception:
                     return f"SerializationError:CannotConvert_{type(obj)}"

        final_log_data = make_serializable(loggable_snapshot)

        # Escribir el objeto JSON final en el archivo log ('a'ppend)
        with open(_log_filepath, 'a', encoding='utf-8') as f:
            json.dump(final_log_data, f, ensure_ascii=False, indent=None)
            f.write('\n')

        # Incrementar contador DESPUÉS de escribir exitosamente
        _current_line_count += 1

        print(f"[Open Pos Snapshot Logger] Instantánea final guardada en '{os.path.basename(_log_filepath)}'.")

    except Exception as e:
        print(f"ERROR [Open Pos Snapshot Logger] No se pudo escribir la instantánea en '{os.path.basename(_log_filepath)}': {e}")
        traceback.print_exc()