"""
Configuración Esencial para el Bot de Trading.

v6.0 (Reestructuración a Diccionarios):
- Todos los parámetros configurables se han organizado en diccionarios anidados
  (BOT, SESSION, OPERATION_DEFAULTS) para mejorar la claridad y la mantenibilidad.
- Se eliminan variables redundantes y se agrupan lógicamente los parámetros.
"""
import os
import sys
from dotenv import load_dotenv, find_dotenv

# --- 1. CONFIGURACIÓN GENERAL DEL BOT (Parámetros que no cambian durante una sesión) ---

BOT_CONFIG = {
    "LOG_LEVEL": "INFO",
    "EXCHANGE_NAME": "bybit",
    "PAPER_TRADING_MODE": False,
    "UNIVERSAL_TESTNET_MODE": False,

    # Parámetros del Ticker (el símbolo puede ser sobreescrito por la TUI)
    "TICKER": {
        "SYMBOL": "BTCUSDT",
        "SOURCE_ACCOUNT": "profit"
    },
    
    # Mapeo de cuentas y credenciales (leído desde .env)
    "ACCOUNTS": {
        "MAIN": "main",
        "LONGS": "longs",
        "SHORTS": "shorts",
        "PROFIT": "profit",
    },

    "API_KEYS_ENV_MAP": {
        "main":   ("BYBIT_MAIN_API_KEY", "BYBIT_MAIN_API_SECRET"),
        "longs":  ("BYBIT_LONGS_API_KEY", "BYBIT_LONGS_API_SECRET"),
        "shorts": ("BYBIT_SHORTS_API_KEY", "BYBIT_SHORTS_API_SECRET"),
        "profit": ("BYBIT_PROFIT_API_KEY", "BYBIT_PROFIT_API_SECRET"),
    },

    "UID_ENV_VAR_MAP": {
        "longs": "BYBIT_LONGS_UID",
        "shorts": "BYBIT_SHORTS_UID",
        "profit": "BYBIT_PROFIT_UID",
    },

    "LOGGING": {
        "LOG_SIGNAL_OUTPUT": True,
        "LOG_CLOSED_POSITIONS": True,
        "LOG_OPEN_SNAPSHOT": True,
        "TUI_LOG_VIEWER_MAX_LINES": 1000,
    }
}

# --- 2. CONFIGURACIÓN DE LA SESIÓN (Parámetros que se pueden cambiar en caliente) ---

SESSION_CONFIG = {
    # Intervalo del Ticker (en segundos)
    "TICKER_INTERVAL_SECONDS": 1,
    
    # Parámetros de Análisis Técnico (TA)
    "TA": {
        "ENABLED": True,
        "EMA_WINDOW": 50,
        "WEIGHTED_INC_WINDOW": 25,
        "WEIGHTED_DEC_WINDOW": 25,
    },

    # Parámetros de Generación de Señales
    "STRATEGY": {
        "ENABLED": True,
        "MARGIN_BUY": -0.1,
        "MARGIN_SELL": 0.1,
        "DECREMENT_THRESHOLD": 0.45,
        "INCREMENT_THRESHOLD": 0.45,
    },

    # Límites Globales de la Sesión (Disyuntores)
    "SESSION_LIMITS": {
        "ROI_SL": {
            "ENABLED": True,
            "PERCENTAGE": 20.0  # Siempre positivo, el código lo hará negativo
        },
        "ROI_TP": {
            "ENABLED": True,
            "PERCENTAGE": 10.0
        },
        "MAX_DURATION": {
            "MINUTES": 0,  # 0 para ilimitado
            "ACTION": "NEUTRAL"  # "NEUTRAL" o "STOP"
        }
    }
}

# --- 3. CONFIGURACIÓN POR DEFECTO PARA NUEVAS OPERACIONES ---
# Estos son los valores que la TUI usará como predeterminados al crear una
# nueva operación estratégica.

