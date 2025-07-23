"""
Módulo para la Pantalla del Dashboard Principal.

v3.2: Actualizada la sección de configuración para mostrar el estado de
activación (Activado/Desactivado) de los límites de ROI de sesión,
reflejando las flags booleanas del módulo `config`.
"""
import time
import datetime
from typing import Dict, Any, List

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen,
    print_tui_header,
    press_enter_to_continue,
    print_section
)
from .. import _helpers as helpers_module

from . import _config_editor, _manual_mode, _auto_mode, _position_viewer, _log_viewer

try:
    from core.exchange._models import StandardBalance
except ImportError:
    class StandardBalance: pass

_deps: Dict[str, Any] = {}

# --- Funciones de Ayuda para Renderizado (sin cambios) ---
def _print_positions_table(title: str, positions: List[Dict[str, Any]], current_price: float, side: str):
    """Imprime una tabla formateada para las posiciones abiertas."""
    print(f"\n--- {title} ({len(positions)}) " + "-" * (76 - len(title) - 4 - len(str(len(positions)))))
    
    if not positions:
        print("  (No hay posiciones abiertas)")
        return

    header = f"{'Idx':<4} {'Entrada':>10} {'Tamaño':>12} {'Margen':>10} {'SL':>10} {'PNL (U)':>15}"
    print(header)
    print("-" * len(header))

    COLOR_GREEN = "\033[92m"
    COLOR_RED = "\033[91m"
    COLOR_RESET = "\033[0m"

    for i, pos in enumerate(positions):
        entry_price = pos.get('entry_price', 0.0)
        size_contracts = pos.get('size_contracts', 0.0)
        margin_usdt = pos.get('margin_usdt', 0.0)
        stop_loss_price = pos.get('stop_loss_price')

        pnl = 0.0
        if current_price > 0 and entry_price > 0 and size_contracts > 0:
            pnl = (current_price - entry_price) * size_contracts if side == 'long' else (entry_price - current_price) * size_contracts
        
        pnl_color = COLOR_GREEN if pnl >= 0 else COLOR_RED
        
        idx_str = f"{i:<4}"
        entry_str = f"{entry_price:10.4f}"
        size_str = f"{size_contracts:12.4f}"
        margin_str = f"{margin_usdt:9.2f}$"
        sl_str = f"{stop_loss_price:10.4f}" if stop_loss_price else f"{'N/A':>10}"
        pnl_str = f"{pnl_color}{pnl:14.4f}${COLOR_RESET}"

        print(f"{idx_str} {entry_str} {size_str} {margin_str} {sl_str} {pnl_str}")

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

