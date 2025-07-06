# =============== INICIO ARCHIVO: config.py (v13 - Modo Automático y SL Físico) ===============
"""
Configuración Esencial (v13 - Modo Automático, SL Físico, Menú Mejorado).
Parámetros para TA, Feeder, Logger, Plotter, conexiones Live y Gestión de Posiciones.
ASUME QUE ESTE ARCHIVO ESTÁ EN LA RAÍZ DEL PROYECTO.
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
TICKER_SYMBOL = "BTCUSDT"
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
# 'LONG_SHORT', 'LONG_ONLY', 'SHORT_ONLY' son para modo interactivo.
# 'NEUTRAL' es un estado de espera. El modo automático gestionará este valor dinámicamente.
POSITION_TRADING_MODE = "LONG_SHORT"
POSITION_BASE_SIZE_USDT = 5.0
POSITION_MAX_LOGICAL_POSITIONS = 10
POSITION_LEVERAGE = 3.0
POSITION_TAKE_PROFIT_PCT_LONG = 0.3
POSITION_TAKE_PROFIT_PCT_SHORT = 0.3
POSITION_COMMISSION_RATE = 0.001
POSITION_REINVEST_PROFIT_PCT = 0.2
POSITION_MIN_TRANSFER_AMOUNT_USDT = 0.001

# --- Stop Loss Físico (NUEVO) ---
# Porcentaje de pérdida sobre el margen inicial AGREGADO de la posición física
# que activará el cierre de todas las posiciones de ese lado.
POSITION_PHYSICAL_STOP_LOSS_PCT = 5.0 # 5% de Stop Loss

# --- Filtros, Delays y Cooldown ---
POSITION_SIGNAL_COOLDOWN_ENABLED = True
POSITION_SIGNAL_COOLDOWN_LONG = 0
POSITION_SIGNAL_COOLDOWN_SHORT = 0
POSITION_PRE_OPEN_SYNC_CHECK = False
POSITION_MIN_PRICE_DIFF_LONG_PCT = -0.25
POSITION_MIN_PRICE_DIFF_SHORT_PCT = 0.25
POST_ORDER_CONFIRMATION_DELAY_SECONDS = 0.1
POST_CLOSE_SYNC_DELAY_SECONDS = 0.1

# --- Modos de Operación y Control ---
INTERACTIVE_MANUAL_MODE = True # Habilita el menú de intervención con 'm'

# --- AUTOMATIC MODE & UT BOT CONFIGURATION (NUEVO) ---
# True para ejecutar este modo desde main.py. Anula los menús de selección de modo.
AUTOMATIC_MODE_ENABLED = False

# Intervalo en segundos para que el UT Bot genere una nueva señal de alto nivel.
# Cada 3600 ticks de 1 segundo = 1 hora.
UT_BOT_SIGNAL_INTERVAL_SECONDS = 3600

# Parámetros específicos para la lógica del indicador UT Bot Alerts.
UT_BOT_KEY_VALUE = 1.0  # a.k.a. "Sensitivity"
UT_BOT_ATR_PERIOD = 10  # Periodo del ATR

# Define el comportamiento al recibir una señal de "flip" (cambio de dirección).
# True: Cierra posiciones actuales y abre el mismo número en la dirección opuesta.
# False: Solo cierra las posiciones actuales y espera que el bot de bajo nivel abra nuevas.
AUTOMATIC_FLIP_OPENS_NEW_POSITIONS = True

# Período de enfriamiento en segundos después de que salte un Stop Loss,
# antes de que el bot vuelva a aceptar señales del UT Bot.
AUTOMATIC_SL_COOLDOWN_SECONDS = 900 # 15 minutos

# --- Printing / Logging Configuration ---
POSITION_LOG_CLOSED_POSITIONS = True
POSITION_PRINT_POSITION_UPDATES = True
POSITION_LOG_OPEN_SNAPSHOT = True
PRINT_SIGNAL_OUTPUT = False
LOG_SIGNAL_OUTPUT = True
PRINT_RAW_EVENT_ALWAYS = False
PRINT_PROCESSED_DATA_ALWAYS = False
# PRINT_TICK_LIVE_STATUS se controla ahora dinámicamente desde el menú

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
BACKTEST_CSV_PRICE_COL = "close"

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

# --- Función de Impresión de Configuración (se mantiene para depuración) ---
def print_initial_config(operation_mode="unknown"):
    """Imprime un resumen de la configuración cargada."""
    print("-" * 70); print(f"Configuración Base Cargada (config.py v13)");
    print(f"  Modo Testnet API        : {UNIVERSAL_TESTNET_MODE}")
    print(f"  Ticker Símbolo          : {TICKER_SYMBOL}")
    print("-" * 70)
    pos_enabled = POSITION_MANAGEMENT_ENABLED
    print(f"  Gestión Posiciones Base : {'Activada' if pos_enabled else 'Desactivada'}")
    if pos_enabled:
        print(f"    Modo Automático por Defecto: {'Activado' if AUTOMATIC_MODE_ENABLED else 'Desactivado'}")
        print(f"    Stop Loss Físico (%)  : {POSITION_PHYSICAL_STOP_LOSS_PCT}%")
        print(f"    Apalancamiento        : {POSITION_LEVERAGE:.1f}x")
        print(f"    TP % (L/S)            : {POSITION_TAKE_PROFIT_PCT_LONG * 100:.2f}% / {POSITION_TAKE_PROFIT_PCT_SHORT * 100:.2f}%")
    print("-" * 70)

# Carga UIDs al importar el módulo
_load_and_validate_uids()

# =============== FIN ARCHIVO: config.py (v13 - Modo Automático y SL Físico) ===============