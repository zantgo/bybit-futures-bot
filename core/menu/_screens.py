# =============== INICIO ARCHIVO: core/menu/_screens.py (CORREGIDO FINAL V2) ===============
"""
Módulo de Pantallas de la TUI (Terminal User Interface).

Contiene las funciones que renderizan cada una de las pantallas específicas
del menú principal. Cada función es una "vista" que interactúa con el
Position Manager para obtener datos y presentarlos al usuario.
"""
import time
from typing import Dict, Any, Optional

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Proyecto ---
try:
    from core.strategy import pm_facade as position_manager
    # --- INICIO MODIFICACIÓN: Eliminar add_menu_footer ---
    from ._helpers import (
        clear_screen,
        print_tui_header,
        get_input,
        MENU_STYLE,
        press_enter_to_continue,
        print_section
    )
    from core.logging import memory_logger
    # --- FIN MODIFICACIÓN ---
except ImportError as e:
    print(f"ERROR [TUI Screens]: Falló importación de dependencias: {e}")
    position_manager = None
    memory_logger = None
    def clear_screen(): pass
    def print_tui_header(title): print(f"--- {title} ---")
    def get_input(prompt, type_func, default): return default
    def press_enter_to_continue(): input("Press Enter...")
    def print_section(title, data, is_account_balance=False): print(f"--- {title} --- \n {data}")
    MENU_STYLE = {}


# --- Pantallas del Menú Principal ---


def show_status_screen():
    """Muestra una pantalla con el estado detallado de la sesión."""
    clear_screen()
    print_tui_header("Estado Detallado de la Sesión")
    
    summary = position_manager.get_position_summary()
    if not summary or summary.get('error'):
        print(f"\nError al obtener el estado del bot: {summary.get('error', 'Desconocido')}")
        press_enter_to_continue()
        return

    # --- Balances Reales de Cuentas ---
    real_account_balances = summary.get('real_account_balances', {})
    if real_account_balances:
        print_section("Balances Reales de Cuentas (UTA)", real_account_balances, is_account_balance=True)

    # --- Estado y Rendimiento de la Sesión ---
    manual_state = summary.get('manual_mode_status', {})
    limit_str = manual_state.get('limit') or 'Ilimitados'
    
    current_price = position_manager.get_current_price_for_exit() or 0.0
    unrealized_pnl = position_manager.get_unrealized_pnl(current_price)
    total_pnl = summary.get('total_realized_pnl_session', 0.0) + unrealized_pnl
    initial_capital = summary.get('initial_total_capital', 0.0)
    current_roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0

    print_section("Estado Lógico de la Sesión (Bot)", {
        "Modo Manual Actual": f"{manual_state.get('mode', 'N/A')} (Trades: {manual_state.get('executed', 0)}/{limit_str})",
        "Precio Actual de Mercado": f"{current_price:.4f} USDT",
        "Capital Lógico Inicial": f"{initial_capital:.2f} USDT",
        "PNL Realizado (Sesión)": f"{summary.get('total_realized_pnl_session', 0.0):+.4f} USDT",
        "PNL No Realizado (Actual)": f"{unrealized_pnl:+.4f} USDT",
        "PNL Total (Estimado)": f"{total_pnl:+.4f} USDT",
        "ROI Actual (Estimado)": f"{current_roi:+.2f}%",
    })

    # --- Parámetros de Riesgo ---
    risk_params = {
        "Stop Loss Individual": f"{position_manager.pm_state.get_individual_stop_loss_pct() or 0.0:.2f}% (para nuevas posiciones)",
        "Trailing Stop": f"Activación: {position_manager.pm_state.get_trailing_stop_params()['activation']:.2f}% / Distancia: {position_manager.pm_state.get_trailing_stop_params()['distance']:.2f}%",
        "SL Global por ROI": f"{position_manager.get_global_sl_pct():.2f}%" if position_manager.get_global_sl_pct() else "Desactivado",
        "TP Global por ROI": f"{position_manager.pm_state.get_global_tp_pct():.2f}%" if position_manager.pm_state.get_global_tp_pct() else "Desactivado",
    }
    print_section("Parámetros de Riesgo Actuales", risk_params)
    
    # --- Posiciones Lógicas Abiertas ---
    print("\n--- Posiciones Lógicas Abiertas ---")
    position_manager.display_logical_positions()
    
    press_enter_to_continue()