OPERATION_DEFAULTS = {
    "CAPITAL": {
        "BASE_SIZE_USDT": 1.0,
        "MAX_POSITIONS": 5,
        "LEVERAGE": 100.0,
    },
    "RISK": {
        "INDIVIDUAL_SL_PCT": 10.0,
        "TSL_ACTIVATION_PCT": 0.4,
        "TSL_DISTANCE_PCT": 0.1,
    },
    "PROFIT": {
        "REINVEST_PROFIT_PCT": 10.0,
        "COMMISSION_RATE": 0.001,
    },
    "LIMITS": {
        "MAX_TRADES": 0,            # 0 para ilimitado
        "DURATION_MINUTES": 0,      # 0 para ilimitado
        "TP_ROI_PCT": 2.5,          # 0 para desactivado
        "SL_ROI_PCT": 1.5,          # Siempre positivo, el código lo hará negativo
    }
}

# --- 4. CONSTANTES Y RUTAS (No deben ser modificadas por el usuario) ---

# Define el directorio raíz del proyecto dinámicamente
try:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    PROJECT_ROOT = os.path.abspath(os.getcwd())

# Constantes del Exchange
EXCHANGE_CONSTANTS = {
    "BYBIT": {
        "DEFAULT_RECV_WINDOW": 30000,
        "CATEGORY_LINEAR": "linear",
        "HEDGE_MODE_ENABLED": True,
        "UNIVERSAL_TRANSFER_FROM_TYPE": "UNIFIED",
        "UNIVERSAL_TRANSFER_TO_TYPE": "UNIFIED"
    }
}

# Fallbacks de Precisión
PRECISION_FALLBACKS = {
    "QTY_PRECISION": 3,
    "MIN_ORDER_QTY": 0.001,
    "PRICE_PRECISION": 4,
    "PNL_PRECISION": 4,
}

# Rutas de Archivos de Log
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILES = {
    "SIGNAL": os.path.join(LOG_DIR, "signals_log.jsonl"),
    "CLOSED_POSITIONS": os.path.join(LOG_DIR, "closed_positions.jsonl"),
    "OPEN_SNAPSHOT": os.path.join(LOG_DIR, "open_positions_snapshot.jsonl"),
}

# --- 5. LÓGICA DE CARGA DE ENTORNO (UIDs y Claves API) ---

# Variable global para almacenar UIDs cargados.
LOADED_UIDS = {}

def _load_and_validate_uids_and_keys():
    """
    Carga y valida las claves API y los UIDs desde el .env.
    Detiene el programa si faltan datos esenciales.
    """
    global LOADED_UIDS
    try:
        env_path = find_dotenv(filename='.env', raise_error_if_not_found=True, usecwd=True)
        load_dotenv(dotenv_path=env_path, override=True)
    except IOError:
        print("="*80)
        print("!!! ERROR FATAL: No se encontró el archivo de configuración de entorno '.env' !!!")
        print("Este archivo es OBLIGATORIO para las claves API y los UIDs.")
        print("="*80)
        sys.exit(1)

    # Validar Claves API
    print("Validando Claves API desde .env...")
    for account_name, (key_var, secret_var) in BOT_CONFIG["API_KEYS_ENV_MAP"].items():
        if not os.getenv(key_var) or not os.getenv(secret_var):
            print(f"  -> ERROR: Faltan claves API para '{account_name}' (Variables: {key_var}, {secret_var})")
            sys.exit(1)
    print("  -> Validación de Claves API OK.")

    # Validar UIDs
    print("Validando UIDs desde .env...")
    for account_name, uid_var in BOT_CONFIG["UID_ENV_VAR_MAP"].items():
        uid_value = os.getenv(uid_var)
        if not uid_value or not uid_value.strip().isdigit():
            print(f"  -> ERROR: UID inválido/faltante para '{account_name}' (Variable: {uid_var})")
            sys.exit(1)
        LOADED_UIDS[account_name] = uid_value.strip()
    print(f"  -> Validación de UIDs OK. Cargados para: {list(LOADED_UIDS.keys())}")

# Ejecutar la carga al importar el módulo
_load_and_validate_uids_and_keys()