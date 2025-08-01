# core/strategy/ta/_data_store.py

"""
Módulo de Almacenamiento de Datos para el Análisis Técnico (Versión de Clase).

v2.0: El DataFrame interno trabaja con timestamps conscientes de la zona horaria
(UTC) para mantener la consistencia a lo largo del flujo de datos.
Esta clase encapsula el estado y la lógica de gestión del DataFrame.
"""
import pandas as pd
import numpy as np

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
    # Definición de tipos de datos como atributo de clase.
    # El cambio clave a 'datetime64[ns, UTC]' se mantiene.
    _RAW_TABLE_DTYPES = {
        'timestamp': 'datetime64[ns, UTC]',
        'price': 'float64',
        'increment': 'int8',
        'decrement': 'int8'
    }

    def __init__(self):
        """
        Inicializa el DataStore.
        Lee el tamaño de la ventana de la configuración y crea un DataFrame
        vacío con los tipos de datos correctos.
        """
        self._window_size = getattr(config, 'TA_WINDOW_SIZE', 100)
        self._raw_data_df = pd.DataFrame(columns=list(self._RAW_TABLE_DTYPES.keys())).astype(self._RAW_TABLE_DTYPES)

    def initialize(self):
        """
        Resetea el almacén de datos a un estado vacío, manteniendo los tipos.
        Este método es idéntico a la función `initialize` original.
        """
        self._raw_data_df = pd.DataFrame(columns=list(self._RAW_TABLE_DTYPES.keys())).astype(self._RAW_TABLE_DTYPES)

    def add_event(self, raw_event_data: dict):
        """
        Añade un nuevo evento de precio al DataFrame, asegura los tipos de datos
        (incluyendo la conversión a UTC) y mantiene el tamaño de la ventana.
        Este método contiene toda la lógica de la función `add_event` original.
        """
        if not isinstance(raw_event_data, dict):
            return

        try:
            # Prepara los datos para añadir. La lógica de conversión es idéntica
            # a la versión funcional, asegurando la conversión a UTC.
            data_to_add = {
                'timestamp': pd.to_datetime(raw_event_data.get('timestamp'), errors='coerce', utc=True),
                'price': utils.safe_float_convert(raw_event_data.get('price'), default=np.nan),
                'increment': int(utils.safe_float_convert(raw_event_data.get('increment', 0), default=0)),
                'decrement': int(utils.safe_float_convert(raw_event_data.get('decrement', 0), default=0))
            }

            # Omite el evento si los datos esenciales son inválidos.
            if pd.isna(data_to_add['timestamp']) or pd.isna(data_to_add['price']):
                return

            new_row = pd.DataFrame([data_to_add])

            # Concatena la nueva fila. El estado (_raw_data_df) ahora es un
            # atributo de la instancia (self).
            self._raw_data_df = pd.concat([self._raw_data_df, new_row], ignore_index=True)

            # Mantiene el tamaño de la ventana, usando el tamaño almacenado en el constructor.
            if len(self._raw_data_df) > self._window_size:
                self._raw_data_df = self._raw_data_df.iloc[-self._window_size:]

        except Exception as e:
            # El registro de errores se mantiene igual.
            memory_logger.log(f"ERROR [DataStore - add_event]: {e}", level="ERROR")

    def get_data(self) -> pd.DataFrame:
        """
        Devuelve una copia del DataFrame actual para evitar modificaciones externas.
        Este método es idéntico a la función `get_data` original.
        """
        return self._raw_data_df.copy()