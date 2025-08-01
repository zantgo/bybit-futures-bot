# core/strategy/ta/_manager.py

import pandas as pd
import numpy as np
import traceback
from typing import Dict, Any

# Dependencias del proyecto
import config
from core import utils
from core.logging import memory_logger
from ._data_store import DataStore  # Importar la nueva clase
from . import _calculator

class TAManager:
    """
    Orquesta el flujo de Análisis Técnico. Mantiene un almacén de datos y
    utiliza un calculador para generar indicadores. Cada instancia es independiente.
    """

    def __init__(self):
        """
        Inicializa el TAManager, creando su propio DataStore y
        estableciendo su estado inicial.
        """
        # El TAManager ahora es dueño de su propio DataStore
        self._data_store = DataStore()
        
        # El estado (caché de indicadores) ahora es un atributo de la instancia
        self._latest_indicators = {}
        
        # Inicializar al crear la instancia para asegurar un estado válido
        self.initialize()

    def initialize(self):
        """
        Inicializa o resetea el estado del gestor para una nueva sesión,
        limpiando el almacén de datos y la caché de indicadores.
        """
        print("[TAManager] Inicializando...")
        self._data_store.initialize()
        self._latest_indicators = {
            'timestamp': pd.NaT, 'price': np.nan, 'ema': np.nan,
            'weighted_increment': np.nan, 'weighted_decrement': np.nan,
            'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan,
        }
        print("[TAManager] Inicializado.")

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

        # 1. Almacenar el nuevo evento usando la instancia de DataStore
        self._data_store.add_event(raw_event_data)

        # 2. Obtener la ventana de datos actualizada del DataStore
        current_raw_df = self._data_store.get_data()

        # 3. Calcular los nuevos indicadores si está habilitado
        calculated_indicators = {}
        if getattr(config, 'TA_CALCULATE_PROCESSED_DATA', True):
            try:
                # Utiliza el módulo _calculator para procesar el DataFrame
                calculated_indicators = _calculator.calculate_all_indicators(current_raw_df)
            except Exception as e:
                ts_str = utils.format_datetime(raw_event_data.get('timestamp'))
                memory_logger.log(f"ERROR [TAManager - Calculator Call @ {ts_str}]: {e}", level="ERROR")
                memory_logger.log(traceback.format_exc(), level="ERROR")

                # En caso de error, devolver los datos base sin indicadores calculados
                calculated_indicators = {
                    'timestamp': raw_event_data.get('timestamp', pd.NaT),
                    'price': raw_event_data.get('price', np.nan),
                    'ema': np.nan, 'weighted_increment': np.nan, 'weighted_decrement': np.nan,
                    'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan,
                }
        else:
            # Si el cálculo está desactivado, solo devolver los datos base del evento
            calculated_indicators = {
                'timestamp': raw_event_data.get('timestamp', pd.NaT),
                'price': raw_event_data.get('price', np.nan),
                'ema': np.nan, 'weighted_increment': np.nan, 'weighted_decrement': np.nan,
                'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan,
            }

        # 4. Actualizar la caché interna con los nuevos resultados
        self._latest_indicators = calculated_indicators.copy()

        # 5. Opcional: Imprimir datos para depuración si está activado en config
        if getattr(config, 'PRINT_PROCESSED_DATA_ALWAYS', False):
            print(f"DEBUG [TA Calculated]: {self._latest_indicators}")

        return self.get_latest_indicators()

    def get_latest_indicators(self) -> dict:
        """
        Devuelve una copia del último conjunto de indicadores almacenado en caché.
        Es seguro de usar ya que devuelve una copia, no una referencia.
        """
        return self._latest_indicators.copy()