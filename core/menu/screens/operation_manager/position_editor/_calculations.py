# core/menu/screens/operation_manager/position_editor/_calculations.py

from typing import List, Dict, Optional
import numpy as np

try:
    from core.strategy.entities import Operacion, LogicalPosition
    from core import utils
    from core.strategy.pm import _calculations as pm_calculations
except ImportError:
    utils = type('obj', (object,), {'safe_division': lambda n, d, default=0.0: (n / d) if d != 0 else default})()
    class Operacion: pass
    class LogicalPosition:
        def __init__(self, id, capital_asignado, entry_price=None, size_contracts=None, estado='PENDIENTE'):
            self.id = id
            self.capital_asignado = capital_asignado
            self.entry_price = entry_price
            self.size_contracts = size_contracts
            self.estado = estado

def calculate_avg_entry_and_liquidation(
    positions: List[LogicalPosition], 
    leverage: float, 
    side: str
) -> Dict[str, Optional[float]]:
    from core.strategy.pm._calculations import calculate_liquidation_price
    
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
    
    liquidation_price = calculate_liquidation_price(side, avg_entry_price, leverage)

    return {
        'avg_entry_price': avg_entry_price,
        'liquidation_price': liquidation_price
    }

def calculate_coverage_metrics(
    pending_positions: List[LogicalPosition],
    averaging_distance_pct: float,
    start_price: float,
    side: str
) -> Dict[str, Optional[float]]:
    if not pending_positions or not isinstance(averaging_distance_pct, (int, float)) or averaging_distance_pct <= 0 or not start_price:
        return {
            'coverage_pct': 0.0,
            'covered_price_range_start': start_price,
            'covered_price_range_end': start_price,
        }
    
    coverage_pct = len(pending_positions) * averaging_distance_pct
    
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
    if not all([leverage > 0, start_price > 0, avg_capital_per_pos > 0, distance_pct > 0]):
        return {'max_positions': 0, 'max_coverage_pct': 0.0}

    sim_positions = []
    
    current_price = start_price
    size = utils.safe_division(avg_capital_per_pos * leverage, current_price)
    if size == 0:
        return {'max_positions': 0, 'max_coverage_pct': 0.0}
        
    sim_positions.append({'price': current_price, 'size': size})

    for _ in range(1, 500):
        total_value = sum(p['price'] * p['size'] for p in sim_positions)
        total_size = sum(p['size'] for p in sim_positions)
        current_avg_price = utils.safe_division(total_value, total_size)

        last_entry_price = sim_positions[-1]['price']
        next_entry_price = last_entry_price * (1 - distance_pct / 100) if side == 'long' else last_entry_price * (1 + distance_pct / 100)
        
        liq_metrics = calculate_avg_entry_and_liquidation(
            [LogicalPosition('sim', 0, entry_price=current_avg_price, size_contracts=total_size)], leverage, side
        )
        liq_price = liq_metrics['liquidation_price']

        if liq_price is None:
            break

        if (side == 'long' and next_entry_price <= liq_price) or \
           (side == 'short' and next_entry_price >= liq_price):
            break

        new_size = utils.safe_division(avg_capital_per_pos * leverage, next_entry_price)
        if new_size == 0:
            break
        sim_positions.append({'price': next_entry_price, 'size': new_size})
    
    max_positions = len(sim_positions)
    final_price = sim_positions[-1]['price'] if sim_positions else start_price
    max_coverage_pct = abs(((start_price - final_price) / start_price) * 100)
    
    return {'max_positions': max_positions, 'max_coverage_pct': max_coverage_pct}

