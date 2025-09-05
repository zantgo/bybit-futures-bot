# Reemplaza el archivo completo: core/menu/screens/operation_manager/position_editor/_displayers.py

from typing import Any, Dict, List, Optional
import shutil
import re

try:
    from ...._helpers import _create_box_line, _truncate_text, _get_terminal_width, _clean_ansi_codes
    from core.strategy.entities import Operacion, LogicalPosition
    from core import utils
except ImportError:
    def _create_box_line(content: str, width: int, alignment: str = 'left') -> str: return content
    def _truncate_text(text: str, max_length: int) -> str: return text
    def _get_terminal_width() -> int: return 90
    def _clean_ansi_codes(text: str) -> str: return text
    class Operacion: pass
    class LogicalPosition: pass
    utils = None

def display_positions_table(operacion: Operacion, current_market_price: float, side: str):
    """
    Muestra una tabla detallada de las posiciones abiertas y pendientes.
    Se ha añadido la columna ROI (%) para un análisis más completo por posición.
    """
    box_width = _get_terminal_width() - 4
    
    print("\n┌" + "─" * box_width + "┐")
    print(_create_box_line(f"Lista de Posiciones (Abiertas: {operacion.posiciones_abiertas_count}, Pendientes: {operacion.posiciones_pendientes_count})", box_width + 2, 'center'))
    
    if operacion.posiciones_abiertas:
        print("├" + "─" * box_width + "┤")
        
        header_open = (
            f"  {'ID':<8} {'Estado':<10} {'Entrada':>12} {'Capital':>12} {'Tamaño':>12} "
            f"{'PNL (U)':>13} {'ROI (%)':>10}"
        )
        
        print(_create_box_line(_truncate_text(header_open, box_width - 2), box_width + 2))
        print("├" + "─" * box_width + "┤")
        
        for pos in operacion.posiciones_abiertas:
            pnl = 0.0
            roi = 0.0
            entry_price = pos.entry_price or 0.0
            size = pos.size_contracts or 0.0
            
            if current_market_price > 0 and entry_price > 0 and size > 0:
                pnl = (current_market_price - entry_price) * size if side == 'long' else (entry_price - current_market_price) * size

            if pos.capital_asignado and pos.capital_asignado > 0:
                roi = (pnl / pos.capital_asignado) * 100
            
            pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
            reset = "\033[0m"

            line = (
                f"  {str(pos.id)[-6:]:<8} "
                f"\033[92m{pos.estado:<10}\033[0m "
                f"{entry_price:>12.4f} "
                f"{pos.capital_asignado:>12.2f} "
                f"{pos.size_contracts or 0.0:>12.4f} "
                f"{pnl_color}{pnl:>13.4f}{reset}"
                f"{pnl_color}{roi:>9.2f}%{reset}"
            )
            
            print(_create_box_line(_truncate_text(line, box_width - 2), box_width + 2))

    if operacion.posiciones_pendientes:
        print("├" + "─" * box_width + "┤")
        header_pending = f"  {'ID':<10} {'Estado':<12} {'Capital Asignado':>20}"
        print(_create_box_line(_truncate_text(header_pending, box_width-2), box_width + 2))
        print("├" + "─" * box_width + "┤")
        for pos in operacion.posiciones_pendientes:
            line = (
                f"  {str(pos.id)[-6:]:<10} "
                f"\033[96m{pos.estado:<12}\033[0m "
                f"{pos.capital_asignado:>20.2f} USDT"
            )
            print(_create_box_line(_truncate_text(line, box_width-2), box_width + 2))

    print("└" + "─" * box_width + "┘")

def display_strategy_parameters(operacion: Operacion):
    """
    Muestra un cuadro con los parámetros estratégicos clave.
    """
    box_width = _get_terminal_width() - 4
    print("\n┌" + "─" * box_width + "┐")
    print(_create_box_line("Parámetros Estratégicos", box_width + 2, 'center'))
    print("├" + "─" * box_width + "┤")
    
    distancia_promediacion_str = "Desactivado"
    if isinstance(operacion.averaging_distance_pct, (int, float)):
        distancia_promediacion_str = f"{operacion.averaging_distance_pct:.2f}%"

    params = {
        "Apalancamiento (Fijo)": f"{operacion.apalancamiento:.1f}x",
        "Distancia de Promediación (%)": distancia_promediacion_str
    }
    
    max_key_len = max(len(k) for k in params.keys()) if params else 0
    
    for key, value in params.items():
        line = f"  {key:<{max_key_len}} : {value}"
        print(_create_box_line(line, box_width + 2))

    print("└" + "─" * box_width + "┘")
    
