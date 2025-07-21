# core/menu/screens/_positions.py

"""
Módulo para la pantalla de "Gestionar Posiciones Abiertas" de la TUI.

Esta pantalla permite al usuario visualizar las posiciones abiertas para cada
lado (long y short) y ejecutar cierres manuales, ya sea de forma individual
o masiva.
"""
import sys
import os
import time
from typing import Dict, Any, Optional

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias
try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

try:
    from core.strategy import pm as position_manager
    from .._helpers import MENU_STYLE
except ImportError as e:
    print(f"ERROR [TUI Positions Screen]: Falló importación de dependencias: {e}")
    position_manager = None
    MENU_STYLE = {}

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Pantallas de Gestión de Posiciones ---

def _manage_side_positions(side: str):
    """Función interna para gestionar las posiciones de un lado (long o short)."""
    while True:
        summary = position_manager.get_position_summary()
        if not summary or summary.get('error'):
            print("Error obteniendo resumen de posiciones.")
            time.sleep(1.5)
            return

        open_positions = summary.get(f'open_{side}_positions', [])
        current_price = position_manager.get_current_price_for_exit() or 0.0
        
        menu_items = []
        if not open_positions:
            menu_items.append("(No hay posiciones lógicas abiertas en este lado)")
        else:
            for i, pos in enumerate(open_positions):
                pnl = 0.0
                entry_price = pos.get('entry_price', 0.0)
                size_contracts = pos.get('size_contracts', 0.0)
                if current_price > 0 and entry_price > 0 and size_contracts > 0:
                    pnl = (current_price - entry_price) * size_contracts if side == 'long' else (entry_price - current_price) * size_contracts
                
                menu_items.append(f"[Cerrar Idx {i}] Px: {pos.get('entry_price', 0.0):.4f}, Qty: {pos.get('size_contracts', 0.0):.4f}, PNL: {pnl:+.2f} USDT")

        menu_items.extend([
            None, 
            f"[Cerrar TODAS] las {len(open_positions)} posiciones {side.upper()}" if open_positions else "(No hay posiciones para cerrar)",
            None,
            "[b] Volver"
        ])
        
        title = f"Gestionar Posiciones {side.upper()}"
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()

        if choice_index is None or choice_index >= len(menu_items) - 2 or menu_items[choice_index] is None:
            break
        
        action_text = menu_items[choice_index]

        # --- Lógica para cierre individual MANUAL ---
        if "[Cerrar Idx" in action_text:
            try:
                pos_index_to_close = int(action_text.split(']')[0].split(' ')[-1])
                success, msg = position_manager.manual_close_logical_position_by_index(side, pos_index_to_close)
                print(f"\n{msg}")
                
                if success:
                    # Volvemos a pedir el estado para ver si la lista está vacía AHORA.
                    remaining_positions = len(position_manager.get_position_summary().get(f'open_{side}_positions', []))
                    if remaining_positions == 0:
                        print(f"\nINFO: Última posición {side.upper()} cerrada manualmente.")
                        print("Cambiando a modo NEUTRAL por seguridad para prevenir reaperturas...")
                        position_manager.set_manual_trading_mode("NEUTRAL")
                
                time.sleep(2.5)
            except (ValueError, IndexError):
                print("\nError al procesar la selección.")
                time.sleep(1.5)

        # --- Lógica para cierre total MANUAL ---
        elif "[Cerrar TODAS]" in action_text and open_positions:
            confirm_title = f"¿Confirmas cerrar TODAS las {len(open_positions)} posiciones {side.upper()}?"
            confirm_menu = TerminalMenu(["[s] Sí, cerrar todas", "[n] No, cancelar"], title=confirm_title, **MENU_STYLE)
            if confirm_menu.show() == 0:
                print("\nEnviando órdenes de cierre total, por favor espera...")
                closed_successfully = position_manager.close_all_logical_positions(side, reason="MANUAL_CLOSE_ALL")
                if closed_successfully:
                    print(f"\nÉXITO: Todas las posiciones {side.upper()} han sido cerradas.")
                    print("Cambiando a modo NEUTRAL por seguridad...")
                    position_manager.set_manual_trading_mode("NEUTRAL")
                else:
                    print(f"\nFALLO: No se pudieron cerrar todas las posiciones. Revisa los logs.")
                time.sleep(3)


def show_positions_menu():
    """Muestra el menú para elegir qué lado de las posiciones gestionar."""
    if not TerminalMenu or not position_manager:
        print("\nError: Dependencias de menú no disponibles (TerminalMenu o PositionManager).")
        time.sleep(2)
        return
        
    while True:
        menu_items = ["[1] Gestionar posiciones LONG", "[2] Gestionar posiciones SHORT", None, "[b] Volver al menú principal"]
        title = "Selecciona qué lado gestionar"
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            _manage_side_positions('long')
        elif choice_index == 1:
            _manage_side_positions('short')
        else: # Si el usuario presiona 'b', ESC o elige una opción nula
            break