# core/logging/_close_position_logger.py

"""
Módulo para escribir detalles de posiciones CERRADAS a un archivo log.
Delega la escritura a un gestor de logs asíncrono.
"""
import json
import datetime
import numpy as np
import pandas as pd
from typing import Dict, Any

# --- Estado del Módulo ---
_manager: Any = None

def setup(manager: Any):
    """
    Inyecta la instancia del FileLogManager configurado desde el paquete de logging.
    """
    global _manager
    _manager = manager

def log_closed_position(position_data: Dict):
    """
    Formatea los datos de la posición cerrada a JSON y los envía al gestor de logs
    para su escritura asíncrona.
    """
    if not _manager or not isinstance(position_data, dict):
        return

    try:
        # Función interna para hacer el diccionario serializable a JSON
        def make_serializable(obj):
            if isinstance(obj, (datetime.datetime, pd.Timestamp)):
                return obj.isoformat()
            if isinstance(obj, (np.float64, np.float32, np.int64, np.int32)):
                return obj.item()
            if obj is pd.NaT:
                return None
            if pd.isna(obj) or obj == np.inf or obj == -np.inf:
                 return str(obj)
            return obj
            
        # Añadimos un timestamp de log en UTC para consistencia
        position_data['log_timestamp_utc'] = datetime.datetime.now(datetime.timezone.utc)
        loggable_data = {k: make_serializable(v) for k, v in position_data.items()}
        
        # Convertir a string JSON
        json_message = json.dumps(loggable_data, ensure_ascii=False)
        
        # Enviar al gestor asíncrono
        _manager.log(json_message)

    except Exception as e:
        # Evitamos que un error de logging detenga el bot.
        print(f"ERROR CRÍTICO [Closed Pos Logger]: No se pudo formatear o encolar el log de posición: {e}")