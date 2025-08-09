# Contenido completo y corregido para: core/menu/screens/operation_manager/position_editor/_calculations.py

from typing import List, Dict, Optional
import numpy as np

try:
    from core.strategy.entities import Operacion, LogicalPosition
    from core import utils
except ImportError:
    # Fallback para análisis estático y para evitar errores si las importaciones fallan
    utils = type('obj', (object,), {'safe_division': lambda n, d, default=0.0: (n / d) if d != 0 else default})()
    class Operacion: pass
    class LogicalPosition:
        def __init__(self, id, capital_asignado, entry_price=None, size_contracts=None, estado='PENDIENTE'):
            self.id = id
            self.capital_asignado = capital_asignado
            self.entry_price = entry_price
            self.size_contracts = size_contracts
            self.estado = estado

# --- Función de Cálculo Base ---

def calculate_avg_entry_and_liquidation(
    positions: List[LogicalPosition], 
    leverage: float, 
    side: str
) -> Dict[str, Optional[float]]:
    if not positions:
        return {'avg_entry_price': None, 'liquidation_price': None}

    valid_positions = [p for p in positions if p.size_contracts and p.entry_price]
    if not valid_positions:
        return {'avg_entry_price': None, 'liquidation_price': None}

    total_size_contracts = sum(p.size_contracts for p in valid_positions)
    total_value_usd = sum(p.entry_price * p.size_contracts for p in valid_positions)
    avg_entry_price = utils.safe_division(total_value_usd, total_size_contracts)

    if not avg_entry_price or avg_entry_price <= 0:
        return {'avg_entry_price': avg_entry_price, 'liquidation_price': None}
    
    maintenance_margin_rate = 0.005
    if side == 'long':
        liquidation_price = avg_entry_price * (1 - (1 / leverage) + maintenance_margin_rate)
    else:
        liquidation_price = avg_entry_price * (1 + (1 / leverage) - maintenance_margin_rate)

    return {
        'avg_entry_price': avg_entry_price,
        'liquidation_price': max(0, liquidation_price)
    }

# --- Funciones de Simulación y Cobertura (Corregidas) ---

def calculate_coverage_metrics(
    pending_positions: List[LogicalPosition],
    averaging_distance_pct: float,
    start_price: float,
    side: str
) -> Dict[str, Optional[float]]:
    """
    Calcula la cobertura porcentual y el rango de precios que cubren las posiciones pendientes.
    """
    # --- INICIO DE LA MODIFICACIÓN ---
    # La línea original fallaba si averaging_distance_pct era None.
    # Se añade una comprobación para asegurar que es un número válido antes de la comparación.
    # if not pending_positions or averaging_distance_pct <= 0 or not start_price: # <-- LÍNEA ORIGINAL COMENTADA
    if not pending_positions or not isinstance(averaging_distance_pct, (int, float)) or averaging_distance_pct <= 0 or not start_price:
    # --- FIN DE LA MODIFICACIÓN ---
        return {
            'coverage_pct': 0.0,
            'covered_price_range_start': start_price,
            'covered_price_range_end': start_price,
        }
    
    # Cálculo simple e intuitivo para el usuario.
    coverage_pct = len(pending_positions) * averaging_distance_pct
    
    # Simulación de la caída/subida compuesta para el rango de precios.
    price_level = start_price
    if side == 'long':
        price_level *= (1 - averaging_distance_pct / 100) ** len(pending_positions)
    else:
        price_level *= (1 + averaging_distance_pct / 100) ** len(pending_positions)

    return {
        'coverage_pct': coverage_pct,
        'covered_price_range_start': start_price,
        'covered_price_range_end': price_level,
    }

