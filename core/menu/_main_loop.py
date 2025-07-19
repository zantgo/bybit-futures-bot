# =============== INICIO ARCHIVO: core/menu/_main_loop.py (MODIFICADO) ===============
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
    from ._helpers import MENU_STYLE
    # Importamos el módulo de screens completo para evitar ciclos de importación
    # y poder llamar a las funciones de pantalla de forma segura.
    from . import _screens 
except ImportError as e:
    # Definir fallbacks si las importaciones fallan
    print(f"ERROR [TUI Main Loop]: Falló importación de dependencias: {e}")
    position_manager = None
    MENU_STYLE = {}
    # Crear un objeto dummy para _screens
    class ScreensFallback:
        def show_status_screen(self): print("Función no disponible.")
        def show_mode_menu(self): print("Función no disponible.")
        def show_risk_menu(self): print("Función no disponible.")
        def show_capital_menu(self): print("Función no disponible.")
        def show_positions_menu(self): print("Función no disponible.")
        def show_log_viewer(self): print("Función no disponible.")
    _screens = ScreensFallback()


def run_tui_menu_loop():
    """
    Ejecuta el bucle del menú interactivo principal.
    Ahora alterna entre la vista del menú y el visor de logs, garantizando
    una interfaz limpia.
    """
    if not TerminalMenu or not position_manager:
        print("ERROR CRITICO: TUI no puede funcionar sin 'simple-term-menu' o sin el Position Manager.")
        return

    # --- Bucle principal que maneja los modos de vista ---
    current_view = "MENU" # Puede ser "MENU" o "LOGS"

    while True:
        if current_view == "LOGS":
            # Si estamos en la vista de logs, cedemos el control a la pantalla del visor de logs.
            # Esta función tendrá su propio bucle interno y se encargará de limpiar la pantalla.
            _screens.show_log_viewer() 
            
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

        menu_items = [
            (" [s] Ver Estado Detallado", _screens.show_status_screen),
            (" [m] Cambiar Modo de Trading", _screens.show_mode_menu),
            (" [r] Ajustar Parámetros de Riesgo", _screens.show_risk_menu),
            (" [c] Ajustar Capital", _screens.show_capital_menu),
            (" [p] Gestionar Posiciones Abiertas", _screens.show_positions_menu),
            None,
            (" [l] Visor de Logs", "VIEW_LOGS"), # Usamos un string como señal para cambiar de vista
            (" [q] Salir del Menú", "EXIT_TUI")
        ]

        # --- INICIO MODIFICACIÓN: Comentar 'shortcuts' para compatibilidad con versiones antiguas ---
        # El parámetro 'shortcuts' causa un error si la versión de simple-term-menu es antigua.
        # Se comenta para asegurar la compatibilidad. La solución ideal es actualizar la librería.
        terminal_menu = TerminalMenu(
            [item[0] if item else None for item in menu_items],
            title=title,
            **MENU_STYLE,
            # # Añadimos atajos de teclado para una navegación más rápida
            # shortcuts={
            #     "s": 0, "m": 1, "r": 2, "c": 3, "p": 4, "l": 6, "q": 7
            # }
        )
        # --- FIN MODIFICACIÓN ---
        
        selected_index = terminal_menu.show()
        
        if selected_index is None: # El usuario presionó ESC
            continue # Simplemente redibujar el menú principal

        # Obtener la acción asociada al ítem seleccionado
        selected_action = menu_items[selected_index][1]

        if selected_action == "EXIT_TUI":
            break # Salir del bucle while y terminar la TUI
        elif selected_action == "VIEW_LOGS":
            current_view = "LOGS" # Cambiar al modo de vista de logs para el siguiente ciclo
        elif callable(selected_action):
            selected_action() # Llamar a la función de pantalla (ej: show_status_screen)

# =============== FIN ARCHIVO: core/menu/_main_loop.py (MODIFICADO) ===============