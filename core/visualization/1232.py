# =============== INICIO ARCHIVO: core/visualization/plotter.py (v6.5 - SL Individual y TS en Gráfico) ===============
"""
Genera un gráfico a partir de datos históricos y logs.
v6.5:
- Diferencia los marcadores de cierre en el gráfico para:
    - Cierre por Stop Loss individual.
    - Cierre por Trailing Stop.
- Asegura que los logs de posiciones cerradas incluyan la 'exit_reason'
  (aunque la lectura aquí solo necesite la columna).
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import ScalarFormatter, FormatStrFormatter
import json
import os
import traceback
import sys
from typing import Optional

# Importar módulos core necesarios de forma segura
try:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import config
    from core import utils
except ImportError:
    print("ERROR CRITICO [Plotter Import]: No se pudo importar config o utils.")
    config = type('obj', (object,), {'TA_EMA_WINDOW': 20, 'TICKER_SYMBOL': 'N/A'})()
    utils = type('obj', (object,), {'safe_float_convert': float})()

# --- Constantes ---
MAX_POINTS_TO_PLOT = 10000 # Umbral para activar el remuestreo (se mantiene este valor)

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

# --- Función para cargar Log de Posiciones Cerradas (MODIFICADA) ---
def load_closed_positions_log(log_filepath: str) -> pd.DataFrame:
    """
    Carga el log de posiciones cerradas (JSON Lines) en un DataFrame.
    Ahora incluye la columna 'exit_reason' para distinguir los cierres.
    """
    print(f"[Plotter] Cargando log de posiciones cerradas desde: {os.path.basename(log_filepath)}")
    data = []
    # <<< MODIFICADO: Añadir 'exit_reason' a required_cols >>>
    required_cols = ['side', 'entry_timestamp', 'exit_timestamp', 'entry_price', 'exit_price', 'exit_reason']
    try:
        with open(log_filepath, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f):
                try:
                    if not line.strip(): continue
                    closed_pos = json.loads(line)
                    # Asegurarse de que exit_reason esté presente, si no, usar 'UNKNOWN' por defecto
                    if 'exit_reason' not in closed_pos:
                        closed_pos['exit_reason'] = 'UNKNOWN'

                    if all(col in closed_pos for col in required_cols[:-1]): # Chequear las columnas obligatorias excepto exit_reason
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
        # <<< NUEVO: Asegurarse que exit_reason sea string >>>
        df_closed['exit_reason'] = df_closed['exit_reason'].astype(str)

        # Eliminar filas con valores nulos en columnas críticas
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

# --- Función Principal de Ploteo (MODIFICADA) ---
def plot_signals_and_price(
    historical_data_df: pd.DataFrame,
    signal_log_filepath: str,
    closed_positions_log_filepath: Optional[str],
    output_filepath: str,
    state_changes_log_filepath: Optional[str] = None
):
    """
    Genera gráfico combinando precio, EMA, señales, posiciones y sombreado de tendencia.
    Aplica downsampling si el número de datos es muy grande.
    """
    print("\n--- Iniciando Generación de Gráfico (v6.5 - SL Individual y TS en Gráfico) ---")

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

    # Lógica de Downsampling
    plot_df = historical_data_df
    resample_rule = None
    if len(historical_data_df) > MAX_POINTS_TO_PLOT:
        duration_hours = (historical_data_df.index[-1] - historical_data_df.index[0]).total_seconds() / 3600
        if duration_hours > 72: resample_rule = '30Min'
        elif duration_hours > 24: resample_rule = '15Min'
        elif duration_hours > 6: resample_rule = '5Min'
        elif duration_hours > 1: resample_rule = '1Min'
        else: resample_rule = '15S'

        print(f"[Plotter Info] Demasiados puntos ({len(historical_data_df)}). Remuestreando a '{resample_rule}'.")

        ohlc_dict = {'price': 'ohlc'}
        plot_df = historical_data_df.resample(resample_rule).apply(ohlc_dict)
        plot_df.columns = plot_df.columns.droplevel(0)
        plot_df.dropna(inplace=True)
        print(f"  Datos reducidos a {len(plot_df)} puntos (barras OHLC).")

    # 2. Cargar Logs
    df_signals = load_signal_log(signal_log_filepath)
    df_closed_positions = pd.DataFrame()
    # <<< MODIFICADO: Solo cargar si el path existe, como antes >>>
    if closed_positions_log_filepath and os.path.exists(closed_positions_log_filepath):
         df_closed_positions = load_closed_positions_log(closed_positions_log_filepath)
    # <<< FIN MODIFICACIÓN >>>

    state_changes = []
    if state_changes_log_filepath and os.path.exists(state_changes_log_filepath):
        state_changes = load_state_changes_log(state_changes_log_filepath)

    # 3. Calcular EMA
    ema_window = getattr(config, 'TA_EMA_WINDOW', 20)
    print(f"[Plotter Info] Calculando EMA({ema_window})...")
    price_series_for_ema = plot_df['close'] if 'close' in plot_df.columns else plot_df['price']
    try:
        if len(price_series_for_ema) >= ema_window:
            plot_df['EMA'] = price_series_for_ema.ewm(span=ema_window, adjust=False, min_periods=ema_window).mean()
        else:
             plot_df['EMA'] = np.nan
    except Exception as e:
        print(f"[Plotter Error] Cálculo EMA falló: {e}");
        plot_df['EMA'] = np.nan

    # 4. Crear Gráfico
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(25, 12))

    # 5. Plotear Sombreado de Fondo
    if state_changes:
        print("[Plotter Info] Aplicando sombreado de fondo por tendencia...")
        for i in range(len(state_changes)):
            start_time = state_changes[i]['timestamp']
            mode = state_changes[i]['mode']
            end_time = state_changes[i+1]['timestamp'] if i + 1 < len(state_changes) else historical_data_df.index[-1]
            color = {'LONG_ONLY': 'green', 'SHORT_ONLY': 'red'}.get(mode, 'none')
            if color != 'none':
                ax.axvspan(start_time, end_time, color=color, alpha=0.1, zorder=0)

    # 6. Plotear Datos de Precio y EMA
    if resample_rule:
        ax.plot(plot_df.index, plot_df['close'], label='Precio (Cierre Agregado)', color='grey', lw=1.2, alpha=0.9, zorder=1)
        ax.fill_between(plot_df.index, plot_df['low'], plot_df['high'], color='grey', alpha=0.2, label=f'Rango H-L ({resample_rule})')
    else:
        ax.plot(plot_df.index, plot_df['price'], label='Precio Histórico', color='grey', lw=1.0, alpha=0.8, zorder=1)

    if 'EMA' in plot_df and plot_df['EMA'].notna().any():
        ax.plot(plot_df.index, plot_df['EMA'], label=f'EMA ({ema_window})', color='darkorange', ls='--', lw=1.5, alpha=0.9, zorder=2)

    # <<< INICIO DE CAMBIOS: Plotear marcadores de cierre por razón >>>
    if not df_closed_positions.empty:
        print("[Plotter Info] Graficando marcadores de apertura y cierre de posiciones por razón...")

        # Filtrar por tipos de cierre
        closed_by_sl_long = df_closed_positions[(df_closed_positions['side'] == 'long') & (df_closed_positions['exit_reason'] == 'SL')]
        closed_by_sl_short = df_closed_positions[(df_closed_positions['side'] == 'short') & (df_closed_positions['exit_reason'] == 'SL')]
        closed_by_ts_long = df_closed_positions[(df_closed_positions['side'] == 'long') & (df_closed_positions['exit_reason'] == 'TS')]
        closed_by_ts_short = df_closed_positions[(df_closed_positions['side'] == 'short') & (df_closed_positions['exit_reason'] == 'TS')]

        # Marcadores de Apertura (sin cambios)
        # Recopilar todas las aperturas para long y short, ya que los cierres se dividen por razón
        open_long_trades = df_closed_positions[df_closed_positions['side'] == 'long']
        open_short_trades = df_closed_positions[df_closed_positions['side'] == 'short']

        if not open_long_trades.empty:
            ax.scatter(open_long_trades['entry_timestamp_dt'], open_long_trades['entry_price'], label='Open Long', marker='o', color='blue', s=80, alpha=0.7, zorder=3)
            print(f"  - Graficadas {len(open_long_trades)} aperturas Long.")
        if not open_short_trades.empty:
            ax.scatter(open_short_trades['entry_timestamp_dt'], open_short_trades['entry_price'], label='Open Short', marker='o', color='purple', s=80, alpha=0.7, zorder=3)
            print(f"  - Graficadas {len(open_short_trades)} aperturas Short.")

        # Marcadores de Cierre por SL Individual
        if not closed_by_sl_long.empty:
            ax.scatter(closed_by_sl_long['exit_timestamp_dt'], closed_by_sl_long['exit_price'], label='Close Long (SL)', marker='X', color='red', s=120, lw=2, alpha=0.9, zorder=4)
            print(f"  - Graficados {len(closed_by_sl_long)} cierres Long por SL.")
        if not closed_by_sl_short.empty:
            ax.scatter(closed_by_sl_short['exit_timestamp_dt'], closed_by_sl_short['exit_price'], label='Close Short (SL)', marker='X', color='red', s=120, lw=2, alpha=0.9, zorder=4)
            print(f"  - Graficados {len(closed_by_sl_short)} cierres Short por SL.")

        # Marcadores de Cierre por Trailing Stop
        if not closed_by_ts_long.empty:
            ax.scatter(closed_by_ts_long['exit_timestamp_dt'], closed_by_ts_long['exit_price'], label='Close Long (TS)', marker='v', color='darkgreen', s=120, lw=2, alpha=0.9, zorder=4)
            print(f"  - Graficados {len(closed_by_ts_long)} cierres Long por TS.")
        if not closed_by_ts_short.empty:
            ax.scatter(closed_by_ts_short['exit_timestamp_dt'], closed_by_ts_short['exit_price'], label='Close Short (TS)', marker='^', color='darkgreen', s=120, lw=2, alpha=0.9, zorder=4)
            print(f"  - Graficados {len(closed_by_ts_short)} cierres Short por TS.")

        # Manejar cierres desconocidos/por defecto si no tienen una razón específica
        closed_by_unknown = df_closed_positions[~df_closed_positions['exit_reason'].isin(['SL', 'TS'])]
        if not closed_by_unknown.empty:
            # Aquí podríamos plotearlos con un marcador genérico o simplemente loguear una advertencia
            print(f"  - Advertencia: {len(closed_by_unknown)} cierres con razón desconocida/por defecto no graficados específicamente.")
            # Si quieres graficarlos de alguna forma:
            # ax.scatter(closed_by_unknown['exit_timestamp_dt'], closed_by_unknown['exit_price'], label='Close Unknown', marker='o', color='lightgrey', s=80, alpha=0.6, zorder=4)

    else:
        print("[Plotter Info] No hay datos de posiciones cerradas para graficar.")
    # <<< FIN DE CAMBIOS >>>

    if not df_signals.empty:
        # ... (código de ploteo de señales idéntico)
        buy_markers = df_signals[df_signals['signal'] == 'BUY']
        sell_markers = df_signals[df_signals['signal'] == 'SELL']
        if not buy_markers.empty:
            ax.scatter(buy_markers.index, buy_markers['price_float'], label='BUY Signal', marker='^', color='lime', s=120, ec='black', lw=0.5, zorder=5)
            print(f"[Plotter Info] Graficando {len(buy_markers)} marcador(es) de señal BUY.") # Añadir print aquí
        if not sell_markers.empty:
            ax.scatter(sell_markers.index, sell_markers['price_float'], label='SELL Signal', marker='v', color='red', s=120, ec='black', lw=0.5, zorder=5)
            print(f"[Plotter Info] Graficando {len(sell_markers)} marcador(es) de señal SELL.") # Añadir print aquí
    else:
        print("[Plotter Info] No hay datos de señales BUY/SELL para graficar.")


    # 7. AJUSTAR LÍMITES Y FORMATO DEL EJE Y
    all_y_values_list = []
    price_data_for_lim = plot_df['close'] if resample_rule else plot_df['price']
    if price_data_for_lim.notna().any(): all_y_values_list.append(price_data_for_lim.dropna())
    if 'EMA' in plot_df and plot_df['EMA'].notna().any(): all_y_values_list.append(plot_df['EMA'].dropna())
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
            ymin, ymax = all_y_data.min(), all_y_data.max()
            padding = (ymax - ymin) * 0.05 if (ymax - ymin) > 1e-9 else abs(ymin * 0.01)
            padding = max(padding, 1e-8)
            final_ymin = ymin - padding
            final_ymax = ymax + padding
            if ymin >= 0: final_ymin = max(0, final_ymin)
            ax.set_ylim(final_ymin, final_ymax)

    ax.yaxis.set_major_formatter(FormatStrFormatter('%.8f'))
    plt.setp(ax.get_yticklabels(), rotation=30, ha="right")

    # 8. Configuración Final y Guardado
    symbol_plot = getattr(config, 'TICKER_SYMBOL', 'N/A')
    title = f'Historial {symbol_plot}, EMA({ema_window}), Señales y Posiciones (v6.5' # Version actualizada
    if resample_rule:
        title += f' - Agregado a {resample_rule})'
    else:
        title += ')'
    ax.set_title(title, fontsize=18)
    ax.set_xlabel('Timestamp', fontsize=12); ax.set_ylabel('Precio (USDT)', fontsize=12)
    ax.legend(fontsize=10, loc='best'); ax.grid(True, linestyle=':', alpha=0.6)

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
