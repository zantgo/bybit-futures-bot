# core/strategy/ta_manager.py
"""
Orquesta el cálculo de Indicadores Técnicos (TA) (v5.3).
Utiliza raw_price_table y calculator.
"""
import datetime
import pandas as pd
import numpy as np
import traceback

# Importaciones relativas dentro del paquete strategy
from . import raw_price_table
from . import calculator
# from . import processed_price_table # Eliminado en v5.3

# Importaciones core absolutas
import config
from core import utils

# Caché del último resultado
_latest_indicators = {}

def initialize():
    """Inicializa el gestor de TA y sus componentes."""
    global _latest_indicators
    print("[TA Manager] Inicializando...")
    raw_price_table.initialize()
    # processed_price_table.initialize() # Eliminado
    _latest_indicators = { # Reset cache
        'timestamp': pd.NaT, 'price': np.nan, 'ema': np.nan,
        'weighted_increment': np.nan, 'weighted_decrement': np.nan,
        'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan, }
    print("[TA Manager] Inicializado.")

def process_raw_price_event(raw_event_data: dict) -> dict | None:
    """
    Procesa un evento raw para calcular y devolver indicadores TA.
    """
    global _latest_indicators
    if not isinstance(raw_event_data, dict) or 'price' not in raw_event_data: return None

    # 1. Añadir a tabla raw
    raw_price_table.add_raw_event(raw_event_data)

    # 2. Obtener datos raw actualizados
    current_raw_df = raw_price_table.get_raw_data()

    # 3. Calcular indicadores (si está habilitado)
    calculated_indicators = None
    if config.TA_CALCULATE_PROCESSED_DATA:
        try:
            calculated_indicators = calculator.calculate_indicators(current_raw_df)
        except Exception as calc_err:
            ts_str = utils.format_datetime(raw_event_data.get('timestamp'))
            print(f"ERROR [Calculator Call @ {ts_str}]: {calc_err}"); traceback.print_exc()
            calculated_indicators = { # Devolver NaNs pero con ts/price
                 'timestamp': raw_event_data.get('timestamp', pd.NaT), 'price': raw_event_data.get('price', np.nan),
                 'ema': np.nan, 'weighted_increment': np.nan, 'weighted_decrement': np.nan,
                 'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan, }
    else: # Si TA está deshabilitado
        calculated_indicators = {
            'timestamp': raw_event_data.get('timestamp', pd.NaT), 'price': raw_event_data.get('price', np.nan),
            'ema': np.nan, 'weighted_increment': np.nan, 'weighted_decrement': np.nan,
            'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan, }

    # 4. Actualizar caché
    if calculated_indicators: _latest_indicators = calculated_indicators.copy()

    # 5. Almacenar en tabla procesada (ELIMINADO en v5.3)
    # if calculated_indicators and config.TA_CALCULATE_PROCESSED_DATA:
    #     processed_price_table.add_processed_data(calculated_indicators)

    # 6. Imprimir debug (si está habilitado)
    if config.PRINT_PROCESSED_DATA_ALWAYS and calculated_indicators:
        print(f"DEBUG [TA Calculated]: {calculated_indicators}")

    # 7. Retornar resultado
    return calculated_indicators

def get_latest_indicators() -> dict:
    """Devuelve copia del último diccionario de indicadores."""
    return _latest_indicators.copy()