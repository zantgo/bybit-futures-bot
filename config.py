"""
Configuración Esencial para el Bot de Trading.

Este archivo centraliza todos los parámetros configurables. Ha sido refactorizado
para eliminar redundancias y mejorar la claridad de los nombres de las variables.
"""
import os
import sys
from dotenv import load_dotenv, find_dotenv

# --- Define project root dinámicamente ---
try:
    # Esto funcionará cuando se ejecute desde main.py en la raíz
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # Fallback si __file__ no está definido (ej. en un entorno interactivo)
    PROJECT_ROOT = os.path.abspath(os.getcwd())
    print(f"Advertencia [config]: __file__ no definido, usando CWD como PROJECT_ROOT: {PROJECT_ROOT}")

# --- Exchange Configuration (NUEVO) ---
# Define qué adaptador de exchange cargar. Opciones: "bybit"
EXCHANGE_NAME = "bybit"

# --- Log Level Configuration ---
# Define el nivel de detalle de los logs. Opciones: "DEBUG", "INFO", "WARN", "ERROR"
LOG_LEVEL = "INFO"

# --- Account Configuration ---
ACCOUNT_MAIN = "main"
ACCOUNT_LONGS = "longs"
ACCOUNT_SHORTS = "shorts"
ACCOUNT_PROFIT = "profit"

# --- API Key & UID Mapping (desde .env) ---
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

# --- General API Settings ---
UNIVERSAL_TESTNET_MODE = False
DEFAULT_RECV_WINDOW = 30000

# --- Live Ticker Settings ---
TICKER_SYMBOL = "BTCUSDT" # Símbolo por defecto, se puede cambiar en el wizard
TICKER_INTERVAL_SECONDS = 1
TICKER_SOURCE_ACCOUNT = ACCOUNT_PROFIT

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
POSITION_BASE_SIZE_USDT = 1.0
POSITION_MAX_LOGICAL_POSITIONS = 5
POSITION_LEVERAGE = 10.0
POSITION_MIN_PRICE_DIFF_LONG_PCT = -0.25
POSITION_MIN_PRICE_DIFF_SHORT_PCT = 0.25
POSITION_REINVEST_PROFIT_PCT = 10.0
POSITION_MIN_TRANSFER_AMOUNT_USDT = 0.001
POSITION_COMMISSION_RATE = 0.001

#-- Risk Management: Default Trend & Position Parameters ---
# Estos son los valores por defecto que se mostrarán en la TUI al crear un nuevo Hito.

# Defaults para el Riesgo de Posiciones Individuales (dentro de una tendencia)
DEFAULT_TREND_INDIVIDUAL_SL_PCT = 10.0
DEFAULT_TREND_TS_ACTIVATION_PCT = 0.4
DEFAULT_TREND_TS_DISTANCE_PCT = 0.1

# Defaults para los Límites de Finalización de Tendencia
DEFAULT_TREND_LIMIT_TRADE_COUNT = 0     # 0 para ilimitado
DEFAULT_TREND_LIMIT_DURATION_MINUTES = 0 # 0 para ilimitado
DEFAULT_TREND_LIMIT_TP_ROI_PCT = 2.5    # 0 para desactivado
DEFAULT_TREND_LIMIT_SL_ROI_PCT = -1.5   # 0 para desactivado. ¡Nota: Debe ser negativo!

# --- Session Limits (Circuit Breakers) ---
SESSION_STOP_LOSS_ROI_PCT = 20.0
SESSION_TAKE_PROFIT_ROI_PCT = 10.0
SESSION_MAX_DURATION_MINUTES = 0
SESSION_TIME_LIMIT_ACTION = "NEUTRAL" # "NEUTRAL" o "STOP"

SESSION_ROI_SL_ENABLED = True
SESSION_ROI_TP_ENABLED = True

# --- Printing / Logging Configuration ---
POSITION_LOG_CLOSED_POSITIONS = True
POSITION_PRINT_POSITION_UPDATES = True
POSITION_LOG_OPEN_SNAPSHOT = True
LOG_SIGNAL_OUTPUT = True

# --- Fallbacks y Constantes ---
DEFAULT_QTY_PRECISION = 3
DEFAULT_MIN_ORDER_QTY = 0.001
PRICE_PRECISION = 4
PNL_PRECISION = 4
CATEGORY_LINEAR = "linear"
BYBIT_HEDGE_MODE_ENABLED = True
UNIVERSAL_TRANSFER_FROM_TYPE = "UNIFIED"
UNIVERSAL_TRANSFER_TO_TYPE = "UNIFIED"

