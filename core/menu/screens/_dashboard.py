# Contenido completo y corregido para: core/menu/screens/_dashboard.py

import time
import datetime
from datetime import timezone
from typing import Dict, Any, List
import re
import os
import shutil
import numpy as np

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
    from core.strategy.pm import api as pm_api
    from core.strategy.om import api as om_api
    from core.strategy.entities import Operacion, LogicalPosition
    from core import utils
except ImportError:
    sm_api = pm_api = om_api = utils = None
    class Operacion:
        def get_live_performance(self, current_price: float, utils_module: Any) -> Dict[str, float]:
            return {"pnl_no_realizado": 0.0, "pnl_total": 0.0, "equity_actual_vivo": 0.0, "roi_twrr_vivo": 0.0}
    class LogicalPosition: pass


_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

def _get_terminal_width():
    try: return shutil.get_terminal_size().columns
    except: return 90

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

def _display_final_summary(summary: Dict[str, Any], config_module: Any):
    clear_screen()
    print_tui_header("Resumen Final de la Sesión")

    if not summary or summary.get('error'):
        print("\nNo se pudo generar el resumen final.")
        press_enter_to_continue()
        return

    if config_module:
        print("\n--- Configuración del Bot ---")
        bot_cfg = config_module.BOT_CONFIG
        modo_trading_str = "Paper Trading" if bot_cfg.get("PAPER_TRADING_MODE", False) else "Live Trading"
        bot_params_to_show = {
            "Exchange": bot_cfg.get("EXCHANGE_NAME", "N/A").upper(),
            "Símbolo Ticker": bot_cfg.get("TICKER", {}).get("SYMBOL", "N/A"),
            "Modo de Trading": modo_trading_str,
            "Modo Testnet": "ACTIVADO" if bot_cfg.get("UNIVERSAL_TESTNET_MODE", False) else "DESACTIVADO"
        }
        max_bot_key_len = max(len(k) for k in bot_params_to_show.keys())
        for key, value in bot_params_to_show.items():
            print(f"  {key:<{max_bot_key_len}} : {value}")

    start_time = pm_api.get_session_start_time()
    duration_str = "N/A"
    if start_time:
        duration = datetime.datetime.now(timezone.utc) - start_time
        duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))

    print(f"\nDuración Total de la Sesión: {duration_str}")

    print("\n--- Estado Final de las Operaciones ---")
    sides = ['long', 'short']
    for side in sides:
        op_obj = om_api.get_operation_by_side(side) if om_api else None
        if not op_obj: continue

        pnl_realizado = op_obj.pnl_realizado_usdt
        ganancias_netas = pnl_realizado - op_obj.comisiones_totales_usdt
        roi = 0.0
        if utils and op_obj.capital_inicial_usdt > 0:
            roi = utils.safe_division(pnl_realizado, op_obj.capital_inicial_usdt) * 100

        print(f"\n  Operación {side.upper()}:")
        print(f"    - Estado Final          : {op_obj.estado.upper()}")
        print(f"    - Trades Cerrados       : {op_obj.comercios_cerrados_contador}")
        print(f"    - Capital Inicial       : ${op_obj.capital_inicial_usdt:.2f}")
        print(f"    - Equity Total (Final)  : ${op_obj.equity_total_usdt:.2f}")
        print(f"    - Ganancias Netas       : ${ganancias_netas:+.4f}")
        print(f"    - PNL (Realizado)       : {pnl_realizado:+.4f} USDT")
        print(f"    - ROI                   : {roi:+.2f}%")

    open_longs = summary.get('open_long_positions', [])
    open_shorts = summary.get('open_short_positions', [])

    if open_longs or open_shorts:
        print("\n--- Posiciones que Quedaron Abiertas ---")
        if open_longs:
            print(f"  LONGs ({len(open_longs)}):")
            for pos in open_longs:
                print(f"    - ID: {str(pos.id)[-6:]}, Entrada: {pos.entry_price or 0.0:.4f}, Tamaño: {pos.size_contracts or 0.0:.4f}")
        if open_shorts:
            print(f"  SHORTs ({len(open_shorts)}):")
            for pos in open_shorts:
                print(f"    - ID: {str(pos.id)[-6:]}, Entrada: {pos.entry_price or 0.0:.4f}, Tamaño: {pos.size_contracts or 0.0:.4f}")
    else:
        print("\n--- No quedaron posiciones abiertas ---")

    press_enter_to_continue()


