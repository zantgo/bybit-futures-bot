# ./core/menu/screens/operation_manager/_displayers.py

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
    # <<-- CAMBIO: Se importa LogicalPosition para type hinting.
    from core.strategy.entities import Operacion, LogicalPosition
    from core import utils
except ImportError:
    utils = None
    # <<-- CAMBIO: Se actualiza el mock de Operacion con la nueva estructura de datos.
    class LogicalPosition:
        pass
    class Operacion:
        def __init__(self):
            self.estado, self.tendencia, self.accion_al_finalizar, self.tipo_cond_entrada = 'DESCONOCIDO', 'N/A', 'N/A', 'N/A'
            self.apalancamiento, self.pnl_realizado_usdt, self.pnl_no_realizado_usdt_vivo = 0.0, 0.0, 0.0
            self.capital_inicial_usdt, self.comisiones_totales_usdt = 0.0, 0.0
            self.total_reinvertido_usdt, self.valor_cond_entrada, self.valor_cond_salida = 0.0, 0.0, None
            self.tsl_roi_activacion_pct, self.tsl_roi_distancia_pct, self.sl_roi_pct = None, None, None
            self.tsl_roi_peak_pct = 0.0
            self.comercios_cerrados_contador, self.tiempo_maximo_min, self.max_comercios = 0, None, None
            self.tiempo_inicio_ejecucion, self.tipo_cond_salida = None, None
            self.tsl_roi_activo = False
            self.posiciones: List[LogicalPosition] = []
        
        @property
        def equity_total_usdt(self): return self.capital_inicial_usdt + self.pnl_realizado_usdt
        @property
        def equity_actual_vivo(self): return self.equity_total_usdt + self.pnl_no_realizado_usdt_vivo
        @property
        def twrr_roi(self) -> float: return 0.0
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
    """Obtiene el ancho actual del terminal."""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 90

def _get_unified_box_width() -> int:
    """
    Calcula un ancho unificado para todas las cajas de esta pantalla,
    basado en el contenido más ancho (la tabla de posiciones) y el tamaño del terminal.
    """
    terminal_width = _get_terminal_width()
    # <<-- CAMBIO: Ancho ajustado para la nueva tabla de posiciones abiertas
    content_width = 7 + 9 + 10 + 10 + 9 + 9 + 20 + (6 * 2) 
    box_width = min(terminal_width - 2, content_width, 120)
    return box_width

def _clean_ansi_codes(text: str) -> str:
    """Función de ayuda para eliminar códigos de color ANSI de un string."""
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', str(text))

def _truncate_text(text: str, max_length: int) -> str:
    """Trunca el texto si es muy largo, añadiendo '...' al final."""
    clean_text = _clean_ansi_codes(text)
    if len(clean_text) <= max_length:
        return text

    truncated_clean = clean_text[:max_length-3] + "..."

    color_codes = re.findall(r'(\x1B\[[0-?]*[ -/]*[@-~])', text)
    if color_codes:
        return color_codes[0] + truncated_clean + "\033[0m"
    return truncated_clean

def _create_box_line(content: str, width: int, alignment: str = 'left') -> str:
    """Crea una línea de caja con el contenido alineado correctamente."""
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
    """Muestra la sección de parámetros de la operación para un lado específico."""
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
    
    # <<-- CAMBIO: La lógica de conteo de posiciones ahora usa las nuevas propiedades.
    pos_abiertas = operacion.posiciones_abiertas_count
    pos_total = len(operacion.posiciones)
    # <<-- ANTERIOR:
    # pos_abiertas = summary.get(f'open_{side}_positions_count', 0)
    # pos_total = operacion.max_posiciones_logicas

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
        # <<-- CAMBIO: Se elimina el tamaño base, se actualiza el conteo de posiciones.
        # "Tamaño Base": f"${operacion.tamaño_posicion_base_usdt:.2f} USDT",
        "Posiciones (Abiertas/Total)": f"{pos_abiertas} / {pos_total}",
        "Apalancamiento": f"{operacion.apalancamiento:.1f}x",
        "Fecha Activacion": fecha_activacion_str,
        "Tiempo Activa": tiempo_ejecucion_str
    }

    max_key_len = max(len(_clean_ansi_codes(k)) for k in data.keys()) if data else 0
    for key, value in data.items():
        content = f"{key:<{max_key_len}} : {value}"
        print(_create_box_line(content, box_width))

    print("└" + "─" * (box_width - 2) + "┘")

