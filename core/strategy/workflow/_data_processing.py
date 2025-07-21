# core/strategy/workflow/_data_processing.py

"""
Módulo para el Procesamiento de Datos y Generación de Señales.

Responsabilidad: Orquestar el flujo de datos de un tick a través de las
capas de Análisis Técnico (TA) y Generación de Señales, y registrar
la señal resultante.
"""
import sys
import os
import datetime
import traceback
import pandas as pd
import numpy as np
import json
from typing import Dict, Any, Optional

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias con rutas absolutas desde la raíz del proyecto
try:
    import config
    from core import utils
    from core.logging import memory_logger, signal_logger
    from core.strategy import ta, signal
except ImportError as e:
    print(f"ERROR [Workflow Data Processing Import]: Falló importación de dependencias: {e}")
    config = None; utils = None; memory_logger = None; signal_logger = None
    ta = None; signal = None

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Estado del Módulo ---
# Este estado es necesario para calcular increment/decrement
_previous_raw_event_price = np.nan
_is_first_event = True

def initialize_data_processing():
    """Resetea el estado interno del procesador de datos."""
    global _previous_raw_event_price, _is_first_event
    _previous_raw_event_price = np.nan
    _is_first_event = True


def process_tick_and_generate_signal(
    current_timestamp: datetime.datetime,
    current_price: float
) -> Optional[Dict[str, Any]]:
    """
    Procesa un tick, calcula TA, genera y registra una señal.

    Args:
        current_timestamp: El timestamp del tick.
        current_price: El precio del tick.

    Returns:
        Un diccionario con los datos de la señal, o None si hay un error.
    """
    global _previous_raw_event_price, _is_first_event

    if not all([config, utils, memory_logger, ta, signal]):
        print("ERROR CRÍTICO [Data Processing]: Faltan módulos esenciales.")
        return None

    # 1. Calcular incremento/decremento
    increment = 0
    decrement = 0
    if not _is_first_event and pd.notna(_previous_raw_event_price):
        if current_price > _previous_raw_event_price + 1e-9:
            increment = 1
        elif current_price < _previous_raw_event_price - 1e-9:
            decrement = 1
    _is_first_event = False

    raw_price_event = {
        'timestamp': current_timestamp,
        'price': current_price,
        'increment': increment,
        'decrement': decrement
    }

    # 2. Procesar a través del TA Manager
    processed_data = None
    if getattr(config, 'TA_CALCULATE_PROCESSED_DATA', True):
        try:
            processed_data = ta.process_raw_price_event(raw_price_event.copy())
        except Exception as e_ta:
            memory_logger.log(f"Error en llamada a TA Manager: {e_ta}", level="ERROR")
            memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")

    # 3. Generar la señal
    signal_data = None
    nan_fmt = "NaN"
    base_signal_dict = {
        "timestamp": utils.format_datetime(current_timestamp),
        "price_float": current_price,
        "price": f"{current_price:.{getattr(config, 'PRICE_PRECISION', 4)}f}",
        "ema": nan_fmt, "inc_price_change_pct": nan_fmt, "dec_price_change_pct": nan_fmt,
        "weighted_increment": nan_fmt, "weighted_decrement": nan_fmt
    }

    try:
        if getattr(config, 'STRATEGY_ENABLED', True):
            if processed_data:
                signal_data = signal.generate_signal(processed_data.copy())
            else:
                signal_data = {**base_signal_dict, "signal": "HOLD_NO_TA", "signal_reason": "No TA data"}
        else:
            signal_data = {**base_signal_dict, "signal": "HOLD_STRATEGY_DISABLED", "signal_reason": "Strategy disabled"}
    except Exception as e_signal:
        memory_logger.log(f"ERROR en Signal Generator: {e_signal}", level="ERROR")
        memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")
        signal_data = {**base_signal_dict, "signal": "HOLD_SIGNAL_ERROR", "signal_reason": f"Error: {e_signal}"}

    # 4. Registrar la señal (si está habilitado)
    if signal_data and signal_logger and getattr(config, 'LOG_SIGNAL_OUTPUT', False):
        try:
            signal_logger.log_signal_event(signal_data.copy())
        except Exception as e_log_write:
            memory_logger.log(f"ERROR al escribir en signal log: {e_log_write}", level="ERROR")

    # 5. Actualizar el precio anterior para el siguiente tick
    _previous_raw_event_price = current_price

    return signal_data