def _render_session_status_block(summary: Dict[str, Any], box_width: int):
    session_start_time = pm_api.get_session_start_time()
    start_time_str = "N/A"
    duration_str = "0:00:00"
    if session_start_time:
        start_time_str = session_start_time.strftime('%H:%M:%S %d-%m-%Y (UTC)')
        now_utc = datetime.datetime.now(timezone.utc)
        start_time_utc = session_start_time.replace(tzinfo=timezone.utc)
        duration_seconds = (now_utc - start_time_utc).total_seconds()
        duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))

    total_equity = 0.0
    transferido_val = 0.0
    if om_api:
        long_op = om_api.get_operation_by_side('long')
        short_op = om_api.get_operation_by_side('short')
        if long_op:
            total_equity += long_op.equity_total_usdt
            transferido_val += getattr(long_op, 'profit_balance_acumulado', 0.0)
        if short_op:
            total_equity += short_op.equity_total_usdt
            transferido_val += getattr(short_op, 'profit_balance_acumulado', 0.0)
    
    data = {
        "Inicio Sesión": start_time_str,
        "Duración": duration_str,
        "Equity Total (Ambas Ops)": f"${total_equity:.2f} USDT",
        "Total Transferido a PROFIT": f"{transferido_val:+.4f} USDT"
    }

    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Estado de Sesión", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    max_key_len = max(len(k) for k in data.keys()) if data else 0

    for key, value in data.items():
        content = f"{key:<{max_key_len}} : {value}"
        print(_create_box_line(content, box_width))

    print("└" + "─" * (box_width - 2) + "┘")


def _render_signal_status_block(summary: Dict[str, Any], config_module: Any, box_width: int):
    ticker_symbol = config_module.BOT_CONFIG["TICKER"]["SYMBOL"]
    latest_signal_info = summary.get('latest_signal', {})

    price_val = latest_signal_info.get('price_float')
    price_str = f"{price_val:.8f}" if isinstance(price_val, float) else "N/A"

    ema_str = latest_signal_info.get('ema', 'N/A')
    inc_pct_str = latest_signal_info.get('inc_price_change_pct', 'N/A')
    w_inc_str = latest_signal_info.get('weighted_increment', 'N/A')
    dec_pct_str = latest_signal_info.get('dec_price_change_pct', 'N/A')
    w_dec_str = latest_signal_info.get('weighted_decrement', 'N/A')

    print("┌" + "─" * (box_width - 2) + "┐")
    print(_create_box_line("Señal", box_width, 'center'))
    print("├" + "─" * (box_width - 2) + "┤")

    data_top = {"Ticker": ticker_symbol, "Precio Actual": price_str}
    max_key_top = max(len(k) for k in data_top.keys())
    for key, value in data_top.items():
        content = f"{key:<{max_key_top}} : {value}"
        print(_create_box_line(content, box_width))

    print("├" + "─" * (box_width - 2) + "┤")
    print(_create_box_line("Indicadores TA", box_width, 'center'))
    print(_create_box_line(f"  EMA: {_truncate_text(str(ema_str), box_width-10)}", box_width))
    print(_create_box_line(f"  W.Inc / W.Dec: {_truncate_text(f'{w_inc_str} / {w_dec_str}', box_width-20)}", box_width))
    print(_create_box_line(f"  Price Inc.(%)/ Dec.(%): {_truncate_text(f'{inc_pct_str} / {dec_pct_str}', box_width-35)}", box_width))

    print("├" + "─" * (box_width - 2) + "┤")

    signal_val = latest_signal_info.get('signal', 'N/A')
    reason_val = latest_signal_info.get('signal_reason', '')

    print(_create_box_line(f"Señal Generada : {_truncate_text(str(signal_val), box_width-20)}", box_width))
    print(_create_box_line(f"Razón          : {_truncate_text(str(reason_val), box_width-20)}", box_width))

    print("└" + "─" * (box_width - 2) + "┘")

def _render_operations_status_block(summary: Dict[str, Any], box_width: int):
    if not all([om_api, utils]):
        print("Error: Dependencias om_api o utils no disponibles.")
        return

    sides = ['long', 'short']
    data = {side: {} for side in sides}
    current_price = summary.get('current_market_price', 0.0)

    for side in sides:
        operacion = om_api.get_operation_by_side(side)
        if not operacion:
            data[side]['Estado'] = 'NO_DISPONIBLE'
            continue
            
        live_performance = operacion.get_live_performance(current_price, utils)
        
        pnl_realizado = operacion.pnl_realizado_usdt
        pnl_no_realizado = live_performance.get("pnl_no_realizado", 0.0)
        equity_actual_vivo = live_performance.get("equity_actual_vivo", 0.0)
        
        roi_realizado = operacion.realized_twrr_roi
        
        roi_no_realizado = utils.safe_division(pnl_no_realizado, operacion.capital_operativo_logico_actual) * 100
        
        def get_color(value):
            return "\033[92m" if value >= 0 else "\033[91m"
        reset = "\033[0m"
        
        data[side] = {
            'Estado': operacion.estado.upper(),
            'Posiciones': f"{operacion.posiciones_abiertas_count}/{len(operacion.posiciones)}",
            'Equity Total (Hist.)': f"${operacion.equity_total_usdt:.2f}",
            'Equity Actual (Vivo)': f"{get_color(pnl_no_realizado)}${equity_actual_vivo:.2f}{reset}",
            'Transferido a PROFIT': f"{get_color(getattr(operacion, 'profit_balance_acumulado', 0.0))}{getattr(operacion, 'profit_balance_acumulado', 0.0):+.4f}{reset}",
            'PNL Realizado': f"{get_color(pnl_realizado)}{pnl_realizado:+.4f}${reset}",
            'PNL No Realizado': f"{get_color(pnl_no_realizado)}{pnl_no_realizado:+.4f}${reset}",
            'ROI Realizado': f"{get_color(roi_realizado)}{roi_realizado:+.2f}%{reset}",
            'ROI No Realizado': f"{get_color(roi_no_realizado)}{roi_no_realizado:+.2f}%{reset}",
        }

    width_col = (box_width - 3) // 2

    print("┌" + "─" * width_col + "┬" + "─" * width_col + "┐")
    print(f"│{'Operación LONG':^{width_col}}│{'Operación SHORT':^{width_col}}│")
    print("├" + "─" * width_col + "┼" + "─" * width_col + "┤")

    labels = [
        'Estado', 'Posiciones', 'Equity Total (Hist.)', 'Equity Actual (Vivo)',
        'Transferido a PROFIT', 'PNL Realizado', 'PNL No Realizado',
        'ROI Realizado', 'ROI No Realizado'
    ]
    
    max_label_len = min(max(len(k) for k in labels), width_col - 12) if labels else 0

    for label in labels:
        long_val = data['long'].get(label, 'N/A')
        short_val = data['short'].get(label, 'N/A')

        display_label = _truncate_text(label, max_label_len)

        content_left = f"{display_label:<{max_label_len}} : {long_val}"
        content_right = f"{display_label:<{max_label_len}} : {short_val}"

        content_left = _truncate_text(content_left, width_col - 2)
        content_right = _truncate_text(content_right, width_col - 2)

        padding_left = ' ' * max(0, width_col - len(_clean_ansi_codes(content_left)) - 1)
        padding_right = ' ' * max(0, width_col - len(_clean_ansi_codes(content_right)) - 1)

        print(f"│ {content_left}{padding_left}│ {content_right}{padding_right}│")

    print("└" + "─" * width_col + "┴" + "─" * width_col + "┘")