# Reemplaza esta función completa en core/menu/screens/operation_manager/position_editor/_calculations.py
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
    
    # --- 1. Cálculo de Métricas ACTUALES (basado solo en posiciones abiertas) ---
    live_avg_price = None
    if open_positions:
        live_metrics = calculate_avg_entry_and_liquidation(open_positions, leverage, side)
        live_avg_price = live_metrics.get('avg_entry_price')
    
    live_liq_price = None
    if live_avg_price:
        live_liq_price = pm_calculations.calculate_liquidation_price(side, live_avg_price, leverage)

    # --- 2. Determinación del Punto de Partida para la Simulación ---
    start_price_for_simulation = current_market_price
    if open_positions:
        valid_prices = [p.entry_price for p in open_positions if p.entry_price is not None]
        if valid_prices:
            start_price_for_simulation = min(valid_prices) if side == 'long' else max(valid_prices)

    # --- 3. Cálculo de Métricas de Cobertura ---
    coverage_metrics = calculate_coverage_metrics(
        pending_positions, distance_pct, start_price_for_simulation, side
    )

    # --- 4. Simulación de Agregados Proyectados (abiertas + pendientes) ---
    sim_total_value = 0
    sim_total_size = 0
    if open_positions:
        for pos in open_positions:
             if pos.entry_price is None or pos.entry_price <= 0: continue
             size = utils.safe_division(pos.capital_asignado * leverage, pos.entry_price)
             if size > 0:
                 sim_total_value += pos.entry_price * size
                 sim_total_size += size

    last_simulated_price = start_price_for_simulation
    if distance_pct is not None and distance_pct > 0:
        for pos in pending_positions:
            next_entry_price = last_simulated_price * (1 - distance_pct / 100) if side == 'long' else last_simulated_price * (1 + distance_pct / 100)
            size = utils.safe_division(pos.capital_asignado * leverage, next_entry_price)
            if size <= 0: continue
            
            sim_total_value += next_entry_price * size
            sim_total_size += size
            last_simulated_price = next_entry_price
    
    sim_avg_price = utils.safe_division(sim_total_value, sim_total_size)
    
    projected_liq_price = None
    if sim_avg_price:
        projected_liq_price = pm_calculations.calculate_liquidation_price(side, sim_avg_price, leverage)

    liquidation_distance_pct = None
    if current_market_price > 0 and projected_liq_price is not None:
        liquidation_distance_pct = ((current_market_price - projected_liq_price) / current_market_price) * 100 if side == 'long' else ((projected_liq_price - current_market_price) / current_market_price) * 100

    # --- 5. Cálculo del Break-Even y Precios Objetivo Proyectados ---
    projected_break_even_price = None
    if sim_avg_price and sim_avg_price > 0 and sim_total_size > 0:
        pnl_unrealized_target = -operacion.pnl_realizado_usdt
        price_change_needed = utils.safe_division(pnl_unrealized_target, sim_total_size)
        if side == 'long':
            projected_break_even_price = sim_avg_price + price_change_needed
        else:
            projected_break_even_price = sim_avg_price - price_change_needed
    
    # --- INICIO DE LA MODIFICACIÓN ---
    projected_roi_sl_manual_price = None
    projected_roi_sl_dynamic_price = None
    projected_roi_tp_price = None

    # Cálculo para SL Dinámico
    if operacion.dynamic_roi_sl:
        realized_roi = operacion.realized_twrr_roi
        dynamic_sl_target = realized_roi - operacion.dynamic_roi_sl.get('distancia', 0)
        projected_roi_sl_dynamic_price = operacion.get_projected_sl_tp_price(start_price_for_simulation, dynamic_sl_target)

    # Cálculo para SL Manual
    if operacion.roi_sl:
        manual_sl_target = operacion.roi_sl.get('valor')
        if manual_sl_target is not None:
            projected_roi_sl_manual_price = operacion.get_projected_sl_tp_price(start_price_for_simulation, manual_sl_target)

    # Cálculo para TP Manual
    if operacion.roi_tp:
        tp_roi_pct_target = operacion.roi_tp.get('valor')
        if tp_roi_pct_target is not None:
            projected_roi_tp_price = operacion.get_projected_sl_tp_price(start_price_for_simulation, tp_roi_pct_target)
    # --- FIN DE LA MODIFICACIÓN ---

    # --- 6. Simulación de Cobertura Máxima Teórica ---
    avg_capital = utils.safe_division(sum(p.capital_asignado for p in all_positions), len(all_positions)) if all_positions else 0
    max_sim_metrics = {}
    if distance_pct is not None and distance_pct > 0:
        max_sim_metrics = simulate_max_positions(leverage, current_market_price, avg_capital, distance_pct, side)

    # --- 7. Ensamblaje del Diccionario Final de Métricas ---
    final_metrics = {
        'avg_entry_price_actual': live_avg_price,
        'liquidation_price_actual': live_liq_price,
        'roi_sl_tp_target_price_actual': operacion.get_active_sl_tp_price(),
        
        'projected_break_even_price': projected_break_even_price,
        'projected_liquidation_price': projected_liq_price,
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se añaden las nuevas claves separadas al diccionario
        'projected_roi_sl_manual_price': projected_roi_sl_manual_price,
        'projected_roi_sl_dynamic_price': projected_roi_sl_dynamic_price,
        'projected_roi_tp_price': projected_roi_tp_price,
        # --- FIN DE LA MODIFICACIÓN ---
        
        'liquidation_distance_pct': liquidation_distance_pct,
        'total_capital_at_risk': sum(p.capital_asignado for p in all_positions),
    }
    
    final_metrics.update(coverage_metrics)
    final_metrics.update(max_sim_metrics)
    
    return final_metrics