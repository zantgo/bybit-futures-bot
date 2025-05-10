# core/strategy/raw_price_table.py
"""
Gestiona el DataFrame de precios raw para cálculos TA (v5.3).
"""
import pandas as pd
import numpy as np
import config
from core import utils

RAW_TABLE_DTYPES = { 'timestamp': 'datetime64[ns]', 'price': 'float64',
                     'increment': 'int8', 'decrement': 'int8' }
_raw_data_df = pd.DataFrame(columns=list(RAW_TABLE_DTYPES.keys())).astype(RAW_TABLE_DTYPES)

def initialize():
    """Resetea la tabla raw."""
    global _raw_data_df
    # print("[TA Raw Table] Inicializando tabla raw...") # Menos verboso
    _raw_data_df = pd.DataFrame(columns=list(RAW_TABLE_DTYPES.keys())).astype(RAW_TABLE_DTYPES)

def add_raw_event(raw_event_data: dict):
    """Añade evento raw, asegura tipos y tamaño de ventana."""
    global _raw_data_df
    if not isinstance(raw_event_data, dict): return
    try:
        data_to_add = {
            'timestamp': pd.to_datetime(raw_event_data.get('timestamp'), errors='coerce'),
            'price': utils.safe_float_convert(raw_event_data.get('price'), default=np.nan),
            'increment': int(utils.safe_float_convert(raw_event_data.get('increment', 0), default=0)),
            'decrement': int(utils.safe_float_convert(raw_event_data.get('decrement', 0), default=0)) }
        if pd.isna(data_to_add['timestamp']) or pd.isna(data_to_add['price']): return # Saltar inválidos
        new_row = pd.DataFrame([data_to_add]).astype(RAW_TABLE_DTYPES)
        _raw_data_df = pd.concat([_raw_data_df, new_row], ignore_index=True)
        if len(_raw_data_df) > config.TA_WINDOW_SIZE:
            _raw_data_df = _raw_data_df.iloc[-config.TA_WINDOW_SIZE:]
    except Exception as e: print(f"ERROR [TA Raw Table Add]: {e}")

def get_raw_data() -> pd.DataFrame:
    """Devuelve copia de la tabla raw actual."""
    return _raw_data_df.copy()