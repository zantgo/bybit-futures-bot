# backtest/connection/data_feeder.py
"""
Carga datos históricos y los alimenta al core event processor.
Modificado para leer CSV con formato específico: 'timestamp,price'.
"""
import traceback
import pandas as pd
import os
import time
import datetime
import numpy as np

# Importaciones del proyecto
import config
from core import utils

# --- load_and_prepare_data Function ---
def load_and_prepare_data(data_dir: str, csv_file: str, ts_col: str, price_col: str) -> pd.DataFrame | None:
    """
    Carga y prepara datos CSV históricos del formato 'timestamp,price'.
    
    Args:
        data_dir (str): El directorio donde se encuentra el archivo CSV.
        csv_file (str): El nombre del archivo CSV.
        ts_col (str): El nombre de la columna de timestamp (ej: 'timestamp').
        price_col (str): El nombre de la columna de precio (ej: 'price').
    """
    filepath = os.path.join(data_dir, csv_file)
    print(f"[Data Feeder] Cargando datos desde: {filepath}")

    if not os.path.exists(filepath):
        print(f"  ERROR: Archivo no encontrado en la ruta especificada.")
        return None
        
    try:
        # --- INICIO DE LA MODIFICACIÓN ---
        # 1. Leer el CSV. Pandas debería detectar la cabecera 'timestamp,price' automáticamente.
        #    Aseguramos que la columna de timestamp se lea como texto para un procesamiento manual robusto.
        df = pd.read_csv(filepath, dtype={ts_col: str}, low_memory=False)

        # 2. Verificar que las columnas esperadas ('timestamp' y 'price') existan.
        if ts_col not in df.columns or price_col not in df.columns:
            print(f"  ERROR: Las columnas requeridas '{ts_col}' o '{price_col}' no se encontraron en el archivo CSV.")
            print(f"  Columnas encontradas: {df.columns.tolist()}")
            return None

        # 3. Procesar la columna de timestamp.
        #    El formato '2025-07-10T07:56:38.150840' es estándar (ISO 8601), por lo que pd.to_datetime debería manejarlo sin problemas.
        df['timestamp_dt'] = pd.to_datetime(df[ts_col], errors='coerce')
        
        # Eliminar filas donde la conversión de fecha falló.
        df.dropna(subset=['timestamp_dt'], inplace=True)
        if df.empty:
            print("  ERROR: No se encontraron timestamps válidos después de la conversión.")
            return None

        # 4. Procesar la columna de precio.
        df['price_numeric'] = pd.to_numeric(df[price_col], errors='coerce')

        # Eliminar filas donde la conversión de precio falló.
        df.dropna(subset=['price_numeric'], inplace=True)
        if df.empty:
            print("  ERROR: No se encontraron precios válidos después de la conversión.")
            return None

        # 5. Preparar el DataFrame final para el backtest.
        #    Seleccionamos las columnas procesadas, las renombramos si es necesario,
        #    y establecemos el timestamp como índice.
        df_prepared = df[['timestamp_dt', 'price_numeric']].copy()
        df_prepared.rename(columns={'timestamp_dt': 'timestamp', 'price_numeric': 'price'}, inplace=True)
        df_prepared.set_index('timestamp', inplace=True)
        df_prepared.sort_index(inplace=True) # Asegurar orden cronológico

        # --- FIN DE LA MODIFICACIÓN ---

        print(f"  Datos preparados: {len(df_prepared)} filas, con índice Datetime.")
        return df_prepared

    except Exception as e:
        print(f"  ERROR cargando o preparando los datos: {e}")
        traceback.print_exc()
        return None

# --- run_backtest Function ---
def run_backtest(historical_data_df: pd.DataFrame, callback: callable):
    """
    Itera sobre datos históricos y llama al callback (core event processor).
    Esta función ya está adaptada para un DataFrame con DatetimeIndex.
    """
    if historical_data_df is None or historical_data_df.empty:
        print("[Backtest Runner] No hay datos para procesar.")
        return
    if not callable(callback):
        print("[Backtest Runner] Error: Callback no es una función válida.")
        return

    print(f"\n--- Iniciando Backtest ({len(historical_data_df)} intervalos) ---")
    start_time = time.time()
    total_rows = len(historical_data_df)
    error_count = 0
    print_interval = max(1, total_rows // 20)

    # itertuples() en un DataFrame con DatetimeIndex devolverá el timestamp como `row.Index`
    for i, row in enumerate(historical_data_df.itertuples(index=True)):
        row_ts = row.Index # El índice es el objeto Timestamp
        row_price = getattr(row, 'price', np.nan)

        if pd.isna(row_ts) or pd.isna(row_price):
            error_count += 1
            continue

        intermediate_ticks_info = []
        final_price_info = {
            "timestamp": row_ts,
            "price": float(row_price),
            "symbol": config.TICKER_SYMBOL
        }

        if (i + 1) % print_interval == 0 or i == total_rows - 1:
            progress_percent = ((i + 1) / total_rows) * 100
            print(f"\r[Backtest Runner] Procesando: {i + 1}/{total_rows} ({progress_percent:.1f}%)", end="")

        try:
            callback(intermediate_ticks_info, final_price_info)
        except Exception as e:
            ts_str = utils.format_datetime(row_ts) if utils else str(row_ts)
            print(f"\nERROR en callback (Índice {i}, TS: {ts_str}): {e}")
            traceback.print_exc()
            error_count += 1
            # break # Descomentar para detener en el primer error

    print(f"\n--- Backtest Finalizado ({error_count} errores encontrados) ---")
    print(f"Tiempo total: {time.time() - start_time:.2f} segundos")