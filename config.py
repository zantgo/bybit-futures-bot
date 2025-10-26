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
        "EMA_WINDOW": 200,  
        "WEIGHTED_INC_WINDOW": 100, 
        "WEIGHTED_DEC_WINDOW": 100,  
    },

    # Parámetros de Generación de Señales
    "SIGNAL": {
        "ENABLED": True, 
        "PRICE_CHANGE_BUY_PERCENTAGE": -0.05,
        "PRICE_CHANGE_SELL_PERCENTAGE": 0.05,
        "WEIGHTED_DECREMENT_THRESHOLD": 0.25,
        "WEIGHTED_INCREMENT_THRESHOLD": 0.25,
    },

    # Parámetros de Ganancias
    "PROFIT": {
        "COMMISSION_RATE": 0.001,
        "REINVEST_PROFIT_PCT": 1.0,
        "MIN_TRANSFER_AMOUNT_USDT": 0.001, 
        "SLIPPAGE_PCT": 0.0005, 
    },

    # --- INICIO DE LA MODIFICACIÓN ---
    # Parámetros de Riesgo de la Sesión
    "RISK": {
        "MAINTENANCE_MARGIN_RATE": 0.005,
        "MAX_SYNC_FAILURES": 10000,
    },
    # --- FIN DE LA MODIFICACIÓN ---
}

# --- 3. CONFIGURACIÓN POR DEFECTO PARA NUEVAS OPERACIONES ---
# Estos son los valores que la TUI usará como predeterminados al crear una
# nueva operación estratégica.

OPERATION_DEFAULTS = {
    "CAPITAL": {
        "BASE_SIZE_USDT": 100.0,
        "MAX_POSITIONS": 100,
        "LEVERAGE": 4.0,
    },
    "RISK": {
        "INDIVIDUAL_SL": {
            "ENABLED": True, 
            "PERCENTAGE": 50.0, 
        },
        "INDIVIDUAL_TSL": {
            "ENABLED": True, 
            "TSL_ACTIVATION_PCT": 0.5,
            "TSL_DISTANCE_PCT": 0.05,
        },
        "AVERAGING": {
            "ENABLED": True, 
            "DISTANCE_PCT_LONG": 0.5,
            "DISTANCE_PCT_SHORT": 0.5,
        },
    },
    # Parámetros de RIESGO a nivel de OPERACIÓN COMPLETA.
    # La acción al cumplirse (PAUSAR o DETENER) se configura en el config.py
    "OPERATION_RISK": {
        "AFTER_STATE": 'DETENER', # PAUSAR O DETENER DEFAULT PARA TODOS LOS RIESGOS SE PUEDE EDITAR EN LA TUI
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se separan SL y TP en diccionarios independientes
        "ROI_SL": {
            "ENABLED": False,
            "PERCENTAGE": -25.0 # Valor negativo para Stop Loss
        },
        "ROI_TP": {
            "ENABLED": False,
            "PERCENTAGE": 50.0 # Valor positivo para Take Profit
        },
        # --- FIN DE LA MODIFICACIÓN ---
        "ROI_TSL": {
            "ENABLED": False,
            "ACTIVATION_PCT": 25.0,
            "DISTANCE_PCT": 5.0,
        },
        "DYNAMIC_ROI_SL": {
            "ENABLED": False, # Por defecto, está desactivado.
            "TRAIL_PCT": 50.0 # El valor a restar del ROI realizado. (ej. ROI 20% - 10% = SL/TP en +10%)
        },
                # --- INICIO DE LA MODIFICACIÓN ---
        "BE_SL_TP": { # <-- NUEVO DICCIONARIO
            "ENABLED": False,
            "SL_DISTANCE_PCT": 10.0,
            "TP_DISTANCE_PCT": 20.0,
        },
        # --- FIN DE LA MODIFICACIÓN ---
    },
    # Parámetros de LÍMITES OPERATIVOS.
    # La acción al cumplirse (PAUSAR o DETENER) es configurable en la TUI.
    "OPERATION_LIMITS": {
        "AFTER_STATE": 'PAUSAR', # PAUSAR O DETENER
        "MAX_TRADES": {
            "ENABLED": False,
            "VALUE": 1000,
        },
        "MAX_DURATION": {
            "ENABLED": False,
            "MINUTES": 1440 # 24 hrs
        },
    },

    "PROFIT_MANAGEMENT": {
        "AUTO_REINVEST_ENABLED": True,
        },
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
    "MAINTENANCE_MARGIN_RATE": 0.005 #0.02 # Tasa de Margen de Mantenimiento (ej. 1% = 0.01). Ajusta este valor si es necesario.
}

# Rutas de Archivos de Log y Resultados
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

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