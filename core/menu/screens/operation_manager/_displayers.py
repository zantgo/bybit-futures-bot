"""
Módulo de Visualizadores del Panel de Control de Operación.

Contiene todas las funciones auxiliares cuya única responsabilidad es
mostrar (imprimir en la consola) secciones de información específicas, como
los detalles de la operación, las estadísticas de capital o las tablas de posiciones.
Estas funciones son "vistas puras": solo renderizan los datos que reciben.
"""
from typing import Any, Dict, List
import datetime
import shutil
import re
import numpy as np

try:
    from core.strategy.entities import Operacion, LogicalPosition
    from core import utils
except ImportError:
    utils = None
    class LogicalPosition:
        pass
    class Operacion:
        def __init__(self):
            self.estado, self.tendencia, self.accion_al_finalizar, self.tipo_cond_entrada = 'DESCONOCIDO', 'N/A', 'N/A', 'N/A'
            self.apalancamiento, self.pnl_realizado_usdt = 10.0, 0.0
            self.capital_inicial_usdt, self.comisiones_totales_usdt = 0.0, 0.0
            self.total_reinvertido_usdt, self.valor_cond_entrada, self.valor_cond_salida = 0.0, 0.0, None
            self.tsl_roi_activacion_pct, self.tsl_roi_distancia_pct, self.sl_roi_pct = None, None, None
            self.tsl_roi_peak_pct = 0.0
            self.comercios_cerrados_contador, self.tiempo_maximo_min, self.max_comercios = 0, None, None
            self.tiempo_inicio_ejecucion, self.tipo_cond_salida = None, None
            self.tsl_roi_activo = False
            self.posiciones: List[LogicalPosition] = []
        
        def get_live_performance(self, current_price: float, utils_module: Any) -> Dict[str, float]:
            return {"pnl_no_realizado": 0.0, "pnl_total": 0.0, "equity_actual_vivo": 0.0, "roi_twrr_vivo": 0.0}
        @property
        def equity_total_usdt(self): return self.capital_inicial_usdt + self.pnl_realizado_usdt
        @property
        def capital_operativo_logico_actual(self) -> float: return 0.0
        @property
        def capital_en_uso(self) -> float: return 0.0
        @property
        def capital_disponible(self) -> float: return 0.0
        @property
        def posiciones_abiertas(self) -> list: return []
        @property
        def posiciones_pendientes(self) -> list: return []
        @property
        def posiciones_abiertas_count(self) -> int: return 0


# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el __init__.py del módulo."""
    global _deps
    _deps = dependencies

# --- Funciones de Ayuda para UI Dinámica ---

def _get_terminal_width():
    try:
        return shutil.get_terminal_size().columns
    except:
        return 90

def _get_unified_box_width() -> int:
    terminal_width = _get_terminal_width()
    open_pos_content_width = 8 + 10 + 11 + 12 + 10 + 10 + 20 
    pending_pos_content_width = 12 + 22 + 22
    content_width = max(open_pos_content_width, pending_pos_content_width) + 4
    box_width = min(terminal_width - 2, content_width, 120)
    return box_width

def _clean_ansi_codes(text: str) -> str:
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', str(text))

def _truncate_text(text: str, max_length: int) -> str:
    clean_text = _clean_ansi_codes(text)
    if len(clean_text) <= max_length:
        return text
    truncated_clean = clean_text[:max_length-3] + "..."
    color_codes = re.findall(r'(\x1B\[[0-?]*[ -/]*[@-~])', text)
    if color_codes:
        return color_codes[0] + truncated_clean + "\033[0m"
    return truncated_clean

def _create_box_line(content: str, width: int, alignment: str = 'left') -> str:
    clean_content = _clean_ansi_codes(content)
    padding_needed = width - 2 - len(clean_content)
    if padding_needed < 0:
        content = _truncate_text(content, width - 2)
        clean_content = _clean_ansi_codes(content)
        padding_needed = width - 2 - len(clean_content)
    if alignment == 'center':
        left_pad = padding_needed // 2
        right_pad = padding_needed - left_pad
        return f"│{' ' * left_pad}{content}{' ' * right_pad}│"
    elif alignment == 'right':
        return f"│{' ' * padding_needed}{content} │"
    else:
        return f"│ {content}{' ' * (padding_needed - 1)}│"

