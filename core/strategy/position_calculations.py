# =============== INICIO ARCHIVO: core/strategy/position_calculations.py (v14 - Con SL Individual) ===============
"""
Módulo con funciones de cálculo puras relacionadas con la gestión de posiciones.
No mantiene estado, recibe toda la información necesaria como argumentos.

v14:
- Añadida la función `calculate_stop_loss` para el SL individual por posición.
- Eliminada la función `calculate_take_profit`, ya que es reemplazada por la
  lógica de Trailing Stop.
"""
import math
import numpy as np
from typing import Optional, Dict, Any, List

# Importar config y utils de forma segura
try:
    import os
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path: sys.path.insert(0, project_root)
    import config
    from core import utils
except ImportError as e:
    print(f"ERROR [Position Calculations Import]: No se pudo importar core.config o core.utils: {e}")
    config_attrs = {
        'POSITION_MAX_LOGICAL_POSITIONS': 1,
        'POSITION_INDIVIDUAL_STOP_LOSS_PCT': 2.0,
        'POSITION_COMMISSION_RATE': 0.0,
        'POSITION_REINVEST_PROFIT_PCT': 0.0
    }
    config = type('obj', (object,), config_attrs)()
    utils_dummy = type('obj', (object,), {
        'safe_division': lambda num, den, default=0.0: (num / den) if den and den != 0 else default,
        'safe_float_convert': lambda v, default=0.0: float(v) if v is not None else default
    })()
    utils = utils_dummy
except Exception as e_imp:
     print(f"ERROR inesperado importando en position_calculations: {e_imp}")
     config = type('obj', (object,), {})()
     utils = None


# --- Funciones de Cálculo ---

def calculate_margin_per_slot(available_margin: float, open_positions_count: int, max_logical_positions: int) -> float:
    """
    Calcula el margen a asignar a una NUEVA posición lógica basado en el margen
    disponible y los slots libres.
    """
    available_slots = max(0, max_logical_positions - open_positions_count)
    if available_slots <= 0 or available_margin < 1e-6:
        return 0.0
    if utils:
        margin_per_slot = utils.safe_division(available_margin, available_slots, default=0.0)
    else:
        print("WARN [Calc]: utils.safe_division no disponible, usando división estándar.")
        margin_per_slot = available_margin / available_slots if available_slots != 0 else 0.0
    return margin_per_slot

# <<< FUNCIÓN ELIMINADA: calculate_take_profit >>>
# Esta función ya no es necesaria porque la lógica de toma de ganancias ahora
# será manejada por el Trailing Stop en `position_manager.py`.

