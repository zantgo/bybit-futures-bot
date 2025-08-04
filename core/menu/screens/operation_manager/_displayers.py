# ./core/menu/screens/operation_manager/_displayers.py

"""
Módulo de Visualizadores del Panel de Control de Operación.

Contiene todas las funciones auxiliares cuya única responsabilidad es
mostrar (imprimir en la consola) secciones de información específicas, como
los detalles de la operación, las estadísticas de capital o las tablas de posiciones.
Estas funciones son "vistas puras": solo renderizan los datos que reciben.

v3.0 (UI Dinámica):
- Implementado sistema de cajas y ancho dinámico basado en el terminal.
- Corregido el problema de alineación de las secciones con el menú.
- Añadido truncamiento inteligente para texto largo.
- Mantenido todo el funcionamiento original sin cambios.

v2.0 (Fallback Robusto):
- La clase de fallback para 'Operacion' ahora incluye todos los atributos
  necesarios con valores por defecto. Esto previene un `AttributeError` si
  la importación principal falla y asegura que la TUI pueda renderizar un
  estado vacío en lugar de crashear.
"""
from typing import Any, Dict
import datetime
import shutil
import re
import numpy as np

try:
    from core.strategy.om._entities import Operacion
except ImportError:
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
            self.comercios_cerrados_contador = 0
            self.comisiones_totales_usdt = 0.0
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
    terminal_width = _get_terminal_width()
    box_width = min(terminal_width - 2, 90)

    
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
    terminal_width = _get_terminal_width()
    box_width = min(terminal_width - 2, 90)

    
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Capital y Rendimiento", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")
    
    if not operacion or operacion.estado == 'DETENIDA':
        print(_create_box_line(f"La operación {side.upper()} está DETENIDA", box_width, 'center'))
        print("└" + "─" * (box_width - 2) + "┘")
        return

    unrealized_pnl = 0.0
    for pos_data in summary.get(f'open_{side}_positions', []):
        entry = pos_data.get('entry_price', 0.0)
        size = pos_data.get('size_contracts', 0.0)
        if side == 'long': unrealized_pnl += (current_price - entry) * size
        else: unrealized_pnl += (entry - current_price) * size

    realized_pnl = operacion.pnl_realizado_usdt
    total_pnl = realized_pnl + unrealized_pnl
    initial_capital = operacion.capital_inicial_usdt
    roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
    pnl_color, reset = ("\033[92m" if total_pnl >= 0 else "\033[91m"), "\033[0m"
    
    capital_actual = initial_capital + realized_pnl
    balances_info = summary.get('logical_balances', {}).get(side, {})
    margen_uso = balances_info.get('used_margin', 0.0)
    margen_disp = balances_info.get('available_margin', 0.0)
    
    comisiones_totales = getattr(operacion, 'comisiones_totales_usdt', 0.0)
    ganancias_netas = total_pnl - comisiones_totales
    netas_color = "\033[92m" if ganancias_netas >= 0 else "\033[91m"
    
    trades_abiertos = summary.get(f'open_{side}_positions_count', 0)
    trades_cerrados = operacion.comercios_cerrados_contador

    data_top = {
        "Capital Total Inicial": f"${initial_capital:.2f}",
        "Capital Total Actual": f"${capital_actual:.2f}",
        "Margen En Uso": f"${margen_uso:.2f}",
        "Margen Disponible": f"${margen_disp:.2f}",
        "PNL Operación": f"{pnl_color}{total_pnl:+.4f}${reset}",
        "ROI Operación": f"{pnl_color}{roi:+.2f}%{reset}"
    }
    
    data_bottom = {
        "Ganancias Netas": f"{netas_color}{ganancias_netas:+.4f}{reset}",
        "Comisiones Totales": f"${comisiones_totales:.4f}",
        "Trades Abiertos Totales": str(trades_abiertos),
        "Trades Cerrados Totales": str(trades_cerrados)
    }

    max_key_len = max(len(_clean_ansi_codes(k)) for k in list(data_top.keys()) + list(data_bottom.keys()))
    for key, value in data_top.items():
        print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))

    print("├" + "─" * (box_width - 2) + "┤")

    for key, value in data_bottom.items():
        print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))
        
    print("└" + "─" * (box_width - 2) + "┘")


