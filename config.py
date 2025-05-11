# =============== INICIO ARCHIVO: config.py (RAÍZ v8.7.x - Lógica Tamaño Base Posición) ===============
"""
Configuración Esencial (v8.7.x - Lógica Tamaño Base Posición).
Parámetros para TA, Feeder, Logger, Plotter, conexiones Live y Gestión de Posiciones.
ASUME QUE ESTE ARCHIVO ESTÁ EN LA RAÍZ DEL PROYECTO.
"""
import os
import json
import sys
from dotenv import load_dotenv, find_dotenv # Importar find_dotenv aquí

# Define project root dinámicamente ASUMIENDO config.py ESTÁ EN LA RAÍZ
try:
    # Si __file__ es la ruta a config.py en la RAÍZ, dirname nos da la ruta a esa raíz.
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # Fallback si __file__ no está definido
    PROJECT_ROOT = os.path.abspath(os.getcwd())
    print(f"Advertencia [config]: __file__ no definido, usando CWD como PROJECT_ROOT: {PROJECT_ROOT}")

# --- Account Configuration (Requerido por live.connection.manager) ---
ACCOUNT_MAIN = "main"
ACCOUNT_LONGS = "longs"
ACCOUNT_SHORTS = "shorts"
ACCOUNT_PROFIT = "profit"

# --- API Key Mapping (Nombres de Variables de Entorno) ---
ACCOUNT_API_KEYS_ENV_MAP = {
    ACCOUNT_MAIN:   ("BYBIT_MAIN_API_KEY", "BYBIT_MAIN_API_SECRET"),
    ACCOUNT_LONGS:  ("BYBIT_LONGS_API_KEY", "BYBIT_LONGS_API_SECRET"),
    ACCOUNT_SHORTS: ("BYBIT_SHORTS_API_KEY", "BYBIT_SHORTS_API_SECRET"),
    ACCOUNT_PROFIT: ("BYBIT_PROFIT_API_KEY", "BYBIT_PROFIT_API_SECRET"),
}

# --- Subaccount UID Mapping (Nombres de Variables de Entorno) ---
ACCOUNT_UID_ENV_VAR_MAP = {
    ACCOUNT_LONGS: "BYBIT_LONGS_UID",
    ACCOUNT_SHORTS: "BYBIT_SHORTS_UID",
    ACCOUNT_PROFIT: "BYBIT_PROFIT_UID",
}

# --- Accounts to Initialize (Live Mode) ---
ACCOUNTS_TO_INITIALIZE = [
    ACCOUNT_MAIN,
    ACCOUNT_LONGS,
    ACCOUNT_SHORTS,
    ACCOUNT_PROFIT,
]


# --- General Settings ---
UNIVERSAL_TESTNET_MODE = False
DEFAULT_RECV_WINDOW = 30000

# --- Live Ticker / Backtest Feeder Settings ---
TICKER_SYMBOL = "BTCUSDT"
TICKER_INTERVAL_SECONDS = 60
TICKER_SOURCE_ACCOUNT = ACCOUNT_PROFIT

# --- Core Processing ---
RAW_PRICE_TICK_INTERVAL = 1

# --- Technical Analysis Configuration ---
TA_WINDOW_SIZE = 300
TA_EMA_WINDOW = 100 #
TA_WEIGHTED_INC_WINDOW = 50 #
TA_WEIGHTED_DEC_WINDOW = 50 #
TA_CALCULATE_PROCESSED_DATA = True

# --- Signal Generation Configuration ---
STRATEGY_ENABLED = True
STRATEGY_MARGIN_BUY = -0.3 #
STRATEGY_MARGIN_SELL = 0.3 #
STRATEGY_DECREMENT_THRESHOLD = 0.45 #
STRATEGY_INCREMENT_THRESHOLD = 0.45 #

