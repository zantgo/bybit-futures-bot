# core/strategy/signal/_generator.py

"""
Módulo Generador de Señales (Orquestador).

Su única responsabilidad es coordinar el proceso de generación de señales:
1. Utiliza `_data_handler` para extraer y validar los datos de entrada.
2. Utiliza `_rules` para evaluar la lógica de la estrategia.
3. Utiliza `_data_handler` para construir el diccionario de salida final.
"""
from typing import Dict, Any
import pandas as pd

# Dependencias del proyecto y del paquete
import config
from . import _data_handler
from . import _rules

def generate_signal(processed_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Orquesta la evaluación de indicadores técnicos para generar una señal de trading.

    Args:
        processed_data (dict): Un diccionario que contiene los indicadores calculados.

    Returns:
        dict: Un diccionario completo representando la señal y el estado de los indicadores.
    """
    # 1. Extraer y validar los datos de entrada
    (timestamp, price, ema, inc_pct, dec_pct, w_inc, w_dec) = _data_handler.extract_indicator_values(processed_data)

    # Validación básica de datos
    if pd.isna(timestamp) or pd.isna(price):
        signal = "HOLD_INVALID_DATA"
        reason = "Timestamp o Precio inválido en los datos procesados"
    
    # 2. Evaluar la lógica de la estrategia (si está habilitada)
    elif config.STRATEGY_ENABLED:
        signal, reason = _rules.evaluate_strategy(price, ema, inc_pct, dec_pct, w_inc, w_dec)
    
    else:
        signal = "HOLD_STRATEGY_DISABLED"
        reason = "Estrategia desactivada en config.py"

    # 3. Construir el diccionario de salida
    return _data_handler.build_signal_dict(
        timestamp, price, ema, inc_pct, dec_pct, w_inc, w_dec, signal, reason
    )