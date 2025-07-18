"""
Configuración Esencial (v15.0 - Estrategia de Régimen de Mercado).
Parámetros para TA, Feeder, Logger, Plotter, conexiones Live y Gestión de Posiciones.

v15.0:
- Reemplazado UT Bot con Market Regime Controller (Bollinger Bands) para definir zonas de operación.
v14.2:
- Añadidos AUTOMATIC_TRADE_LIMIT_ENABLED y AUTOMATIC_MAX_TRADES_PER_TREND.
v14.1:
- Añadido GLOBAL_ACCOUNT_STOP_LOSS_ROI_PCT para un disyuntor a nivel de cuenta.
"""
import os
import json
import sys
from dotenv import load_dotenv, find_dotenv

# Define project root dinámicamente
try:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    PROJECT_ROOT = os.path.abspath(os.getcwd())
    print(f"Advertencia [config]: __file__ no definido, usando CWD como PROJECT_ROOT: {PROJECT_ROOT}")

# --- Account Configuration ---
ACCOUNT_MAIN = "main"
ACCOUNT_LONGS = "longs"
ACCOUNT_SHORTS = "shorts"
ACCOUNT_PROFIT = "profit"

# --- API Key & UID Mapping ---
ACCOUNT_API_KEYS_ENV_MAP = {
    ACCOUNT_MAIN:   ("BYBIT_MAIN_API_KEY", "BYBIT_MAIN_API_SECRET"),
    ACCOUNT_LONGS:  ("BYBIT_LONGS_API_KEY", "BYBIT_LONGS_API_SECRET"),
    ACCOUNT_SHORTS: ("BYBIT_SHORTS_API_KEY", "BYBIT_SHORTS_API_SECRET"),
    ACCOUNT_PROFIT: ("BYBIT_PROFIT_API_KEY", "BYBIT_PROFIT_API_SECRET"),
}
ACCOUNT_UID_ENV_VAR_MAP = {
    ACCOUNT_LONGS: "BYBIT_LONGS_UID",
    ACCOUNT_SHORTS: "BYBIT_SHORTS_UID",
    ACCOUNT_PROFIT: "BYBIT_PROFIT_UID",
}
ACCOUNTS_TO_INITIALIZE = [ACCOUNT_MAIN, ACCOUNT_LONGS, ACCOUNT_SHORTS, ACCOUNT_PROFIT]

# --- General Settings ---
UNIVERSAL_TESTNET_MODE = False
DEFAULT_RECV_WINDOW = 30000

# --- Live Ticker / Backtest Feeder Settings ---
TICKER_SYMBOL = "FARTCOINUSDT"
TICKER_INTERVAL_SECONDS = 1
TICKER_SOURCE_ACCOUNT = ACCOUNT_PROFIT
RAW_PRICE_TICK_INTERVAL = 1

# --- Technical Analysis Configuration (Estrategia de Bajo Nivel) ---
TA_WINDOW_SIZE = 100
TA_EMA_WINDOW = 50
TA_WEIGHTED_INC_WINDOW = 25
TA_WEIGHTED_DEC_WINDOW = 25
TA_CALCULATE_PROCESSED_DATA = True

# --- Signal Generation Configuration (Estrategia de Bajo Nivel) ---
STRATEGY_ENABLED = True
STRATEGY_MARGIN_BUY = -0.1
STRATEGY_MARGIN_SELL = 0.1
STRATEGY_DECREMENT_THRESHOLD = 0.45
STRATEGY_INCREMENT_THRESHOLD = 0.45

# --- Position Management Configuration ---
POSITION_MANAGEMENT_ENABLED = True
POSITION_TRADING_MODE = "LONG_SHORT"
POSITION_BASE_SIZE_USDT = 1.0
POSITION_MAX_LOGICAL_POSITIONS = 10
POSITION_LEVERAGE = 10.0
POSITION_COMMISSION_RATE = 0.001
POSITION_REINVEST_PROFIT_PCT = 10.0
POSITION_MIN_TRANSFER_AMOUNT_USDT = 0.001

# --- Stop Loss Individual por Posición Lógica ---
POSITION_INDIVIDUAL_STOP_LOSS_PCT = 10.0

# --- Trailing Stop (reemplaza al Take Profit fijo) ---
TRAILING_STOP_ACTIVATION_PCT = 0.3
TRAILING_STOP_DISTANCE_PCT = 0.1

# --- Global Account Stop-Loss (Circuit Breaker) ---
GLOBAL_ACCOUNT_STOP_LOSS_ROI_PCT = 10.0