# --- Position Management Configuration ---
POSITION_MANAGEMENT_ENABLED = True
POSITION_TRADING_MODE = "LONG_SHORT"        # Sobrescrito interactivamente
# ANTERIOR: POSITION_CAPITAL_USDT = 100.0
POSITION_BASE_SIZE_USDT = 100              # Tamaño base de margen (en USDT) para CADA posición lógica individual. Usado como fallback/default si no se define interactivamente.
POSITION_MAX_LOGICAL_POSITIONS = 1          # Número MÁXIMO INICIAL de posiciones lógicas (slots) por lado. Puede ser ajustado dinámicamente.
POSITION_LEVERAGE = 3.0 #
POSITION_TAKE_PROFIT_PCT_LONG = 0.5 #
POSITION_TAKE_PROFIT_PCT_SHORT = 0.5 #
POSITION_COMMISSION_RATE = 0.001
POSITION_REINVEST_PROFIT_PCT = 1.0 # Para 1% reinversión en margen operacional y 99% transferible a profit. (Anteriormente 0.01)
POSITION_MIN_TRANSFER_AMOUNT_USDT = 0.1
POSITION_LOG_CLOSED_POSITIONS = True
POSITION_PRINT_POSITION_UPDATES = True
POSITION_LOG_OPEN_SNAPSHOT = True
POSITION_SIGNAL_COOLDOWN_ENABLED = True
POSITION_SIGNAL_COOLDOWN_LONG = 3 #
POSITION_SIGNAL_COOLDOWN_SHORT = 3 #
POSITION_PRE_OPEN_SYNC_CHECK = True         # Chequeo físico antes de abrir en Live

# Nueva variable para el modo interactivo manual
INTERACTIVE_MANUAL_MODE = True # True para habilitar el menú de intervención manual en modo Live

# --- NUEVAS VARIABLES: Filtro de Distancia de Precio Mínima ---
POSITION_MIN_PRICE_DIFF_LONG_PCT = -0.5 #
POSITION_MIN_PRICE_DIFF_SHORT_PCT = 0.5 #
# --- FIN NUEVAS VARIABLES ---

# --- Logical Position Settings (OBSOLETO) ---
LOGICAL_POSITIONS_ENABLED = False           # DEPRECATED

# --- Fallbacks para Información del Instrumento ---
DEFAULT_QTY_PRECISION = 3
DEFAULT_MIN_ORDER_QTY = 0.001

# --- Precisiones de Formateo ---
PRICE_PRECISION = 4
PNL_PRECISION = 4

# --- Printing / Logging Configuration ---
PRINT_SIGNAL_OUTPUT = False
LOG_SIGNAL_OUTPUT = True
PRINT_RAW_EVENT_ALWAYS = False
PRINT_PROCESSED_DATA_ALWAYS = False
# PRINT_TICK_ALWAYS ahora no se usa
# PRINT_TICK_LIVE_STATUS se activa en live_runner

# --- Logging Configuration ---
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
SIGNAL_LOG_FILE = os.path.join(LOG_DIR, "signals_log.jsonl")
POSITION_CLOSED_LOG_FILE = os.path.join(LOG_DIR, "closed_positions.jsonl")
POSITION_OPEN_SNAPSHOT_FILE = os.path.join(LOG_DIR, "open_positions_snapshot.jsonl")
os.makedirs(LOG_DIR, exist_ok=True)

# --- Backtesting Configuration ---
BACKTEST_DATA_DIR = os.path.join(PROJECT_ROOT, "data")
BACKTEST_CSV_FILE = "data.csv"
BACKTEST_CSV_TIMESTAMP_COL = "timestamp"
BACKTEST_CSV_PRICE_COL = "close"

# --- Visualization / Results Configuration ---
RESULT_DIR = os.path.join(PROJECT_ROOT, "result")
PLOT_OUTPUT_FILENAME = f"plot_{TICKER_SYMBOL}.png" # Será sobreescrito/ajustado en runner
RESULTS_FILENAME = "results.txt"
RESULTS_FILEPATH = os.path.join(RESULT_DIR, RESULTS_FILENAME)
os.makedirs(RESULT_DIR, exist_ok=True)

