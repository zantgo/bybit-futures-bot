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
    from core.logging import memory_logger
except ImportError as e:
    print(f"ERROR [Position Calculations Import]: No se pudo importar core.config o core.utils: {e}")
    # Definir stubs/dummies si las importaciones fallan, para que las funciones no fallen catastróficamente
    config_attrs = {
        'OPERATION_DEFAULTS': {'PROFIT': {'COMMISSION_RATE': 0.0, 'REINVEST_PROFIT_PCT': 0.0}},
        'SESSION_CONFIG': {'PROFIT': {'COMMISSION_RATE': 0.0, 'REINVEST_PROFIT_PCT': 0.0}}
    }
    config = type('obj', (object,), config_attrs)()
    _utils = type('obj', (object,), {
        'safe_division': lambda num, den, default=0.0: (num / den) if den and den != 0 else default
    })()
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
except Exception as e_imp:
     print(f"ERROR inesperado importando en position_calculations: {e_imp}")
     config = type('obj', (object,), {})()
     _utils = None
     class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
     memory_logger = MemoryLoggerFallback()


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

def calculate_stop_loss(side: str, entry_price: float, sl_pct: float) -> Optional[float]:
    """
    Calcula el precio de Stop Loss para una posición individual.
    Recibe el porcentaje de SL como argumento para permitir el ajuste dinámico.
    """
    if not isinstance(sl_pct, (int, float)) or not np.isfinite(sl_pct):
        return None # No hay Stop Loss si el valor no es un número válido.

    if sl_pct <= 0:
        return None # No hay Stop Loss si el porcentaje es cero o negativo.

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
            memory_logger.log(f"WARN [Calc SL]: Lado '{side}' inválido.", level="WARN")
            return None
    except Exception as e:
        memory_logger.log(f"ERROR [Calc SL]: Excepción calculando SL: {e}", level="ERROR")
        return None

# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función Única) ---
# ==============================================================================

def calculate_liquidation_price(side: str, avg_entry_price: float, leverage: float) -> Optional[float]:
    """
    Estima el precio de liquidación usando la fórmula de Bybit para margen aislado.
    """
    if not isinstance(avg_entry_price, (int, float)) or not np.isfinite(avg_entry_price) or avg_entry_price <= 0:
        return None
    if not isinstance(leverage, (int, float)) or not np.isfinite(leverage) or leverage <= 0:
        return None
    
    # --- INICIO DE LA CORRECCIÓN ---
    # Se lee la tasa de margen de mantenimiento desde la configuración para mayor precisión.
    # Si no se encuentra, se usa un fallback seguro.
    mmr = config.PRECISION_FALLBACKS.get("MAINTENANCE_MARGIN_RATE", 0.005) 
    
    try:
        initial_margin_rate = 1.0 / leverage
        
        if side == 'long':
            # Fórmula Oficial Bybit (simplificada): PrecioEntrada * (1 - TasaMargenInicial + TasaMargenMantenimiento)
            factor = 1 - initial_margin_rate + mmr
            liq_price = avg_entry_price * factor
        elif side == 'short':
            # Fórmula Oficial Bybit (simplificada): PrecioEntrada * (1 + TasaMargenInicial - TasaMargenMantenimiento)
            factor = 1 + initial_margin_rate - mmr
            liq_price = avg_entry_price * factor
        else:
            return None
            
        return max(0.0, liq_price)
        
    except (ZeroDivisionError, TypeError, ValueError):
        return None
    # --- FIN DE LA CORRECCIÓN ---

# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================

def calculate_pnl_commission_reinvestment(side: str, entry_price: float, exit_price: float, size_contracts: float) -> Dict[str, float]:
    """
    Calcula PNL bruto, comisión, PNL neto.
    Luego, calcula la porción del PNL NETO a reinvertir y la porción a transferir.
    """
    profit_cfg = config.SESSION_CONFIG["PROFIT"]
    commission_rate = profit_cfg["COMMISSION_RATE"]
    reinvest_fraction = profit_cfg["REINVEST_PROFIT_PCT"] / 100.0
    slippage_pct = profit_cfg.get("SLIPPAGE_PCT", 0.0) 

    pnl_gross_usdt = 0.0
    slippage_cost_usdt = 0.0
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

            # Calcular coste de slippage sobre el valor nominal de entrada y salida
            if np.isfinite(entry_nominal_value) and np.isfinite(exit_nominal_value):
                slippage_cost_usdt = (abs(entry_nominal_value) + abs(exit_nominal_value)) * slippage_pct
            
            # Ajustar el PNL bruto por el coste de slippage
            pnl_gross_adjusted = pnl_gross_usdt - slippage_cost_usdt
            
            # La fórmula correcta debe sumar el valor nominal de la entrada y la salida,
            # ya que la comisión se paga en ambas transacciones.
            if np.isfinite(entry_nominal_value) and np.isfinite(exit_nominal_value):
                commission_usdt = (abs(entry_nominal_value) + abs(exit_nominal_value)) * commission_rate

            pnl_net_usdt = pnl_gross_adjusted - commission_usdt
            
            if pnl_net_usdt > 0:
                amount_reinvested = pnl_net_usdt * reinvest_fraction
                amount_transferable = pnl_net_usdt - amount_reinvested
        except Exception as e:
            memory_logger.log(f"ERROR [Calc PNL]: Excepción calculando PNL: {e}", level="ERROR")
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