def show_dashboard_screen():
    """
    Muestra el dashboard principal en un bucle con un diseño mejorado.
    """
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado.")
        time.sleep(2)
        return

    pm_api = _deps.get("position_manager_api_module")
    config_module = _deps.get("config_module")
    
    if not pm_api or not config_module:
        print("ERROR CRÍTICO: Dependencias (PM API o Config) no inyectadas en el Dashboard.")
        time.sleep(3)
        return

    clear_screen()
    print("Dashboard: Esperando la recepción del primer tick de precio del mercado...")
    
    wait_animation = ['|', '/', '-', '\\']
    i = 0
    while True:
        current_price = pm_api.get_current_price_for_exit()
        if current_price and current_price > 0:
            print("\n¡Precio recibido! Cargando dashboard...")
            time.sleep(1.5)
            break
        
        print(f"\rEsperando... {wait_animation[i % len(wait_animation)]}", end="")
        i += 1
        time.sleep(0.2)

    while True:
        try:
            current_price = pm_api.get_current_price_for_exit() or 0.0
            
            summary = pm_api.get_position_summary()
            if not summary or summary.get('error'):
                print(f"\nError al obtener el estado del bot: {summary.get('error', 'Desconocido')}")
                press_enter_to_continue()
                continue
            
            unrealized_pnl = pm_api.get_unrealized_pnl(current_price)
            realized_pnl = summary.get('total_realized_pnl_session', 0.0)
            total_pnl = realized_pnl + unrealized_pnl
            initial_capital = summary.get('initial_total_capital', 0.0)
            current_roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
            
            session_start_time = pm_api.get_session_start_time()
            duration_seconds = (datetime.datetime.now() - session_start_time).total_seconds() if session_start_time else 0
            duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))
            
            ticker_symbol = getattr(config_module, 'TICKER_SYMBOL', 'N/A')
            manual_state = summary.get('manual_mode_status', {})

        except Exception as e:
            clear_screen()
            print(f"Error al recopilar datos para el dashboard: {e}")
            time.sleep(2)
            continue
        
        clear_screen()
        
        header_title = f"Dashboard: {ticker_symbol} @ {current_price:.4f} USDT | Modo: {manual_state.get('mode', 'N/A')}"
        print_tui_header(header_title)
        
        print("\n--- Estado General y Configuración de la Sesión " + "-"*31)
        
        col1_data = {
            "Duración Sesión": duration_str, "Capital Inicial": f"{initial_capital:.2f} USDT",
            "PNL Realizado": f"{realized_pnl:+.4f} USDT", "PNL No Realizado": f"{unrealized_pnl:+.4f} USDT",
            "PNL Total": f"{total_pnl:+.4f} USDT", "ROI Sesión": f"{current_roi:+.2f}%",
        }
        
        # --- INICIO DE LA LÓGICA CORREGIDA ---
        sl_roi_enabled = getattr(config_module, 'SESSION_ROI_SL_ENABLED', False)
        tp_roi_enabled = getattr(config_module, 'SESSION_ROI_TP_ENABLED', False)
        
        sl_roi_val = getattr(config_module, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
        tp_roi_val = getattr(config_module, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)

        sl_roi_str = f"Activo (-{sl_roi_val}%)" if sl_roi_enabled else "Desactivado"
        tp_roi_str = f"Activo (+{tp_roi_val}%)" if tp_roi_enabled else "Desactivado"

        col2_data = {
            "Apalancamiento": f"{getattr(config_module, 'POSITION_LEVERAGE', 0.0):.1f}x",
            "Tamaño Base / Max Pos": f"{getattr(config_module, 'POSITION_BASE_SIZE_USDT', 0.0):.2f}$ / {getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS', 0)}",
            "SL Individual": f"{getattr(config_module, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', 0.0)}%",
            "Trailing Stop (A/D)": f"{getattr(config_module, 'TRAILING_STOP_ACTIVATION_PCT', 0.0)}% / {getattr(config_module, 'TRAILING_STOP_DISTANCE_PCT', 0.0)}%",
            "SL Sesión (ROI)": sl_roi_str,
            "TP Sesión (ROI)": tp_roi_str,
        }
        # --- FIN DE LA LÓGICA CORREGIDA ---

        max_key_len1 = max(len(k) for k in col1_data.keys())
        max_key_len2 = max(len(k) for k in col2_data.keys())
        keys1, keys2 = list(col1_data.keys()), list(col2_data.keys())
        num_rows = max(len(keys1), len(keys2))
        
        for i in range(num_rows):
            line = ""
            if i < len(keys1):
                key = keys1[i]
                line += f"  {key:<{max_key_len1}} : {col1_data[key]:<22}"
            else:
                line += " " * (max_key_len1 + 25)
            if i < len(keys2):
                key = keys2[i]
                line += f"|  {key:<{max_key_len2}} : {col2_data[key]}"
            print(line)

        print("\n--- Estado Cuentas Reales " + "-"*56)
        real_balances = summary.get('real_account_balances', {})
        if not real_balances:
            print("  (No hay datos de balance disponibles)")
        else:
            for acc_name, balance_info in real_balances.items():
                if isinstance(balance_info, StandardBalance):
                    equity = balance_info.total_equity_usd
                    available = balance_info.available_balance_usd
                    margin_used = equity - available
                    print(f"  {acc_name.upper():<15}: Equity: {equity:9.2f}$ | En Uso: {margin_used:8.2f}$ | Disponible: {available:8.2f}$")
                else:
                    print(f"  {acc_name.upper():<15}: ({str(balance_info)})")

        _print_positions_table("Posiciones LONG", summary.get('open_long_positions', []), current_price, 'long')
        _print_positions_table("Posiciones SHORT", summary.get('open_short_positions', []), current_price, 'short')

        menu_items = [
            "[1] Refrescar", "[2] Gestionar Posiciones", "[3] Modo Manual", "[4] Modo Automático",
            "[5] Editar Configuración", "[6] Ver Logs", "[h] Ayuda", "[q] Salir del Bot"
        ]
        
        menu_options = helpers_module.MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu_options['menu_cursor_style'] = ("fg_cyan", "bold")

        menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
        choice = menu.show()
        
        action_map = {0: 'refresh', 1: 'view_positions', 2: 'manual_mode', 3: 'auto_mode', 4: 'edit_config', 5: 'view_logs', 6: 'help', 7: 'exit'}
        action = action_map.get(choice)
        
        if action == 'refresh': 
            continue
        elif action == 'view_positions': 
            _position_viewer.show_position_viewer_screen(pm_api)
        elif action == 'manual_mode': 
            _manual_mode.show_manual_mode_screen(pm_api)
        elif action == 'auto_mode': 
            _auto_mode.show_auto_mode_screen(pm_api)
        elif action == 'edit_config': 
            _config_editor.show_config_editor_screen(config_module)
        elif action == 'view_logs': 
            _log_viewer.show_log_viewer()
        elif action == 'help': 
            helpers_module.show_help_popup("dashboard_main")
        elif action == 'exit' or choice is None:
            confirm_menu = TerminalMenu(["[1] Sí, apagar el bot", "[2] No, continuar"], title="¿Confirmas apagar el bot?", **helpers_module.MENU_STYLE)
            if confirm_menu.show() == 0: 
                break