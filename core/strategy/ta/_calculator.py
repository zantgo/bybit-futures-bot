# core/strategy/ta/_calculator.py

"""
Módulo de Cálculo de Indicadores Técnicos.

Su única responsabilidad es contener funciones puras que toman datos de mercado
(en forma de DataFrame) y devuelven indicadores técnicos calculados.
Este módulo no mantiene ningún estado.
"""
import pandas as pd
import numpy as np
import warnings
from typing import Dict

# Dependencias del proyecto
import config

# --- Funciones de Ayuda para Cálculos (Privadas) ---

def _calculate_weighted_moving_average(series: np.ndarray, window_size: int) -> float:
    """Calcula la Media Móvil Ponderada para una serie de datos."""
    if len(series) < window_size:
        return np.nan
    
    weights = np.arange(1, window_size + 1)
    
    # Ignorar NaNs en el cálculo para robustez
    valid_indices = ~np.isnan(series)
    series_valid = series[valid_indices]
    weights_valid = weights[-len(series_valid):] # Alinea los pesos con los datos válidos

    if len(series_valid) == 0 or np.sum(weights_valid) == 0:
        return np.nan
        
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        try:
            wma = np.dot(series_valid, weights_valid) / np.sum(weights_valid)
            return wma if np.isfinite(wma) else np.nan
        except Exception:
            return np.nan

# --- Función Principal de Cálculo (Pública) ---

def calculate_all_indicators(raw_df: pd.DataFrame) -> Dict[str, any]:
    """
    Calcula todos los indicadores técnicos requeridos a partir de un DataFrame de datos crudos.
    
    Args:
        raw_df (pd.DataFrame): DataFrame con columnas 'timestamp', 'price', 'increment', 'decrement'.

    Returns:
        dict: Un diccionario con los últimos valores de todos los indicadores calculados.
    """
    # Inicializar diccionario de resultados con valores por defecto
    latest_indicators = {
        'timestamp': raw_df['timestamp'].iloc[-1] if not raw_df.empty else pd.NaT,
        'price': raw_df['price'].iloc[-1] if not raw_df.empty else np.nan,
        'ema': np.nan,
        'weighted_increment': np.nan,
        'weighted_decrement': np.nan,
        'inc_price_change_pct': np.nan,
        'dec_price_change_pct': np.nan,
    }

    if raw_df.empty or len(raw_df) < 2:
        return latest_indicators

    # --- INICIO DE LA CORRECCIÓN ---
    ta_config = config.SESSION_CONFIG["TA"]
    # --- FIN DE LA CORRECCIÓN ---

    # --- 1. Cálculo de la EMA (Exponential Moving Average) ---
    ema_window = ta_config["EMA_WINDOW"]
    if len(raw_df) >= ema_window:
        try:
            ema_series = raw_df['price'].ewm(span=ema_window, adjust=False, min_periods=ema_window).mean()
            last_valid_ema = ema_series.iloc[-1]
            if pd.notna(last_valid_ema) and np.isfinite(last_valid_ema):
                latest_indicators['ema'] = last_valid_ema
        except Exception:
            pass # Mantener NaN si el cálculo falla

    # --- 2. Cálculo del Incremento Ponderado y su Cambio de Precio ---
    inc_window = ta_config["WEIGHTED_INC_WINDOW"]
    if len(raw_df) >= inc_window:
        inc_series = raw_df['increment'].iloc[-inc_window:].to_numpy()
        latest_indicators['weighted_increment'] = _calculate_weighted_moving_average(inc_series, inc_window)
        
        price_slice = raw_df['price'].iloc[-inc_window:]
        old_price, current_price = price_slice.iloc[0], price_slice.iloc[-1]
        if pd.notna(current_price) and pd.notna(old_price) and old_price != 0:
            change = ((current_price - old_price) / abs(old_price)) * 100.0
            latest_indicators['inc_price_change_pct'] = change if np.isfinite(change) else np.nan
        elif old_price == 0 and current_price != 0:
            latest_indicators['inc_price_change_pct'] = np.inf
        else:
            latest_indicators['inc_price_change_pct'] = 0.0

    # --- 3. Cálculo del Decremento Ponderado y su Cambio de Precio ---
    dec_window = ta_config["WEIGHTED_DEC_WINDOW"]
    if len(raw_df) >= dec_window:
        dec_series = raw_df['decrement'].iloc[-dec_window:].to_numpy()
        latest_indicators['weighted_decrement'] = _calculate_weighted_moving_average(dec_series, dec_window)

        price_slice = raw_df['price'].iloc[-dec_window:]
        old_price, current_price = price_slice.iloc[0], price_slice.iloc[-1]
        if pd.notna(current_price) and pd.notna(old_price) and old_price != 0:
            change = ((current_price - old_price) / abs(old_price)) * 100.0
            latest_indicators['dec_price_change_pct'] = change if np.isfinite(change) else np.nan
        elif old_price == 0 and current_price != 0:
            latest_indicators['dec_price_change_pct'] = np.inf
        else:
            latest_indicators['dec_price_change_pct'] = 0.0

    return latest_indicators