# --- Global Account Take-Profit (Session Target) ---
# Si el ROI total de la cuenta alcanza este objetivo positivo, el bot entrará
# en modo NEUTRAL, dejando de abrir nuevas posiciones pero gestionando las existentes.
# Escribe el valor como un número positivo (ej: 5.0 para +5%).
# Ponlo a 0.0 para desactivar esta función.
GLOBAL_ACCOUNT_TAKE_PROFIT_ROI_PCT = 5.0

# --- Session Time Management ---
# Tiempo máximo de ejecución de la sesión en minutos. 0 para desactivar.
SESSION_MAX_DURATION_MINUTES = 0

# Acción a tomar cuando se alcanza el tiempo máximo.
# Opciones: "NEUTRAL" (deja de abrir posiciones) o "STOP" (cierra todo y detiene el bot).
SESSION_TIME_LIMIT_ACTION = "NEUTRAL"

# --- Filtros, Delays y Cooldown ---
POSITION_SIGNAL_COOLDOWN_ENABLED = False
POSITION_SIGNAL_COOLDOWN_LONG = 0
POSITION_SIGNAL_COOLDOWN_SHORT = 0
POSITION_PRE_OPEN_SYNC_CHECK = True
POSITION_MIN_PRICE_DIFF_LONG_PCT = -0.25
POSITION_MIN_PRICE_DIFF_SHORT_PCT = 0.25
POST_ORDER_CONFIRMATION_DELAY_SECONDS = 0.1
POST_CLOSE_SYNC_DELAY_SECONDS = 0.1

# --- Modos de Operación y Control ---
INTERACTIVE_MANUAL_MODE = True

# --- AUTOMATIC MODE CONFIGURATION ---
AUTOMATIC_MODE_ENABLED = False

# <<< INICIO DE LA MODIFICACIÓN >>>
# --- Market Regime Controller Configuration (High-Level Strategy) ---
# Intervalo en segundos para recalcular el régimen del mercado (ej. 300s = 5 minutos)
MARKET_REGIME_INTERVAL_SECONDS = 900 

# Parámetros de las Bandas de Bollinger
MARKET_REGIME_BBANDS_LENGTH = 20    # Período para la media móvil y la desviación estándar
MARKET_REGIME_BBANDS_STD = 2.0      # Número de desviaciones estándar
# Porcentaje de proximidad a las bandas para considerar una zona "activa".
# 0.05 significa que el precio debe estar en el 5% inferior/superior del rango de las bandas.
MARKET_REGIME_BBANDS_ZONE_PCT = 0.05 
# <<< FIN DE LA MODIFICACIÓN >>>

AUTOMATIC_FLIP_OPENS_NEW_POSITIONS = False
AUTOMATIC_SL_COOLDOWN_SECONDS = 1

# --- Lógica de Toma de Ganancias por ROI de Tendencia (Modo Automático) ---
AUTOMATIC_ROI_PROFIT_TAKING_ENABLED = True
AUTOMATIC_ROI_PROFIT_TARGET_PCT = 0.1

# --- Lógica de Límite de Trades por Tendencia (Modo Automático) ---
AUTOMATIC_TRADE_LIMIT_ENABLED = True
AUTOMATIC_MAX_TRADES_PER_TREND = 10

# --- Printing / Logging Configuration ---
POSITION_LOG_CLOSED_POSITIONS = True
POSITION_PRINT_POSITION_UPDATES = True
POSITION_LOG_OPEN_SNAPSHOT = True
PRINT_SIGNAL_OUTPUT = False
LOG_SIGNAL_OUTPUT = True
PRINT_RAW_EVENT_ALWAYS = False
PRINT_PROCESSED_DATA_ALWAYS = False

# --- Fallbacks y Constantes ---
DEFAULT_QTY_PRECISION = 3
DEFAULT_MIN_ORDER_QTY = 0.001
PRICE_PRECISION = 4
PNL_PRECISION = 4
CATEGORY_LINEAR = "linear"
UNIVERSAL_TRANSFER_FROM_TYPE = "UNIFIED"
UNIVERSAL_TRANSFER_TO_TYPE = "UNIFIED"

# --- Paths (Directorios y Archivos) ---
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
SIGNAL_LOG_FILE = os.path.join(LOG_DIR, "signals_log.jsonl")
POSITION_CLOSED_LOG_FILE = os.path.join(LOG_DIR, "closed_positions.jsonl")
POSITION_OPEN_SNAPSHOT_FILE = os.path.join(LOG_DIR, "open_positions_snapshot.jsonl")
os.makedirs(LOG_DIR, exist_ok=True)

BACKTEST_DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BACKTEST_CSV_FILE = "data.csv"
BACKTEST_CSV_TIMESTAMP_COL = "timestamp"
BACKTEST_CSV_PRICE_COL = "price"

