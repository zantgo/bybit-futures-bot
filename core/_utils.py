# core/_utils.py

"""
Módulo con funciones de utilidad generales reutilizables.
"""
import datetime
import pandas as pd
import numpy as np
from typing import Union

def safe_float_convert(value, default=np.nan):
    """Convierte de forma segura a float, devuelve default (NaN por defecto)."""
    if value is None or value == '':
        return default
    try:
        # Intentar convertir a float
        f_value = float(value)
        # Devolver el valor si es finito, sino el default
        return f_value if np.isfinite(f_value) else default
    except (ValueError, TypeError):
        # Si la conversión falla, devolver el default
        return default

def format_datetime(dt_object: Union[datetime.datetime, pd.Timestamp, None], fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    """Formatea un objeto datetime/Timestamp a string, manejando None."""
    if isinstance(dt_object, (datetime.datetime, pd.Timestamp)):
        try:
            return dt_object.strftime(fmt)
        except ValueError:
            # Error si el formato es inválido para el objeto
            return "Invalid DateTime Format"
        except Exception:
            # Otro error de formateo
            return "Formatting Error"
    elif dt_object is None:
        return "N/A"
    else:
        # Si no es un tipo esperado, intentar convertir a string como fallback
        return str(dt_object)

def safe_division(numerator, denominator, default=0.0):
    """
    Realiza una división segura, evitando errores por cero o tipos inválidos.

    Args:
        numerator: El numerador.
        denominator: El denominador.
        default: Valor a devolver si la división falla o no es válida (default: 0.0).

    Returns:
        El resultado de la división o el valor default.
    """
    try:
        # Intentar convertir ambos a float para la división
        num = float(numerator)
        den = float(denominator)

        # Verificar si el denominador es None, NaN, Inf o muy cercano a cero
        if den is None or not np.isfinite(den) or abs(den) < 1e-12: # Usar umbral muy pequeño
            return default

        result = num / den

        # Verificar si el resultado es Inf o NaN
        if not np.isfinite(result):
            return default

        return result
    except (TypeError, ValueError, ZeroDivisionError):
        # Capturar errores de conversión o división por cero explícita
        return default
