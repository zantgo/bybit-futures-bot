# backtest/connection/data_feeder.py
"""
Carga datos históricos y los alimenta al core event processor (v5.3).
"""
import traceback
import pandas as pd
import os
import time
import datetime
import numpy as np # Para NaN

import config
from core import utils

# --- load_and_prepare_data Function ---
def load_and_prepare_data(data_dir: str, csv_file: str, ts_col: str, price_col: str) -> pd.DataFrame | None:
    """Carga y prepara datos CSV históricos."""
    filepath = os.path.join(data_dir, csv_file)
    print(f"[Data Feeder] Cargando datos desde: {filepath}")
    if not os.path.exists(filepath): print(f"  ERROR: Archivo no encontrado."); return None
    try:
        df = pd.read_csv(filepath, dtype={ts_col: str}, low_memory=False)
        if ts_col not in df.columns or price_col not in df.columns: print(f" ERROR: Columnas '{ts_col}' o '{price_col}' no encontradas."); return None
        
        # Convertir la columna de timestamp a objetos datetime
        df['timestamp'] = pd.to_datetime(df[ts_col], errors='coerce')
        df.dropna(subset=['timestamp'], inplace=True)
        if df.empty: print(" ERROR: No hay timestamps válidos."); return None
        
        # Renombrar y convertir la columna de precio
        df.rename(columns={price_col: 'price'}, inplace=True)
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df.dropna(subset=['price'], inplace=True)
        if df.empty: print(" ERROR: No hay precios válidos."); return None
        
        # <<< INICIO DE LA CORRECCIÓN >>>
        # Preparar el DataFrame final con 'timestamp' como índice
        df_prepared = df[['timestamp', 'price']].copy()
        df_prepared.set_index('timestamp', inplace=True)
        df_prepared.sort_index(inplace=True) # Asegurar que esté ordenado cronológicamente
        # <<< FIN DE LA CORRECCIÓN >>>

        print(f"  Datos preparados: {len(df_prepared)} filas, con índice Datetime.")
        return df_prepared
        
    except Exception as e: print(f"  ERROR cargando/preparando datos: {e}"); traceback.print_exc(); return None

# --- run_backtest Function ---
def run_backtest(historical_data_df: pd.DataFrame, callback: callable):
    """Itera sobre datos históricos y llama al callback (core event processor)."""
    if historical_data_df is None or historical_data_df.empty: print("[Backtest Runner] No hay datos."); return
    if not callable(callback): print("[Backtest Runner] Error: Callback inválido."); return

    print(f"\n--- Iniciando Backtest ({len(historical_data_df)} intervalos) ---")
    start_time = time.time(); total_rows = len(historical_data_df); error_count = 0; print_interval = max(1, total_rows // 20) # Imprimir progreso ~20 veces

    # itertuples ahora devolverá el índice (timestamp) como el primer elemento
    for index, row in enumerate(historical_data_df.itertuples(index=True)):
        # <<< CORRECCIÓN: el timestamp es ahora el primer elemento de la tupla `row` >>>
        row_ts = row[0]  # El índice Datetime
        row_price = getattr(row, 'price', np.nan)
        
        if pd.isna(row_ts) or pd.isna(row_price): error_count+=1; continue # Saltar filas inválidas

        # Preparar datos para el callback del core event processor
        intermediate_ticks_info = []
        final_price_info = { "timestamp": row_ts, "price": float(row_price), "symbol": config.TICKER_SYMBOL }

        # Imprimir progreso
        if (index + 1) % print_interval == 0 or index == total_rows - 1:
            progress_percent = ((index + 1) / total_rows) * 100
            print(f"\r[Backtest Runner] Procesando: {index + 1}/{total_rows} ({progress_percent:.1f}%)", end="")

        # Llamar al core event processor
        try: callback(intermediate_ticks_info, final_price_info)
        except Exception as e:
            print(f"\nERROR en callback (Índice {index}, TS: {utils.format_datetime(row_ts)}): {e}"); traceback.print_exc(); error_count += 1

    # Finalizar
    print(); print(f"--- Backtest Finalizado ({error_count} errores encontrados) ---")
    print(f"Tiempo total: {time.time() - start_time:.2f} segundos")