# --- API Constants ---
CATEGORY_LINEAR = "linear"
CATEGORY_SPOT = "spot"
UNIVERSAL_TRANSFER_FROM_TYPE = "UNIFIED"
UNIVERSAL_TRANSFER_TO_TYPE = "UNIFIED"

# --- Cached UIDs ---
LOADED_UIDS = {} # Se poblará por _load_and_validate_uids

# --- Validation Function ---
def _load_and_validate_uids():
    """Carga y valida UIDs desde .env. Se llama automáticamente al final."""
    global LOADED_UIDS
    all_uids_valid = True
    required_uids_map = ACCOUNT_UID_ENV_VAR_MAP

    try:
        env_path = find_dotenv(filename='.env', raise_error_if_not_found=False, usecwd=True)
        if env_path:
            load_dotenv(dotenv_path=env_path, override=True)
        else:
            if any(arg.startswith('live') for arg in sys.argv[1:] if isinstance(arg, str)):
                print("ADVERTENCIA [config]: .env no encontrado (necesario para UIDs en live).")
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

# --- Initial Configuration Printouts (Función) ---
def print_initial_config(operation_mode="unknown"):
    """Imprime un resumen de la configuración cargada."""
    # Referenciar la nueva variable POSITION_BASE_SIZE_USDT
    print("-" * 70); print(f"Configuración Base Cargada (config.py v8.7.x - Lógica Tamaño Base)");
    print(f"  Proyecto Root Detectado: {PROJECT_ROOT}");
    print(f"  Modo Testnet API        : {UNIVERSAL_TESTNET_MODE}")
    print(f"  Cuentas Live a Init.    : {ACCOUNTS_TO_INITIALIZE}")
    print(f"  UIDs Cargados           : {'Sí (' + ', '.join(LOADED_UIDS.keys()) + ')' if LOADED_UIDS else 'No (Verifica .env o errores)'}")
    print("-" * 70)
    print(f"  Ticker Símbolo          : {TICKER_SYMBOL}")
    print(f"  Fuente Ticker API       : {TICKER_SOURCE_ACCOUNT}")
    print(f"  Intervalo Ticker        : {TICKER_INTERVAL_SECONDS}s")
    print(f"  Evento Core cada        : {RAW_PRICE_TICK_INTERVAL} ticks (Efectivo: {TICKER_INTERVAL_SECONDS * RAW_PRICE_TICK_INTERVAL}s)")
    print("-" * 70)
    print(f"  Config TA:")
    print(f"    Ventana Max Historial : {TA_WINDOW_SIZE}")
    print(f"    Periodo EMA           : {TA_EMA_WINDOW}")
    print(f"    Periodo Inc/Dec WMA   : {TA_WEIGHTED_INC_WINDOW} / {TA_WEIGHTED_DEC_WINDOW}")
    print(f"    Cálculo Indicadores   : {'Activado' if TA_CALCULATE_PROCESSED_DATA else 'Desactivado'}")
    print("-" * 70)
    print(f"  Generación Señales      : {'Activada' if STRATEGY_ENABLED else 'Desactivada'}")
    if STRATEGY_ENABLED:
        print(f"    Margen (%) Buy / Sell : {STRATEGY_MARGIN_BUY * 100:.3f}% / {STRATEGY_MARGIN_SELL * 100:.3f}%") # Ajustado a 3 decimales para el margen
        print(f"    Umbral WMA Dec / Inc  : {STRATEGY_DECREMENT_THRESHOLD:.3f} / {STRATEGY_INCREMENT_THRESHOLD:.3f}")
    print("-" * 70)
    pos_enabled = POSITION_MANAGEMENT_ENABLED
    print(f"  Gestión Posiciones Base : {'Activada' if pos_enabled else 'Desactivada'}")
    if pos_enabled:
        print(f"    Modo Interactivo Manual: {'Activado' if INTERACTIVE_MANUAL_MODE else 'Desactivado'}")
        # Mostrar la nueva variable y su significado
        print(f"    Tamaño Base por Posición (Config): {POSITION_BASE_SIZE_USDT:.2f} USDT (Default/Fallback)")
        print(f"    Apalancamiento        : {POSITION_LEVERAGE:.1f}x")
        print(f"    Max Pos Lógicas Inicial (Config): {POSITION_MAX_LOGICAL_POSITIONS} (por lado, Default/Fallback)")
        print(f"    TP % (L/S)            : {POSITION_TAKE_PROFIT_PCT_LONG * 100:.2f}% / {POSITION_TAKE_PROFIT_PCT_SHORT * 100:.2f}%")
        print(f"    Comisión Estimada (%) : {POSITION_COMMISSION_RATE * 100:.3f}%")
        print(f"    Reinvertir PNL Operacional %: {POSITION_REINVEST_PROFIT_PCT:.2f}%") # Ajustado a .2f para mostrar 1.00%
        print(f"    Transferir PNL Neto > : {POSITION_MIN_TRANSFER_AMOUNT_USDT:.2f} USDT a '{ACCOUNT_PROFIT}'")
        print(f"    Chequeo Sync Pre-Open : {'Activado' if POSITION_PRE_OPEN_SYNC_CHECK else 'Desactivado'}")
        cooldown_enabled = POSITION_SIGNAL_COOLDOWN_ENABLED
        print(f"    Cooldown Señales      : {'Activado' if cooldown_enabled else 'Desactivado'}")
        if cooldown_enabled: print(f"      -> Periodo L/S: {POSITION_SIGNAL_COOLDOWN_LONG} / {POSITION_SIGNAL_COOLDOWN_SHORT} eventos")
        print(f"    Filtro Distancia Precio: Activado (si hay pos previas)")
        print(f"      -> Dif. Mín (%) L/S : {POSITION_MIN_PRICE_DIFF_LONG_PCT:.2f}% / {POSITION_MIN_PRICE_DIFF_SHORT_PCT:.2f}%")
        print(f"    Log Pos Cerradas      : {POSITION_LOG_CLOSED_POSITIONS}")
        print(f"    Log Snap Abiertas     : {POSITION_LOG_OPEN_SNAPSHOT}")
        print(f"    Imprimir Updates Pos  : {POSITION_PRINT_POSITION_UPDATES}")
    print("-" * 70)
    print(f"  Logging:")
    print(f"    Directorio Logs       : {LOG_DIR}")
    print(f"    Log Señales Archivo   : {LOG_SIGNAL_OUTPUT} ({os.path.basename(SIGNAL_LOG_FILE)})")
    print(f"    Imprimir Señal Consola: {PRINT_SIGNAL_OUTPUT}")
    print(f"    Imprimir Raw Event    : {PRINT_RAW_EVENT_ALWAYS}")
    print(f"    Imprimir Proc. Data   : {PRINT_PROCESSED_DATA_ALWAYS}")
    print("-" * 70)
    print(f"  Backtesting:")
    print(f"    Directorio Datos      : {BACKTEST_DATA_DIR}")
    print(f"    Archivo CSV           : {BACKTEST_CSV_FILE}")
    print(f"    Cols Timestamp/Precio : {BACKTEST_CSV_TIMESTAMP_COL} / {BACKTEST_CSV_PRICE_COL}")
    print("-" * 70)
    print(f"  Resultados:")
    print(f"    Directorio Resultados : {RESULT_DIR}")
    print(f"    Archivo Reporte TXT   : {RESULTS_FILENAME}")
    print("-" * 70)

# --- Carga UIDs al importar (Importante para Live) ---
_load_and_validate_uids()

# =============== FIN ARCHIVO: config.py (RAÍZ v8.7.x - Lógica Tamaño Base Posición) ===============