# --- Paths (Directorios y Archivos) ---
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
SIGNAL_LOG_FILE = os.path.join(LOG_DIR, "signals_log.jsonl")
POSITION_CLOSED_LOG_FILE = os.path.join(LOG_DIR, "closed_positions.jsonl")
POSITION_OPEN_SNAPSHOT_FILE = os.path.join(LOG_DIR, "open_positions_snapshot.jsonl")
os.makedirs(LOG_DIR, exist_ok=True)

# --- UID Management ---
LOADED_UIDS = {}

# EN: ./config.py

def _load_and_validate_uids():
    """
    Carga y valida los UIDs desde el .env.
    --- VERSIÓN MODIFICADA: Detiene el programa si el .env o los UIDs faltan. ---
    """
    global LOADED_UIDS
    all_uids_valid = True
    required_uids_map = ACCOUNT_UID_ENV_VAR_MAP
    
    try:
        # <-- CAMBIO CLAVE: raise_error_if_not_found ahora es True
        env_path = find_dotenv(filename='.env', raise_error_if_not_found=True, usecwd=True)
        load_dotenv(dotenv_path=env_path, override=True)
    except IOError:
        # <-- CAMBIO CLAVE: Manejo explícito del error si el .env no se encuentra
        print("="*80)
        print("!!! ERROR FATAL: No se encontró el archivo de configuración de entorno '.env' !!!")
        print("Este archivo es OBLIGATORIO para las claves API y los UIDs.")
        print("Por favor, crea un archivo .env en la raíz del proyecto y reinicia el bot.")
        print("="*80)
        sys.exit(1) # Detiene el programa inmediatamente
    except Exception as e:
        print(f"ERROR [config]: Excepción inesperada cargando .env: {e}")
        sys.exit(1)

    if not required_uids_map: 
        return True
    
    loaded_temp = {}
    print("Validando UIDs desde .env...")
    for account_name, env_var_name in required_uids_map.items():
        uid_value = os.getenv(env_var_name)
        if uid_value is None or not uid_value.strip().isdigit():
             print(f"  -> ERROR: UID inválido/faltante para '{account_name}' (Variable de entorno: {env_var_name})")
             all_uids_valid = False
        else:
             loaded_temp[account_name] = uid_value.strip()

    if all_uids_valid:
        LOADED_UIDS = loaded_temp
        print(f"  -> Validación de UIDs OK. Cargados para: {list(LOADED_UIDS.keys())}")
        return True
    else:
        # <-- CAMBIO CLAVE: Detiene el programa si los UIDs son inválidos
        print("="*80)
        print("!!! ERROR FATAL: Faltan o son inválidos UIDs para transferencias API en el archivo .env !!!")
        print("El bot no puede continuar de forma segura sin esta configuración.")
        print("="*80)
        sys.exit(1)
        
# --- Función de Impresión de Configuración ---
def print_initial_config(operation_mode="unknown"):
    """Imprime un resumen de la configuración cargada."""
    print("-" * 70)
    print(f"Configuración Base Cargada (Modo: {operation_mode})".center(70))
    print(f"  Exchange Seleccionado   : {EXCHANGE_NAME.upper()}")
    print(f"  Modo Testnet API        : {UNIVERSAL_TESTNET_MODE}")
    print(f"  Ticker Símbolo (Default): {TICKER_SYMBOL}")
    print(f"  Intervalo de Estrategia : {TICKER_INTERVAL_SECONDS} segundos")
    print("-" * 70)
    pos_enabled = POSITION_MANAGEMENT_ENABLED
    print(f"  Gestión Posiciones      : {'Activada' if pos_enabled else 'Desactivada'}")
    if pos_enabled:
        # Actualizamos para reflejar los nuevos nombres de variables
        print(f"    Stop Loss Individual    : {DEFAULT_TREND_INDIVIDUAL_SL_PCT}% (Default)")
        print(f"    Trailing Stop           : Act {DEFAULT_TREND_TS_ACTIVATION_PCT}% / Dist {DEFAULT_TREND_TS_DISTANCE_PCT}% (Default)")
        print(f"    Stop Loss de Sesión     : {'Desactivado' if not SESSION_ROI_SL_ENABLED else f'-{SESSION_STOP_LOSS_ROI_PCT}%'}")
        print(f"    Take Profit de Sesión   : {'Desactivado' if not SESSION_ROI_TP_ENABLED else f'+{SESSION_TAKE_PROFIT_ROI_PCT}%'}")
        print(f"    Apalancamiento          : {POSITION_LEVERAGE:.1f}x")
    print("-" * 70)

# Carga UIDs al importar el módulo
_load_and_validate_uids()
