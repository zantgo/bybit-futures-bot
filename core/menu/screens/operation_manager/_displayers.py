# ./core/menu/screens/operation_manager/_displayers.py

"""
Módulo de Visualizadores del Panel de Control de Operación.

Contiene todas las funciones auxiliares cuya única responsabilidad es
mostrar (imprimir en la consola) secciones de información específicas, como
los detalles de la operación, las estadísticas de capital o las tablas de posiciones.
Estas funciones son "vistas puras": solo renderizan los datos que reciben.
"""
from typing import Any, Dict
import datetime
import shutil
import re
import numpy as np

try:
    from core.strategy.entities import Operacion
    from core import utils
except ImportError:
    utils = None
    class Operacion:
        def __init__(self):
            self.estado = 'DESCONOCIDO'
            self.tendencia = 'N/A'
            self.tamaño_posicion_base_usdt = 0.0
            self.apalancamiento = 0.0
            self.max_posiciones_logicas = 0
            self.tiempo_inicio_ejecucion = None
            self.tsl_activacion_pct = 0.0
            self.tsl_distancia_pct = 0.0
            self.sl_posicion_individual_pct = 0.0
            self.accion_al_finalizar = 'N/A'
            self.pnl_realizado_usdt = 0.0
            self.capital_inicial_usdt = 0.0
            self.capital_actual_usdt = 0.0
            self.comercios_cerrados_contador = 0
            self.comisiones_totales_usdt = 0.0
            self.total_reinvertido_usdt = 0.0 # Añadido para el nuevo layout
            self.tipo_cond_entrada = 'N/A'
            self.valor_cond_entrada = 0.0
            self.tipo_cond_salida = None
            self.valor_cond_salida = None
            self.tsl_roi_activacion_pct = None
            self.tsl_roi_distancia_pct = None
            self.tsl_roi_activo = False
            self.tsl_roi_peak_pct = 0.0
            self.sl_roi_pct = None
            self.tiempo_maximo_min = None
            self.max_comercios = None
            class Balances:
                def __init__(self):
                    self.profit_balance = 0.0
                    self.used_margin = 0.0
                @property
                def available_margin(self):
                    return 0.0
            self.balances = Balances()


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
    content_width = 7 + 9 + 8 + 10 + 9 + 9 + 20 + (6 * 2) 
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
    
    pos_abiertas = summary.get(f'open_{side}_positions_count', 0)
    pos_total = operacion.max_posiciones_logicas

    fecha_activacion_str = "N/A"
    tiempo_ejecucion_str = "N/A"
    if operacion.tiempo_inicio_ejecucion:
        fecha_activacion_str = operacion.tiempo_inicio_ejecucion.strftime('%H:%M:%S %d-%m-%Y (UTC)')
        # El tiempo solo se calcula y muestra si la operación está ACTIVA
        if operacion.estado == 'ACTIVA':
            duration = datetime.datetime.now(datetime.timezone.utc) - operacion.tiempo_inicio_ejecucion
            total_seconds = int(duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            tiempo_ejecucion_str = f"{hours:02}:{minutes:02}:{seconds:02}"
    
    data = {
        "Tendencia": f"{color}{tendencia}{reset}",
        "Tamaño Base": f"${operacion.tamaño_posicion_base_usdt:.2f} USDT",
        "Posiciones": f"{pos_abiertas} / {pos_total}",
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
    """Muestra la sección de estadísticas de capital para un lado específico."""
    box_width = _get_unified_box_width()
    
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Capital y Rendimiento", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")
    
    if not operacion or operacion.estado == 'DETENIDA':
        print(_create_box_line(f"La operación {side.upper()} está DETENIDA", box_width, 'center'))
        print("└" + "─" * (box_width - 2) + "┘")
        return

    # 1. Calcular todas las métricas
    pnl_realizado = operacion.pnl_realizado_usdt
    pnl_no_realizado = 0.0
    for pos_data in summary.get(f'open_{side}_positions', []):
        entry = pos_data.get('entry_price', 0.0)
        size = pos_data.get('size_contracts', 0.0)
        if side == 'long': pnl_no_realizado += (current_price - entry) * size
        else: pnl_no_realizado += (entry - current_price) * size

    pnl_total = pnl_realizado + pnl_no_realizado
    
    capital_inicial = operacion.capital_inicial_usdt
    capital_actual = operacion.capital_actual_usdt
    capital_promedio = (capital_inicial + capital_actual) / 2
    
    safe_division = utils.safe_division if utils else lambda n, d: n / d if d != 0 else 0
    roi_realizado = safe_division(pnl_realizado, capital_promedio) * 100
    roi_no_realizado = safe_division(pnl_no_realizado, capital_promedio) * 100
    roi_total = safe_division(pnl_total, capital_promedio) * 100

    margen_uso = operacion.balances.used_margin
    margen_disp = operacion.balances.available_margin
    
    comisiones_totales = getattr(operacion, 'comisiones_totales_usdt', 0.0)
    total_reinvertido = getattr(operacion, 'total_reinvertido_usdt', 0.0)
    profit_balance = getattr(operacion.balances, 'profit_balance', 0.0)
    trades_cerrados = operacion.comercios_cerrados_contador

    def get_color(value):
        return "\033[92m" if value >= 0 else "\033[91m"
    reset = "\033[0m"

    # 2. Ensamblar los datos en secciones
    data_capital = {
        "Capital Inicial / Actual": f"${capital_inicial:.2f} / ${capital_actual:.2f}",
        "Margen En Uso / Disponible": f"${margen_uso:.2f} / ${margen_disp:.2f}",
        "Capital Base (Promedio)": f"${capital_promedio:.2f}",
    }
    data_pnl = {
        "PNL Realizado": f"{get_color(pnl_realizado)}{pnl_realizado:+.4f}${reset}",
        "PNL No Realizado": f"{get_color(pnl_no_realizado)}{pnl_no_realizado:+.4f}${reset}",
        "PNL Total": f"{get_color(pnl_total)}{pnl_total:+.4f}${reset}",
    }
    data_roi = {
        "ROI Realizado": f"{get_color(roi_realizado)}{roi_realizado:+.2f}%{reset}",
        "ROI No Realizado": f"{get_color(roi_no_realizado)}{roi_no_realizado:+.2f}%{reset}",
        "ROI Total": f"{get_color(roi_total)}{roi_total:+.2f}%{reset}",
    }
    data_otros = {
        "Comisiones Totales": f"${comisiones_totales:.4f}",
        "Total Reinvertido": f"${total_reinvertido:.4f}",
        "Transferido a PROFIT": f"{get_color(profit_balance)}{profit_balance:+.4f}{reset}",
        "Trades Cerrados": str(trades_cerrados),
    }

    all_keys = list(data_capital.keys()) + list(data_pnl.keys()) + list(data_roi.keys()) + list(data_otros.keys())
    max_key_len = max(len(_clean_ansi_codes(k)) for k in all_keys)

    # 3. Renderizar secciones
    for key, value in data_capital.items():
        print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))
    
    print("├" + "─" * (box_width - 2) + "┤")
    for key, value in data_pnl.items():
        print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))
        
    print("├" + "─" * (box_width - 2) + "┤")
    for key, value in data_roi.items():
        print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))

    print("├" + "─" * (box_width - 2) + "┤")
    for key, value in data_otros.items():
        print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))

    print("└" + "─" * (box_width - 2) + "┘")

