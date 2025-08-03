"""
Módulo para la Pantalla del Dashboard de Sesión.

v8.2 (Corrección de Alineación):
- Corregido el problema de alineación de las cajas del dashboard
- Implementado sistema de ancho dinámico basado en el terminal
- Mejorado el truncamiento de texto largo para mantener la estructura

v8.1 (Refactor de Configuración):
- Adaptado para leer el `TICKER_SYMBOL` desde la nueva estructura de `config.py`.

v8.0 (Capital Lógico y Nuevo UI):
- La pantalla ha sido rediseñada completamente para mostrar el estado de la sesión
  y los balances lógicos de las operaciones LONG y SHORT de forma separada y clara.
- El menú de acciones ahora permite el acceso directo a la gestión de la operación
  LONG o SHORT, eliminando menús intermedios.
- Se añade una opción para refrescar la vista del dashboard en tiempo real.
- La opción "Ver/Gestionar Posiciones" se elimina del dashboard.
"""
import time
import datetime
from datetime import timezone
from typing import Dict, Any
import re # Importar el módulo de expresiones regulares para limpiar colores
import os
import shutil

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen,
    print_tui_header,
    press_enter_to_continue
)
from .. import _helpers as helpers_module
from . import _log_viewer, operation_manager
try:
    from core.strategy.sm import api as sm_api
    from core.strategy.pm import api as pm_api # Aún necesario para algunos datos como el start time
except ImportError:
    sm_api = pm_api = None


# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies


def _get_terminal_width():
    """Obtiene el ancho actual del terminal."""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 80  # Ancho por defecto


