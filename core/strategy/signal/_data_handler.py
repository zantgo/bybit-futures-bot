# core/strategy/signal/_data_handler.py

"""
Módulo de Manejo de Datos para la Generación de Señales.

Responsabilidades:
- Extraer y validar los datos numéricos de los indicadores desde el diccionario de entrada.
- Formatear los datos numéricos y la señal final en un diccionario de salida legible.
"""
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np

# Dependencias del proyecto
from core import utils

def extract_indicator_values(processed_data: Dict[str, Any]) -> Tuple:
    """
    Extrae los valores numéricos de los indicadores del diccionario de entrada.
    
    Returns:
        Una tupla con todos los valores extraídos, usando NaN como default.
    """
    timestamp = processed_data.get('timestamp', pd.NaT)
    price = processed_data.get('price', np.nan)
    ema = processed_data.get('ema', np.nan)
    inc_pct = processed_data.get('inc_price_change_pct', np.nan)
    dec_pct = processed_data.get('dec_price_change_pct', np.nan)
    w_inc = processed_data.get('weighted_increment', np.nan)
    w_dec = processed_data.get('weighted_decrement', np.nan)
    
    return timestamp, price, ema, inc_pct, dec_pct, w_inc, w_dec

def build_signal_dict(
    timestamp: Any,
    price: float,
    ema: float,
    inc_pct: float,
    dec_pct: float,
    w_inc: float,
    w_dec: float,
    signal: str,
    reason: str
) -> Dict[str, Any]:
    """
    Construye el diccionario de salida final con todos los valores formateados.
    """
    # Formatear valores para una salida legible
    formatted_ts = utils.format_datetime(timestamp)
    formatted_price = f"{price:.8f}" if pd.notna(price) else "NaN"
    formatted_ema = f"{ema:.8f}" if pd.notna(ema) else "NaN"
    
    # Manejar infinitos y NaNs en los porcentajes
    def format_pct(p):
        if pd.notna(p):
            if np.isinf(p): return "Inf%"
            return f"{p:.4f}%"
        return "NaN"

    formatted_inc_pct = format_pct(inc_pct)
    formatted_dec_pct = format_pct(dec_pct)

    formatted_w_inc = f"{w_inc:.4f}" if pd.notna(w_inc) else "NaN"
    formatted_w_dec = f"{w_dec:.4f}" if pd.notna(w_dec) else "NaN"

    # Ensamblar el diccionario final
    return {
        "timestamp": formatted_ts,
        "price_float": price,
        "price": formatted_price,
        "signal": signal,
        "signal_reason": reason,
        "ema": formatted_ema,
        "inc_price_change_pct": formatted_inc_pct,
        "dec_price_change_pct": formatted_dec_pct,
        "weighted_increment": formatted_w_inc,
        "weighted_decrement": formatted_w_dec,
    }