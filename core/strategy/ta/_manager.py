import pandas as pd
import numpy as np
import traceback
from typing import Dict, Any

# Dependencias del proyecto
import config
from core import utils
from core.logging import memory_logger
from ._data_store import DataStore
from . import _calculator

class TAManager:
    """
    Orquesta el flujo de Análisis Técnico. Mantiene un almacén de datos y
    utiliza un calculador para generar indicadores. Cada instancia es independiente.
    """

    def __init__(self, config_module: Any = config):
        """
        Inicializa el TAManager, creando su propio DataStore y
        estableciendo su estado inicial.
        """
        self._config = config_module
        self._data_store = DataStore(self._config)
        
        self._latest_indicators = {}
        self.initialize()

    def initialize(self):
        """
        Inicializa o resetea el estado del gestor para una nueva sesión,
        limpiando el almacén de datos y la caché de indicadores.
        """
        memory_logger.log("[TAManager] Inicializando...", "INFO")
        self._data_store.initialize()
        self._latest_indicators = {
            'timestamp': pd.NaT, 'price': np.nan, 'ema': np.nan,
            'weighted_increment': np.nan, 'weighted_decrement': np.nan,
            'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan,
        }
        memory_logger.log("[TAManager] Inicializado.", "INFO")

    def get_latest_indicators(self) -> dict:
        """
        Devuelve una copia del último conjunto de indicadores almacenado en caché.
        """
        return self._latest_indicators.copy()

    def process_raw_price_event(self, raw_event_data: dict) -> dict:
        """
        Procesa un único evento de precio crudo: lo almacena, recalcula
        todos los indicadores y actualiza la caché interna.
        
        Args:
            raw_event_data (dict): Un diccionario con los datos del tick de precio.

        Returns:
            dict: Una copia del conjunto más reciente de indicadores calculados.
        """
        if not isinstance(raw_event_data, dict) or 'price' not in raw_event_data:
            return self.get_latest_indicators()

        self._data_store.add_event(raw_event_data)
        
        # 1. Primero, se obtiene el DataFrame actual después de añadir el nuevo evento.
        current_raw_df = self._data_store.get_data()

        # 2. Si el Análisis Técnico (TA) está desactivado, se construye un diccionario con los datos básicos del tick y se sale de la función.
        if not self._config.SESSION_CONFIG["TA"]["ENABLED"]:
            calculated_indicators = {
                'timestamp': raw_event_data.get('timestamp', pd.NaT),
                'price': raw_event_data.get('price', np.nan),
                'ema': np.nan, 'weighted_increment': np.nan, 'weighted_decrement': np.nan,
                'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan,
            }
        else:
            # 3. Si el TA está activado, se intenta calcular todos los indicadores.
            try:
                calculated_indicators = _calculator.calculate_all_indicators(current_raw_df)
            except Exception as e:
                # 4. Si el cálculo falla por CUALQUIER razón, se loguea el error
                ts_str = utils.format_datetime(raw_event_data.get('timestamp'))
                memory_logger.log(f"ERROR [TAManager - Calculator Call @ {ts_str}]: {e}", level="ERROR")
                memory_logger.log(traceback.format_exc(), level="ERROR")
                return self.get_latest_indicators()
        self._latest_indicators = calculated_indicators.copy()
        return self.get_latest_indicators()