def simulate_max_positions(
    leverage: float,
    start_price: float,
    avg_capital_per_pos: float,
    distance_pct: float,
    side: str
) -> Dict[str, Optional[float]]:
    """
    Simula cuántas posiciones se pueden abrir antes de la liquidación y qué cobertura ofrecen.
    """
    if not all([leverage > 0, start_price > 0, avg_capital_per_pos > 0, distance_pct > 0]):
        return {'max_positions': 0, 'max_coverage_pct': 0.0}

    sim_positions_data = []
    current_avg_price = start_price
    total_size = 0
    total_value = 0
    
    size = utils.safe_division(avg_capital_per_pos * leverage, start_price)
    sim_positions_data.append({'price': start_price, 'size': size})
    total_size += size
    total_value += start_price * size
    
    for i in range(1, 250):
        next_entry_price = current_avg_price * (1 - distance_pct / 100) if side == 'long' else current_avg_price * (1 + distance_pct / 100)
        
        size = utils.safe_division(avg_capital_per_pos * leverage, next_entry_price)
        if size == 0: break
        
        total_value += next_entry_price * size
        total_size += size
        current_avg_price = utils.safe_division(total_value, total_size)

        liq_price_metrics = calculate_avg_entry_and_liquidation(
            [LogicalPosition('sim', 0, entry_price=current_avg_price, size_contracts=total_size)], leverage, side)
        liq_price = liq_price_metrics['liquidation_price']

        if liq_price is None: break

        if (side == 'long' and next_entry_price <= liq_price) or (side == 'short' and next_entry_price >= liq_price):
            break
            
        sim_positions_data.append({'price': next_entry_price, 'size': size})

    max_positions = len(sim_positions_data)
    final_price = sim_positions_data[-1]['price'] if sim_positions_data else start_price
    max_coverage_pct = abs(((start_price - final_price) / start_price) * 100)
    
    return {'max_positions': max_positions, 'max_coverage_pct': max_coverage_pct}

# --- Función Orquestadora Principal (Corregida) ---

def calculate_projected_risk_metrics(
    operacion: 'Operacion',
    current_market_price: float,
    side: str
) -> Dict[str, Optional[float]]:
    all_positions = operacion.posiciones
    leverage = operacion.apalancamiento
    distance_pct = operacion.averaging_distance_pct
    
    open_positions = [p for p in all_positions if p.estado == 'ABIERTA']
    pending_positions = [p for p in all_positions if p.estado == 'PENDIENTE']
    
    live_metrics = calculate_avg_entry_and_liquidation(open_positions, leverage, side)

    # Llamada a función con argumentos correctos
    last_real_avg_price = live_metrics['avg_entry_price'] or current_market_price
    coverage_metrics = calculate_coverage_metrics(pending_positions, distance_pct, last_real_avg_price, side)

    sim_total_value = sum(p.size_contracts * p.entry_price for p in open_positions if p.size_contracts and p.entry_price)
    sim_total_size = sum(p.size_contracts for p in open_positions if p.size_contracts)
    sim_avg_price = live_metrics['avg_entry_price'] or current_market_price

    if distance_pct is not None and distance_pct > 0:
        for pos in pending_positions:
            next_entry_price = sim_avg_price * (1 - distance_pct / 100) if side == 'long' else sim_avg_price * (1 + distance_pct / 100)
            size = utils.safe_division(pos.capital_asignado * leverage, next_entry_price)
            if size <= 0: continue
            
            sim_total_value += next_entry_price * size
            sim_total_size += size
            sim_avg_price = utils.safe_division(sim_total_value, sim_total_size)

    projected_liq_metrics = calculate_avg_entry_and_liquidation(
        [LogicalPosition('proj', 0, entry_price=sim_avg_price, size_contracts=sim_total_size)], leverage, side)
    projected_liq_price = projected_liq_metrics.get('liquidation_price')

    liquidation_distance_pct = None
    if current_market_price > 0 and projected_liq_price is not None:
        if side == 'long':
            liquidation_distance_pct = ((current_market_price - projected_liq_price) / current_market_price) * 100
        else:
            liquidation_distance_pct = ((projected_liq_price - current_market_price) / current_market_price) * 100
    
    avg_capital = utils.safe_division(sum(p.capital_asignado for p in all_positions), len(all_positions)) if all_positions else 0
    
    # Solo simular si la distancia es válida
    max_sim_metrics = {}
    if distance_pct is not None and distance_pct > 0:
        max_sim_metrics = simulate_max_positions(leverage, current_market_price, avg_capital, distance_pct, side)

    final_metrics = {
        'avg_entry_price': live_metrics['avg_entry_price'],
        'liquidation_price': live_metrics['liquidation_price'],
        'total_capital_at_risk': sum(p.capital_asignado for p in all_positions),
        'projected_avg_price': sim_avg_price,
        'projected_liquidation_price': projected_liq_price,
        'liquidation_distance_pct': liquidation_distance_pct,
    }
    final_metrics.update(coverage_metrics)
    final_metrics.update(max_sim_metrics)
    
    return final_metrics