RESULT_DIR = os.path.join(PROJECT_ROOT, "result")
PLOT_OUTPUT_FILENAME = f"plot_{TICKER_SYMBOL}.png"
RESULTS_FILENAME = "results.txt"
RESULTS_FILEPATH = os.path.join(RESULT_DIR, RESULTS_FILENAME)
os.makedirs(RESULT_DIR, exist_ok=True)

# --- UID Management ---
LOADED_UIDS = {}

def _load_and_validate_uids():
    global LOADED_UIDS
    all_uids_valid = True
    required_uids_map = ACCOUNT_UID_ENV_VAR_MAP
    try:
        env_path = find_dotenv(filename='.env', raise_error_if_not_found=False, usecwd=True)
        if env_path:
            load_dotenv(dotenv_path=env_path, override=True)
        else:
            if any(arg.startswith(('live', 'automatic')) for arg in sys.argv[1:] if isinstance(arg, str)):
                print("ADVERTENCIA [config]: .env no encontrado (necesario para UIDs).")
    except Exception as e:
        print(f"ERROR [config]: Excepción cargando .env para UIDs: {e}"); return False

    if not required_uids_map: return True
    loaded_temp = {}
    print("Validando UIDs desde .env...")
    for account_name, env_var_name in required_uids_map.items():
        uid_value = os.getenv(env_var_name)
        if uid_value is None or not uid_value.strip().isdigit():
             print(f"ERROR [config]: UID inválido/faltante para '{account_name}' (Env: {env_var_name}).")
             all_uids_valid = False
        else:
             loaded_temp[account_name] = uid_value.strip()

    if all_uids_valid:
        LOADED_UIDS = loaded_temp
        print(f"  [config] Validación de UIDs OK. Cargados: {list(LOADED_UIDS.keys())}")
    else:
        print("ERROR Crítico [config]: Faltan o son inválidos UIDs para transferencias API.")
        LOADED_UIDS = {}
    return all_uids_valid

# --- Función de Impresión de Configuración ---
def print_initial_config(operation_mode="unknown"):
    """Imprime un resumen de la configuración cargada."""
    print("-" * 70); print(f"Configuración Base Cargada (config.py v15.0)");
    print(f"  Modo Testnet API        : {UNIVERSAL_TESTNET_MODE}")
    print(f"  Ticker Símbolo          : {TICKER_SYMBOL}")
    print("-" * 70)
    pos_enabled = POSITION_MANAGEMENT_ENABLED
    print(f"  Gestión Posiciones Base : {'Activada' if pos_enabled else 'Desactivada'}")
    if pos_enabled:
        print(f"    Modo Automático por Defecto: {'Activado' if AUTOMATIC_MODE_ENABLED else 'Desactivado'}")
        # La impresión de la configuración de alto nivel se podría añadir aquí si se desea,
        # pero para mantenerlo simple, se deja como está, ya que el cambio es interno a la estrategia.
        print(f"    Toma Ganancias por ROI   : {'Activado' if AUTOMATIC_ROI_PROFIT_TAKING_ENABLED else 'Desactivado'} (Objetivo: {AUTOMATIC_ROI_PROFIT_TARGET_PCT}%)")
        print(f"    Límite de Trades x Tendencia: {'Activado (' + str(AUTOMATIC_MAX_TRADES_PER_TREND) + ' trades)' if AUTOMATIC_TRADE_LIMIT_ENABLED else 'Desactivado'}")
        print(f"    Stop Loss Individual (%) : {POSITION_INDIVIDUAL_STOP_LOSS_PCT}%")
        print(f"    Trailing Stop Activación(%): {TRAILING_STOP_ACTIVATION_PCT}%")
        print(f"    Trailing Stop Distancia(%): {TRAILING_STOP_DISTANCE_PCT}%")
        print(f"    Stop Loss Global Cuenta (% ROI): {'Desactivado' if GLOBAL_ACCOUNT_STOP_LOSS_ROI_PCT <= 0 else f'-{GLOBAL_ACCOUNT_STOP_LOSS_ROI_PCT}%'}")
        print(f"    Take Profit Global Cuenta (% ROI): {'Desactivado' if GLOBAL_ACCOUNT_TAKE_PROFIT_ROI_PCT <= 0 else f'+{GLOBAL_ACCOUNT_TAKE_PROFIT_ROI_PCT}%'}")
        
        timer_duration = SESSION_MAX_DURATION_MINUTES
        timer_action = SESSION_TIME_LIMIT_ACTION.upper()
        timer_status = f"Activado ({timer_duration} mins, Acción: {timer_action})" if timer_duration > 0 else "Desactivado"
        print(f"    Temporizador de Sesión   : {timer_status}")
        
        print(f"    Apalancamiento           : {POSITION_LEVERAGE:.1f}x")
    print("-" * 70)

# Carga UIDs al importar el módulo
_load_and_validate_uids()