# --- Funciones de Visualización ---

def _display_operation_details(summary: Dict[str, Any], operacion: Operacion, side: str):
    box_width = _get_unified_box_width()
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Parámetros de la Operación", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    if not operacion or operacion.estado == 'DETENIDA':
        print(_create_box_line(f"La operación {side.upper()} está DETENIDA", box_width, 'center'))
        print("└" + "─" * (box_width - 2) + "┘")
        return

    tendencia = operacion.tendencia
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m"}
    color, reset = color_map.get(tendencia, ""), "\033[0m"
    
    pos_abiertas = operacion.posiciones_abiertas_count
    pos_total = len(operacion.posiciones)

    fecha_activacion_str = "N/A"
    tiempo_ejecucion_str = "N/A"
    if operacion.tiempo_inicio_ejecucion:
        fecha_activacion_str = operacion.tiempo_inicio_ejecucion.strftime('%H:%M:%S %d-%m-%Y (UTC)')
        if operacion.estado == 'ACTIVA':
            duration = datetime.datetime.now(datetime.timezone.utc) - operacion.tiempo_inicio_ejecucion
            total_seconds = int(duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            tiempo_ejecucion_str = f"{hours:02}:{minutes:02}:{seconds:02}"

    data = {
        "Tendencia": f"{color}{tendencia}{reset}",
        "Posiciones (Abiertas/Total)": f"{pos_abiertas} / {pos_total}",
        "Apalancamiento (Fijo)": f"{operacion.apalancamiento:.1f}x",
        "Fecha Activacion": fecha_activacion_str,
        "Tiempo Activa": tiempo_ejecucion_str
    }

    max_key_len = max(len(_clean_ansi_codes(k)) for k in data.keys()) if data else 0
    for key, value in data.items():
        content = f"{key:<{max_key_len}} : {value}"
        print(_create_box_line(content, box_width))

    print("└" + "─" * (box_width - 2) + "┘")

def _display_capital_stats(summary: Dict[str, Any], operacion: Operacion, side: str, current_price: float):
    box_width = _get_unified_box_width()
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Capital y Rendimiento", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    if not operacion or operacion.estado == 'DETENIDA':
        print(_create_box_line(f"La operación {side.upper()} está DETENIDA", box_width, 'center'))
        print("└" + "─" * (box_width - 2) + "┘")
        return
    
    utils_module = _deps.get("utils_module")
    if not utils_module:
        print(_create_box_line("Error: Módulo utils no disponible", box_width, 'center'))
        print("└" + "─" * (box_width - 2) + "┘")
        return

    # --- INICIO DE LA MODIFICACIÓN (Verificación final) ---
    # Se confirma que todos los datos de rendimiento se obtienen de la llamada
    # a get_live_performance(), que es la única fuente de verdad corregida.
    # No hay cambios funcionales aquí, solo se confirma que el código ya es correcto.
    live_performance = operacion.get_live_performance(current_price, utils_module)
    
    pnl_realizado = operacion.pnl_realizado_usdt
    pnl_no_realizado = live_performance.get("pnl_no_realizado", 0.0)
    equity_actual_vivo = live_performance.get("equity_actual_vivo", 0.0)
    roi_twrr_vivo = live_performance.get("roi_twrr_vivo", 0.0)
    # --- FIN DE LA MODIFICACIÓN ---

    capital_inicial = operacion.capital_inicial_usdt
    equity_total_historico = operacion.equity_total_usdt
    comisiones_totales = getattr(operacion, 'comisiones_totales_usdt', 0.0)
    total_reinvertido = getattr(operacion, 'total_reinvertido_usdt', 0.0)

    def get_color(value): 
        return "\033[92m" if value >= 0 else "\033[91m"
    reset = "\033[0m"
    
    data = {
        "--- CAPITAL ---": "",
        "Capital Inicial (Base ROI)": f"${capital_inicial:.2f}",
        "Capital Operativo (Lógico)": f"${operacion.capital_operativo_logico_actual:.2f}",
        "Capital en Uso": f"${operacion.capital_en_uso:.2f}",
        "Capital Disponible": f"${operacion.capital_disponible:.2f}",
        "--- RENDIMIENTO ---": "",
        "Equity Total (Histórico)": f"${equity_total_historico:.2f}",
        "Equity Actual (Vivo)": f"{get_color(pnl_no_realizado)}{equity_actual_vivo:.2f}${reset}",
        "PNL Realizado / No Realiz.": f"{get_color(pnl_realizado)}{pnl_realizado:+.4f}${reset} / {get_color(pnl_no_realizado)}{pnl_no_realizado:+.4f}${reset}",
        "ROI (TWRR)": f"{get_color(roi_twrr_vivo)}{roi_twrr_vivo:+.2f}%{reset}",
        "--- CONTADORES ---": "",
        "Total Reinvertido": f"${total_reinvertido:.4f}",
        "Comisiones Totales": f"${comisiones_totales:.4f}",
        "Trades Cerrados": str(operacion.comercios_cerrados_contador),
    }

    max_key_len = max(len(_clean_ansi_codes(k)) for k in data.keys())
    for key, value in data.items():
        if "---" in key: 
            print(_create_box_line(f"\033[96m{key.center(box_width - 6)}\033[0m", box_width))
        else: 
            print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))
    print("└" + "─" * (box_width - 2) + "┘")