# <<< INICIO NUEVA FUNCIÓN >>>
def calculate_stop_loss(side: str, entry_price: float) -> Optional[float]:
    """
    Calcula el precio de Stop Loss para una posición individual.
    """
    sl_pct = getattr(config, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', 0.0)
    if sl_pct <= 0:
        return None # No hay Stop Loss si el porcentaje es cero o negativo

    if not isinstance(entry_price, (int, float)) or not np.isfinite(entry_price) or entry_price <= 0:
        return None

    try:
        if side == 'long':
            sl_price = entry_price * (1 - sl_pct / 100.0)
            return max(0.0, sl_price) # Asegurar que no sea negativo
        elif side == 'short':
            sl_price = entry_price * (1 + sl_pct / 100.0)
            return sl_price
        else:
            print(f"WARN [Calc SL]: Lado '{side}' inválido.")
            return None
    except Exception as e:
        print(f"ERROR [Calc SL]: Excepción calculando SL: {e}")
        return None
# <<< FIN NUEVA FUNCIÓN >>>

def calculate_liquidation_price(side: str, avg_entry_price: float, leverage: float) -> Optional[float]:
    """
    Estima el precio de liquidación (aproximación simple margen aislado).
    """
    if not isinstance(avg_entry_price, (int, float)) or not np.isfinite(avg_entry_price) or avg_entry_price <= 0:
        return None
    if not isinstance(leverage, (int, float)) or not np.isfinite(leverage) or leverage <= 0:
        return None
    mmr_approx = 0.005
    try:
        if leverage == 0:
            return None
        leverage_inv = 1.0 / leverage
        if side == 'long':
            factor = 1.0 - leverage_inv + mmr_approx
            liq_price = avg_entry_price * factor
            return max(0.0, liq_price)
        elif side == 'short':
            factor = 1.0 + leverage_inv - mmr_approx
            liq_price = avg_entry_price * factor
            return liq_price
        else:
            print(f"WARN [Calc Liq]: Lado '{side}' inválido.")
            return None
    except (ZeroDivisionError, TypeError, ValueError):
        return None
    except Exception as e:
        print(f"ERROR [Calc Liq]: Excepción calculando Liq Price: {e}")
        return None

def calculate_pnl_commission_reinvestment(side: str, entry_price: float, exit_price: float, size_contracts: float) -> Dict[str, float]:
    """
    Calcula PNL bruto, comisión, PNL neto.
    Luego, calcula la porción del PNL NETO a reinvertir y la porción a transferir.
    """
    commission_rate = getattr(config, 'POSITION_COMMISSION_RATE', 0.0)
    reinvest_pct_raw = getattr(config, 'POSITION_REINVEST_PROFIT_PCT', 0.0)
    reinvest_fraction = reinvest_pct_raw / 100.0

    pnl_gross_usdt = 0.0
    commission_usdt = 0.0
    pnl_net_usdt = 0.0
    amount_reinvested_in_operational_margin = 0.0
    amount_transferable_to_profit = 0.0

    valid_inputs = (isinstance(entry_price, (int, float)) and np.isfinite(entry_price) and
                    isinstance(exit_price, (int, float)) and np.isfinite(exit_price) and
                    isinstance(size_contracts, (int, float)) and np.isfinite(size_contracts) and size_contracts > 0)

    if valid_inputs:
        try:
            if side == 'long':
                pnl_gross_usdt = (exit_price - entry_price) * size_contracts
            elif side == 'short':
                pnl_gross_usdt = (entry_price - exit_price) * size_contracts

            entry_nominal_value = entry_price * size_contracts
            exit_nominal_value = exit_price * size_contracts
            if np.isfinite(entry_nominal_value) and np.isfinite(exit_nominal_value):
                commission_usdt = (abs(entry_nominal_value) + abs(exit_nominal_value)) * commission_rate

            pnl_net_usdt = pnl_gross_usdt - commission_usdt

            if pnl_net_usdt > 1e-9:
                amount_reinvested_in_operational_margin = pnl_net_usdt * reinvest_fraction
                amount_transferable_to_profit = pnl_net_usdt - amount_reinvested_in_operational_margin
        except Exception as e:
            print(f"ERROR [Calc PNL]: Excepción calculando PNL/Comm/Reinv: {e}")
            pnl_gross_usdt, commission_usdt, pnl_net_usdt, amount_reinvested_in_operational_margin, amount_transferable_to_profit = 0.0, 0.0, 0.0, 0.0, 0.0
    else:
        print(f"WARN [Calc PNL]: Entradas inválidas para cálculo PNL ({entry_price=}, {exit_price=}, {size_contracts=}).")

    return {
        "pnl_gross_usdt": float(pnl_gross_usdt),
        "commission_usdt": float(commission_usdt),
        "pnl_net_usdt": float(pnl_net_usdt),
        "amount_reinvested_in_operational_margin": float(amount_reinvested_in_operational_margin),
        "amount_transferable_to_profit": float(amount_transferable_to_profit)
    }

def calculate_physical_aggregates(open_positions: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calcula los agregados para la posición física (precio promedio, tamaño, margen)
    a partir de la lista de posiciones lógicas abiertas.
    """
    if not open_positions:
        return {'avg_entry_price': 0.0, 'total_size_contracts': 0.0, 'total_margin_usdt': 0.0}

    total_value = 0.0
    total_contracts = 0.0
    total_margin = 0.0

    for pos in open_positions:
        entry = pos.get('entry_price', 0.0)
        size = pos.get('size_contracts', 0.0)
        margin = pos.get('margin_usdt', 0.0)

        if isinstance(entry, (int, float)) and np.isfinite(entry) and \
           isinstance(size, (int, float)) and np.isfinite(size) and \
           isinstance(margin, (int, float)) and np.isfinite(margin):
            total_value += entry * size
            total_contracts += size
            total_margin += margin

    if utils:
        avg_entry_price = utils.safe_division(total_value, total_contracts, default=0.0)
    else:
        avg_entry_price = (total_value / total_contracts) if total_contracts else 0.0

    return {
        'avg_entry_price': float(avg_entry_price),
        'total_size_contracts': float(total_contracts),
        'total_margin_usdt': float(total_margin)
    }

# =============== FIN ARCHIVO: core/strategy/position_calculations.py (v14 - Con SL Individual) ===============