def show_mode_menu():
    """Muestra el menú para cambiar el modo de trading."""
    current_mode = position_manager.pm_state.get_manual_state().get('mode', 'N/A')
    
    menu_items = [
        "[1] LONG_SHORT (Operar en ambos lados)",
        "[2] LONG_ONLY (Solo compras)",
        "[3] SHORT_ONLY (Solo ventas)",
        "[4] NEUTRAL (Detener nuevas entradas)",
        None,
        "[b] Volver al menú principal"
    ]
    
    # --- INICIO MODIFICACIÓN: Integrar pie de página en el título ---
    title = (
        f"Selecciona el nuevo modo de trading\n"
        f"Modo actual: {current_mode}\n"
        f"----------------------------------------\n"
        f"[Enter] Seleccionar | [b] o [ESC] Volver"
    )
    # --- FIN MODIFICACIÓN ---
    
    terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
    choice_index = terminal_menu.show()

    if choice_index is not None and choice_index < 4:
        modes = ["LONG_SHORT", "LONG_ONLY", "SHORT_ONLY", "NEUTRAL"]
        new_mode = modes[choice_index]
        
        confirm_title = (
            f"¿Deseas cerrar posiciones que no encajen con el modo '{new_mode}'?\n"
            f"----------------------------------------\n"
            f"[s] Sí | [n] No | [ESC] Cancelar"
        )
        confirm_menu = TerminalMenu(
            ["[s] Sí, cerrar posiciones no coincidentes", "[n] No, mantener todas las posiciones"],
            title=confirm_title,
            **MENU_STYLE
        )
        close_choice = confirm_menu.show()
        close_open = (close_choice == 0)

        success, message = position_manager.set_manual_trading_mode(new_mode, close_open=close_open)
        print(f"\n{message}")
        time.sleep(2)

def show_risk_menu():
    """Muestra el menú para ajustar parámetros de riesgo en un bucle."""
    while True:
        sl_ind = position_manager.pm_state.get_individual_stop_loss_pct()
        ts_params = position_manager.pm_state.get_trailing_stop_params()
        sl_global = position_manager.get_global_sl_pct() or 0.0
        tp_global = position_manager.pm_state.get_global_tp_pct() or 0.0

        menu_items = [
            f"[1] Ajustar Stop Loss Individual (Actual: {sl_ind:.2f}%)",
            f"[2] Ajustar Trailing Stop (Actual: Act {ts_params['activation']:.2f}% / Dist {ts_params['distance']:.2f}%)",
            f"[3] Ajustar SL Global por ROI (Actual: {sl_global:.2f}%)",
            f"[4] Ajustar TP Global por ROI (Actual: {tp_global:.2f}%)",
            None,
            "[b] Volver al menú principal"
        ]
        
        title = (
            f"Ajustar Parámetros de Riesgo\n"
            f"----------------------------------------\n"
            f"[Enter] Seleccionar | [b] o [ESC] Volver"
        )
        
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            new_sl = get_input("\nNuevo % de Stop Loss Individual (0 para desactivar)", float, sl_ind, min_val=0.0)
            success, msg = position_manager.set_individual_stop_loss_pct(new_sl)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 1:
            print("\n--- Ajustar Trailing Stop (para todas las posiciones) ---")
            new_act = get_input("Nuevo % de Activación (0 para desactivar)", float, ts_params['activation'], min_val=0.0)
            new_dist = get_input("Nuevo % de Distancia", float, ts_params['distance'], min_val=0.0)
            success, msg = position_manager.set_trailing_stop_params(new_act, new_dist)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 2:
            new_sl_g = get_input("\nNuevo % de SL Global por ROI (0 para desactivar)", float, sl_global, min_val=0.0)
            success, msg = position_manager.set_global_stop_loss_pct(new_sl_g)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 3:
            new_tp_g = get_input("\nNuevo % de TP Global por ROI (0 para desactivar)", float, tp_global, min_val=0.0)
            success, msg = position_manager.set_global_take_profit_pct(new_tp_g)
            print(f"\n{msg}"); time.sleep(1.5)
        else:
            break

def show_capital_menu():
    """Muestra el menú para ajustar parámetros de capital en un bucle."""
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
        
        title = (
            f"Ajustar Parámetros de Capital\n"
            f"----------------------------------------\n"
            f"[Enter] Seleccionar | [b] o [ESC] Volver"
        )
        
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()

        if choice_index == 0:
            new_slots = get_input("\nNuevo número de slots por lado", int, slots, min_val=1)
            msg = ""
            if new_slots > slots:
                for _ in range(new_slots - slots):
                    success, msg = position_manager.add_max_logical_position_slot()
            elif new_slots < slots:
                for _ in range(slots - new_slots):
                    success, msg = position_manager.remove_max_logical_position_slot()
                    if not success:
                        break
            else:
                msg = "El número de slots no ha cambiado."
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 1:
            new_size = get_input("\nNuevo tamaño base por posición (USDT)", float, base_size, min_val=1.0)
            success, msg = position_manager.set_base_position_size(new_size)
            print(f"\n{msg}"); time.sleep(1.5)
        else:
            break

