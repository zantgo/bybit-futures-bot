"""
Paquete unificado para la gestión y cálculo de Indicadores Técnicos (TA) (v5.3).

Este __init__.py consolida la lógica que originalmente estaba en:
- ta_manager.py: Orquestador principal.
- calculator.py: Lógica de cálculo de indicadores.
- raw_price_table.py: Gestión de la tabla de datos en memoria.

La interfaz pública de este paquete la componen las funciones:
- initialize()
- process_raw_price_event()
- get_latest_indicators()
"""
# --- Bloque de Importaciones Unificadas ---
import datetime
import pandas as pd
import numpy as np
import traceback
import warnings

# --- Importaciones de la aplicación (asumiendo que 'config' y 'core' son accesibles) ---
import config as config
from core import _utils

# --- Definición de la Interfaz Pública del Paquete ---
__all__ = ['initialize', 'process_raw_price_event', 'get_latest_indicators']

# --- Sección: Lógica de 'raw_price_table.py' (Internalizada) ---

# Constantes y estado de la tabla raw
RAW_TABLE_DTYPES = { 'timestamp': 'datetime64[ns]', 'price': 'float64',
                     'increment': 'int8', 'decrement': 'int8' }
_raw_data_df = pd.DataFrame(columns=list(RAW_TABLE_DTYPES.keys())).astype(RAW_TABLE_DTYPES)

def _initialize_raw_table():
    """Resetea la tabla raw. (Original de raw_price_table.initialize)"""
    global _raw_data_df
    _raw_data_df = pd.DataFrame(columns=list(RAW_TABLE_DTYPES.keys())).astype(RAW_TABLE_DTYPES)

def _add_raw_event(raw_event_data: dict):
    """Añade evento raw, asegura tipos y tamaño de ventana. (Original de raw_price_table.add_raw_event)"""
    global _raw_data_df
    if not isinstance(raw_event_data, dict): return
    try:
        data_to_add = {
            'timestamp': pd.to_datetime(raw_event_data.get('timestamp'), errors='coerce'),
            'price': _utils.safe_float_convert(raw_event_data.get('price'), default=np.nan),
            'increment': int(_utils.safe_float_convert(raw_event_data.get('increment', 0), default=0)),
            'decrement': int(_utils.safe_float_convert(raw_event_data.get('decrement', 0), default=0)) }
        if pd.isna(data_to_add['timestamp']) or pd.isna(data_to_add['price']): return # Saltar inválidos
        new_row = pd.DataFrame([data_to_add]).astype(RAW_TABLE_DTYPES)
        _raw_data_df = pd.concat([_raw_data_df, new_row], ignore_index=True)
        if len(_raw_data_df) > config.TA_WINDOW_SIZE:
            _raw_data_df = _raw_data_df.iloc[-config.TA_WINDOW_SIZE:]
    except Exception as e: print(f"ERROR [TA Raw Table Add]: {e}")

def _get_raw_data() -> pd.DataFrame:
    """Devuelve copia de la tabla raw actual. (Original de raw_price_table.get_raw_data)"""
    return _raw_data_df.copy()


# --- Sección: Lógica de 'calculator.py' (Internalizada) ---

# Funciones Helper WMA (privadas por naturaleza)
def _calcular_pesos_ponderados(largo: int) -> np.ndarray:
    if largo <= 0: return np.array([])
    return np.arange(1, largo + 1)

def _weighted_avg(x: np.ndarray, pesos: np.ndarray) -> float:
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

# Función Principal de Cálculo (internalizada)
def _calculate_indicators(raw_df: pd.DataFrame) -> dict:
    """Calcula indicadores técnicos basados en el DataFrame raw. (Original de calculator.calculate_indicators)"""
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


# --- Sección: Lógica de 'ta_manager.py' (Interfaz Pública del Paquete) ---

# Caché del último resultado para el manager
_latest_indicators = {}

def initialize():
    """Inicializa el gestor de TA y sus componentes."""
    global _latest_indicators
    print("[TA Manager] Inicializando...")
    _initialize_raw_table()  # Llama a la función internalizada
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

    # 1. Añadir a tabla raw (usando la función internalizada)
    _add_raw_event(raw_event_data)

    # 2. Obtener datos raw actualizados (usando la función internalizada)
    current_raw_df = _get_raw_data()

    # 3. Calcular indicadores (si está habilitado, usando la función internalizada)
    calculated_indicators = None
    if config.TA_CALCULATE_PROCESSED_DATA:
        try:
            calculated_indicators = _calculate_indicators(current_raw_df)
        except Exception as calc_err:
            ts_str = _utils.format_datetime(raw_event_data.get('timestamp'))
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

    # 5. Imprimir debug (si está habilitado)
    if config.PRINT_PROCESSED_DATA_ALWAYS and calculated_indicators:
        print(f"DEBUG [TA Calculated]: {calculated_indicators}")

    # 6. Retornar resultado
    return calculated_indicators

def get_latest_indicators() -> dict:
    """Devuelve copia del último diccionario de indicadores."""
    return _latest_indicators.copy()