def calculate_aggregate_liquidation_price(
    open_positions: List[Any], # Acepta objetos LogicalPosition
    leverage: float,
    side: str
) -> Optional[float]:
    """
    Calcula el precio de liquidación estimado para una posición agregada
    compuesta por múltiples posiciones lógicas abiertas.
    """
    if not open_positions:
        return None

    # --- INICIO DE LA CORRECCIÓN ---
    # Se trabaja directamente con los atributos del objeto LogicalPosition.
    valid_positions = [
        p for p in open_positions
        if (hasattr(p, 'entry_price') and isinstance(p.entry_price, (int, float)) and np.isfinite(p.entry_price) and
            hasattr(p, 'size_contracts') and isinstance(p.size_contracts, (int, float)) and np.isfinite(p.size_contracts) and
            p.size_contracts > 1e-12)
    ]
    # --- FIN DE LA CORRECCIÓN ---
    
    if not valid_positions:
        return None

    # --- INICIO DE LA CORRECCIÓN ---
    # Calcular directamente desde los atributos del objeto.
    total_value = sum(pos.entry_price * pos.size_contracts for pos in valid_positions)
    total_size = sum(pos.size_contracts for pos in valid_positions)
    # --- FIN DE LA CORRECCIÓN ---

    avg_entry_price = _utils.safe_division(total_value, total_size)

    if not avg_entry_price or avg_entry_price <= 0:
        return None

    return calculate_liquidation_price(side, avg_entry_price, leverage)

def calculate_projected_roi_target_price(
    all_positions: List[Dict[str, Any]],
    capital_inicial_usdt: float,
    pnl_realizado_usdt: float,
    sl_roi_pct_target: float,
    leverage: float,
    distance_pct: float,
    side: str,
    last_real_entry_price: float
) -> Optional[float]:
    """
    Calcula el precio de mercado objetivo al que se alcanzaría un ROI específico,
    simulando que todas las posiciones (abiertas y pendientes) están activas.

    Args:
        all_positions (List[Dict]): Lista completa de todas las posiciones
                                    (abiertas y pendientes) de la operación.
        capital_inicial_usdt (float): El capital base para el cálculo del ROI.
        pnl_realizado_usdt (float): El PNL ya realizado en la operación.
        sl_roi_pct_target (float): El porcentaje de ROI objetivo (ej. -25.0 o 50.0).
        leverage (float): El apalancamiento de la operación.
        distance_pct (float): El porcentaje de distancia para promediación.
        side (str): El lado de la operación ('long' o 'short').
        last_real_entry_price (float): El último precio de entrada real para
                                       iniciar la simulación de las pendientes.

    Returns:
        Optional[float]: El precio de mercado estimado para alcanzar el ROI
                         objetivo, o None si no se puede calcular.
    """
    if not all_positions or capital_inicial_usdt <= 0 or not np.isfinite(sl_roi_pct_target):
        return None

    open_positions = [p for p in all_positions if p.get('estado') == 'ABIERTA']
    pending_positions = [p for p in all_positions if p.get('estado') == 'PENDIENTE']
    
    # 1. Simular la apertura de todas las posiciones para obtener agregados proyectados
    sim_total_value = sum(p.get('entry_price', 0) * p.get('size_contracts', 0) for p in open_positions)
    sim_total_size = sum(p.get('size_contracts', 0) for p in open_positions)
    
    last_simulated_price = last_real_entry_price

    if distance_pct is not None and distance_pct > 0:
        for pos in pending_positions:
            # Simular el precio de entrada de la siguiente posición pendiente
            if side == 'long':
                next_entry_price = last_simulated_price * (1 - distance_pct / 100)
            else: # 'short'
                next_entry_price = last_simulated_price * (1 + distance_pct / 100)
            
            # Calcular el tamaño de esta posición simulada
            capital_asignado = pos.get('capital_asignado', 0)
            size = _utils.safe_division(capital_asignado * leverage, next_entry_price)
            if size <= 0: continue
            
            # Acumular al total proyectado
            sim_total_value += next_entry_price * size
            sim_total_size += size
            last_simulated_price = next_entry_price

    projected_avg_price = _utils.safe_division(sim_total_value, sim_total_size)
    projected_total_size = sim_total_size

    if projected_total_size <= 1e-12:
        return None

    # 2. Calcular el PNL no realizado necesario para alcanzar el objetivo
    pnl_target_usdt = (sl_roi_pct_target / 100.0) * capital_inicial_usdt
    unrealized_pnl_needed = pnl_target_usdt - pnl_realizado_usdt

    # 3. Calcular el precio de mercado objetivo (inversión de la fórmula de PNL)
    try:
        price_difference_per_contract = _utils.safe_division(unrealized_pnl_needed, projected_total_size)
        
        if side == 'long':
            target_market_price = projected_avg_price + price_difference_per_contract
        elif side == 'short':
            target_market_price = projected_avg_price - price_difference_per_contract
        else:
            return None

        return max(0.0, target_market_price)

    except (TypeError, ValueError):
        return None

# ==============================================================================
# --- FIN DE LA NUEVA FUNCIONALIDAD ---
# ==============================================================================