def _render_dashboard_view(summary: Dict[str, Any], config_module: Any):
    terminal_width = _get_terminal_width()
    box_width = min(terminal_width - 2, 90)

    if box_width < 60:
        box_width = 60

    header_line = "=" * box_width
    print(header_line)

    now_str = datetime.datetime.now(timezone.utc).strftime('%H:%M:%S %d-%m-%Y (UTC)')
    title = "Dashboard de la Sesión"

    print(f"{title:^{box_width}}")
    print(f"{now_str:^{box_width}}")
    print(header_line)

    _render_session_status_block(summary, box_width)
    _render_signal_status_block(summary, config_module, box_width)
    _render_operations_status_block(summary, box_width)

# Reemplaza la función show_dashboard_screen completa en _dashboard.py
# Reemplaza la función show_dashboard_screen completa en core/menu/screens/_dashboard.py

def show_dashboard_screen(session_manager: Any):
    from ._session_config_editor import show_session_config_editor_screen
    # Aseguramos que todas las dependencias necesarias, incluida la de ayuda, estén importadas
    from .. import _helpers as helpers_module

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
        clear_screen()

        error_message = None
        summary = {}
        try:
            summary = sm_api.get_session_summary()
            if not summary or summary.get('error'):
                error_message = f"ADVERTENCIA: No se pudo obtener el estado de la sesión: {summary.get('error', 'Reintentando...')}"
        except Exception as e:
            error_message = f"ERROR CRÍTICO: Excepción inesperada en el dashboard: {e}"

        if error_message:
            print(f"\033[91m{error_message}\033[0m")

        if summary and not summary.get('error'):
            _render_dashboard_view(summary, config_module)

        # La estructura del menú ya es correcta y no necesita cambios.
        menu_items = [
            "[1] Gestionar Operación LONG",
            "[2] Gestionar Operación SHORT",
            None,
            "[3] Editar Configuración de Sesión",
            "[4] Ver Logs en Tiempo Real",
            None,
            "[r] Refrescar",
            "[h] Ayuda",
            "[q] Finalizar Sesión y Volver al Menú Principal"
        ]
        
        action_map = {
            0: 'manage_long', 1: 'manage_short', 3: 'edit_config',
            4: 'view_logs', 6: 'refresh', 7: 'help', 8: 'exit_session'
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
            # La llamada a la ayuda ya es correcta.
            helpers_module.show_help_popup("dashboard_main")
        elif action == 'exit_session' or choice is None:
            clear_screen()
            
            confirm_menu_options = helpers_module.MENU_STYLE.copy()
            confirm_menu_options['clear_screen'] = False
            confirm_menu = TerminalMenu(["[1] Sí, finalizar sesión", "[2] No, continuar"], title="¿Confirmas finalizar la sesión actual?", **confirm_menu_options)
            if confirm_menu.show() == 0:
                break

    final_summary_data = sm_api.get_session_summary()
    _display_final_summary(final_summary_data, config_module)

    if session_manager.is_running():
        session_manager.stop()

    from runner import shutdown_session_backend
    shutdown_session_backend(
        session_manager=session_manager,
        final_summary=final_summary_data,
        config_module=_deps.get("config_module"),
        open_snapshot_logger_module=_deps.get("open_snapshot_logger_module")
    )