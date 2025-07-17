# =============== INICIO ARCHIVO: core/visualization/plotter.py (v6.3 - Con Sombreado de Tendencia) ===============
"""
Genera un gráfico a partir de datos históricos y logs.
v6.3:
- Aumentado el tamaño del gráfico para mejor legibilidad.
- Añadida la función `axvspan` para sombrear el fondo del gráfico según la
  tendencia (LONG_ONLY, SHORT_ONLY) registrada en un nuevo log de estados.
v6.2.2:
- Grafica precio, EMA, señales BUY/SELL, y marcadores de apertura/cierre.
- AJUSTADO para manejar mejor escalas de precios con alta precisión decimal y formato Y explícito.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import ScalarFormatter, FormatStrFormatter # Importar FormatStrFormatter
import json
import os
import traceback
import sys
from typing import Optional # Asegurar que está importado

# Importar módulos core necesarios de forma segura
try:
    # Asumiendo que este módulo está en core/visualization/
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import config
    from core import utils
except ImportError:
    print("ERROR CRITICO [Plotter Import]: No se pudo importar config o utils.")
    # Crear dummies para permitir que el script se cargue parcialmente
    config = type('obj', (object,), {'TA_EMA_WINDOW': 20, 'TICKER_SYMBOL': 'N/A'})()
    utils = type('obj', (object,), {'safe_float_convert': float})()


# --- Función para cargar Log de Señales ---
def load_signal_log(log_filepath: str) -> pd.DataFrame:
    """Carga el log de señales (JSON Lines) en un DataFrame."""
    print(f"[Plotter] Cargando log de señales desde: {os.path.basename(log_filepath)}")
    data = []
    try:
        with open(log_filepath, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f):
                try:
                    if not line.strip(): continue
                    signal_event = json.loads(line)
                    data.append(signal_event)
                except json.JSONDecodeError as json_err:
                    print(f"  Advertencia [Signals Log]: Ignorando línea #{line_number + 1} inválida: {json_err}")
                    continue
        if not data:
            print(f"  Advertencia [Signals Log]: No se encontraron datos JSON válidos.")
            return pd.DataFrame()

        df_signals = pd.DataFrame(data)
        if 'timestamp' not in df_signals.columns or 'signal' not in df_signals.columns:
             print("  Error [Signals Log]: Columnas 'timestamp' o 'signal' no encontradas.")
             return pd.DataFrame()

        df_signals['timestamp_dt'] = pd.to_datetime(df_signals['timestamp'], errors='coerce')
        df_signals.dropna(subset=['timestamp_dt'], inplace=True)
        if df_signals.empty:
             print("  Advertencia [Signals Log]: No hay timestamps válidos.")
             return pd.DataFrame()
        df_signals.set_index('timestamp_dt', inplace=True); df_signals.sort_index(inplace=True)

        if 'price_float' in df_signals.columns:
            df_signals['price_float'] = df_signals['price_float'].replace(['NaN', 'Inf', '-Inf', np.nan, np.inf, -np.inf], np.nan)
            df_signals['price_float'] = pd.to_numeric(df_signals['price_float'], errors='coerce')
        else:
            print("  Advertencia [Signals Log]: Columna 'price_float' no encontrada.")
            df_signals['price_float'] = np.nan

        df_signals_plot = df_signals[df_signals['signal'].isin(['BUY', 'SELL'])].copy()
        df_signals_plot.dropna(subset=['price_float'], inplace=True)

        print(f"  Log de Señales procesado: {len(df_signals_plot)} señales BUY/SELL con precio válido para plotear.")
        return df_signals_plot

    except FileNotFoundError:
        print(f"  Advertencia [Signals Log]: Archivo no encontrado: {os.path.basename(log_filepath)}")
        return pd.DataFrame()
    except Exception as e:
        print(f"  ERROR [Signals Log]: Error inesperado: {e}")
        traceback.print_exc()
        return pd.DataFrame()

# --- Función para cargar Log de Posiciones Cerradas ---
def load_closed_positions_log(log_filepath: str) -> pd.DataFrame:
    """Carga el log de posiciones cerradas (JSON Lines) en un DataFrame."""
    print(f"[Plotter] Cargando log de posiciones cerradas desde: {os.path.basename(log_filepath)}")
    data = []
    required_cols = ['side', 'entry_timestamp', 'exit_timestamp', 'entry_price', 'exit_price']
    try:
        with open(log_filepath, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f):
                try:
                    if not line.strip(): continue
                    closed_pos = json.loads(line)
                    if all(col in closed_pos for col in required_cols):
                        data.append(closed_pos)
                except json.JSONDecodeError as json_err:
                    print(f"  Advertencia [Closed Pos Log]: Ignorando línea #{line_number + 1} inválida: {json_err}")
                    continue
        if not data:
            print(f"  Advertencia [Closed Pos Log]: No se encontraron datos JSON válidos o completos.")
            return pd.DataFrame()

        df_closed = pd.DataFrame(data)

        df_closed['entry_timestamp_dt'] = pd.to_datetime(df_closed['entry_timestamp'], errors='coerce')
        df_closed['exit_timestamp_dt'] = pd.to_datetime(df_closed['exit_timestamp'], errors='coerce')
        df_closed['entry_price'] = pd.to_numeric(df_closed['entry_price'], errors='coerce')
        df_closed['exit_price'] = pd.to_numeric(df_closed['exit_price'], errors='coerce')

        df_closed.dropna(subset=['side', 'entry_timestamp_dt', 'exit_timestamp_dt', 'entry_price', 'exit_price'], inplace=True)

        if df_closed.empty:
             print("  Advertencia [Closed Pos Log]: No hay datos válidos para plotear después del procesamiento.")
             return pd.DataFrame()

        df_closed = df_closed[df_closed['side'].isin(['long', 'short'])].copy()

        print(f"  Log de Posiciones Cerradas procesado: {len(df_closed)} posiciones válidas para plotear.")
        return df_closed

    except FileNotFoundError:
        print(f"  Info [Closed Pos Log]: Archivo no encontrado: {os.path.basename(log_filepath)} (Puede ser normal).")
        return pd.DataFrame()
    except Exception as e:
        print(f"  ERROR [Closed Pos Log]: Error inesperado: {e}")
        traceback.print_exc()
        return pd.DataFrame()

# --- Nueva Función para Cargar Log de Estados ---
def load_state_changes_log(log_filepath: str) -> list:
    """Carga el log de cambios de estado (JSON) en una lista de diccionarios."""
    print(f"[Plotter] Cargando log de cambios de estado desde: {os.path.basename(log_filepath)}")
    try:
        with open(log_filepath, 'r', encoding='utf-8') as f:
            state_changes = json.load(f)
        
        # Convertir timestamps a objetos datetime
        for change in state_changes:
            change['timestamp'] = pd.to_datetime(change['timestamp'])
        
        print(f"  Log de Estados procesado: {len(state_changes)} cambios de estado encontrados.")
        return state_changes
    except FileNotFoundError:
        print(f"  Info [State Log]: Archivo no encontrado: {os.path.basename(log_filepath)} (Normal si no es backtest automático).")
        return []
    except Exception as e:
        print(f"  ERROR [State Log]: Error inesperado: {e}")
        traceback.print_exc()
        return []

# --- Función Principal de Ploteo ---
def plot_signals_and_price(
    historical_data_df: pd.DataFrame,
    signal_log_filepath: str,
    closed_positions_log_filepath: Optional[str],
    output_filepath: str,
    state_changes_log_filepath: Optional[str] = None
):
    """
    Genera gráfico combinando precio, EMA, señales, posiciones y sombreado de tendencia.
    """
    print("\n--- Iniciando Generación de Gráfico (v6.3 - Con Sombreado de Tendencia) ---")

    # 1. Validar y Preparar Datos Históricos
    if historical_data_df is None or historical_data_df.empty:
        print("[Plotter Error] Datos históricos inválidos."); return
    if 'price' not in historical_data_df.columns:
        print("[Plotter Error] Columna 'price' no encontrada en datos históricos."); return
    historical_data_df['price'] = pd.to_numeric(historical_data_df['price'], errors='coerce')
    historical_data_df.dropna(subset=['price'], inplace=True)
    if historical_data_df.empty:
        print("[Plotter Error] No hay datos históricos válidos después de limpiar precios."); return

    if not isinstance(historical_data_df.index, pd.DatetimeIndex):
        if 'timestamp' in historical_data_df.columns:
             try:
                 historical_data_df['timestamp'] = pd.to_datetime(historical_data_df['timestamp'], errors='raise')
                 historical_data_df = historical_data_df.set_index('timestamp')
                 historical_data_df.sort_index(inplace=True)
                 print("[Plotter Info] Índice Datetime establecido para datos históricos.")
             except Exception as e:
                  print(f"[Plotter Error] No se pudo convertir/establecer índice Datetime: {e}"); return
        else:
            print("[Plotter Error] Datos históricos sin índice/columna Datetime."); return
    else:
        historical_data_df.sort_index(inplace=True)

    # 2. Cargar Logs
    df_signals = load_signal_log(signal_log_filepath)
    df_closed_positions = pd.DataFrame()
    if closed_positions_log_filepath and os.path.exists(closed_positions_log_filepath):
         df_closed_positions = load_closed_positions_log(closed_positions_log_filepath)
    
    state_changes = []
    if state_changes_log_filepath and os.path.exists(state_changes_log_filepath):
        state_changes = load_state_changes_log(state_changes_log_filepath)

    # 3. Calcular EMA
    ema_window = getattr(config, 'TA_EMA_WINDOW', 20)
    print(f"[Plotter Info] Calculando EMA({ema_window})...")
    try:
        if len(historical_data_df) >= ema_window:
            historical_data_df['EMA'] = historical_data_df['price'].ewm(span=ema_window, adjust=False, min_periods=ema_window).mean()
        else:
             print(f"  Advertencia: Datos insuficientes ({len(historical_data_df)} filas) para calcular EMA({ema_window}).")
             historical_data_df['EMA'] = np.nan
    except Exception as e:
        print(f"[Plotter Error] Cálculo EMA falló: {e}");
        historical_data_df['EMA'] = np.nan

    # 4. Crear Gráfico (tamaño modificado)
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(25, 12)) # Tamaño aumentado

    # 5. Plotear Sombreado de Fondo
    if state_changes:
        print("[Plotter Info] Aplicando sombreado de fondo por tendencia...")
        for i in range(len(state_changes)):
            start_time = state_changes[i]['timestamp']
            mode = state_changes[i]['mode']
            end_time = state_changes[i+1]['timestamp'] if i + 1 < len(state_changes) else historical_data_df.index[-1]
            
            color = 'none'
            if mode == 'LONG_ONLY':
                color = 'green'
            elif mode == 'SHORT_ONLY':
                color = 'red'
            
            if color != 'none':
                ax.axvspan(start_time, end_time, color=color, alpha=0.1, zorder=0)

    # 6. Plotear Datos
    ax.plot(historical_data_df.index, historical_data_df['price'], label='Precio Histórico', color='grey', lw=1.0, alpha=0.8, zorder=1)
    if 'EMA' in historical_data_df and historical_data_df['EMA'].notna().any():
        ax.plot(historical_data_df.index, historical_data_df['EMA'], label=f'EMA ({ema_window})', color='darkorange', ls='--', lw=1.5, alpha=0.9, zorder=2)

    if not df_closed_positions.empty:
        print("[Plotter Info] Graficando marcadores de apertura/cierre de posiciones...")
        closed_longs = df_closed_positions[df_closed_positions['side'] == 'long']
        closed_shorts = df_closed_positions[df_closed_positions['side'] == 'short']
        if not closed_longs.empty:
            ax.scatter(closed_longs['entry_timestamp_dt'], closed_longs['entry_price'], label='Open Long', marker='o', color='blue', s=80, alpha=0.7, zorder=3)
            ax.scatter(closed_longs['exit_timestamp_dt'], closed_longs['exit_price'], label='Close Long (TP)', marker='x', color='blue', s=100, lw=2, alpha=0.9, zorder=4)
            print(f"  - Graficados {len(closed_longs)} marcadores Open/Close Long.")
        if not closed_shorts.empty:
            ax.scatter(closed_shorts['entry_timestamp_dt'], closed_shorts['entry_price'], label='Open Short', marker='o', color='purple', s=80, alpha=0.7, zorder=3)
            ax.scatter(closed_shorts['exit_timestamp_dt'], closed_shorts['exit_price'], label='Close Short (TP)', marker='x', color='purple', s=100, lw=2, alpha=0.9, zorder=4)
            print(f"  - Graficados {len(closed_shorts)} marcadores Open/Close Short.")
    else:
        print("[Plotter Info] No hay datos de posiciones cerradas para graficar.")

    if not df_signals.empty:
        buy_markers = df_signals[df_signals['signal'] == 'BUY']
        sell_markers = df_signals[df_signals['signal'] == 'SELL']
        if not buy_markers.empty:
            ax.scatter(buy_markers.index, buy_markers['price_float'], label='BUY Signal', marker='^', color='lime', s=120, ec='black', lw=0.5, zorder=5)
            print(f"[Plotter Info] Graficando {len(buy_markers)} marcador(es) de señal BUY.")
        if not sell_markers.empty:
            ax.scatter(sell_markers.index, sell_markers['price_float'], label='SELL Signal', marker='v', color='red', s=120, ec='black', lw=0.5, zorder=5)
            print(f"[Plotter Info] Graficando {len(sell_markers)} marcador(es) de señal SELL.")
    else:
        print("[Plotter Info] No hay datos de señales BUY/SELL para graficar.")

    # 7. AJUSTAR LÍMITES Y FORMATO DEL EJE Y
    print("[Plotter Info] Ajustando escala y formato del eje Y...")
    all_y_values_list = []
    if 'price' in historical_data_df and historical_data_df['price'].notna().any():
        all_y_values_list.append(historical_data_df['price'].dropna())
    if 'EMA' in historical_data_df and historical_data_df['EMA'].notna().any():
        all_y_values_list.append(historical_data_df['EMA'].dropna())
    if not df_signals.empty and 'price_float' in df_signals and df_signals['price_float'].notna().any():
         all_y_values_list.append(df_signals['price_float'].dropna())
    if not df_closed_positions.empty:
        if 'entry_price' in df_closed_positions and df_closed_positions['entry_price'].notna().any():
             all_y_values_list.append(df_closed_positions['entry_price'].dropna())
        if 'exit_price' in df_closed_positions and df_closed_positions['exit_price'].notna().any():
             all_y_values_list.append(df_closed_positions['exit_price'].dropna())

    if all_y_values_list:
        all_y_data = pd.concat(all_y_values_list)
        if not all_y_data.empty:
            ymin = all_y_data.min()
            ymax = all_y_data.max()
            data_range = ymax - ymin
            padding = data_range * 0.05 if data_range > 1e-9 else abs(ymin * 0.01)
            padding = max(padding, 1e-8)
            final_ymin = ymin - padding
            final_ymax = ymax + padding
            if ymin >= 0:
                final_ymin = max(0, final_ymin)
            ax.set_ylim(final_ymin, final_ymax)
            print(f"[Plotter Info] Límites eje Y calculados: ({final_ymin:.8f}, {final_ymax:.8f})")
        else:
             print("[Plotter Warn] No se encontraron datos Y válidos para calcular límites.")
    else:
        print("[Plotter Warn] No hay datos para determinar límites del eje Y.")

    ax.yaxis.set_major_formatter(FormatStrFormatter('%.8f'))
    plt.setp(ax.get_yticklabels(), rotation=30, ha="right")

    # 8. Configuración Final y Guardado
    symbol_plot = getattr(config, 'TICKER_SYMBOL', 'N/A')
    ax.set_title(f'Historial {symbol_plot}, EMA({ema_window}), Señales y Posiciones (v6.3)', fontsize=18)
    ax.set_xlabel('Timestamp', fontsize=12)
    ax.set_ylabel('Precio (USDT)', fontsize=12)
    ax.legend(fontsize=10, loc='best') # Aumentado tamaño de leyenda
    ax.grid(True, linestyle=':', alpha=0.6)
    
    try:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
        plt.xticks(rotation=30, ha='right')
    except Exception as fmt_err:
         print(f"Advertencia: Error formateando eje de fechas: {fmt_err}")

    plt.tight_layout(pad=1.5)

    try:
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
        plt.savefig(output_filepath, dpi=200)
        print(f"[Plotter Info] Gráfico guardado exitosamente en: {output_filepath}")
    except Exception as e:
        print(f"[Plotter Error] No se pudo guardar el gráfico: {e}"); traceback.print_exc()
    finally:
         plt.close(fig)

    print("--- Fin Generación de Gráfico ---")