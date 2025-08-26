# Contenido completo y final para: core/menu/screens/operation_manager/position_editor/_displayers.py

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
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se añade la columna 'ROI (%)' al encabezado y se reajustan los anchos.
        header_open = (
            f"  {'ID':<8} {'Estado':<10} {'Entrada':>12} {'Capital':>12} {'Tamaño':>12} "
            f"{'PNL (U)':>13} {'ROI (%)':>10}"
        )
        # --- FIN DE LA MODIFICACIÓN ---
        
        print(_create_box_line(_truncate_text(header_open, box_width - 2), box_width + 2))
        print("├" + "─" * box_width + "┤")
        
        for pos in operacion.posiciones_abiertas:
            pnl = 0.0
            roi = 0.0
            entry_price = pos.entry_price or 0.0
            size = pos.size_contracts or 0.0
            
            if current_market_price > 0 and entry_price > 0 and size > 0:
                pnl = (current_market_price - entry_price) * size if side == 'long' else (entry_price - current_market_price) * size

            # --- INICIO DE LA MODIFICACIÓN ---
            # Se calcula el ROI basado en el PNL y el capital asignado a la posición.
            if pos.capital_asignado and pos.capital_asignado > 0:
                roi = (pnl / pos.capital_asignado) * 100
            # --- FIN DE LA MODIFICACIÓN ---
            
            pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
            reset = "\033[0m"

            # --- INICIO DE LA MODIFICACIÓN ---
            # Se añade el ROI formateado a la línea de la tabla.
            line = (
                f"  {str(pos.id)[-6:]:<8} "
                f"\033[92m{pos.estado:<10}\033[0m "
                f"{entry_price:>12.4f} "
                f"{pos.capital_asignado:>12.2f} "
                f"{pos.size_contracts or 0.0:>12.4f} "
                f"{pnl_color}{pnl:>13.4f}{reset}"
                f"{pnl_color}{roi:>9.2f}%{reset}"
            )
            # --- FIN DE LA MODIFICACIÓN ---
            
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
    
    params = {
        "Apalancamiento (Fijo)": f"{operacion.apalancamiento:.1f}x",
        "Distancia de Promediación (%)": f"{operacion.averaging_distance_pct:.2f}%"
    }
    
    max_key_len = max(len(k) for k in params.keys()) if params else 0
    
    for key, value in params.items():
        line = f"  {key:<{max_key_len}} : {value}"
        print(_create_box_line(line, box_width + 2))

    print("└" + "─" * box_width + "┘")
# =============================================================================
# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================

# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función Única) ---
# ==============================================================================

def display_risk_panel(
    metrics: Dict[str, Optional[float]],
    current_market_price: float,
    side: str,
    operacion: Operacion
):
    """
    Muestra el panel unificado de cobertura y riesgo estratégico.
    """
    box_width = _get_terminal_width() - 4
    
    avg_price_str = f"{metrics.get('avg_entry_price'):.4f} USDT" if metrics.get('avg_entry_price') else "N/A"
    liq_price_str = f"{metrics.get('liquidation_price'):.4f} USDT" if metrics.get('liquidation_price') else "N/A"
    total_capital_str = f"${metrics.get('total_capital_at_risk', 0.0):.2f} USDT"
    
    coverage_pct = metrics.get('coverage_pct', 0.0)
    range_start = metrics.get('covered_price_range_start')
    range_end = metrics.get('covered_price_range_end')
    direction = "caída" if side == 'long' else "subida"
    coverage_str = f"{coverage_pct:.2f}% de {direction}"
    if range_start and range_end:
        coverage_str += f" (de {range_start:,.2f} a {range_end:,.2f})"

    proj_liq_price_str = f"{metrics.get('projected_liquidation_price'):.4f} USDT" if metrics.get('projected_liquidation_price') else "N/A"
    
    liq_dist_pct = metrics.get('liquidation_distance_pct')
    liq_dist_pct_str = "N/A"
    if liq_dist_pct is not None:
        color = "\033[91m"
        if liq_dist_pct > 50: color = "\033[92m"
        elif liq_dist_pct > 20: color = "\033[93m"
        liq_dist_pct_str = f"{color}{liq_dist_pct:.2f}% de margen de {direction}\033[0m"

    max_pos_str = f"{metrics.get('max_positions', 0):.0f}"
    max_coverage_str = f"{metrics.get('max_coverage_pct', 0.0):.2f}% de {direction}"
    
    # --- INICIO DE LA LÓGICA CORREGIDA ---
    is_sl_roi_configured = (
        getattr(operacion, 'sl_roi_pct') is not None or
        getattr(operacion, 'dynamic_roi_sl_enabled', False)
    )

    roi_target_price_str = "N/A (ROI SL/TP desactivado)"

    if is_sl_roi_configured:
        roi_target_price = metrics.get('roi_sl_tp_target_price')
        
        # Determinar si es SL o TP para el color
        sl_roi_pct_target = operacion.sl_roi_pct
        if getattr(operacion, 'dynamic_roi_sl_enabled', False):
            sl_roi_pct_target = (getattr(operacion, 'realized_twrr_roi', 0) - 
                                 (getattr(operacion, 'dynamic_roi_sl_trail_pct', 0) or 0))

        color_code = "\033[91m" if (sl_roi_pct_target or 0) < 0 else "\033[92m"
        reset_code = "\033[0m"
        
        roi_target_price_str = (f"{color_code}${roi_target_price:.4f} USDT{reset_code}" 
                                if roi_target_price is not None else "Pendiente (esperando 1ra posición)")
    # --- FIN DE LA LÓGICA CORREGIDA ---

    print("\n┌" + "─" * box_width + "┐")
    print(_create_box_line("Panel de Cobertura y Riesgo Estratégico", box_width + 2, 'center'))
    
    print("├" + "─" * box_width + "┤")
    print(_create_box_line(f"\033[96m--- ESTADO ACTUAL (con posiciones abiertas) ---\033[0m", box_width + 2))
    print(_create_box_line(f"  Precio Promedio Actual      : {avg_price_str}", box_width + 2))
    print(_create_box_line(f"  Precio Liquidación Actual   : {liq_price_str}", box_width + 2))

    print("├" + "─" * box_width + "┤")
    print(_create_box_line(f"\033[96m--- PROYECCIÓN (con todas las posiciones) ---\033[0m", box_width + 2))
    print(_create_box_line(f"  Capital Total en Juego      : {total_capital_str}", box_width + 2))
    print(_create_box_line(f"  Cobertura Operativa         : {coverage_str}", box_width + 2))
    print(_create_box_line(f"  Precio Liq. Proyectado      : {proj_liq_price_str}", box_width + 2))
    print(_create_box_line(f"  Distancia a Liq. Proyectada : {liq_dist_pct_str}", box_width + 2))
    print(_create_box_line(f"  Precio Obj. SL/TP por ROI   : {roi_target_price_str}", box_width + 2))
    
    print("├" + "─" * box_width + "┤")
    print(_create_box_line(f"\033[96m--- SIMULACIÓN MÁXIMA TEÓRICA --- \033[0m", box_width + 2))
    print(_create_box_line(f"  Posiciones Máximas Seguras  : {max_pos_str}", box_width + 2))
    print(_create_box_line(f"  Cobertura Máxima Teórica    : {max_coverage_str}", box_width + 2))

    print("└" + "─" * box_width + "┘")

# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================
# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================