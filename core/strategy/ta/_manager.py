# core/strategy/ta/_manager.py

"""
Módulo Gestor de Análisis Técnico (TA Manager).

Su única responsabilidad es orquestar el flujo de datos para el análisis técnico:
1. Recibe eventos de precios crudos.
2. Utiliza `_data_store` para almacenar los datos.
3. Utiliza `_calculator` para procesar los datos y obtener indicadores.
4. Mantiene una caché con los últimos indicadores calculados para un acceso rápido.
"""
import pandas as pd
import numpy as np
import traceback

# Dependencias del proyecto
import config
from core import utils
from core.logging import memory_logger # Importar el logger
from . import _data_store
from . import _calculator

# --- Estado del Módulo (Privado) ---

# Caché para el último conjunto de indicadores calculados
_latest_indicators = {}

# --- Interfaz del Módulo (Funciones Públicas) ---

def initialize():
    """
    Inicializa el gestor de TA, reseteando el almacén de datos y la caché interna.
    """
    global _latest_indicators
    print("[TA Manager] Inicializando...")
    _data_store.initialize()
    _latest_indicators = {
        'timestamp': pd.NaT, 'price': np.nan, 'ema': np.nan,
        'weighted_increment': np.nan, 'weighted_decrement': np.nan,
        'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan,
    }
    print("[TA Manager] Inicializado.")

def process_raw_price_event(raw_event_data: dict) -> dict:
    """
    Procesa un único evento de precio crudo, actualiza el almacén de datos,
    recalcula los indicadores y actualiza la caché.

    Args:
        raw_event_data (dict): Un diccionario con los datos del tick de precio.

    Returns:
        dict: El conjunto más reciente de indicadores calculados.
    """
    global _latest_indicators
    if not isinstance(raw_event_data, dict) or 'price' not in raw_event_data:
        return _latest_indicators.copy()

    # 1. Almacenar el nuevo evento
    _data_store.add_event(raw_event_data)

    # 2. Obtener la ventana de datos actualizada
    current_raw_df = _data_store.get_data()

    # 3. Calcular los nuevos indicadores
    calculated_indicators = {}
    if getattr(config, 'TA_CALCULATE_PROCESSED_DATA', True):
        try:
            calculated_indicators = _calculator.calculate_all_indicators(current_raw_df)
        except Exception as e:
            ts_str = utils.format_datetime(raw_event_data.get('timestamp'))
            memory_logger.log(f"ERROR [TA Manager - Calculator Call @ {ts_str}]: {e}", level="ERROR")
            memory_logger.log(traceback.format_exc(), level="ERROR")

            # En caso de error, devolver los datos base sin indicadores
            calculated_indicators = {
                'timestamp': raw_event_data.get('timestamp', pd.NaT),
                'price': raw_event_data.get('price', np.nan),
                'ema': np.nan, 'weighted_increment': np.nan, 'weighted_decrement': np.nan,
                'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan,
            }
    else:
        # Si el cálculo está desactivado, solo devolver los datos base
        calculated_indicators = {
            'timestamp': raw_event_data.get('timestamp', pd.NaT),
            'price': raw_event_data.get('price', np.nan),
            'ema': np.nan, 'weighted_increment': np.nan, 'weighted_decrement': np.nan,
            'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan,
        }

    # 4. Actualizar la caché interna
    _latest_indicators = calculated_indicators.copy()

    # 5. Opcional: Imprimir datos para depuración
    if getattr(config, 'PRINT_PROCESSED_DATA_ALWAYS', False):
        print(f"DEBUG [TA Calculated]: {_latest_indicators}")

    return _latest_indicators.copy()

def get_latest_indicators() -> dict:
    """
    Devuelve una copia del último conjunto de indicadores almacenado en caché.
    """
    return _latest_indicators.copy()