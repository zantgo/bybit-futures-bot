# # core/logging/_open_position_logger.py
"""
Módulo para escribir una instantánea final del estado de las posiciones ABIERTAS.
Delega la escritura a un gestor de logs asíncrono.
"""
import json
import datetime
import numpy as np
import pandas as pd
from typing import Dict, Any

# Importación segura de utils, aunque la serialización ahora es local.
try:
    from core import utils
except ImportError:
    utils = None

# --- Estado del Módulo ---
_manager: Any = None

def setup(manager: Any):
    """
    Inyecta la instancia del FileLogManager configurado desde el paquete de logging.
    """
    global _manager
    _manager = manager

def log_open_positions_snapshot(snapshot_data: Dict):
    """
    Formatea la instantánea a JSON y la envía al gestor de logs para que
    sobrescriba el archivo de forma asíncrona.
    """
    if not _manager or not isinstance(snapshot_data, dict):
        return

    try:
        # Función recursiva interna para hacer serializable todo el diccionario anidado
        def make_serializable(obj):
            if isinstance(obj, dict):
                return {k: make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_serializable(elem) for elem in obj]
            elif isinstance(obj, (datetime.datetime, pd.Timestamp)):
                # Se recomienda usar isoformat() para un estándar consistente
                return obj.isoformat()
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

        # Añadimos un timestamp de log en UTC para consistencia
        snapshot_data['snapshot_timestamp_utc'] = datetime.datetime.now(datetime.timezone.utc)
        final_log_data = make_serializable(snapshot_data)

        # Convertir a string JSON
        json_message = json.dumps(final_log_data, ensure_ascii=False)
        
        # Enviar al gestor asíncrono. Él se encargará de sobrescribir el archivo.
        _manager.log(json_message)

    except Exception as e:
        # Evitamos que un error de logging detenga el bot.
        print(f"ERROR CRÍTICO [Open Pos Snapshot Logger]: No se pudo formatear o encolar el log: {e}")