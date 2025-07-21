# core/menu/_main_loop.py

"""
Módulo del Bucle Principal de la TUI (Terminal User Interface).

Contiene la función `run_tui_menu_loop`, que es el centro de navegación
principal del asistente interactivo en vivo. Desde aquí, el usuario puede
acceder a todas las pantallas de monitorización y gestión del bot.
"""
import sys
import os
from typing import Optional

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias con las rutas corregidas
try:
    from core.strategy import pm as position_manager
    from ._helpers import MENU_STYLE
    
    # --- CORRECCIÓN CLAVE ---
    # Importamos el paquete `screens` completo, que a su vez expone todas las
    # funciones de pantalla a través de su propio __init__.py.
    # Esto rompe el ciclo de importación.
    from . import screens

except ImportError as e:
    # Definir fallbacks si las importaciones fallan
    print(f"ERROR [TUI Main Loop]: Falló importación de dependencias: {e}")
    position_manager = None
    MENU_STYLE = {}
    # Crear un objeto dummy para screens
    class ScreensFallback:
        def show_status_screen(self): print("Función no disponible.")
        def show_mode_menu(self): print("Función no disponible.")
        def show_risk_menu(self): print("Función no disponible.")
        def show_capital_menu(self): print("Función no disponible.")
        def show_positions_menu(self): print("Función no disponible.")
        def show_log_viewer(self): print("Función no disponible.")
        def show_automation_menu(self): print("Función no disponible.")
    screens = ScreensFallback()

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


def run_tui_menu_loop():
    """
    Ejecuta el bucle del menú interactivo principal.
    Ahora alterna entre la vista del menú y el visor de logs, garantizando
    una interfaz limpia.
    """
    if not TerminalMenu or not position_manager or not screens:
        print("ERROR CRITICO: TUI no puede funcionar sin 'simple-term-menu', el Position Manager o el paquete de pantallas.")
        return

    # --- Bucle principal que maneja los modos de vista ---
    current_view = "MENU" # Puede ser "MENU" o "LOGS"

    while True:
        if current_view == "LOGS":
            # --- CORRECCIÓN CLAVE ---
            # Llamamos a la función a través del paquete `screens`.
            screens.show_log_viewer() 
            
            # Al salir de show_log_viewer (cuando el usuario presiona 'b' o ESC),
            # siempre volvemos a la vista del menú.
            current_view = "MENU"
            continue # Volver al inicio del bucle para que se redibuje el menú.

        # --- Lógica del Menú Principal (se ejecuta solo cuando current_view es "MENU") ---
        
        # 1. Obtener datos frescos para el encabezado del menú
        summary = position_manager.get_position_summary()
        if not summary or summary.get('error'):
            print(f"Error fatal obteniendo resumen del bot: {summary.get('error', 'Desconocido')}")
            break

        manual_state = summary.get('manual_mode_status', {})
        open_longs = summary.get('open_long_positions_count', 0)
        open_shorts = summary.get('open_short_positions_count', 0)
        
        current_price = position_manager.get_current_price_for_exit() or 0.0
        unrealized_pnl = position_manager.get_unrealized_pnl(current_price)
        realized_pnl = summary.get('total_realized_pnl_session', 0.0)
        total_pnl_estimated = realized_pnl + unrealized_pnl
        initial_capital = summary.get('initial_total_capital', 0.0)
        roi_estimated_pct = (total_pnl_estimated / initial_capital * 100) if initial_capital > 0 else 0.0

        footer_text = "[s] Estado | [m] Modo | [r] Riesgo | [c] Capital | [p] Posiciones | [a] Auto | [l] Logs | [q] Salir"
        title = (
            f"Asistente de Trading Interactivo\n"
            f"----------------------------------------\n"
            f"Modo Actual: {manual_state.get('mode', 'N/A')}\n"
            f"Posiciones Abiertas -> LONG: {open_longs} | SHORT: {open_shorts}\n"
            f"PNL Sesión (Est.): {total_pnl_estimated:+.2f} USDT ({roi_estimated_pct:+.2f}%)\n"
            f"----------------------------------------\n"
            f"{footer_text}"
        )

        # --- CORRECCIÓN CLAVE ---
        # Las acciones del menú ahora llaman a las funciones a través del paquete `screens`.
        menu_items = [
            (" [s] Ver Estado Detallado", screens.show_status_screen),
            (" [m] Cambiar Modo de Trading", screens.show_mode_menu),
            (" [r] Ajustar Parámetros de Riesgo", screens.show_risk_menu),
            (" [c] Ajustar Capital", screens.show_capital_menu),
            (" [p] Gestionar Posiciones Abiertas", screens.show_positions_menu),
            None,
            (" [a] Automatización y Triggers", screens.show_automation_menu),
            None,
            (" [l] Visor de Logs", "VIEW_LOGS"),
            (" [q] Salir del Menú", "EXIT_TUI")
        ]

        terminal_menu = TerminalMenu(
            [item[0] if item else None for item in menu_items],
            title=title,
            **MENU_STYLE,
        )
        
        selected_index = terminal_menu.show()
        
        if selected_index is None:
            continue

        selected_action = menu_items[selected_index][1]

        if selected_action == "EXIT_TUI":
            break
        elif selected_action == "VIEW_LOGS":
            current_view = "LOGS"
        elif callable(selected_action):
            selected_action()