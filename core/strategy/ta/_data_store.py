"""
Módulo de Almacenamiento de Datos para el Análisis Técnico.

v2.0: Actualizado para que el DataFrame interno trabaje con timestamps
conscientes de la zona horaria (UTC), evitando errores de conversión y
manteniendo la consistencia a lo largo del flujo de datos.
"""
import pandas as pd
import numpy as np

# Dependencias del proyecto
import config
from core import utils

# --- Estado del Módulo (Privado) ---

# Se cambia el tipo de dato para la columna timestamp para que sea consciente
# de la zona horaria (timezone-aware) y esté fijado a UTC.
_RAW_TABLE_DTYPES = {
    'timestamp': 'datetime64[ns, UTC]', # <-- Cambio clave para soportar UTC
    'price': 'float64',
    'increment': 'int8',
    'decrement': 'int8'
}

# Inicializa el DataFrame vacío con los tipos correctos
_raw_data_df = pd.DataFrame(columns=list(_RAW_TABLE_DTYPES.keys())).astype(_RAW_TABLE_DTYPES)

# --- Interfaz del Módulo (Funciones Públicas) ---

def initialize():
    """
    Resetea el almacén de datos a un estado vacío.
    """
    global _raw_data_df
    _raw_data_df = pd.DataFrame(columns=list(_RAW_TABLE_DTYPES.keys())).astype(_RAW_TABLE_DTYPES)

def add_event(raw_event_data: dict):
    """
    Añade un nuevo evento de precio al DataFrame, asegura los tipos de datos
    y mantiene el tamaño de la ventana definido en la configuración.
    """
    global _raw_data_df
    if not isinstance(raw_event_data, dict):
        return

    try:
        # Prepara los datos para añadir, convirtiendo y validando tipos.
        # pd.to_datetime manejará correctamente el objeto datetime aware que viene del ticker.
        data_to_add = {
            'timestamp': pd.to_datetime(raw_event_data.get('timestamp'), errors='coerce', utc=True),
            'price': utils.safe_float_convert(raw_event_data.get('price'), default=np.nan),
            'increment': int(utils.safe_float_convert(raw_event_data.get('increment', 0), default=0)),
            'decrement': int(utils.safe_float_convert(raw_event_data.get('decrement', 0), default=0))
        }

        # Omite el evento si los datos esenciales son inválidos
        if pd.isna(data_to_add['timestamp']) or pd.isna(data_to_add['price']):
            return

        # Crea una nueva fila. No es estrictamente necesario convertirla a los dtypes
        # aquí, ya que el DataFrame principal ya tiene los tipos definidos.
        new_row = pd.DataFrame([data_to_add])

        # Concatena. Pandas manejará la unión de tipos iguales (datetime64[ns, UTC]) sin problemas.
        _raw_data_df = pd.concat([_raw_data_df, new_row], ignore_index=True)

        # Mantiene el tamaño de la ventana, eliminando los datos más antiguos si es necesario
        window_size = getattr(config, 'TA_WINDOW_SIZE', 100)
        if len(_raw_data_df) > window_size:
            _raw_data_df = _raw_data_df.iloc[-window_size:]

    except Exception as e:
        # Se mantiene el log de errores para depuración.
        print(f"ERROR [TA Data Store - Add Event]: {e}")

def get_data() -> pd.DataFrame:
    """
    Devuelve una copia del DataFrame actual para evitar modificaciones externas.
    """
    return _raw_data_df.copy()