def _manage_side_positions(side: str):
    """Función interna para gestionar las posiciones de un lado (long o short)."""
    while True:
        summary = position_manager.get_position_summary()
        if not summary or summary.get('error'):
            print("Error obteniendo resumen de posiciones."); time.sleep(1.5); return

        open_positions = summary.get(f'open_{side}_positions', [])
        if not open_positions:
            print(f"\nNo hay posiciones {side.upper()} abiertas."); time.sleep(1.5); return

        current_price = position_manager.get_current_price_for_exit() or 0.0
        
        menu_items = []
        for i, pos in enumerate(open_positions):
            pnl = (current_price - pos['entry_price']) * pos['size_contracts'] if side == 'long' else (pos['entry_price'] - current_price) * pos['size_contracts']
            menu_items.append(f"[Idx {i}] Px: {pos['entry_price']:.2f}, Qty: {pos['size_contracts']:.4f}, PNL: {pnl:+.2f} USDT")

        menu_items.extend([None, f"[TODAS] Cerrar TODAS las {len(open_positions)} posiciones {side.upper()}", "[b] Volver"])
        
        title = (
            f"Gestionar Posiciones {side.upper()}\n"
            f"----------------------------------------\n"
            f"[Enter] Cerrar Pos. | [b] o [ESC] Volver"
        )

        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()

        if choice_index is None or choice_index >= len(menu_items) - 1:
            break
        elif choice_index == len(menu_items) - 2:
            confirm_title = (
                f"¿Cerrar TODAS las posiciones {side.upper()}?\n"
                f"----------------------------------------\n"
                f"[s] Sí | [n] No | [ESC] Cancelar"
            )
            confirm_menu = TerminalMenu(["[s] Sí, cerrar todas", "[n] No, cancelar"], title=confirm_title, **MENU_STYLE)
            if confirm_menu.show() == 0:
                position_manager.close_all_logical_positions(side, reason="MANUAL_CLOSE_ALL")
                print(f"Enviando órdenes para cerrar todas las posiciones {side.upper()}..."); time.sleep(2)
        else:
            success, msg = position_manager.manual_close_logical_position_by_index(side, choice_index)
            print(f"\n{msg}"); time.sleep(2)

def show_positions_menu():
    """Muestra el menú para elegir qué lado de las posiciones gestionar."""
    while True:
        menu_items = ["[1] Gestionar posiciones LONG", "[2] Gestionar posiciones SHORT", None, "[b] Volver al menú principal"]
        
        title = (
            f"Selecciona qué lado gestionar\n"
            f"----------------------------------------\n"
            f"[Enter] Seleccionar | [b] o [ESC] Volver"
        )
        
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()
        
        if choice_index == 0: _manage_side_positions('long')
        elif choice_index == 1: _manage_side_positions('short')
        else: break

def show_log_viewer():
    """Muestra una pantalla con los últimos logs capturados en memoria."""
    while True:
        clear_screen()
        print_tui_header("Visor de Logs en Tiempo Real")
        
        logs = memory_logger.get_logs() if memory_logger else []
        if not logs:
            print("\n  (No hay logs para mostrar)")
        else:
            print("\n  --- Últimos Mensajes (más recientes al final) ---")
            for timestamp, level, message in logs:
                color_code = ""
                if level == "ERROR": color_code = "\x1b[91m"
                elif level == "WARN": color_code = "\x1b[93m"
                reset_code = "\x1b[0m"
                print(f"  {timestamp} [{color_code}{level:<5}{reset_code}] {message}")

        is_verbose = memory_logger._is_verbose_mode if memory_logger and hasattr(memory_logger, '_is_verbose_mode') else False
        verbose_status_text = "Activado (los logs se imprimen en consola)" if is_verbose else "Desactivado (solo se capturan)"

        title = (
            f"Modo Verboso: {verbose_status_text}\n"
            f"----------------------------------------\n"
            f"[r] Refrescar | [v] Verboso | [b] Volver"
        )

        terminal_menu = TerminalMenu(
            ["[r] Refrescar", "[v] Act/Desactivar Logs en Consola", "[b] Volver"],
            title=title,
            **MENU_STYLE
        )
        choice_index = terminal_menu.show()

        if choice_index == 1 and memory_logger:
             memory_logger.set_verbose_mode(not is_verbose)
        elif choice_index is None or choice_index == 2:
            break

# =============== FIN ARCHIVO: core/menu/_screens.py (CORREGIDO FINAL V2) ===============