def _display_positions_tables(summary: Dict[str, Any], operacion: Operacion, current_price: float, side: str):
    """Muestra la tabla de posiciones abiertas y datos agregados."""
    box_width = _get_unified_box_width()

    positions = summary.get(f'open_{side}_positions', [])
    max_pos = operacion.max_posiciones_logicas if operacion else 'N/A'
    
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line(f"Posiciones Lógicas Abiertas ({len(positions)}/{max_pos})", box_width, 'center'))
    
    if not positions:
        print("├" + "─" * (box_width - 2) + "┤")
        print(_create_box_line("(No hay posiciones abiertas)", box_width, 'center'))
    else:
        header = f"  {'ID':<7} {'Entrada':>9} {'Tamaño':>8} {'PNL (U)':>10} {'SL':>9} {'TP Act.':>9} {'TS Status':<20}"
        
        separator_width = min(len(_clean_ansi_codes(header)) -1, box_width - 2)
        print("├" + "─" * separator_width + "┤")
        print(_truncate_text(header, box_width - 2))
        print("├" + "─" * separator_width + "┤")
        
        for pos in positions:
            pnl = 0.0
            entry_price = pos.get('entry_price', 0.0)
            size = pos.get('size_contracts', 0.0)
            if current_price > 0 and entry_price > 0:
                pnl = (current_price - entry_price) * size if side == 'long' else (entry_price - current_price) * size

            pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
            reset = "\033[0m"
            sl_str = f"{pos.get('stop_loss_price', 0.0):.4f}" if pos.get('stop_loss_price') else "N/A"

            tp_act_price = 0.0
            tsl_act_pct = pos.get('tsl_activation_pct_at_open', 0.0)
            if tsl_act_pct > 0:
                tp_act_price = entry_price * (1 + tsl_act_pct / 100) if side == 'long' else entry_price * (1 - tsl_act_pct / 100)
            tp_act_str = f"{tp_act_price:.4f}" if tp_act_price > 0 else "N/A"

            ts_status_str = "Inactivo"
            if pos.get('ts_is_active'):
                ts_stop = pos.get('ts_stop_price')
                ts_status_str = f"Activo @ {ts_stop:.4f}" if ts_stop else "Activo (Calc...)"

            line = (
                f"  {str(pos.get('id', ''))[-6:]:<7} "
                f"{entry_price:>9.4f} "
                f"{size:>8.4f} "
                f"{pnl_color}{pnl:>+10.4f}{reset} "
                f"{sl_str:>9} "
                f"{tp_act_str:>9} "
                f"{ts_status_str:<20}"
            )
            print(_truncate_text(line, box_width - 2))

    print("└" + "─" * (box_width - 2) + "┘")


def _display_operation_conditions(operacion: Operacion):
    """Muestra la sección de condiciones de entrada y salida de la operación."""
    box_width = _get_unified_box_width()
    
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Condiciones de la Operación", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    status_color_map = {'ACTIVA': "\033[92m", 'PAUSADA': "\033[93m", 'DETENIDA': "\033[90m", 'EN_ESPERA': "\033[96m"}
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
        # --- INICIO DE LA MODIFICACIÓN ---
        # Lógica de visualización para SL/TP unificado
        if operacion.sl_roi_pct < 0:
            exit_conditions.append(f"SL-ROI <= {operacion.sl_roi_pct}%")
        else:
            exit_conditions.append(f"TP-ROI >= {operacion.sl_roi_pct}%")
        # --- FIN DE LA MODIFICACIÓN ---
    
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