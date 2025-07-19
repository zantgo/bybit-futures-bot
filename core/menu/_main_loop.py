# =============== INICIO ARCHIVO: core/menu/_main_loop.py (CORREGIDO FINAL V2) ===============
"""
Módulo del Bucle Principal de la TUI (Terminal User Interface).

Contiene la función `run_tui_menu_loop`, que es el centro de navegación
principal del asistente interactivo en vivo. Desde aquí, el usuario puede
acceder a todas las pantallas de monitorización y gestión del bot.
"""
from typing import Optional

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Proyecto ---
try:
    from core.strategy import pm_facade as position_manager
    # --- INICIO MODIFICACIÓN: Eliminar add_menu_footer de la importación ---
    from ._helpers import MENU_STYLE
    from ._screens import (
        show_status_screen,
        show_mode_menu,
        show_risk_menu,
        show_capital_menu,
        show_positions_menu,
        show_log_viewer
    )
    # --- FIN MODIFICACIÓN ---
except ImportError as e:
    # Definir fallbacks si las importaciones fallan
    print(f"ERROR [TUI Main Loop]: Falló importación de dependencias: {e}")
    position_manager = None
    MENU_STYLE = {}
    # Crear funciones dummy para evitar errores en tiempo de ejecución
    def show_status_screen(): print("Función no disponible.")
    def show_mode_menu(): print("Función no disponible.")
    def show_risk_menu(): print("Función no disponible.")
    def show_capital_menu(): print("Función no disponible.")
    def show_positions_menu(): print("Función no disponible.")
    def show_log_viewer(): print("Función no disponible.")

def run_tui_menu_loop():
    """
    Ejecuta el bucle del menú interactivo principal de intervención en vivo.
    Esta función es bloqueante y mantiene al usuario dentro de la TUI hasta que
    decide salir.
    """
    if not TerminalMenu or not position_manager:
        print("ERROR CRITICO: TUI no puede funcionar sin 'simple-term-menu' o sin el Position Manager.")
        return

    while True:
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

        # --- INICIO MODIFICACIÓN: Integrar el pie de página en el título ---
        footer_text = "[s] Estado | [m] Modo | [p] Posiciones | [l] Logs | [q] Salir"
        title = (
            f"Asistente de Trading Interactivo\n"
            f"----------------------------------------\n"
            f"Modo Actual: {manual_state.get('mode', 'N/A')}\n"
            f"Posiciones Abiertas -> LONG: {open_longs} | SHORT: {open_shorts}\n"
            f"PNL Sesión (Est.): {total_pnl_estimated:+.2f} USDT ({roi_estimated_pct:+.2f}%)\n"
            f"----------------------------------------\n"
            f"{footer_text}"
        )
        # --- FIN MODIFICACIÓN ---

        menu_items = [
            (" [s] Ver Estado Detallado de la Sesión", show_status_screen),
            (" [m] Cambiar Modo de Trading", show_mode_menu),
            (" [r] Ajustar Parámetros de Riesgo", show_risk_menu),
            (" [c] Ajustar Capital (Slots / Tamaño)", show_capital_menu),
            (" [p] Gestionar Posiciones Abiertas", show_positions_menu),
            None,
            (" [l] Visor de Logs", show_log_viewer),
            (" [q] Salir del Menú (el bot sigue corriendo)", None)
        ]

        terminal_menu = TerminalMenu(
            [item[0] if item else None for item in menu_items],
            title=title,
            **MENU_STYLE
        )
        
        selected_index = terminal_menu.show()

        if selected_index is None or menu_items[selected_index][1] is None:
            break
        
        action_function = menu_items[selected_index][1]
        action_function()

# =============== FIN ARCHIVO: core/menu/_main_loop.py (CORREGIDO FINAL V2) ===============