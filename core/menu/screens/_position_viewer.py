# core/menu/screens/_position_viewer.py

import time
from typing import Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen, 
    print_tui_header, 
    press_enter_to_continue, 
    MENU_STYLE,
    show_help_popup
)

def show_position_viewer_screen(pm_api: Any):
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado.")
        time.sleep(2)
        return

    while True:
        try:
            summary = pm_api.get_position_summary()
            longs_count = summary.get('open_long_positions_count', 0)
            shorts_count = summary.get('open_short_positions_count', 0)
        except Exception as e:
            print(f"Error obteniendo resumen de posiciones: {e}")
            time.sleep(2)
            return

        menu_items = [
            f"[1] Gestionar Posiciones LONG ({longs_count} abiertas)",
            f"[2] Gestionar Posiciones SHORT ({shorts_count} abiertas)",
            None,
            "[h] Ayuda sobre esta pantalla",
            None,
            "[b] Volver al Dashboard Principal"
        ]
        main_menu = TerminalMenu(
            menu_items,
            title="Visor y Gestor de Posiciones",
            **MENU_STYLE
        )
        choice = main_menu.show()

        if choice == 0:
            _manage_side_positions('long', pm_api)
        elif choice == 1:
            _manage_side_positions('short', pm_api)
        elif choice == 3:
            show_help_popup("position_viewer")
        else:
            break


def _manage_side_positions(side: str, pm_api: Any):
    while True:
        clear_screen()
        print_tui_header(f"Gestionando Posiciones {side.upper()}")

        try:
            summary = pm_api.get_position_summary()
            if not summary or summary.get('error'):
                print("Error al refrescar el resumen de posiciones.")
                time.sleep(2)
                return
            
            open_positions = summary.get(f'open_{side}_positions', [])
            current_price = pm_api.get_current_market_price() or 0.0
        except Exception as e:
            print(f"Error refrescando datos de posiciones: {e}")
            time.sleep(2)
            return
            
        menu_items = []
        if not open_positions:
            menu_items.append("(No hay posiciones lógicas abiertas en este lado)")
        else:
            print(f"Precio de Mercado Actual: {current_price:.4f} USDT\n")
            for i, pos in enumerate(open_positions):
                pnl = 0.0
                entry_price = pos.entry_price or 0.0
                size_contracts = pos.size_contracts or 0.0
                sl_price = pos.stop_loss_price
                ts_info = "TS Inactivo"
                if pos.ts_is_active:
                    ts_stop = pos.ts_stop_price
                    ts_info = f"TS Activo @ {ts_stop:.4f}" if ts_stop else "TS Activo (Calculando...)"

                if current_price > 0 and entry_price > 0 and size_contracts > 0:
                    pnl = (current_price - entry_price) * size_contracts if side == 'long' else (entry_price - current_price) * size_contracts
                
                sl_str = f"{sl_price:.4f}" if sl_price is not None else 'N/A'
                entry_str = f"Idx {i:<2} | PNL: {pnl:>+8.2f} USDT | Entrada: {entry_price:>9.4f} | Tamaño: {size_contracts:>8.4f} | SL: {sl_str:<9} | {ts_info}"
                menu_items.append(f"[Cerrar] {entry_str}")

        menu_items.extend([
            None,
            f"[Cerrar TODAS] las {len(open_positions)} posiciones {side.upper()}" if open_positions else "(No hay posiciones para cerrar)",
            "[r] Refrescar",
            "[h] Ayuda",
            None,
            "[b] Volver"
        ])
        
        submenu = TerminalMenu(
            menu_items,
            title=f"Selecciona una posición para cerrar o una acción:",
            **MENU_STYLE
        )
        choice_index = submenu.show()

        if choice_index is None:
            break

        if not (0 <= choice_index < len(menu_items)):
            continue

        action_text = menu_items[choice_index]

        if action_text is None or "Volver" in action_text:
            break
        if "[r] Refrescar" in action_text:
            continue
        if "[h] Ayuda" in action_text:
            show_help_popup("position_viewer")
            continue
        
        if "[Cerrar] Idx" in action_text:
            try:
                pos_index_to_close = choice_index
                print(f"\nEnviando orden de cierre para la posición con índice {pos_index_to_close}...")
                success, msg = pm_api.manual_close_logical_position_by_index(side, pos_index_to_close)

                if success:
                    print(f"\033[92mÉXITO:\033[0m {msg}")
                else:
                    print(f"\033[91mFALLO:\033[0m {msg}")
                
                time.sleep(2.5)
            except (ValueError, IndexError):
                print("\nError al procesar la selección. Inténtalo de nuevo.")
                time.sleep(1.5)

        elif "[Cerrar TODAS]" in action_text and open_positions:
            confirm_title = f"¿Confirmas cerrar TODAS las {len(open_positions)} posiciones {side.upper()}?"
            confirm_menu = TerminalMenu(["[s] Sí, cerrar todas", "[n] No, cancelar"], title=confirm_title, **MENU_STYLE)
            if confirm_menu.show() == 0:
                print("\nEnviando órdenes de cierre total, por favor espera...")
                success, message = pm_api.close_all_logical_positions(side, reason="MANUAL_CLOSE_ALL")
                if success:
                    print(f"\n\033[92mÉXITO:\033[0m {message}")
                else:
                    print(f"\n\033[91mFALLO:\033[0m {message}")
                time.sleep(3)
