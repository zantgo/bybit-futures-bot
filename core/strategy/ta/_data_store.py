# core/strategy/ta/_data_store.py

"""
Módulo de Almacenamiento de Datos para el Análisis Técnico (Versión de Clase).

v2.0: El DataFrame interno trabaja con timestamps conscientes de la zona horaria
(UTC) para mantener la consistencia a lo largo del flujo de datos.
Esta clase encapsula el estado y la lógica de gestión del DataFrame.
"""
import pandas as pd
import numpy as np
from typing import Any

# Dependencias del proyecto
import config
from core import utils
from core.logging import memory_logger

class DataStore:
    """
    Gestiona un DataFrame en memoria para almacenar eventos de precios recientes,
    manteniendo una ventana de tamaño fijo y asegurando la consistencia de los
    timestamps en UTC.
    """
    _RAW_TABLE_DTYPES = {
        'timestamp': 'datetime64[ns, UTC]',
        'price': 'float64',
        'increment': 'int8',
        'decrement': 'int8'
    }

    def __init__(self, config_module: Any = config):
        """
        Inicializa el DataStore.
        Lee el tamaño de la ventana de la configuración y crea un DataFrame
        vacío con los tipos de datos correctos.
        """
        self._config = config_module
        ta_config = self._config.SESSION_CONFIG["TA"]
        self._window_size = max(
            ta_config["EMA_WINDOW"],
            ta_config["WEIGHTED_INC_WINDOW"],
            ta_config["WEIGHTED_DEC_WINDOW"]
        ) * 2
        self._raw_data_df = pd.DataFrame(columns=list(self._RAW_TABLE_DTYPES.keys())).astype(self._RAW_TABLE_DTYPES)

    def initialize(self):
        """
        Resetea el almacén de datos a un estado vacío, manteniendo los tipos.
        """
        self._raw_data_df = pd.DataFrame(columns=list(self._RAW_TABLE_DTYPES.keys())).astype(self._RAW_TABLE_DTYPES)

    def add_event(self, raw_event_data: dict):
        """
        Añade un nuevo evento de precio al DataFrame, asegura los tipos de datos
        (incluyendo la conversión a UTC) y mantiene el tamaño de la ventana.
        """
        if not isinstance(raw_event_data, dict):
            return

        try:
            data_to_add = {
                'timestamp': pd.to_datetime(raw_event_data.get('timestamp'), errors='coerce', utc=True),
                'price': utils.safe_float_convert(raw_event_data.get('price'), default=np.nan),
                'increment': int(utils.safe_float_convert(raw_event_data.get('increment', 0), default=0)),
                'decrement': int(utils.safe_float_convert(raw_event_data.get('decrement', 0), default=0))
            }

            if pd.isna(data_to_add['timestamp']) or pd.isna(data_to_add['price']):
                return

            new_row = pd.DataFrame([data_to_add])
            self._raw_data_df = pd.concat([self._raw_data_df, new_row], ignore_index=True)

            if len(self._raw_data_df) > self._window_size:
                self._raw_data_df = self._raw_data_df.iloc[-self._window_size:]

        except Exception as e:
            memory_logger.log(f"ERROR [DataStore - add_event]: {e}", level="ERROR")

    def get_data(self) -> pd.DataFrame:
        """
        Devuelve una copia del DataFrame actual para evitar modificaciones externas.
        """
        return self._raw_data_df.copy()
