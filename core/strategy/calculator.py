
# core/strategy/calculator.py
"""
Realiza cálculos de indicadores técnicos (EMA, WMA, PctChange) (v5.3).
"""
import pandas as pd
import numpy as np
import warnings
import config

# --- Funciones Helper WMA ---
def _calcular_pesos_ponderados(largo: int) -> np.ndarray:
    if largo <= 0: return np.array([])
    return np.arange(1, largo + 1)

def _weighted_avg(x: np.ndarray, pesos: np.ndarray) -> float:
    # (Misma implementación que en v5.1/v5.2)
    if not isinstance(x, np.ndarray): x = np.array(x)
    if len(x) == 0 or len(pesos) == 0: return np.nan
    current_pesos = pesos[:len(x)] # Asegurar coincidencia de longitud
    valid_indices = ~np.isnan(x); x_valid = x[valid_indices]; pesos_valid = current_pesos[valid_indices]
    if len(x_valid) == 0: return np.nan
    sum_weights_valid = np.sum(pesos_valid)
    if sum_weights_valid == 0: return np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        try: wma = np.dot(x_valid, pesos_valid) / sum_weights_valid; return wma if np.isfinite(wma) else np.nan
        except Exception: return np.nan

# --- Función Principal de Cálculo ---
def calculate_indicators(raw_df: pd.DataFrame) -> dict:
    """Calcula indicadores técnicos basados en el DataFrame raw."""
    latest_indicators = { # Inicializar con NaN/NaT
        'timestamp': raw_df['timestamp'].iloc[-1] if not raw_df.empty else pd.NaT,
        'price': raw_df['price'].iloc[-1] if not raw_df.empty else np.nan,
        'ema': np.nan, 'weighted_increment': np.nan, 'weighted_decrement': np.nan,
        'inc_price_change_pct': np.nan, 'dec_price_change_pct': np.nan, }
    if raw_df.empty or len(raw_df) < 2: return latest_indicators # Necesita >= 2 puntos

    # --- Cálculo EMA ---
    ema_window = config.TA_EMA_WINDOW
    if len(raw_df) >= ema_window:
        try:
            ema_series = raw_df['price'].ewm(span=ema_window, adjust=False, min_periods=ema_window).mean()
            last_valid_ema = ema_series.iloc[-1]
            if pd.notna(last_valid_ema) and np.isfinite(last_valid_ema): latest_indicators['ema'] = last_valid_ema
        except Exception: pass # Mantener NaN si falla

    # --- Cálculo WMA Incremento y Pct Change ---
    inc_window_size = config.TA_WEIGHTED_INC_WINDOW
    if len(raw_df) >= inc_window_size:
        # WMA
        inc_slice = raw_df['increment'].iloc[-inc_window_size:].to_numpy()
        pesos_inc = _calcular_pesos_ponderados(inc_window_size)
        latest_indicators['weighted_increment'] = _weighted_avg(inc_slice, pesos_inc)
        # Pct Change
        price_slice_inc = raw_df['price'].iloc[-inc_window_size:]
        current_p_inc = price_slice_inc.iloc[-1]; old_p_inc = price_slice_inc.iloc[0]
        if pd.notna(current_p_inc) and pd.notna(old_p_inc) and np.isfinite(current_p_inc) and np.isfinite(old_p_inc):
            if old_p_inc != 0: change = ((current_p_inc - old_p_inc) / abs(old_p_inc)) * 100.0; latest_indicators['inc_price_change_pct'] = change if np.isfinite(change) else np.nan
            elif current_p_inc == 0: latest_indicators['inc_price_change_pct'] = 0.0
            else: latest_indicators['inc_price_change_pct'] = np.inf

    # --- Cálculo WMA Decremento y Pct Change ---
    dec_window_size = config.TA_WEIGHTED_DEC_WINDOW
    if len(raw_df) >= dec_window_size:
        # WMA
        dec_slice = raw_df['decrement'].iloc[-dec_window_size:].to_numpy()
        pesos_dec = _calcular_pesos_ponderados(dec_window_size)
        latest_indicators['weighted_decrement'] = _weighted_avg(dec_slice, pesos_dec)
        # Pct Change
        price_slice_dec = raw_df['price'].iloc[-dec_window_size:]
        current_p_dec = price_slice_dec.iloc[-1]; old_p_dec = price_slice_dec.iloc[0]
        if pd.notna(current_p_dec) and pd.notna(old_p_dec) and np.isfinite(current_p_dec) and np.isfinite(old_p_dec):
            if old_p_dec != 0: change = ((current_p_dec - old_p_dec) / abs(old_p_dec)) * 100.0; latest_indicators['dec_price_change_pct'] = change if np.isfinite(change) else np.nan
            elif current_p_dec == 0: latest_indicators['dec_price_change_pct'] = 0.0
            else: latest_indicators['dec_price_change_pct'] = np.inf

    return latest_indicators