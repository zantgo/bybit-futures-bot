# Contenido completo y final para: core/menu/screens/operation_manager/position_editor/_displayers.py

from typing import Any, Dict, List, Optional
import shutil
import re

# --- INICIO DE LA CORRECCIÓN ---
# Movemos las importaciones críticas fuera del try/except para que fallen ruidosamente
# si no se encuentran, en lugar de fallar silenciosamente.
try:
    from ...._helpers import _create_box_line, _truncate_text, _get_terminal_width, _clean_ansi_codes
    from core.strategy.entities import Operacion, LogicalPosition
    from core import utils
except ImportError:
    # Estos fallbacks son solo para que el linter no se queje, pero el programa no debería llegar aquí.
    def _create_box_line(content: str, width: int, alignment: str = 'left') -> str: return content
    def _truncate_text(text: str, max_length: int) -> str: return text
    def _get_terminal_width() -> int: return 90
    def _clean_ansi_codes(text: str) -> str: return text
    class Operacion: pass
    class LogicalPosition: pass
    utils = None
# --- FIN DE LA CORRECCIÓN ---

def display_positions_table(operacion: Operacion, current_market_price: float, side: str):
    """
    Muestra una tabla detallada de las posiciones abiertas y pendientes.
    Incluye PNL y ROI en vivo, con formato mejorado para mayor precisión.
    """
    box_width = _get_terminal_width() - 4
    
    print("\n┌" + "─" * box_width + "┐")
    print(_create_box_line(f"Lista de Posiciones (Abiertas: {operacion.posiciones_abiertas_count}, Pendientes: {operacion.posiciones_pendientes_count})", box_width + 2, 'center'))
    
    if operacion.posiciones_abiertas:
        print("├" + "─" * box_width + "┤")
        
        header_open = (
            f"  {'ID':<8} {'Estado':<10} {'Entrada':>12} {'Capital':>12} {'Tamaño':>15} "
            f"{'PNL (U)':>15} {'ROI (%)':>12}"
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
            
            # --- INICIO DE LA CORRECCIÓN ---
            # Aseguramos que 'utils' existe y calculamos el ROI.
            if utils and pos.capital_asignado > 0:
                roi = utils.safe_division(pnl, pos.capital_asignado) * 100

            pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
            reset = "\033[0m"

            # Formateo mejorado: PNL con 4 decimales, ROI con 3 para más precisión.
            line = (
                f"  {str(pos.id)[-6:]:<8} "
                f"\033[92m{pos.estado:<10}\033[0m "
                f"{entry_price:>12.4f} "
                f"{pos.capital_asignado:>12.2f} "
                f"{pos.size_contracts or 0.0:>15.4f} "
                f"{pnl_color}{pnl:>15.4f}{reset} "
                f"{pnl_color}{roi:>12.3f}{reset}" # <-- CAMBIO CLAVE: .2f a .3f
            )
            # --- FIN DE LA CORRECCIÓN ---
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

def display_risk_panel(
    metrics: Dict[str, Optional[float]],
    current_market_price: float,
    side: str
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
    
    print("\n┌" + "─" * box_width + "┐")
    print(_create_box_line("Panel de Cobertura y Riesgo Estratégico", box_width + 2, 'center'))
    
    print("├" + "─" * box_width + "┤")
    print(_create_box_line(f"\033[96m--- ESTADO ACTUAL (con posiciones abiertas) ---\033[0m", box_width + 2))
    print(_create_box_line(f"  Precio Promedio Actual      : {avg_price_str}", box_width + 2))
    print(_create_box_line(f"  Precio Liquidación Actual   : {liq_price_str}", box_width + 2))

    print("├" + "─" * box_width + "┤")
    print(_create_box_line(f"\033[96m--- PROYECCIÓN (con todas las posiciones pendientes) ---\033[0m", box_width + 2))
    print(_create_box_line(f"  Capital Total en Juego      : {total_capital_str}", box_width + 2))
    print(_create_box_line(f"  Cobertura Operativa         : {coverage_str}", box_width + 2))
    print(_create_box_line(f"  Precio Liq. Proyectado      : {proj_liq_price_str}", box_width + 2))
    print(_create_box_line(f"  Distancia a Liq. Proyectada : {liq_dist_pct_str}", box_width + 2))
    
    print("├" + "─" * box_width + "┤")
    print(_create_box_line(f"\033[96m--- SIMULACIÓN MÁXIMA TEÓRICA --- \033[0m", box_width + 2))
    print(_create_box_line(f"  Posiciones Máximas Seguras  : {max_pos_str}", box_width + 2))
    print(_create_box_line(f"  Cobertura Máxima Teórica    : {max_coverage_str}", box_width + 2))

    print("└" + "─" * box_width + "┘")