def _display_positions_tables(summary: Dict[str, Any], operacion: Operacion, current_price: float, side: str):
    box_width = _get_unified_box_width()

    open_positions = operacion.posiciones_abiertas
    open_count = len(open_positions)
    total_count = len(operacion.posiciones)

    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line(f"Posiciones Abiertas ({open_count}/{total_count})", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    if not open_positions:
        print(_create_box_line("(No hay posiciones abiertas)", box_width, 'center'))
    else:
        header = f"  {'ID':<7} {'Entrada':>9} {'Márgen':>10} {'PNL (U)':>11} {'SL':>9} {'TP Act.':>9} {'TS Status':<20}"
        print(_create_box_line(_truncate_text(header, box_width - 2), box_width))
        print("├" + "─" * (box_width - 2) + "┤")

        for pos in open_positions:
            pnl = 0.0
            entry_price = pos.entry_price or 0.0
            size = pos.size_contracts or 0.0
            if current_price > 0 and entry_price > 0:
                pnl = (current_price - entry_price) * size if side == 'long' else (entry_price - current_price) * size

            pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
            reset = "\033[0m"
            sl_str = f"{pos.stop_loss_price:.4f}" if pos.stop_loss_price else "N/A"

            tp_act_price = 0.0
            tsl_act_pct = pos.tsl_activation_pct_at_open
            if tsl_act_pct > 0 and entry_price > 0:
                tp_act_price = entry_price * (1 + tsl_act_pct / 100) if side == 'long' else entry_price * (1 - tsl_act_pct / 100)
            tp_act_str = f"{tp_act_price:.4f}" if tp_act_price > 0 else "N/A"

            ts_status_str = "Inactivo"
            if pos.ts_is_active:
                ts_stop = pos.ts_stop_price
                ts_status_str = f"Activo @ {ts_stop:.4f}" if ts_stop else "Activo (Calc...)"

            line = (
                f"  {str(pos.id)[-6:]:<7} "
                f"{entry_price:>9.4f} "
                f"{pos.margin_usdt:>10.2f} "
                f"{pnl_color}{pnl:>+11.4f}{reset} "
                f"{sl_str:>9} "
                f"{tp_act_str:>9} "
                f"{ts_status_str:<20}"
            )
            print(_create_box_line(_truncate_text(line, box_width - 2), box_width))
    print("└" + "─" * (box_width - 2) + "┘")

    pending_positions = operacion.posiciones_pendientes
    if pending_positions:
        print("┌" + "─" * (box_width - 2) + "┐")
        print(_create_box_line(f"Posiciones Pendientes ({len(pending_positions)})", box_width, 'center'))
        print("├" + "─" * (box_width - 2) + "┤")
        
        header = f"  {'ID':<10} {'Capital Asignado':>20} {'Valor Nominal':>20}"
        print(_create_box_line(_truncate_text(header, box_width - 2), box_width))
        print("├" + "─" * (box_width - 2) + "┤")

        for pos in pending_positions:
            line = (
                f"  {str(pos.id)[-6:]:<10} "
                f"{pos.capital_asignado:>20.2f} USDT"
                f"{pos.valor_nominal:>20.2f} USDT"
            )
            print(_create_box_line(_truncate_text(line, box_width - 2), box_width))
        print("└" + "─" * (box_width - 2) + "┘")


def _display_operation_conditions(operacion: Operacion):
    box_width = _get_unified_box_width()

    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Condiciones de la Operación", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    status_color_map = {'ACTIVA': "\033[92m", 'PAUSADA': "\033[93m", 'DETENIDA': "\033[90m", 'EN_ESPERA': "\033[96m", 'DETENIENDO': "\033[91m"}
    color = status_color_map.get(operacion.estado, "")
    reset = "\033[0m"

    print(_create_box_line(f"Estado Actual: {color}{operacion.estado}{reset}", box_width))
    if operacion.estado != 'DETENIDA':
        print(_create_box_line(f"Acción al Finalizar por Límite: {operacion.accion_al_finalizar.upper()}", box_width))

    print("├" + "─" * (box_width - 2) + "┤")
    print(_create_box_line("Condición de Entrada:", box_width))
    cond_in_str = "No definida (Operación Inactiva)"
    if operacion.estado != 'DETENIDA':
        if operacion.tipo_cond_entrada == 'MARKET':
            cond_in_str = "- Inmediata (Precio de Mercado)"
        elif operacion.tipo_cond_entrada and operacion.valor_cond_entrada is not None:
            op = ">" if operacion.tipo_cond_entrada == 'PRICE_ABOVE' else "<"
            cond_in_str = f"- Precio {op} {operacion.valor_cond_entrada:.4f}"
    print(_create_box_line(f"  {cond_in_str}", box_width))

    print("├" + "─" * (box_width - 2) + "┤")
    print(_create_box_line("Condiciones de Salida (CUALQUIERA activa la acción):", box_width))
    exit_conditions = []
    if operacion.tipo_cond_salida and operacion.valor_cond_salida is not None:
        op = ">" if operacion.tipo_cond_salida == 'PRICE_ABOVE' else "<"
        exit_conditions.append(f"Precio {op} {operacion.valor_cond_salida:.4f}")

    if operacion.tsl_roi_activacion_pct is not None and operacion.tsl_roi_distancia_pct is not None:
        tsl_config_str = (f"TSL-ROI: Activa a +{operacion.tsl_roi_activacion_pct}%, Distancia {operacion.tsl_roi_distancia_pct}%")
        if operacion.tsl_roi_activo:
            tsl_config_str += f" (\033[92mACTIVO\033[0m | Pico: {operacion.tsl_roi_peak_pct:.2f}%)"
        exit_conditions.append(tsl_config_str)

    if operacion.sl_roi_pct is not None:
        if operacion.sl_roi_pct < 0:
            exit_conditions.append(f"SL-ROI <= {operacion.sl_roi_pct}%")
        else:
            exit_conditions.append(f"TP-ROI >= {operacion.sl_roi_pct}%")

    if operacion.tiempo_maximo_min is not None:
        exit_conditions.append(f"Tiempo >= {operacion.tiempo_maximo_min} min")
    if operacion.max_comercios is not None:
        exit_conditions.append(f"Trades >= {operacion.max_comercios}")

    if not exit_conditions and operacion.estado != 'DETENIDA':
        print(_create_box_line("  - Ninguna (finalización manual)", box_width))
    elif not exit_conditions:
         print(_create_box_line("  (Operación inactiva)", box_width))
    else:
        for cond in exit_conditions:
            print(_create_box_line(f"  - {cond}", box_width))

    print("└" + "─" * (box_width - 2) + "┘")