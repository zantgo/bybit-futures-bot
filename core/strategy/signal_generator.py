# core/strategy/signal_generator.py
"""
Genera señales BUY, SELL, o HOLD basadas en indicadores técnicos (v5.3).
Retorna un diccionario COMPLETO con la señal y todos los indicadores relevantes.
"""
import pandas as pd
import numpy as np

# Importar módulos core necesarios
import config
from core import utils # Para formatear timestamp y números

def generate_signal(processed_data: dict) -> dict:
    """
    Evalúa los indicadores técnicos proporcionados contra las reglas de la estrategia
    definidas en config.py y genera una señal de trading.

    Args:
        processed_data (dict): Un diccionario que contiene los indicadores calculados:
                               'timestamp', 'price', 'ema', 'inc_price_change_pct',
                               'dec_price_change_pct', 'weighted_increment',
                               'weighted_decrement'. Los valores pueden ser NaN.

    Returns:
        dict: Un diccionario COMPLETO representando la señal y el estado de los indicadores
              en ese momento. Incluye: 'timestamp', 'price' (float original y string formateado),
              'signal', y todos los indicadores TA formateados como strings.
    """
    # --- Default Signal ---
    base_signal = "HOLD"
    signal_reason = "Default" # Add a reason for clarity

    # --- Extract Data ---
    current_timestamp = processed_data.get('timestamp', pd.NaT)
    current_price = processed_data.get('price', np.nan) # Mantener como float para lógica
    current_ema = processed_data.get('ema', np.nan)
    inc_pct = processed_data.get('inc_price_change_pct', np.nan)
    dec_pct = processed_data.get('dec_price_change_pct', np.nan)
    w_inc = processed_data.get('weighted_increment', np.nan)
    w_dec = processed_data.get('weighted_decrement', np.nan)

    # --- Formatted values for the output dictionary ---
    formatted_ts = utils.format_datetime(current_timestamp)
    formatted_price = f"{current_price:.8f}" if pd.notna(current_price) else "NaN"
    formatted_ema = f"{current_ema:.8f}" if pd.notna(current_ema) else "NaN"
    # Mostrar porcentaje con el símbolo %
    formatted_inc_pct = f"{inc_pct:.4f}%" if pd.notna(inc_pct) and np.isfinite(inc_pct) else ("Inf%" if inc_pct == np.inf else "NaN")
    formatted_dec_pct = f"{dec_pct:.4f}%" if pd.notna(dec_pct) and np.isfinite(dec_pct) else ("Inf%" if dec_pct == np.inf else "NaN")
    formatted_w_inc = f"{w_inc:.4f}" if pd.notna(w_inc) else "NaN"
    formatted_w_dec = f"{w_dec:.4f}" if pd.notna(w_dec) else "NaN"

    # --- Basic Validation ---
    if pd.isna(current_timestamp) or pd.isna(current_price):
        base_signal = "HOLD_INVALID_DATA"
        signal_reason = "Timestamp o Precio inválido"
        # Construir diccionario de salida incluso con datos inválidos
        signal_dict = {
            "timestamp": formatted_ts, "price_float": current_price, "price": formatted_price,
            "signal": base_signal, "signal_reason": signal_reason, "ema": formatted_ema,
            "inc_price_change_pct": formatted_inc_pct, "dec_price_change_pct": formatted_dec_pct,
            "weighted_increment": formatted_w_inc, "weighted_decrement": formatted_w_dec, }
        return signal_dict

    # --- Evaluate Strategy Rules (if enabled) ---
    if config.STRATEGY_ENABLED:
        allow_buy = True # Siempre evaluar condiciones en v5.3
        allow_sell = True

        # --- Check BUY Condition ---
        buy_conditions_met = (
            allow_buy and
            pd.notna(dec_pct) and np.isfinite(dec_pct) and dec_pct <= config.STRATEGY_MARGIN_BUY and
            pd.notna(w_dec) and w_dec >= config.STRATEGY_DECREMENT_THRESHOLD and
            pd.notna(current_ema) and np.isfinite(current_ema) and current_price < current_ema )

        # --- Check SELL Condition ---
        sell_conditions_met = (
            allow_sell and
            pd.notna(inc_pct) and np.isfinite(inc_pct) and inc_pct >= config.STRATEGY_MARGIN_SELL and
            pd.notna(w_inc) and w_inc >= config.STRATEGY_INCREMENT_THRESHOLD and
            pd.notna(current_ema) and np.isfinite(current_ema) and current_price > current_ema )

        # Determinar señal final y razón
        if buy_conditions_met:
            base_signal = "BUY"
            signal_reason = f"dec_pct({dec_pct:.2f}%)<={config.STRATEGY_MARGIN_BUY}%, w_dec({w_dec:.2f})>={config.STRATEGY_DECREMENT_THRESHOLD}, price<EMA"
        elif sell_conditions_met:
            base_signal = "SELL"
            signal_reason = f"inc_pct({inc_pct:.2f}%)>={config.STRATEGY_MARGIN_SELL}%, w_inc({w_inc:.2f})>={config.STRATEGY_INCREMENT_THRESHOLD}, price>EMA"
        else: signal_reason = "Condiciones BUY/SELL no cumplidas"
    else:
        base_signal = "HOLD_STRATEGY_DISABLED"; signal_reason = "Estrategia desactivada en config.py"

    # --- Construir Diccionario de Salida COMPLETO ---
    signal_dict = {
        "timestamp": formatted_ts, "price_float": current_price, "price": formatted_price,
        "signal": base_signal, "signal_reason": signal_reason, "ema": formatted_ema,
        "inc_price_change_pct": formatted_inc_pct, "dec_price_change_pct": formatted_dec_pct,
        "weighted_increment": formatted_w_inc, "weighted_decrement": formatted_w_dec, }
    return signal_dict