def _display_positions_tables(summary: Dict[str, Any], operacion: Operacion, current_price: float, side: str):
    """Muestra la tabla de posiciones abiertas y datos agregados."""
    terminal_width = _get_terminal_width()
    box_width = min(terminal_width - 2, 90)

    positions = summary.get(f'open_{side}_positions', [])
    max_pos = operacion.max_posiciones_logicas if operacion else 'N/A'
    
    
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line(f"Posiciones ({len(positions)}/{max_pos})", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")
    
    if not positions:
        print(_create_box_line("(No hay posiciones abiertas)", box_width, 'center'))
    else:
        # Aquí iría la tabla, pero el diseño solicitado no la incluye.
        # En su lugar, se muestran datos agregados.
        pass

    print("├" + "─" * (box_width - 2) + "┤")
    
    avg_entry_price = summary.get(f'avg_entry_price_{side}', 'N/A')
    avg_liq_price = summary.get(f'avg_liq_price_{side}', 'N/A')
    
    # Calcular promedios de SL y TSL
    sl_points = [p['stop_loss_price'] for p in positions if p.get('stop_loss_price')]
    avg_sl = np.mean(sl_points) if sl_points else 'N/A'

    tsl_activation_points = []
    if positions:
        first_pos_entry = positions[0].get('entry_price', 0.0)
        first_pos_tsl_pct = _deps['om_api'].get_operation_by_side(side).tsl_activacion_pct
        if first_pos_entry and first_pos_tsl_pct:
            if side == 'long':
                avg_tsl_act = first_pos_entry * (1 + first_pos_tsl_pct / 100)
            else:
                avg_tsl_act = first_pos_entry * (1 - first_pos_tsl_pct / 100)
        else:
            avg_tsl_act = 'N/A'
    else:
        avg_tsl_act = 'N/A'


    data = {
        "Avg Ent Price": f"{avg_entry_price:.4f}" if isinstance(avg_entry_price, (int, float)) else "N/A",
        "Avg Liq Price": f"{avg_liq_price:.4f}" if isinstance(avg_liq_price, (int, float)) else "N/A",
        "Avg Take Profit Activation Point": f"{avg_tsl_act:.4f}" if isinstance(avg_tsl_act, (int, float)) else "N/A",
        "Avg Stop Loss Point": f"{avg_sl:.4f}" if isinstance(avg_sl, (int, float)) else "N/A"
    }

    max_key_len = max(len(k) for k in data.keys())
    for key, value in data.items():
        print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))

    print("└" + "─" * (box_width - 2) + "┘")


def _display_operation_conditions(operacion: Operacion):
    """Muestra la sección de condiciones de entrada y salida de la operación."""
    terminal_width = _get_terminal_width()
    box_width = min(terminal_width - 2, 90)

    
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Condiciones de la Operación", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    status_color_map = {'ACTIVA': "\033[92m", 'PAUSADA': "\033[93m", 'DETENIDA': "\033[90m", 'EN_ESPERA': "\033[96m"}
    color = status_color_map.get(operacion.estado, "")
    reset = "\033[0m"
    
    print(_create_box_line(f"Estado Actual: {color}{operacion.estado}{reset}", box_width))
    if operacion.estado != 'DETENIDA':
        print(_create_box_line(f"Estado de Salida: {operacion.accion_al_finalizar.upper()}", box_width))
    
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
    print(_create_box_line("Condiciones de Salida (CUALQUIERA desactiva la operación):", box_width))
    exit_conditions = []
    if operacion.tipo_cond_salida and operacion.valor_cond_salida is not None:
        op = ">" if operacion.tipo_cond_salida == 'PRICE_ABOVE' else "<"
        exit_conditions.append(f"Precio {op} {operacion.valor_cond_salida:.4f}")
    
    if operacion.tsl_roi_activacion_pct is not None and operacion.tsl_roi_distancia_pct is not None:
        tsl_config_str = (f"TSL-ROI: Activa a {operacion.tsl_roi_activacion_pct}%, Distancia {operacion.tsl_roi_distancia_pct}%")
        if operacion.tsl_roi_activo:
            tsl_config_str += f" (ACTIVO | Pico: {operacion.tsl_roi_peak_pct:.2f}%)"
        exit_conditions.append(tsl_config_str)

    if operacion.sl_roi_pct is not None: 
        exit_conditions.append(f"SL-ROI <= -{abs(operacion.sl_roi_pct)}%")
    if operacion.tiempo_maximo_min is not None: 
        exit_conditions.append(f"Tiempo >= {operacion.tiempo_maximo_min} min")
    if operacion.max_comercios is not None: 
        exit_conditions.append(f"Trades >= {operacion.max_comercios}")

    if not exit_conditions:
        print(_create_box_line("  - Ninguna (finalización manual)", box_width))
    else:
        for cond in exit_conditions:
            print(_create_box_line(f"  - {cond}", box_width))
            
    print("└" + "─" * (box_width - 2) + "┘")