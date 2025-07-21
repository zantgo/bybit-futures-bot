"""
Módulo con funciones de cálculo puras relacionadas con la gestión de posiciones.
No mantiene estado, recibe toda la información necesaria como argumentos.

v17:
- Modificada `calculate_stop_loss` para aceptar `sl_pct` como argumento,
  permitiendo el ajuste dinámico del SL individual por posición.
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
    import config as config
    from core import _utils
except ImportError as e:
    print(f"ERROR [Position Calculations Import]: No se pudo importar core.config o core.utils: {e}")
    # Definir stubs/dummies si las importaciones fallan, para que las funciones no fallen catastróficamente
    config_attrs = {
        'POSITION_COMMISSION_RATE': 0.0,
        'POSITION_REINVEST_PROFIT_PCT': 0.0
    }
    config = type('obj', (object,), config_attrs)()
    _utils = type('obj', (object,), {
        'safe_division': lambda num, den, default=0.0: (num / den) if den and den != 0 else default
    })()
except Exception as e_imp:
     print(f"ERROR inesperado importando en position_calculations: {e_imp}")
     config = type('obj', (object,), {})()
     _utils = None


# --- Funciones de Cálculo ---

def calculate_margin_per_slot(available_margin: float, open_positions_count: int, max_logical_positions: int) -> float:
    """
    Calcula el margen a asignar a una NUEVA posición lógica basado en el margen
    disponible y los slots libres.
    """
    available_slots = max(0, max_logical_positions - open_positions_count)
    if available_slots <= 0 or available_margin < 1e-6:
        return 0.0
    
    if not _utils:
        # Fallback si utils no está disponible
        return available_margin / available_slots if available_slots != 0 else 0.0
        
    return _utils.safe_division(available_margin, available_slots, default=0.0)

# <<< CORRECCIÓN: La función ahora acepta sl_pct como argumento >>>
def calculate_stop_loss(side: str, entry_price: float, sl_pct: float) -> Optional[float]:
    """
    Calcula el precio de Stop Loss para una posición individual.
    Recibe el porcentaje de SL como argumento para permitir el ajuste dinámico.
    """
    # sl_pct = getattr(config, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', 0.0) # Ya no se lee de config
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

def calculate_liquidation_price(side: str, avg_entry_price: float, leverage: float) -> Optional[float]:
    """
    Estima el precio de liquidación (aproximación simple margen aislado).
    """
    if not isinstance(avg_entry_price, (int, float)) or not np.isfinite(avg_entry_price) or avg_entry_price <= 0:
        return None
    if not isinstance(leverage, (int, float)) or not np.isfinite(leverage) or leverage <= 0:
        return None
    
    # El margen de mantenimiento mínimo varía por exchange, usamos una aproximación
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
            return None
    except (ZeroDivisionError, TypeError, ValueError):
        return None

def calculate_pnl_commission_reinvestment(side: str, entry_price: float, exit_price: float, size_contracts: float) -> Dict[str, float]:
    """
    Calcula PNL bruto, comisión, PNL neto.
    Luego, calcula la porción del PNL NETO a reinvertir y la porción a transferir.
    """
    commission_rate = getattr(config, 'POSITION_COMMISSION_RATE', 0.0)
    reinvest_fraction = getattr(config, 'POSITION_REINVEST_PROFIT_PCT', 0.0) / 100.0

    pnl_gross_usdt = 0.0
    commission_usdt = 0.0
    pnl_net_usdt = 0.0
    amount_reinvested = 0.0
    amount_transferable = 0.0

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

            if pnl_net_usdt > 0:
                amount_reinvested = pnl_net_usdt * reinvest_fraction
                amount_transferable = pnl_net_usdt - amount_reinvested
        except Exception as e:
            print(f"ERROR [Calc PNL]: Excepción calculando PNL: {e}")
            pnl_gross_usdt, commission_usdt, pnl_net_usdt, amount_reinvested, amount_transferable = 0.0, 0.0, 0.0, 0.0, 0.0
    
    return {
        "pnl_gross_usdt": float(pnl_gross_usdt),
        "commission_usdt": float(commission_usdt),
        "pnl_net_usdt": float(pnl_net_usdt),
        "amount_reinvested_in_operational_margin": float(amount_reinvested),
        "amount_transferable_to_profit": float(amount_transferable)
    }

def calculate_physical_aggregates(open_positions: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calcula los agregados para la posición física (precio promedio, tamaño, margen)
    a partir de la lista de posiciones lógicas abiertas.
    """
    if not open_positions:
        return {'avg_entry_price': 0.0, 'total_size_contracts': 0.0, 'total_margin_usdt': 0.0}

    total_value, total_contracts, total_margin = 0.0, 0.0, 0.0

    for pos in open_positions:
        entry = pos.get('entry_price', 0.0)
        size = pos.get('size_contracts', 0.0)
        margin = pos.get('margin_usdt', 0.0)

        if all(isinstance(v, (int, float)) and np.isfinite(v) for v in [entry, size, margin]):
            total_value += entry * size
            total_contracts += size
            total_margin += margin

    if not _utils:
        avg_entry_price = (total_value / total_contracts) if total_contracts else 0.0
    else:
        avg_entry_price = _utils.safe_division(total_value, total_contracts, default=0.0)

    return {
        'avg_entry_price': float(avg_entry_price),
        'total_size_contracts': float(total_contracts),
        'total_margin_usdt': float(total_margin)
    }