# --- INICIO DE LA MODIFICACIÓN ---
# La función display_risk_panel ha sido completamente refactorizada.
def display_risk_panel(
    metrics: Dict[str, Optional[float]],
    current_market_price: float,
    side: str,
    operacion: Operacion
):
    """
    Muestra el panel unificado de cobertura y riesgo estratégico, distinguiendo
    entre el estado actual y la proyección de la estrategia completa.
    """
    box_width = _get_terminal_width() - 4
    reset_code = "\033[0m"
    
    # --- 1. Extracción de Métricas Generales ---
    avg_price_actual_str = f"${metrics.get('avg_entry_price_actual'):.4f}" if metrics.get('avg_entry_price_actual') else "N/A"
    liq_price_actual_str = f"${metrics.get('liquidation_price_actual'):.4f}" if metrics.get('liquidation_price_actual') else "N/A"
    
    liq_price_proj_str = f"${metrics.get('projected_liquidation_price'):.4f}" if metrics.get('projected_liquidation_price') else "N/A"
    total_capital_str = f"${metrics.get('total_capital_at_risk', 0.0):.2f} USDT"
    direction = "caída" if side == 'long' else "subida"
    
    coverage_pct = metrics.get('coverage_pct', 0.0)
    range_start = metrics.get('covered_price_range_start')
    range_end = metrics.get('covered_price_range_end')
    coverage_str = f"{coverage_pct:.2f}% de {direction}"
    if range_start and range_end:
        coverage_str += f" (de {range_start:,.2f} a {range_end:,.2f})"

    liq_dist_pct = metrics.get('liquidation_distance_pct')
    liq_dist_pct_str = "N/A"
    if liq_dist_pct is not None:
        color_dist = "\033[91m" if liq_dist_pct < 20 else ("\033[93m" if liq_dist_pct < 50 else "\033[92m")
        liq_dist_pct_str = f"{color_dist}{liq_dist_pct:.2f}% de margen de {direction}{reset_code}"

    max_pos_str = f"{metrics.get('max_positions', 0):.0f}"
    max_coverage_str = f"{metrics.get('max_coverage_pct', 0.0):.2f}% de {direction}"

    # --- 2. Preparación de Variables para SL/TP de Operación ---
    sl_price_actual_str, tp_price_actual_str = "N/A", "N/A"
    sl_price_proj_str, tp_price_proj_str = "N/A", "N/A"
    sl_dist_str, tp_dist_str = "N/A", "N/A"
    
    # -- Lógica para Riesgo Actual (Posiciones Abiertas) --
    if operacion.posiciones_abiertas_count > 0:
        if operacion.be_sl or operacion.be_tp:
            be_price = operacion.get_live_break_even_price()
            if be_price:
                if operacion.be_sl:
                    sl_dist = operacion.be_sl['distancia']
                    sl_price = be_price * (1 - sl_dist / 100) if side == 'long' else be_price * (1 + sl_dist / 100)
                    sl_price_actual_str = f"${sl_price:.4f}"
                if operacion.be_tp:
                    tp_dist = operacion.be_tp['distancia']
                    tp_price = be_price * (1 + tp_dist / 100) if side == 'long' else be_price * (1 - tp_dist / 100)
                    tp_price_actual_str = f"${tp_price:.4f}"
        
        elif operacion.roi_sl or operacion.roi_tp or operacion.dynamic_roi_sl:
            price_obj = metrics.get('roi_sl_tp_target_price_actual')
            if price_obj is not None:
                if operacion.roi_sl or operacion.dynamic_roi_sl:
                    sl_price_actual_str = f"${price_obj:.4f}"
                elif operacion.roi_tp:
                    tp_price_actual_str = f"${price_obj:.4f}"

    # -- Lógica para Riesgo Proyectado (Todas las Posiciones) --
    if operacion.be_sl or operacion.be_tp:
        be_price_proj = metrics.get('projected_break_even_price')
        if be_price_proj:
            if operacion.be_sl:
                sl_dist = operacion.be_sl['distancia']
                sl_price = be_price_proj * (1 - sl_dist / 100) if side == 'long' else be_price_proj * (1 + sl_dist / 100)
                sl_price_proj_str = f"${sl_price:.4f}"
                if current_market_price > 0:
                    dist_pct = ((sl_price - current_market_price) / current_market_price) * 100 if side == 'short' else ((current_market_price - sl_price) / current_market_price) * 100
                    sl_dist_str = f"\033[91m{dist_pct:.2f}% de margen{reset_code}"
            if operacion.be_tp:
                tp_dist = operacion.be_tp['distancia']
                tp_price = be_price_proj * (1 + tp_dist / 100) if side == 'long' else be_price_proj * (1 - tp_dist / 100)
                tp_price_proj_str = f"${tp_price:.4f}"
                if current_market_price > 0:
                    dist_pct = ((tp_price - current_market_price) / current_market_price) * 100 if side == 'long' else ((current_market_price - tp_price) / current_market_price) * 100
                    tp_dist_str = f"\033[92m{dist_pct:+.2f}% de margen{reset_code}"

    elif operacion.roi_sl or operacion.roi_tp or operacion.dynamic_roi_sl:
        price_obj = metrics.get('projected_roi_target_price')
        if price_obj is not None:
            if operacion.roi_sl or operacion.dynamic_roi_sl:
                sl_price_proj_str = f"${price_obj:.4f}"
                if current_market_price > 0:
                    dist_pct = ((price_obj - current_market_price) / current_market_price) * 100 if side == 'short' else ((current_market_price - price_obj) / current_market_price) * 100
                    sl_dist_str = f"\033[91m{dist_pct:.2f}% de margen{reset_code}"
            elif operacion.roi_tp:
                tp_price_proj_str = f"${price_obj:.4f}"
                if current_market_price > 0:
                    dist_pct = ((price_obj - current_market_price) / current_market_price) * 100 if side == 'long' else ((current_market_price - price_obj) / current_market_price) * 100
                    tp_dist_str = f"\033[92m{dist_pct:+.2f}% de margen{reset_code}"

    # --- 3. Renderizado del Panel ---
    print("\n┌" + "─" * box_width + "┐")
    print(_create_box_line("Panel de Riesgo: Realidad vs. Proyección", box_width + 2, 'center'))
    
    print("├" + "─" * box_width + "┤")
    print(_create_box_line(f"\033[96m--- RIESGO ACTUAL (Solo Posiciones Abiertas) ---\033[0m", box_width + 2))
    print(_create_box_line(f"  Precio Promedio             : {avg_price_actual_str}", box_width + 2))
    print(_create_box_line(f"  Precio Liquidación          : \033[91m{liq_price_actual_str}{reset_code}", box_width + 2))
    if sl_price_actual_str != "N/A":
        print(_create_box_line(f"  Precio Obj. SL Activo       : \033[91m{sl_price_actual_str}{reset_code}", box_width + 2))
    if tp_price_actual_str != "N/A":
        print(_create_box_line(f"  Precio Obj. TP Activo       : \033[92m{tp_price_actual_str}{reset_code}", box_width + 2))

    print("├" + "─" * box_width + "┤")
    print(_create_box_line(f"\033[96m--- RIESGO PROYECTADO (Todas las Posiciones) ---\033[0m", box_width + 2))
    print(_create_box_line(f"  Capital Total en Juego      : {total_capital_str}", box_width + 2))
    print(_create_box_line(f"  Cobertura Operativa         : {coverage_str}", box_width + 2))
    print(_create_box_line(f"  Precio Liq. Proyectado      : \033[91m{liq_price_proj_str}{reset_code}", box_width + 2))
    print(_create_box_line(f"  Distancia a Liq. Proyectada : {liq_dist_pct_str}", box_width + 2))
    if sl_price_proj_str != "N/A":
        print(_create_box_line(f"  Precio Obj. SL Proyectado   : \033[91m{sl_price_proj_str}{reset_code}", box_width + 2))
        print(_create_box_line(f"  Distancia a SL Proyectado   : {sl_dist_str}", box_width + 2))
    if tp_price_proj_str != "N/A":
        print(_create_box_line(f"  Precio Obj. TP Proyectado   : \033[92m{tp_price_proj_str}{reset_code}", box_width + 2))
        print(_create_box_line(f"  Distancia a TP Proyectado   : {tp_dist_str}", box_width + 2))
    
    print("├" + "─" * box_width + "┤")
    print(_create_box_line(f"\033[96m--- SIMULACIÓN MÁXIMA TEÓRICA --- \033[0m", box_width + 2))
    print(_create_box_line(f"  Posiciones Máximas Seguras  : {max_pos_str}", box_width + 2))
    print(_create_box_line(f"  Cobertura Máxima Teórica    : {max_coverage_str}", box_width + 2))

    print("└" + "─" * box_width + "┘")
# --- FIN DE LA MODIFICACIÓN ---