def _truncate_text(text: str, max_length: int) -> str:
    """Trunca el texto si es muy largo, añadiendo '...' al final."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def _display_final_summary(summary: Dict[str, Any]):
    """Muestra una pantalla de resumen clara al finalizar la sesión."""
    clear_screen()
    print_tui_header("Resumen Final de la Sesión")

    if not summary or summary.get('error'):
        print("\nNo se pudo generar el resumen final.")
        press_enter_to_continue()
        return

    realized_pnl = summary.get('total_session_pnl', 0.0)
    initial_capital = summary.get('total_session_initial_capital', 0.0)
    final_roi = (realized_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
    start_time = pm_api.get_session_start_time()
    duration_str = "N/A"
    if start_time:
        duration = datetime.datetime.now(timezone.utc) - start_time
        duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))

    print("\n--- Rendimiento General ---")
    print(f"  PNL Realizado Total: {realized_pnl:+.4f} USDT")
    print(f"  ROI Final (Realizado): {final_roi:+.2f}%")
    print(f"  Duración Total: {duration_str}")

    open_longs = summary.get('open_long_positions', [])
    open_shorts = summary.get('open_short_positions', [])
    
    if open_longs or open_shorts:
        print("\n--- Posiciones que Quedaron Abiertas ---")
        if open_longs:
            print(f"  LONGs ({len(open_longs)}):")
            for pos in open_longs:
                print(f"    - ID: {pos.get('id', 'N/A')}, Entrada: {pos.get('entry_price', 0.0):.4f}, Tamaño: {pos.get('size_contracts', 0.0):.4f}")
        if open_shorts:
            print(f"  SHORTs ({len(open_shorts)}):")
            for pos in open_shorts:
                print(f"    - ID: {pos.get('id', 'N/A')}, Entrada: {pos.get('entry_price', 0.0):.4f}, Tamaño: {pos.get('size_contracts', 0.0):.4f}")
    else:
        print("\n--- No quedaron posiciones abiertas ---")

    press_enter_to_continue()

# --- INICIO DE LAS FUNCIONES DE RENDERIZADO CORREGIDAS ---

def _clean_ansi_codes(text: str) -> str:
    """Función de ayuda para eliminar códigos de color ANSI de un string."""
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', str(text))


def _create_box_line(content: str, width: int, alignment: str = 'left') -> str:
    """Crea una línea de caja con el contenido alineado correctamente."""
    clean_content = _clean_ansi_codes(content)
    content_len = len(clean_content)
    
    if content_len > width - 2:  # -2 para los bordes │ │
        content = _truncate_text(clean_content, width - 5) # -5 para bordes y ...
        content_len = len(content)
    
    if alignment == 'center':
        padding_total = width - content_len - 2
        padding_left = padding_total // 2
        padding_right = padding_total - padding_left
        return f"│{' ' * padding_left}{content}{' ' * padding_right}│"
    elif alignment == 'right':
        padding = width - content_len - 2
        return f"│{' ' * padding}{content} │"
    else:  # left
        padding = width - content_len - 2
        return f"│ {content}{' ' * (padding - 1)}│"


def _render_session_status_block(summary: Dict[str, Any], box_width: int):
    """Imprime el bloque de Estado de Sesión con el estilo y formato correctos."""
    session_start_time = pm_api.get_session_start_time()
    start_time_str = "N/A"
    duration_str = "0:00:00"
    if session_start_time:
        start_time_str = session_start_time.strftime('%H:%M:%S %d-%m-%Y (UTC)')
        now_utc = datetime.datetime.now(timezone.utc)
        start_time_utc = session_start_time.replace(tzinfo=timezone.utc)
        duration_seconds = (now_utc - start_time_utc).total_seconds()
        duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))
    
    total_pnl = summary.get('total_session_pnl', 0.0)
    total_roi = summary.get('total_session_roi', 0.0)
    transferido_val = summary.get('total_realized_pnl_session', 0.0)

    data = {
        "Inicio Sesión": start_time_str,
        "Duración": duration_str,
        "ROI Sesión": f"{total_roi:+.2f}%",
        "PNL Total": f"{total_pnl:+.4f} USDT",
        "Total Transferido a PROFIT": f"{transferido_val:+.4f} USDT"
    }
    
    # Crear caja
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Estado de Sesión", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")
    
    # Calcular ancho máximo para las claves
    max_key_len = max(len(k) for k in data.keys()) if data else 0
    
    for key, value in data.items():
        content = f"{key:<{max_key_len}} : {value}"
        print(_create_box_line(content, box_width))
    
    print("└" + "─" * (box_width - 2) + "┘")


def _render_signal_status_block(summary: Dict[str, Any], config_module: Any, box_width: int):
    """Imprime el bloque de Estado de Señal con el estilo y formato correctos."""
    ticker_symbol = config_module.BOT_CONFIG["TICKER"]["SYMBOL"]
    latest_signal_info = summary.get('latest_signal', {})
    
    price_val = latest_signal_info.get('price_float')
    price_str = f"{price_val:.8f}" if isinstance(price_val, float) else "N/A"
    
    ema_str = latest_signal_info.get('ema', 'N/A')
    inc_pct_str = latest_signal_info.get('inc_price_change_pct', 'N/A')
    w_inc_str = latest_signal_info.get('weighted_increment', 'N/A')
    dec_pct_str = latest_signal_info.get('dec_price_change_pct', 'N/A')
    w_dec_str = latest_signal_info.get('weighted_decrement', 'N/A')

    # Crear caja
    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Estado de Señal", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    # Parte superior
    data_top = {"Ticker": ticker_symbol, "Precio Actual": price_str}
    max_key_top = max(len(k) for k in data_top.keys())
    for key, value in data_top.items():
        content = f"{key:<{max_key_top}} : {value}"
        print(_create_box_line(content, box_width))
    
    print(_create_box_line("", box_width))  # Línea vacía
    
    # Indicadores TA
    print(_create_box_line("Indicadores TA", box_width))
    print(_create_box_line(f"  EMA: {_truncate_text(str(ema_str), box_width-10)}", box_width))
    print(_create_box_line(f"  W.Inc/W.Dec: {_truncate_text(f'{w_inc_str}/{w_dec_str}', box_width-20)}", box_width))
    print(_create_box_line(f"  Price Inc.(%)/ Price Dec.(%): {_truncate_text(f'{inc_pct_str} / {dec_pct_str}', box_width-35)}", box_width))

    print(_create_box_line("", box_width))  # Línea vacía
    
    # Parte inferior
    signal_val = latest_signal_info.get('signal', 'N/A')
    reason_val = latest_signal_info.get('signal_reason', '')
    
    print(_create_box_line(f"Señal Generada : {_truncate_text(str(signal_val), box_width-20)}", box_width))
    print(_create_box_line(f"Razón          : {_truncate_text(str(reason_val), box_width-20)}", box_width))
        
    print("└" + "─" * (box_width - 2) + "┘")


def _render_operations_status_block(summary: Dict[str, Any], box_width: int):
    """Imprime el bloque de Estado de Operaciones con el estilo y formato correctos."""
    sides = ['long', 'short']
    data = {side: {} for side in sides}

    for side in sides:
        op_info = summary.get('operations_info', {}).get(side, {})
        balance_info = summary.get('logical_balances', {}).get(side, {})
        pnl = summary.get(f'operation_{side}_pnl', 0.0)
        roi = summary.get(f'operation_{side}_roi', 0.0)
        comisiones = summary.get(f'comisiones_totales_usdt_{side}', 0.0)
        ganancias_netas = pnl - comisiones
        capital_usado = balance_info.get('used_margin', 0.0)
        capital_operativo = balance_info.get('operational_margin', 0.0)
        max_pos_logicas = 0
        op = _deps.get("operation_manager_api_module").get_operation_by_side(side)
        if op: max_pos_logicas = op.max_posiciones_logicas

        data[side] = {
            'Estado': op_info.get('estado', 'DETENIDA').upper(),
            'Posiciones': f"{summary.get(f'open_{side}_positions_count', 0)} / {max_pos_logicas}",
            'Capital (Usado/Total)': f"${capital_usado:.2f} / ${capital_operativo:.2f}",
            'Comisiones Totales': f"${comisiones:.4f}",
            'Ganancias Netas': f"${ganancias_netas:.4f}",
            'PNL': f"{pnl:.4f}",
            'ROI': f"{roi:+.2f}%",
            'Avg Ent Price': f"{summary.get(f'avg_entry_price_{side}', 'N/A')}",
            'Avg Liq Price': f"{summary.get(f'avg_liq_price_{side}', 'N/A')}",
        }

    # Calcular ancho de cada columna
    width_col = (box_width - 3) // 2  # -3 para los 3 caracteres de separación ┌─┬─┐
    
    print("┌" + "─" * width_col + "┬" + "─" * width_col + "┐")
    print(f"│{'Operación LONG':^{width_col}}│{'Operación SHORT':^{width_col}}│")
    print("├" + "─" * width_col + "┼" + "─" * width_col + "┤")
    
    labels = [
        'Estado', 'Posiciones', 'Capital (Usado/Total)', 'Comisiones Totales',
        'Ganancias Netas', 'PNL', 'ROI', 'Avg Ent Price', 'Avg Liq Price'
    ]
    max_label_len = min(max(len(k) for k in labels), width_col - 10)  # Limitar longitud de etiqueta
    
    for label in labels:
        long_val = data['long'].get(label, 'N/A')
        short_val = data['short'].get(label, 'N/A')
        
        if label.startswith("Avg") and isinstance(long_val, (int, float)): 
            long_val = f"{long_val:.4f}"
        if label.startswith("Avg") and isinstance(short_val, (int, float)): 
            short_val = f"{short_val:.4f}"
        
        # Truncar etiqueta si es necesaria
        display_label = _truncate_text(label, max_label_len)
        
        content_left = f"{display_label:<{max_label_len}} : {long_val}"
        content_right = f"{display_label:<{max_label_len}} : {short_val}"

        # Truncar contenido si es muy largo
        content_left = _truncate_text(content_left, width_col - 2)
        content_right = _truncate_text(content_right, width_col - 2)

        # Calcular padding
        padding_left = ' ' * max(0, width_col - len(content_left) - 1)
        padding_right = ' ' * max(0, width_col - len(content_right) - 1)
        
        print(f"│ {content_left}{padding_left}│ {content_right}{padding_right}│")

    print("└" + "─" * width_col + "┴" + "─" * width_col + "┘")


def _render_dashboard_view(summary: Dict[str, Any], config_module: Any):
    """Función dedicada a imprimir el layout completo del dashboard."""
    # Obtener ancho del terminal y ajustar
    terminal_width = _get_terminal_width()
    box_width = min(terminal_width - 2, 90)  # Máximo 90, mínimo terminal_width - 2
    
    # Asegurar que el ancho sea al menos 60 para que sea funcional
    if box_width < 60:
        box_width = 60
    
    header_line = "=" * box_width
    print(header_line)
    
    # Centrar título y fecha
    now_str = datetime.datetime.now(timezone.utc).strftime('%H:%M:%S %d-%m-%Y (UTC)')
    title = "Dashboard de la Sesión"
    
    title_padding = (box_width - len(title)) // 2
    date_padding = (box_width - len(now_str)) // 2
    
    print(" " * title_padding + title)
    print(" " * date_padding + now_str)
    print(header_line)
    
    _render_session_status_block(summary, box_width)
    _render_signal_status_block(summary, config_module, box_width)
    _render_operations_status_block(summary, box_width)
    

# --- Lógica Principal de la Pantalla (Sin cambios) ---
def show_dashboard_screen(session_manager: Any):
    from ._session_config_editor import show_session_config_editor_screen

    config_module = _deps.get("config_module")
    if not TerminalMenu or not config_module or not sm_api or not session_manager:
        print("ERROR CRÍTICO: Dependencias del Dashboard no disponibles.")
        time.sleep(3)
        return

    sm_api.init_sm_api(session_manager)
    session_manager.start()

    clear_screen()
    print("Dashboard: Esperando la recepción del primer tick de precio del mercado...")
    
    wait_animation = ['|', '/', '-', '\\']
    i = 0
    while True:
        current_price = pm_api.get_current_market_price()
        if current_price and current_price > 0:
            print("\n¡Precio recibido! Cargando dashboard...")
            time.sleep(1.5)
            break
        print(f"\rEsperando... {wait_animation[i % len(wait_animation)]}", end="")
        i += 1
        time.sleep(0.2)

    while True:
        error_message = None
        summary = {}
        try:
            summary = sm_api.get_session_summary()
            if not summary or summary.get('error'):
                error_message = f"ADVERTENCIA: No se pudo obtener el estado de la sesión: {summary.get('error', 'Reintentando...')}"
        except Exception as e:
            error_message = f"ERROR CRÍTICO: Excepción inesperada en el dashboard: {e}"
        
        clear_screen()
        if error_message:
            print(f"\033[91m{error_message}\033[0m")
        
        if summary and not summary.get('error'):
            _render_dashboard_view(summary, config_module)
        
        menu_items = [
            "[1] Gestionar Operación LONG", 
            "[2] Gestionar Operación SHORT",
            "[3] Editar Configuración de Sesión", 
            "[4] Ver Logs en Tiempo Real",
            None,
            "[r] Refrescar",
            "[h] Ayuda", 
            "[q] Finalizar Sesión y Volver al Menú Principal"
        ]
        action_map = {
            0: 'manage_long', 1: 'manage_short', 2: 'edit_config', 3: 'view_logs',
            5: 'refresh', 6: 'help', 7: 'exit_session'
        }
        
        menu_options = helpers_module.MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu_options['menu_cursor_style'] = ("fg_cyan", "bold")

        menu = TerminalMenu(menu_items, title="Acciones de la Sesión:", **menu_options)
        choice = menu.show()
        action = action_map.get(choice)
        
        if action == 'manage_long':
            operation_manager.show_operation_manager_screen(side_filter='long')
        elif action == 'manage_short':
            operation_manager.show_operation_manager_screen(side_filter='short')
        elif action == 'edit_config':
            changes_made = show_session_config_editor_screen(config_module)
            if changes_made:
                sm_api.update_session_parameters(changes_made) 
        elif action == 'view_logs': 
            _log_viewer.show_log_viewer()
        elif action == 'refresh':
            time.sleep(0.1)
            continue
        elif action == 'help': 
            helpers_module.show_help_popup("dashboard_main")
        elif action == 'exit_session' or choice is None:
            confirm_menu = TerminalMenu(["[1] Sí, finalizar sesión", "[2] No, continuar"], title="¿Confirmas finalizar la sesión actual?", **helpers_module.MENU_STYLE)
            if confirm_menu.show() == 0: 
                break
    
    final_summary_data = sm_api.get_session_summary()
    _display_final_summary(final_summary_data)
    
    if session_manager.is_running():
        session_manager.stop()
    
    from runner import shutdown_session_backend
    shutdown_session_backend(
        session_manager=session_manager,
        final_summary=final_summary_data,
        config_module=_deps.get("config_module"),
        open_snapshot_logger_module=_deps.get("open_snapshot_logger_module")
    )