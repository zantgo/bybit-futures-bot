"""
Módulo de Visualizadores del Panel de Control de Operación.

Contiene todas las funciones auxiliares cuya única responsabilidad es
mostrar (imprimir en la consola) secciones de información específicas, como
los detalles de la operación, las estadísticas de capital o las tablas de posiciones.
Estas funciones son "vistas puras": solo renderizan los datos que reciben.
"""
from typing import Any, Dict, List, Optional
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
            self.estado, self.tendencia = 'DESCONOCIDO', 'N/A'
            self.cond_entrada_above: Optional[float] = None
            self.cond_entrada_below: Optional[float] = None
            self.cond_salida_above: Optional[Dict[str, Any]] = None
            self.cond_salida_below: Optional[Dict[str, Any]] = None
            self.tiempo_espera_minutos: Optional[int] = None
            self.tiempo_inicio_espera: Optional[datetime.datetime] = None
            self.accion_por_sl_tp_roi = 'DETENER'
            self.accion_por_tsl_roi = 'PAUSAR'
            self.estado_razon = "Razón no disponible (fallback)."
            self.apalancamiento, self.pnl_realizado_usdt = 10.0, 0.0
            self.capital_inicial_usdt, self.comisiones_totales_usdt = 0.0, 0.0
            self.total_reinvertido_usdt = 0.0
            self.tsl_roi_activacion_pct, self.tsl_roi_distancia_pct, self.sl_roi_pct = None, None, None
            self.tsl_roi_peak_pct = 0.0
            self.comercios_cerrados_contador, self.tiempo_maximo_min, self.max_comercios = 0, None, None
            self.tiempo_inicio_ejecucion = None
            self.tsl_roi_activo = False
            self.posiciones: List[LogicalPosition] = []
            self.profit_balance_acumulado = 0.0
            self.accion_por_limite_tiempo = 'PAUSAR'
            self.accion_por_limite_trades = 'PAUSAR'
        
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
        def get_roi_sl_tp_price(self): return None
        @property
        def avg_entry_price(self): return None


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
    """
    Calcula un ancho de caja unificado y dinámico.
    
    CORRECCIÓN: Se ajusta la lógica para permitir que la caja se expanda con el
    ancho del terminal, sin quedar limitada por un ancho de contenido fijo.
    """
    terminal_width = _get_terminal_width()
    
    open_pos_content_width = 8 + 10 + 11 + 12 + 10 + 10 + 20 
    pending_pos_content_width = 12 + 22 + 22
    content_width = max(open_pos_content_width, pending_pos_content_width) + 4
    
    base_width = terminal_width - 2
    
    box_width = max(base_width, content_width)
    box_width = min(box_width, 120)
    
    if box_width > terminal_width - 2:
        box_width = terminal_width - 2
        
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
            
            entry_price = pos.entry_price if pos.entry_price is not None else 0.0
            size = pos.size_contracts if pos.size_contracts is not None else 0.0
            margin = pos.margin_usdt if pos.margin_usdt is not None else 0.0

            if current_price > 0 and entry_price > 0:
                pnl = (current_price - entry_price) * size if side == 'long' else (entry_price - current_price) * size

            pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
            reset = "\033[0m"
            sl_str = f"{pos.stop_loss_price:.4f}" if pos.stop_loss_price is not None else "N/A"

            tp_act_price = 0.0
            tsl_act_pct = getattr(pos, 'tsl_activation_pct_at_open', 0)
            if tsl_act_pct and tsl_act_pct > 0 and entry_price > 0:
                tp_act_price = entry_price * (1 + tsl_act_pct / 100) if side == 'long' else entry_price * (1 - tsl_act_pct / 100)
            tp_act_str = f"{tp_act_price:.4f}" if tp_act_price > 0 else "N/A"

            ts_status_str = "Inactivo"
            if getattr(pos, 'ts_is_active', False):
                ts_stop = getattr(pos, 'ts_stop_price', None)
                ts_status_str = f"Activo @ {ts_stop:.4f}" if ts_stop else "Activo (Calc...)"

            line = (
                f"  {str(pos.id)[-6:]:<7} "
                f"{entry_price:>9.4f} "
                f"{margin:>10.2f} "
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
            capital_asignado = pos.capital_asignado if pos.capital_asignado is not None else 0.0
            valor_nominal = pos.valor_nominal if pos.valor_nominal is not None else 0.0
            
            line = (
                f"  {str(pos.id)[-6:]:<10} "
                f"{capital_asignado:>20.2f} USDT"
                f"{valor_nominal:>20.2f} USDT"
            )
            print(_create_box_line(_truncate_text(line, box_width - 2), box_width))
        print("└" + "─" * (box_width - 2) + "┘")
    
def _display_capital_stats(summary: Dict[str, Any], operacion: Operacion, side: str, current_price: float):
    box_width = _get_unified_box_width()
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Capital y Rendimiento", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    if not operacion:
        print(_create_box_line(f"No hay datos para la operación {side.upper()}", box_width, 'center'))
        print("└" + "─" * (box_width - 2) + "┘")
        return
    
    utils_module = _deps.get("utils_module")
    if not utils_module:
        print(_create_box_line("Error: Módulo utils no disponible", box_width, 'center'))
        print("└" + "─" * (box_width - 2) + "┘")
        return

    from core.strategy.pm import _calculations as pm_calculations
    
    aggr_liq_price = pm_calculations.calculate_aggregate_liquidation_price(
        open_positions=operacion.posiciones_abiertas,
        leverage=operacion.apalancamiento,
        side=side
    )
    live_break_even_price = operacion.get_live_break_even_price()
    
    live_performance = operacion.get_live_performance(current_price, utils_module)
    
    pnl_realizado = operacion.pnl_realizado_usdt
    pnl_no_realizado = live_performance.get("pnl_no_realizado", 0.0)
    equity_actual_vivo = live_performance.get("equity_actual_vivo", 0.0)
    roi_twrr_vivo = live_performance.get("roi_twrr_vivo", 0.0)

    if operacion.estado == 'DETENIDA':
        pnl_no_realizado = 0.0
        equity_actual_vivo = operacion.equity_total_usdt
        roi_twrr_vivo = operacion.realized_twrr_roi

    capital_inicial = operacion.capital_inicial_usdt
    equity_total_historico = operacion.equity_total_usdt
    comisiones_totales = getattr(operacion, 'comisiones_totales_usdt', 0.0)
    total_reinvertido = getattr(operacion, 'total_reinvertido_usdt', 0.0)
    total_transferido = getattr(operacion, 'profit_balance_acumulado', 0.0)

    def get_color(value): 
        return "\033[92m" if value >= 0 else "\033[91m"
    reset = "\033[0m"
    
    dist_to_be_str = "N/A"
    if live_break_even_price is not None and current_price > 0:
        if side == 'long':
            dist_pct = ((current_price - live_break_even_price) / live_break_even_price) * 100
        else:
            dist_pct = ((live_break_even_price - current_price) / live_break_even_price) * 100
        dist_to_be_str = f"{get_color(dist_pct)}{dist_pct:+.2f}%{reset}"

    dist_to_liq_str = "N/A"
    if aggr_liq_price is not None and current_price > 0:
        if side == 'long':
            dist_pct = ((current_price - aggr_liq_price) / current_price) * 100
        else:
            dist_pct = ((aggr_liq_price - current_price) / current_price) * 100
        
        color_dist = "\033[91m" if dist_pct < 20 else ("\033[93m" if dist_pct < 50 else "\033[92m")
        dist_to_liq_str = f"{color_dist}{dist_pct:.2f}%{reset}"

    data = {
        "--- CAPITAL ---": "",
        "Capital Inicial (Base ROI)": f"${capital_inicial:.2f}",
        "Capital Operativo (Lógico)": f"${operacion.capital_operativo_logico_actual:.2f}",
        "Capital en Uso": f"${operacion.capital_en_uso:.2f}",
        "Capital Disponible": f"${operacion.capital_disponible:.2f}",
        "--- RENDIMIENTO Y RIESGO ---": "",
        "Equity Total (Histórico)": f"${equity_total_historico:.2f}",
        "Equity Actual (Vivo)": f"{get_color(pnl_no_realizado)}{equity_actual_vivo:.2f}${reset}",
        "PNL Realizado / No Realiz.": f"{get_color(pnl_realizado)}{pnl_realizado:+.4f}${reset} / {get_color(pnl_no_realizado)}{pnl_no_realizado:+.4f}${reset}",
        "ROI (TWRR)": f"{get_color(roi_twrr_vivo)}{roi_twrr_vivo:+.2f}%{reset}",
        "Precio Break-Even (Est.)": f"\033[96m${live_break_even_price:.4f}\033[0m" if live_break_even_price else "N/A",
        "Distancia a Break-Even": dist_to_be_str,
        "Precio Liq. Actual (Est.)": f"\033[91m${aggr_liq_price:.4f}\033[0m" if aggr_liq_price else "N/A",
        "Distancia a Liquidación": dist_to_liq_str,
        "--- CONTADORES ---": "",
        "Total Reinvertido": f"${total_reinvertido:.4f}",
        "Comisiones Totales": f"${comisiones_totales:.4f}",
        "Total Transferido a PROFIT": f"{get_color(total_transferido)}{total_transferido:+.4f}${reset}",
        "Trades Cerrados": str(operacion.comercios_cerrados_contador),
    }

    max_key_len = max(len(_clean_ansi_codes(k)) for k in data.keys())
    for key, value in data.items():
        if "---" in key: 
            print(_create_box_line(f"\033[96m{key.center(box_width - 6)}\033[0m", box_width))
        else: 
            print(_create_box_line(f"{key:<{max_key_len}} : {value}", box_width))
    print("└" + "─" * (box_width - 2) + "┘")

def _display_operation_conditions(operacion: Operacion):
    box_width = _get_unified_box_width()

    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Condiciones y Límites", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    status_color_map = {'ACTIVA': "\033[92m", 'PAUSADA': "\033[93m", 'DETENIDA': "\033[90m", 'EN_ESPERA': "\033[96m", 'DETENIENDO': "\033[91m"}
    color = status_color_map.get(operacion.estado, "")
    reset = "\033[0m"
    
    razon_estado_str = f"\033[94m{operacion.estado_razon}\033[0m"
    precio_transicion = getattr(operacion, 'precio_de_transicion', None)
    if precio_transicion is not None:
        razon_estado_str += f" @ ${precio_transicion:.4f}"

    estado_data = {
        "Estado Actual": f"{color}{operacion.estado}{reset}",
        "Razón de Estado": razon_estado_str
    }
    max_key_len = max(len(_clean_ansi_codes(k)) for k in estado_data.keys())

    for key, value in estado_data.items():
        content = f"{key:<{max_key_len}} : {value}"
        print(_create_box_line(_truncate_text(content, box_width - 4), box_width))

    if operacion.estado != 'DETENIDA':
        # --- Condición de Entrada ---
        print("├" + "─" * (box_width - 2) + "┤")
        print(_create_box_line("\033[96mCondición de Entrada\033[0m", box_width, 'center'))
        
        has_any_entry_condition = any([
            operacion.cond_entrada_above is not None,
            operacion.cond_entrada_below is not None,
            operacion.tiempo_espera_minutos is not None
        ])

        if not has_any_entry_condition:
            print(_create_box_line("  - Inmediata (Market)", box_width))
        else:
            if operacion.cond_entrada_above is not None:
                print(_create_box_line(f"  - Activar si Precio > {operacion.cond_entrada_above:.4f}", box_width))
            if operacion.cond_entrada_below is not None:
                print(_create_box_line(f"  - Activar si Precio < {operacion.cond_entrada_below:.4f}", box_width))
            if operacion.tiempo_espera_minutos:
                print(_create_box_line(f"  - Activar tras esperar {operacion.tiempo_espera_minutos} minutos", box_width))

        # --- Gestión de Riesgo de Operación ---
        print("├" + "─" * (box_width - 2) + "┤")
        print(_create_box_line("\033[96mGestión de Riesgo de Operación\033[0m", box_width, 'center'))
        
        riesgos_activos = []
        
        def format_price(price):
            return f"@ ${price:.4f}" if price is not None else ""

        active_roi_price = operacion.get_active_sl_tp_price()
        
        if operacion.dynamic_roi_sl:
            riesgos_activos.append(f"SL Dinámico por ROI: Dist: {operacion.dynamic_roi_sl['distancia']}% (Acción: {operacion.dynamic_roi_sl['accion']}) {format_price(active_roi_price)}")
        if operacion.roi_sl:
            riesgos_activos.append(f"SL por ROI: {operacion.roi_sl['valor']}% (Acción: {operacion.roi_sl['accion']}) {format_price(active_roi_price)}")
        if operacion.roi_tp:
            riesgos_activos.append(f"TP por ROI: {operacion.roi_tp['valor']}% (Acción: {operacion.roi_tp['accion']}) {format_price(active_roi_price)}")

        if operacion.roi_tsl:
            tsl_str = f"TSL por ROI: Act: {operacion.roi_tsl['activacion']}%, Dist: {operacion.roi_tsl['distancia']}% (Acción: {operacion.roi_tsl['accion']})"
            if operacion.tsl_roi_activo:
                tsl_str += f" (\033[92mACTIVO\033[0m | Pico: {operacion.tsl_roi_peak_pct:.2f}%)"
            riesgos_activos.append(tsl_str)

        be_price = operacion.get_live_break_even_price()
        if operacion.be_sl:
            sl_price = None
            if be_price:
                sl_dist = operacion.be_sl['distancia']
                sl_price = be_price * (1 - sl_dist / 100) if operacion.tendencia == 'LONG_ONLY' else be_price * (1 + sl_dist / 100)
            riesgos_activos.append(f"SL por Break-Even: Dist: {operacion.be_sl['distancia']}% (Acción: {operacion.be_sl['accion']}) {format_price(sl_price)}")
        
        if operacion.be_tp:
            tp_price = None
            if be_price:
                tp_dist = operacion.be_tp['distancia']
                tp_price = be_price * (1 + tp_dist / 100) if operacion.tendencia == 'LONG_ONLY' else be_price * (1 - tp_dist / 100)
            riesgos_activos.append(f"TP por Break-Even: Dist: {operacion.be_tp['distancia']}% (Acción: {operacion.be_tp['accion']}) {format_price(tp_price)}")

        # --- INICIO DE LA ÚNICA SECCIÓN MODIFICADA ---
        if not riesgos_activos:
            print(_create_box_line("  - Ningún límite de riesgo de operación configurado.", box_width))
        else:
            # Ordenamos la lista 'riesgos_activos' antes de imprimirla
            riesgos_activos.sort(key=lambda x: (
                'SL' not in x,      # Pone las cadenas que contienen 'SL' al principio
                'TSL' in x,         # Pone las cadenas con 'TSL' después de las de 'SL'
                'TP' in x           # Pone las cadenas con 'TP' al final
            ))
            
            for riesgo in riesgos_activos:
                print(_create_box_line(f"  - {riesgo}", box_width))
        # --- FIN DE LA ÚNICA SECCIÓN MODIFICADA ---

        # --- Límites de Salida de Operación ---
        print("├" + "─" * (box_width - 2) + "┤")
        print(_create_box_line("\033[96mLímites de Salida (por Sesión Activa)\033[0m", box_width, 'center'))
        
        exit_limits = []
        if operacion.cond_salida_above:
            cond = operacion.cond_salida_above
            exit_limits.append(f"Precio Salida: > {cond['valor']:.4f} (Acción: {cond['accion']})")
        
        if operacion.cond_salida_below:
            cond = operacion.cond_salida_below
            exit_limits.append(f"Precio Salida: < {cond['valor']:.4f} (Acción: {cond['accion']})")
        
        # Límite de Duración (por Sesión Activa)
        if operacion.tiempo_maximo_min is not None:
            # Usamos el contador temporal que se reinicia con cada pausa/reanudación
            tiempo_actual_min = 0.0
            if operacion.estado == 'ACTIVA' and hasattr(operacion, 'tiempo_inicio_sesion_activa') and operacion.tiempo_inicio_sesion_activa:
                tiempo_actual_min = (datetime.datetime.now(datetime.timezone.utc) - operacion.tiempo_inicio_sesion_activa).total_seconds() / 60
            
            # Calculamos el tiempo restante para esta sesión activa
            tiempo_restante_min = max(0, operacion.tiempo_maximo_min - tiempo_actual_min)
            
            exit_limits.append(f"Duración Máx: {operacion.tiempo_maximo_min} min (Restante: {tiempo_restante_min:.1f} min) (Acción: {operacion.accion_por_limite_tiempo})")
        
        # Límite de Trades (por Sesión Activa)
        if operacion.max_comercios is not None:
            # Usamos el contador temporal que se reinicia con cada pausa/reanudación
            trades_actuales_sesion = getattr(operacion, 'trades_en_sesion_activa', 0)
            
            # Calculamos los trades restantes para esta sesión activa
            trades_restantes = max(0, operacion.max_comercios - trades_actuales_sesion)
            
            exit_limits.append(f"Máx. Trades: {operacion.max_comercios} (Restantes: {trades_restantes}) (Acción: {operacion.accion_por_limite_trades})")
        
        if not exit_limits:
            print(_create_box_line("  - Ningún límite de salida configurado.", box_width))
        else:
            for limit in exit_limits:
                print(_create_box_line(f"  - {limit}", box_width))

    print("└" + "─" * (box_width - 2) + "┘")
def _display_operation_details(summary: Dict[str, Any], operacion: Operacion, side: str):
    box_width = _get_unified_box_width()
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Parámetros de la Operación", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    if not operacion:
        print(_create_box_line(f"No hay datos para la operación {side.upper()}", box_width, 'center'))
        print("└" + "─" * (box_width - 2) + "┘")
        return

    tendencia = operacion.tendencia
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m"}
    color, reset = color_map.get(tendencia, ""), "\033[0m"
    
    pos_abiertas = operacion.posiciones_abiertas_count
    pos_total = len(operacion.posiciones)

    data = {
        "Tendencia": f"{color}{tendencia}{reset}",
        "Posiciones (Abiertas/Total)": f"{pos_abiertas} / {pos_total}",
        "Apalancamiento (Fijo)": f"{operacion.apalancamiento:.1f}x",
    }
    
    if operacion.estado in ['EN_ESPERA', 'PAUSADA'] and operacion.tiempo_espera_minutos:
        if getattr(operacion, 'tiempo_inicio_espera', None):
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            end_time = operacion.tiempo_inicio_espera + datetime.timedelta(minutes=operacion.tiempo_espera_minutos)
            time_left = end_time - now_utc
            if time_left.total_seconds() > 0:
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                data["Activación en (Temporizador)"] = f"{hours:02}:{minutes:02}:{seconds:02}"
    
    ### INICIO DE LA CORRECCIÓN DEL BUG ###
    
    # Lógica de visualización del "Tiempo Sesión Activa" (el cronómetro que cuenta hacia arriba)
    tiempo_sesion_activa_str = ""
    if operacion.estado == 'ACTIVA':
        start_time = getattr(operacion, 'tiempo_inicio_sesion_activa', None)
        if start_time:
            # Si está activa y tiene un timestamp, calculamos el tiempo transcurrido.
            total_seconds_active = (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds()
            hours, remainder = divmod(int(total_seconds_active), 3600)
            minutes, seconds = divmod(remainder, 60)
            tiempo_sesion_activa_str = f"{hours:02}:{minutes:02}:{seconds:02}"
        else:
            # Medida de seguridad por si el estado es ACTIVA pero falta el timestamp. No debería ocurrir.
            tiempo_sesion_activa_str = "Calculando..." 
    else:
        # Para cualquier otro estado (PAUSADA, DETENIDA, etc.), mostramos "Pausado".
        tiempo_sesion_activa_str = "00:00:00 (Pausado)"

    data["Tiempo Sesión Activa"] = tiempo_sesion_activa_str
    
    ### FIN DE LA CORRECCIÓN DEL BUG ###

    max_key_len = max(len(_clean_ansi_codes(k)) for k in data.keys()) if data else 0
    for key, value in data.items():
        content = f"{key:<{max_key_len}} : {value}"
        print(_create_box_line(content, box_width))

    print("└" + "─" * (box_width - 2) + "┘")