"""
Módulo de Reglas de Estrategia para la Generación de Señales.

Su única responsabilidad es contener la lógica de negocio pura para decidir
si se debe generar una señal de compra o venta. Las funciones aquí
reciben valores numéricos y devuelven booleanos o tuplas de decisión.
"""
from typing import Tuple
import pandas as pd
import numpy as np

# Dependencias del proyecto
import config

def check_buy_condition(
    price: float,
    ema: float,
    dec_pct: float,
    w_dec: float
) -> bool:
    """
    Evalúa si se cumplen todas las condiciones para una señal de COMPRA.
    """
    signal_cfg = config.SESSION_CONFIG["SIGNAL"]
    return (
        pd.notna(dec_pct) and np.isfinite(dec_pct) and dec_pct <= signal_cfg["PRICE_CHANGE_BUY_PERCENTAGE"] and
        pd.notna(w_dec) and w_dec >= signal_cfg["WEIGHTED_DECREMENT_THRESHOLD"] and
        pd.notna(ema) and np.isfinite(ema) and price < ema
    )

def check_sell_condition(
    price: float,
    ema: float,
    inc_pct: float,
    w_inc: float
) -> bool:
    """
    Evalúa si se cumplen todas las condiciones para una señal de VENTA.
    """
    signal_cfg = config.SESSION_CONFIG["SIGNAL"]
    return (
        pd.notna(inc_pct) and np.isfinite(inc_pct) and inc_pct >= signal_cfg["PRICE_CHANGE_SELL_PERCENTAGE"] and
        pd.notna(w_inc) and w_inc >= signal_cfg["WEIGHTED_INCREMENT_THRESHOLD"] and
        pd.notna(ema) and np.isfinite(ema) and price > ema
    )

def evaluate_strategy(
    price: float,
    ema: float,
    inc_pct: float,
    dec_pct: float,
    w_inc: float,
    w_dec: float
) -> Tuple[str, str]:
    """
    Evalúa todas las reglas de la estrategia y devuelve la señal y la razón.
    """
    signal_cfg = config.SESSION_CONFIG["SIGNAL"]
    if check_buy_condition(price, ema, dec_pct, w_dec):
        signal = "BUY"
        reason = (f"dec_pct({dec_pct:.2f}%) <= {signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE']}%, "
                  f"w_dec({w_dec:.2f}) >= {signal_cfg['WEIGHTED_DECREMENT_THRESHOLD']}, price < EMA")
        return signal, reason
    
    if check_sell_condition(price, ema, inc_pct, w_inc):
        signal = "SELL"
        reason = (f"inc_pct({inc_pct:.2f}%) >= {signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE']}%, "
                  f"w_inc({w_inc:.2f}) >= {signal_cfg['WEIGHTED_INCREMENT_THRESHOLD']}, price > EMA")
        return signal, reason

    return "HOLD", "Condiciones BUY/SELL no cumplidas"