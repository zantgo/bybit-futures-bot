"""
Genera un gráfico a partir de datos históricos y logs.

v7.0 (Gráfico de Régimen de Mercado):
- Rediseñado para visualizar la estrategia de Bandas de Bollinger.
- Dibuja las bandas superior, media e inferior.
- Sombrea las zonas de oportunidad (NEAR_SUPPORT/NEAR_RESISTANCE) en lugar de tendencias completas.
- Distingue visualmente entre señales de bajo nivel aceptadas y las ignoradas por el filtro de contexto.
- Se ha eliminado la dependencia del log de cambios de estado, ya que el contexto ahora es dinámico.
- Estética general mejorada para mayor claridad.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FormatStrFormatter
import pandas_ta as ta
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
    config = type('obj', (object,), {})()
    utils = type('obj', (object,), {'safe_float_convert': float})()

# --- Constantes ---
MAX_POINTS_TO_PLOT = 1000000

# --- Funciones de Carga de Logs (Sin cambios significativos) ---

def load_signal_log(log_filepath: str) -> pd.DataFrame:
    """Carga el log de señales (JSON Lines) en un DataFrame."""
    print(f"[Plotter] Cargando log de señales desde: {os.path.basename(log_filepath)}")
    data = []
    try:
        with open(log_filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip(): data.append(json.loads(line))
        if not data: return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df['timestamp_dt'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df.dropna(subset=['timestamp_dt', 'signal', 'price_float'], inplace=True)
        df['price_float'] = pd.to_numeric(df['price_float'], errors='coerce')
        df.dropna(subset=['price_float'], inplace=True)
        df.set_index('timestamp_dt', inplace=True).sort_index(inplace=True)
        
        print(f"  Log de Señales procesado: {len(df)} señales totales.")
        return df
    except FileNotFoundError:
        print(f"  Advertencia [Signals Log]: Archivo no encontrado: {os.path.basename(log_filepath)}")
        return pd.DataFrame()
    except Exception as e:
        print(f"  ERROR [Signals Log]: Error inesperado: {e}"); traceback.print_exc()
        return pd.DataFrame()

def load_closed_positions_log(log_filepath: str) -> pd.DataFrame:
    """Carga el log de posiciones cerradas (JSON Lines) en un DataFrame."""
    print(f"[Plotter] Cargando log de posiciones cerradas desde: {os.path.basename(log_filepath)}")
    data = []
    try:
        with open(log_filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip(): data.append(json.loads(line))
        if not data: return pd.DataFrame()

        df = pd.DataFrame(data)
        for col in ['entry_timestamp', 'exit_timestamp']:
            df[f'{col}_dt'] = pd.to_datetime(df[col], errors='coerce')
        for col in ['entry_price', 'exit_price']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df.dropna(subset=['side', 'entry_timestamp_dt', 'exit_timestamp_dt', 'entry_price', 'exit_price'], inplace=True)
        df = df[df['side'].isin(['long', 'short'])].copy()
        print(f"  Log de Posiciones Cerradas procesado: {len(df)} posiciones válidas.")
        return df
    except FileNotFoundError:
        print(f"  Info [Closed Pos Log]: Archivo no encontrado (puede ser normal).")
        return pd.DataFrame()
    except Exception as e:
        print(f"  ERROR [Closed Pos Log]: Error inesperado: {e}"); traceback.print_exc()
        return pd.DataFrame()


# --- Función Principal de Ploteo (REDISEÑADA) ---
def plot_signals_and_price(
    historical_data_df: pd.DataFrame,
    signal_log_filepath: str,
    closed_positions_log_filepath: Optional[str],
    output_filepath: str,
    **kwargs # Captura argumentos extra como state_changes_log_filepath para ignorarlos
):
    print("\n--- Iniciando Generación de Gráfico (v7.0 - Régimen de Mercado) ---")

    # 1. Validar y Preparar Datos Históricos
    if historical_data_df is None or historical_data_df.empty or 'price' not in historical_data_df.columns:
        print("[Plotter Error] Datos históricos inválidos."); return
    historical_data_df.index = pd.to_datetime(historical_data_df.index)
    historical_data_df.sort_index(inplace=True)

    # 2. Lógica de Downsampling (Remuestreo)
    plot_df = historical_data_df
    resample_rule = None
    if len(historical_data_df) > MAX_POINTS_TO_PLOT:
        duration_hours = (historical_data_df.index[-1] - historical_data_df.index[0]).total_seconds() / 3600
        if duration_hours > 72: resample_rule = '30Min'
        elif duration_hours > 24: resample_rule = '15Min'
        elif duration_hours > 6: resample_rule = '5Min'
        else: resample_rule = '1Min'
        print(f"[Plotter Info] Remuestreando datos a '{resample_rule}' para visualización.")
        plot_df = historical_data_df['price'].resample(resample_rule).ohlc().dropna()
    
    # 3. Cargar Logs
    df_signals = load_signal_log(signal_log_filepath)
    df_closed_positions = pd.DataFrame()
    if closed_positions_log_filepath:
        df_closed_positions = load_closed_positions_log(closed_positions_log_filepath)

    # 4. Calcular Indicadores para el Gráfico
    bb_length = getattr(config, 'MARKET_REGIME_BBANDS_LENGTH', 20)
    bb_std = getattr(config, 'MARKET_REGIME_BBANDS_STD', 2.0)
    bb_zone_pct = getattr(config, 'MARKET_REGIME_BBANDS_ZONE_PCT', 0.05)
    
    price_series = plot_df['close'] if 'close' in plot_df.columns else plot_df['price']
    
    if len(price_series) >= bb_length:
        print(f"[Plotter Info] Calculando Bandas de Bollinger ({bb_length}, {bb_std})...")
        bband_cols = f"_{bb_length}_{bb_std}"
        plot_df.ta.bbands(close=price_series, length=bb_length, std=bb_std, append=True)
        
        # Renombrar columnas para facilitar el acceso
        plot_df.rename(columns={
            f'BBL{bband_cols}': 'lower_band',
            f'BBM{bband_cols}': 'middle_band',
            f'BBU{bband_cols}': 'upper_band'
        }, inplace=True, errors='ignore')

    # 5. Crear Gráfico y Ejes
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(28, 14), facecolor='#F0F0F0')
    ax.set_facecolor('#FDFDFD')

    # 6. Plotear Bandas de Bollinger y Zonas de Oportunidad
    if 'upper_band' in plot_df.columns:
        ax.plot(plot_df.index, plot_df['middle_band'], label=f'BBands Media ({bb_length})', color='orange', ls=':', lw=1.5, alpha=0.8, zorder=2)
        ax.plot(plot_df.index, plot_df['upper_band'], color='cornflowerblue', ls='--', lw=1.2, alpha=0.7, zorder=1)
        ax.plot(plot_df.index, plot_df['lower_band'], color='cornflowerblue', ls='--', lw=1.2, alpha=0.7, zorder=1)
        
        # Sombreado entre las bandas
        ax.fill_between(plot_df.index, plot_df['lower_band'], plot_df['upper_band'], color='skyblue', alpha=0.1, zorder=0, label='Rango Bollinger')
        
        # Sombreado de Zonas de Oportunidad
        band_range = plot_df['upper_band'] - plot_df['lower_band']
        support_zone_limit = plot_df['lower_band'] + (band_range * bb_zone_pct)
        resistance_zone_limit = plot_df['upper_band'] - (band_range * bb_zone_pct)
        
        ax.fill_between(plot_df.index, plot_df['lower_band'], support_zone_limit, color='green', alpha=0.15, zorder=0, label=f'Zona Compra ({bb_zone_pct*100}%)')
        ax.fill_between(plot_df.index, resistance_zone_limit, plot_df['upper_band'], color='red', alpha=0.15, zorder=0, label=f'Zona Venta ({bb_zone_pct*100}%)')

    # 7. Plotear Precio
    if 'ohlc' in str(plot_df.columns): # Si es remuestreado
        ax.plot(plot_df.index, plot_df['close'], label='Precio (Cierre Agregado)', color='#333333', lw=1.5, zorder=3)
    else:
        ax.plot(plot_df.index, plot_df['price'], label='Precio', color='#333333', lw=1.2, zorder=3)

    # 8. Plotear Señales (Aceptadas vs. Ignoradas)
    if not df_signals.empty:
        accepted_buys = df_closed_positions[df_closed_positions['side'] == 'long']['entry_timestamp_dt']
        accepted_sells = df_closed_positions[df_closed_positions['side'] == 'short']['entry_timestamp_dt']
        
        all_buy_signals = df_signals[df_signals['signal'] == 'BUY']
        all_sell_signals = df_signals[df_signals['signal'] == 'SELL']

        # Marcadores de señales aceptadas (las que se convirtieron en una posición)
        ax.scatter(accepted_buys, all_buy_signals.loc[accepted_buys]['price_float'],
                   label='Señal Compra (Ejecutada)', marker='^', color='limegreen', s=150, ec='black', lw=1, zorder=5)
        ax.scatter(accepted_sells, all_sell_signals.loc[accepted_sells]['price_float'],
                   label='Señal Venta (Ejecutada)', marker='v', color='red', s=150, ec='black', lw=1, zorder=5)

        # Marcadores de señales ignoradas
        ignored_buys = all_buy_signals.index.difference(accepted_buys)
        ignored_sells = all_sell_signals.index.difference(accepted_sells)
        
        ax.scatter(ignored_buys, all_buy_signals.loc[ignored_buys]['price_float'],
                   label='Señal Compra (Ignorada)', marker='.', color='green', s=30, alpha=0.5, zorder=4)
        ax.scatter(ignored_sells, all_sell_signals.loc[ignored_sells]['price_float'],
                   label='Señal Venta (Ignorada)', marker='.', color='maroon', s=30, alpha=0.5, zorder=4)

    # 9. Plotear Entradas/Salidas de Posiciones Cerradas
    if not df_closed_positions.empty:
        for _, row in df_closed_positions.iterrows():
            color = 'blue' if row['side'] == 'long' else 'purple'
            linestyle = '-' if row['pnl_net_usdt'] >= 0 else '--'
            ax.plot([row['entry_timestamp_dt'], row['exit_timestamp_dt']], 
                    [row['entry_price'], row['exit_price']], 
                    color=color, lw=1.5, ls=linestyle, marker='o', markersize=5, alpha=0.8, zorder=6)

    # 10. Configuración Final y Guardado
    symbol_plot = getattr(config, 'TICKER_SYMBOL', 'N/A')
    title = f'Análisis de Estrategia para {symbol_plot} - Régimen de Mercado con Bandas de Bollinger'
    ax.set_title(title, fontsize=20, pad=20)
    ax.set_xlabel('Timestamp', fontsize=14)
    ax.set_ylabel('Precio (USDT)', fontsize=14)
    
    # Formato de ejes
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.4f'))
    ax.tick_params(axis='both', which='major', labelsize=12)
    plt.setp(ax.get_yticklabels(), rotation=15, ha="right")
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=30, ha='right')

    ax.legend(fontsize=12, loc='upper left')
    ax.grid(True, which='major', linestyle='--', linewidth=0.5, color='gray')
    
    plt.tight_layout(pad=2.0)

    try:
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
        plt.savefig(output_filepath, dpi=200, bbox_inches='tight')
        print(f"[Plotter Info] Gráfico guardado exitosamente en: {output_filepath}")
    except Exception as e:
        print(f"[Plotter Error] No se pudo guardar el gráfico: {e}"); traceback.print_exc()
    finally:
         plt.close(fig)

    print("--- Fin Generación de Gráfico ---")