def _display_capital_stats(summary: Dict[str, Any], operacion: Operacion, side: str, current_price: float):
    """Muestra la sección de estadísticas de capital, ahora basada en el nuevo modelo."""
    box_width = _get_unified_box_width()

    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Capital y Rendimiento", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    if not operacion or operacion.estado == 'DETENIDA':
        print(_create_box_line(f"La operación {side.upper()} está DETENIDA", box_width, 'center'))
        print("└" + "─" * (box_width - 2) + "┘")
        return
    
    # <<-- CAMBIO: Toda esta sección ha sido reescrita para usar las nuevas propiedades de la entidad Operacion.
    # <<-- La lógica de cálculo ahora está encapsulada en la entidad, haciendo esta vista mucho más limpia.

    def get_color(value): 
        return "\033[92m" if value >= 0 else "\033[91m"
    reset = "\033[0m"
    
    # Obtener valores directamente de la operación
    pnl_realizado = operacion.pnl_realizado_usdt
    pnl_no_realizado = operacion.pnl_no_realizado_usdt_vivo # Este valor se actualiza externamente
    roi_twrr = operacion.twrr_roi

    data = {
        "--- CAPITAL ---": "",
        "Capital Inicial (Base ROI)": f"${operacion.capital_inicial_usdt:.2f}",
        "Capital Operativo (Lógico)": f"${operacion.capital_operativo_logico_actual:.2f}",
        "Capital en Uso": f"${operacion.capital_en_uso:.2f}",
        "Capital Disponible": f"${operacion.capital_disponible:.2f}",
        "--- RENDIMIENTO ---": "",
        "Equity Total (Histórico)": f"${operacion.equity_total_usdt:.2f}",
        "Equity Actual (Vivo)": f"{get_color(operacion.equity_actual_vivo)}{operacion.equity_actual_vivo:+.2f}${reset}",
        "PNL Realizado / No Realiz.": f"{get_color(pnl_realizado)}{pnl_realizado:+.4f}${reset} / {get_color(pnl_no_realizado)}{pnl_no_realizado:+.4f}${reset}",
        "ROI (TWRR)": f"{get_color(roi_twrr)}{roi_twrr:+.2f}%{reset}",
        "--- CONTADORES ---": "",
        "Total Reinvertido": f"${operacion.total_reinvertido_usdt:.4f}",
        "Comisiones Totales": f"${operacion.comisiones_totales_usdt:.4f}",
        "Trades Cerrados": str(operacion.comercios_cerrados_contador),
    }

    # <<-- ANTERIOR: Lógica de cálculo que estaba en la vista
    # pnl_realizado = operacion.pnl_realizado_usdt; pnl_no_realizado = 0.0
    # for pos_data in summary.get(f'open_{side}_positions', []):
    #     entry = pos_data.get('entry_price', 0.0); size = pos_data.get('size_contracts', 0.0)
    #     pnl_no_realizado += (current_price - entry) * size if side == 'long' else (entry - current_price) * size
    # pnl_total = pnl_realizado + pnl_no_realizado
    # capital_inicial = operacion.capital_inicial_usdt
    # equity_total_historico = operacion.equity_total_usdt
    # equity_actual_vivo = operacion.balances.operational_margin + pnl_no_realizado
    # safe_division = utils.safe_division if utils else lambda n, d: n / d if d != 0 else 0.0
    # roi_total = safe_division(pnl_total, capital_inicial) * 100
    # ... etc ...
    
    max_key_len = max(len(_clean_ansi_codes(k)) for k in data.keys())
    for key, value in data.items():
        if "---" in key: 
            print(_create_box_line(f"\033[96m{key.center(box_width - 6)}\033[0m", box_width))
        else: 
            print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))
    print("└" + "─" * (box_width - 2) + "┘")

def _display_positions_tables(summary: Dict[str, Any], operacion: Operacion, current_price: float, side: str):
    """Muestra la tabla de posiciones abiertas y PENDIENTES, y datos agregados."""
    box_width = _get_unified_box_width()

    # --- TABLA DE POSICIONES ABIERTAS ---
    open_positions = operacion.posiciones_abiertas
    open_count = len(open_positions)
    total_count = len(operacion.posiciones)

    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line(f"Posiciones Abiertas ({open_count}/{total_count})", box_width, 'center'))

    if not open_positions:
        print("├" + "─" * (box_width - 2) + "┤")
        print(_create_box_line("(No hay posiciones abiertas)", box_width, 'center'))
    else:
        header = f"  {'ID':<7} {'Entrada':>9} {'Márgen':>10} {'PNL (U)':>10} {'SL':>9} {'TP Act.':>9} {'TS Status':<20}"
        separator_width = min(len(_clean_ansi_codes(header)) -1, box_width - 2)
        print("├" + "─" * separator_width + "┤")
        print(_truncate_text(header, box_width - 2))
        print("├" + "─" * separator_width + "┤")

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
                f"{pos.margin_usdt:>10.2f} " # <<-- CAMBIO: Se usa el margen real
                f"{pnl_color}{pnl:>+10.4f}{reset} "
                f"{sl_str:>9} "
                f"{tp_act_str:>9} "
                f"{ts_status_str:<20}"
            )
            print(_truncate_text(line, box_width - 2))
    print("└" + "─" * (box_width - 2) + "┘")

    # --- NUEVA TABLA: POSICIONES PENDIENTES ---
    pending_positions = operacion.posiciones_pendientes
    if pending_positions:
        print("┌" + "─" * (box_width - 2) + "┐")
        print(_create_box_line(f"Posiciones Pendientes ({len(pending_positions)})", box_width, 'center'))
        
        header = f"  {'ID':<10} {'Capital Asignado':>20} {'Valor Nominal':>20}"
        separator_width = min(len(_clean_ansi_codes(header)) -1, box_width - 2)
        print("├" + "─" * separator_width + "┤")
        print(_truncate_text(header, box_width - 2))
        print("├" + "─" * separator_width + "┤")

        for pos in pending_positions:
            line = (
                f"  {str(pos.id)[-6:]:<10} "
                f"{pos.capital_asignado:>20.2f} USDT"
                f"{pos.valor_nominal:>20.2f} USDT"
            )
            print(_truncate_text(line, box_width-2))
        print("└" + "─" * (box_width - 2) + "┘")


def _display_operation_conditions(operacion: Operacion):
    """Muestra la sección de condiciones de entrada y salida de la operación."""
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