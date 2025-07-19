# =============== INICIO ARCHIVO: core/menu.py (CORREGIDO Y ABSOLUTAMENTE COMPLETO) ===============
"""
Módulo para gestionar la Interfaz de Usuario de Terminal (TUI) del bot.
Utiliza `simple-term-menu` para crear una experiencia de usuario guiada e
intuitiva, similar a los instaladores de sistemas operativos.
"""
import os
import time
import datetime
import click  # Se mantiene para el lanzador principal de main.py
from typing import Dict, Any, Optional, Tuple

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    print("ERROR CRITICO: La librería 'simple-term-menu' no está instalada.")
    print("Por favor, ejecute: pip install simple-term-menu")
    TerminalMenu = None

# Dependencias del Proyecto
try:
    from core.strategy import pm_facade as position_manager
    from core import utils
    import config
except ImportError:
    position_manager, utils, config = None, None, None

# --- Funciones de Ayuda para Formato y TUI ---
def clear_screen():
    """Limpia la pantalla de la terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_input(prompt: str, type_func=str, default=None):
    """Función robusta para obtener entrada del usuario con validación de tipo."""
    while True:
        try:
            val_str = input(f"{prompt} [{default}]: ")
            if not val_str and default is not None:
                return default
            val = type_func(val_str)
            # Validaciones adicionales
            if type_func == float and val < 0:
                print("El valor no puede ser negativo.")
                continue
            if type_func == int and val < 0:
                print("El valor no puede ser negativo.")
                continue
            return val
        except (ValueError, TypeError):
            print(f"Entrada inválida. Por favor, introduce un valor de tipo '{type_func.__name__}'.")

def print_tui_header(title: str, width: int = 80):
    """Imprime una cabecera estilizada para la TUI."""
    print("=" * width)
    print(f"{title.center(width)}")
    if utils and hasattr(utils, 'format_datetime'):
        now_str = utils.format_datetime(datetime.datetime.now())
        print(f"{now_str.center(width)}")
    print("=" * width)

# ---
# --- Asistente de Inicio / Wizard para el Modo Live ---
# ---
def run_trading_assistant_wizard() -> Optional[Tuple[float, int]]:
    """Guía al usuario a través de la configuración inicial antes de lanzar el bot."""
    if not TerminalMenu: return None, None

    clear_screen()
    print_tui_header("Asistente de Configuración - Modo Live Interactivo")
    print("\n¡Bienvenido! Este asistente te guiará para configurar tu sesión de trading.")
    input("\nPresiona Enter para comenzar...")

    # 1. Configurar Símbolo
    clear_screen()
    print_tui_header("PASO 1 de 2: SÍMBOLO DEL TICKER")
    print("\nEste es el par de trading que el bot monitoreará (ej: BTCUSDT, ETHUSDT).")
    default_symbol = getattr(config, 'TICKER_SYMBOL', 'BTCUSDT')
    symbol = get_input(f"\nIntroduce el símbolo del ticker", str, default_symbol).upper()
    setattr(config, 'TICKER_SYMBOL', symbol)
    print(f"\n✅ Símbolo establecido en: {symbol}")
    time.sleep(1.5)

    # 2. Configurar Capital
    clear_screen()
    print_tui_header("PASO 2 de 2: GESTIÓN DE CAPITAL")
    print("\nDefine cuánto capital arriesgar y cuántas posiciones simultáneas permitir.")
    default_base_size = float(getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0))
    base_size = get_input("\nTamaño base por posición (USDT)", float, default_base_size)
    
    default_slots = int(getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1))
    slots = get_input("Número máximo de posiciones (slots) por lado", int, default_slots)
    print(f"\n✅ Configuración de capital: {slots} posiciones de ~{base_size:.2f} USDT cada una.")
    time.sleep(1.5)

    # 3. Confirmación Final
    clear_screen()
    print_tui_header("CONFIRMACIÓN FINAL")
    print("\nRevisa la configuración de tu sesión:")
    print(f"  - Símbolo:        {symbol}")
    print(f"  - Tamaño Base:    {base_size:.2f} USDT")
    print(f"  - Slots por Lado: {slots}")
    print(f"  - Apalancamiento: {getattr(config, 'POSITION_LEVERAGE', 1.0)}x\n")
    
    confirm_menu = TerminalMenu(
        ["[1] Iniciar Bot con esta Configuración", "[2] Cancelar y Salir"],
        title="¿Es correcta esta configuración?",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("bg_cyan", "fg_black"),
    )
    choice_index = confirm_menu.show()

    if choice_index == 0:
        return base_size, slots
    else:
        clear_screen()
        print("Inicio cancelado por el usuario.")
        time.sleep(2)
        return None, None

# ---
# --- Menú de Intervención en Vivo (TUI) ---
# ---
def run_tui_menu_loop():
    """Ejecuta el bucle del menú interactivo de intervención en vivo."""
    if not TerminalMenu: return

    while True:
        summary = position_manager.get_position_summary()
        manual_state = summary.get('manual_mode_status', {})
        current_mode_str = f"Modo Actual: {manual_state.get('mode', 'N/A')}"
        open_longs = summary.get('open_long_positions_count', 0)
        open_shorts = summary.get('open_short_positions_count', 0)
        status_line = f"Posiciones Abiertas -> LONG: {open_longs} | SHORT: {open_shorts}"

        main_menu_items = [
            " [s] Ver Estado Detallado de la Sesión",
            " [m] Cambiar Modo de Trading",
            " [r] Ajustar Parámetros de Riesgo",
            " [c] Ajustar Capital (Slots / Tamaño)",
            " [p] Gestionar Posiciones Abiertas",
            None,
            " [q] Salir del Menú (el bot sigue corriendo)"
        ]
        
        terminal_menu = TerminalMenu(
            main_menu_items,
            title=f"Asistente de Trading Interactivo\n{current_mode_str}\n{status_line}",
            menu_cursor="> ",
            menu_cursor_style=("fg_yellow", "bold"),
            menu_highlight_style=("bg_yellow", "fg_black"),
            cycle_cursor=True,
            clear_screen=True,
        )
        selected_index = terminal_menu.show()
        
        if selected_index is None or main_menu_items[selected_index].strip().startswith("[q]"):
            break
        
        action = main_menu_items[selected_index].strip().split("]")[0][1:]
        if action == "s": show_status_screen()
        elif action == "m": show_mode_menu()
        elif action == "r": show_risk_menu()
        elif action == "c": show_capital_menu()
        elif action == "p": show_positions_menu()

def show_status_screen():
    clear_screen()
    print_tui_header("Estado Actual de la Sesión")
    summary = position_manager.get_position_summary()
    if not summary or summary.get('error'):
        print(f"Error al obtener estado: {summary.get('error', 'Desconocido')}")
        input("\nPresiona Enter para volver...")
        return

    # <<< INICIO DE LA CORRECCIÓN >>>
    def print_section(title, data, is_account_balance=False):
        print(f"\n--- {title} ---")
        if not data:
            print("  (No hay datos disponibles)")
            return
        
        if is_account_balance:
            for acc_name, balance_info in data.items():
                if balance_info:
                    equity = float(balance_info.get('totalEquity', 0))
                    margin = float(balance_info.get('totalMarginBalance', 0)) # Capital en uso
                    available = float(balance_info.get('totalAvailableBalance', 0)) # Capital disponible
                    print(f"  Cuenta: {acc_name}")
                    print(f"    - Equity Total:     {equity:.2f} USDT")
                    print(f"    - Capital en Uso:   {margin:.2f} USDT")
                    print(f"    - Capital Disponible: {available:.2f} USDT")
                else:
                    print(f"  Cuenta: {acc_name} (No se pudieron obtener datos)")
        else:
            max_key_len = max(len(k) for k in data.keys()) if data else 0
            for key, value in data.items():
                print(f"  {key:<{max_key_len + 2}}: {value}")

    real_account_balances = summary.get('real_account_balances', {})
    if real_account_balances:
        print_section("Balances Reales de Cuentas (UTA)", real_account_balances, is_account_balance=True)
    # <<< FIN DE LA CORRECCIÓN >>>

    manual_state = summary.get('manual_mode_status', {})
    limit_str = manual_state.get('limit') or 'Ilimitados'
    
    current_price = position_manager.get_current_price_for_exit() or 0.0
    unrealized_pnl = position_manager.get_unrealized_pnl(current_price)
    total_pnl = summary.get('total_realized_pnl_session', 0.0) + unrealized_pnl
    initial_capital = summary.get('initial_total_capital', 0.0)
    current_roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0

    print_section("Estado de la Sesión (Bot)", {
        "Modo Manual Actual": f"{manual_state.get('mode', 'N/A')} ({manual_state.get('executed', 0)}/{limit_str})",
        "Precio Actual de Mercado": f"{current_price:.4f} USDT",
    })
    print_section("Rendimiento Lógico (Sesión)", {
        "Capital Lógico Inicial": f"{initial_capital:.2f} USDT",
        "PNL Realizado (Sesión)": f"{summary.get('total_realized_pnl_session', 0.0):+.4f} USDT",
        "PNL No Realizado (Actual)": f"{unrealized_pnl:+.4f} USDT",
        "PNL Total (Estimado)": f"{total_pnl:+.4f} USDT",
        "ROI Actual (Estimado)": f"{current_roi:+.2f}%",
    })
    print_section("Parámetros de Riesgo Actuales", {
        "Stop Loss Individual": f"{position_manager.pm_state.get_individual_stop_loss_pct() or 0.0:.2f}%",
        "Trailing Stop": f"Act: {position_manager.pm_state.get_trailing_stop_params()['activation']:.2f}% / Dist: {position_manager.pm_state.get_trailing_stop_params()['distance']:.2f}%",
    })
    
    print("\n--- Posiciones Lógicas Abiertas ---")
    position_manager.display_logical_positions()
    
    input("\nPresiona Enter para volver al menú principal...")

def show_mode_menu():
    menu_items = ["[1] LONG_SHORT (Operar en ambos lados)", "[2] LONG_ONLY (Solo compras)", "[3] SHORT_ONLY (Solo ventas)", "[4] NEUTRAL (Detener nuevas entradas)", None, "[b] Volver al menú principal"]
    terminal_menu = TerminalMenu(menu_items, title="Selecciona el nuevo modo de trading", clear_screen=True)
    choice_index = terminal_menu.show()

    if choice_index is not None and choice_index < 4:
        modes = ["LONG_SHORT", "LONG_ONLY", "SHORT_ONLY", "NEUTRAL"]
        new_mode = modes[choice_index]
        
        confirm_menu = TerminalMenu(["[s] Sí", "[n] No"], title=f"¿Deseas cerrar posiciones existentes que no coincidan con el modo '{new_mode}'?", clear_screen=True)
        close_choice = confirm_menu.show()
        close_open = (close_choice == 0)

        success, message = position_manager.set_manual_trading_mode(new_mode, close_open=close_open)
        print(f"\n{message}")
        time.sleep(2)

def show_risk_menu():
    while True:
        sl_ind = position_manager.pm_state.get_individual_stop_loss_pct()
        ts_params = position_manager.pm_state.get_trailing_stop_params()
        
        menu_items = [
            f"[1] Ajustar Stop Loss Individual (Actual: {sl_ind:.2f}%)",
            f"[2] Ajustar Trailing Stop (Actual: Act {ts_params['activation']:.2f}% / Dist {ts_params['distance']:.2f}%)",
            None,
            "[b] Volver al menú principal"
        ]
        terminal_menu = TerminalMenu(menu_items, title="Ajustar Parámetros de Riesgo", clear_screen=True, cycle_cursor=True)
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            new_sl = get_input("\nNuevo % de Stop Loss Individual (para nuevas posiciones)", float, sl_ind)
            success, msg = position_manager.set_individual_stop_loss_pct(new_sl)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 1:
            print("\n--- Ajustar Trailing Stop (para todas las posiciones) ---")
            new_act = get_input("Nuevo % de Activación", float, ts_params['activation'])
            new_dist = get_input("Nuevo % de Distancia", float, ts_params['distance'])
            success, msg = position_manager.set_trailing_stop_params(new_act, new_dist)
            print(f"\n{msg}"); time.sleep(1.5)
        else:
            break

def show_capital_menu():
    while True:
        summary = position_manager.get_position_summary()
        slots = summary.get('max_logical_positions', 0)
        base_size = summary.get('initial_base_position_size_usdt', 0.0)

        menu_items = [
            f"[1] Ajustar Slots por Lado (Actual: {slots})",
            f"[2] Ajustar Tamaño Base de Posición (Actual: {base_size:.2f} USDT)",
            None,
            "[b] Volver al menú principal"
        ]
        terminal_menu = TerminalMenu(menu_items, title="Ajustar Parámetros de Capital", clear_screen=True, cycle_cursor=True)
        choice_index = terminal_menu.show()

        if choice_index == 0:
            new_slots = get_input("\nNuevo número de slots por lado", int, slots)
            if new_slots > slots:
                for _ in range(new_slots - slots): success, msg = position_manager.add_max_logical_position_slot()
            elif new_slots < slots:
                for _ in range(slots - new_slots): success, msg = position_manager.remove_max_logical_position_slot()
            else:
                success, msg = True, "El número de slots no ha cambiado."
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 1:
            new_size = get_input("\nNuevo tamaño base por posición (USDT)", float, base_size)
            success, msg = position_manager.set_base_position_size(new_size)
            print(f"\n{msg}"); time.sleep(1.5)
        else:
            break

def _manage_side_positions(side: str):
    while True:
        summary = position_manager.get_position_summary()
        if not summary or summary.get('error'):
            print("Error obteniendo resumen de posiciones."); time.sleep(1.5)
            return

        open_positions = summary.get(f'open_{side}_positions', [])
        current_price = position_manager.get_current_price_for_exit() or 0.0
        
        if not open_positions:
            print(f"\nNo hay posiciones {side.upper()} abiertas."); time.sleep(1.5)
            return

        # Calcular PNL No Realizado para cada posición
        for pos in open_positions:
            pnl = (current_price - pos['entry_price']) * pos['size_contracts'] if side == 'long' else (pos['entry_price'] - current_price) * pos['size_contracts']
            pos['unrealized_pnl'] = pnl

        menu_items = [f"[Idx {i}] Px: {p['entry_price']:.2f}, Qty: {p['size_contracts']:.4f}, PNL: {p.get('unrealized_pnl', 0):+.2f}" for i, p in enumerate(open_positions)]
        menu_items.append(None)
        menu_items.append(f"[TODAS] Cerrar TODAS las {len(open_positions)} posiciones {side.upper()}")
        menu_items.append("[b] Volver")

        terminal_menu = TerminalMenu(menu_items, title=f"Gestionar Posiciones {side.upper()}", clear_screen=True, cycle_cursor=True)
        choice_index = terminal_menu.show()

        if choice_index is None or choice_index >= len(menu_items) -1:
             break
        elif choice_index == len(menu_items) - 2:
            confirm_menu = TerminalMenu(["[s] Sí, cerrar todas", "[n] No, cancelar"], title=f"¿Estás seguro de cerrar TODAS las posiciones {side.upper()}?", clear_screen=True)
            if confirm_menu.show() == 0:
                position_manager.close_all_logical_positions(side)
                print(f"Enviando órdenes para cerrar todas las posiciones {side.upper()}..."); time.sleep(2)
                break 
        else:
            success, msg = position_manager.manual_close_logical_position_by_index(side, choice_index)
            print(f"\n{msg}"); time.sleep(2)

def show_positions_menu():
    while True:
        menu_items = ["[1] Gestionar posiciones LONG", "[2] Gestionar posiciones SHORT", None, "[b] Volver al menú principal"]
        terminal_menu = TerminalMenu(menu_items, title="Selecciona qué lado gestionar", clear_screen=True, cycle_cursor=True)
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            _manage_side_positions('long')
        elif choice_index == 1:
            _manage_side_positions('short')
        else:
            break

# ---
# --- Grupo principal de comandos para `main.py` ---
# ---
@click.group(name="main_cli")
def main_cli():
    """Punto de entrada principal del Bot de Trading. Selecciona un modo para empezar."""
    pass

@main_cli.command(name="live")
def run_live_interactive_command():
    from main import run_selected_mode
    run_selected_mode("live_interactive")

@main_cli.command(name="backtest")
def run_backtest_interactive_command():
    from main import run_selected_mode
    run_selected_mode("backtest_interactive")

@main_cli.command(name="auto")
def run_automatic_live_command():
    from main import run_selected_mode
    run_selected_mode("automatic")

@main_cli.command(name="backtest-auto")
def run_automatic_backtest_command():
    from main import run_selected_mode
    run_selected_mode("automatic_backtest")
    
# =============== FIN ARCHIVO: core/menu.py (CORREGIDO Y ABSOLUTAMENTE COMPLETO) ===============