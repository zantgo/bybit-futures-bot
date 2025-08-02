"""
Módulo para la Pantalla de Bienvenida (Vista del BotController).

v4.2 (UX Mejorada):
- La conexión y validación de la API ahora se ejecutan automáticamente al
  iniciar esta pantalla, mostrando los balances directamente.
- Se ha rediseñado la interfaz para mostrar un panel de estado persistente
  en la parte superior, con balances y configuración en columnas.
- El menú de acciones ahora aparece debajo del panel sin borrarlo.
"""

import time
from typing import Dict, Any
from . import _log_viewer, _dashboard

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen, print_tui_header, MENU_STYLE,
    press_enter_to_continue
)

_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- Funciones de Ayuda para la Pantalla ---

def _display_welcome_panel(bot_controller: Any):
    """Dibuja el panel superior con toda la información de estado."""
    print_tui_header("Bienvenido al Asistente de Trading")
    
    connections_ready = bot_controller.are_connections_initialized()
    status_color = "\033[92m" if connections_ready else "\033[91m"
    status_text = "CONECTADO Y VALIDADO" if connections_ready else "ERROR DE CONEXIÓN"
    print(f"\n Estado: {status_color}{status_text}\033[0m")

    # Obtener datos
    balances = bot_controller.get_balances() or {}
    general_config = bot_controller.get_general_config()

    # Preparar datos para las columnas
    balance_data = {
        name.upper(): f"{info.get('totalEquity', 0.0):.4f} USD"
        for name, info in balances.items() if info
    }

    is_paper_trading = general_config.get('Paper Trading', False)
    modo_trading_str = "Paper Trading" if is_paper_trading else "Live Trading"

    config_data = {
        "Exchange": general_config.get('Exchange', 'N/A').upper(),
        "Modo": modo_trading_str,
        "Testnet": "ON" if general_config.get('Modo Testnet', False) else "OFF",
        "Símbolo": general_config.get('Ticker Symbol', 'N/A')
    }

    # Lógica de impresión en columnas
    print("┌" + "─" * 38 + "┬" + "─" * 39 + "┐")
    print(f"│{'Balances de Cuentas':^38}│{'Configuración General':^39}│")
    print("├" + "─" * 38 + "┼" + "─" * 39 + "┤")

    # --- INICIO DE LA MODIFICACIÓN ---
    # Define el orden explícito para la visualización de las cuentas.
    account_order = ["MAIN", "LONGS", "SHORTS", "PROFIT"]
    # Construye la lista de claves de balance (b_keys) respetando el orden definido.
    # Se filtran solo las cuentas que existen en balance_data.
    b_keys = [acc for acc in account_order if acc in balance_data]
    
    # La lógica para las claves de configuración (c_keys) no cambia.
    c_keys = list(config_data.keys())
    # --- FIN DE LA MODIFICACIÓN ---

    num_rows = max(len(b_keys), len(c_keys))
    
    # Ajustar para encontrar el ancho máximo de las claves en ambas columnas
    max_b_key = max(len(k) for k in b_keys) if b_keys else 0
    max_c_key = max(len(k) for k in c_keys) if c_keys else 0

    for i in range(num_rows):
        left_col, right_col = "", ""
        if i < len(b_keys):
            key, value = b_keys[i], balance_data[b_keys[i]]
            left_col = f"  {key:<{max_b_key}} : {value}"
        if i < len(c_keys):
            key, value = c_keys[i], config_data[c_keys[i]]
            right_col = f"  {key:<{max_c_key}} : {value}"
        
        print(f"│{left_col:<38}│{right_col:<39}│")

    print("└" + "─" * 38 + "┴" + "─" * 39 + "┘")

def _run_transfer_test(bot_controller: Any):
    clear_screen()
    print_tui_header("Prueba de Transferencias entre Cuentas")
    print("\nIniciando secuencia de prueba...")
    success, message = bot_controller.run_transfer_test()
    print("\n" + "-"*50)
    print(f"Resultado: {message}")
    press_enter_to_continue()

def _run_position_test(bot_controller: Any):
    clear_screen()
    print_tui_header("Asistente de Prueba de Trading")
    success, message = bot_controller.run_position_test()
    print("\n" + "="*50)
    print("RESULTADO FINAL DE LA PRUEBA DE TRADING")
    print(f"Estado: {'ÉXITO' if success else 'FALLO'}")
    print(f"Mensaje: {message}")
    print("="*50)
    press_enter_to_continue()

# --- Lógica Principal de la Pantalla ---

def show_welcome_screen(bot_controller: Any):
    from ._general_config_editor import show_general_config_editor_screen
    from ._session_config_editor import show_session_config_editor_screen

    config_module = _deps.get("config_module")
    if not TerminalMenu or not config_module:
        print("ERROR CRÍTICO: Dependencias no disponibles."); time.sleep(1); return

    # --- PASO 1: CONEXIÓN AUTOMÁTICA (se ejecuta una sola vez) ---
    print("\nConectando y validando credenciales API...")
    success, message = bot_controller.initialize_connections()
    
    if not success:
        clear_screen()
        print_tui_header("Error Crítico de Conexión")
        print(f"\n-> {message}")
        print("\nEl bot no puede continuar. Revisa tu archivo .env, claves API y conexión.")
        press_enter_to_continue()
        bot_controller.shutdown_bot()
        return

    # --- PASO 2: BUCLE PRINCIPAL DEL MENÚ ---
    while True:
        clear_screen()
        _display_welcome_panel(bot_controller)
        
        menu_items = [
            "[1] Iniciar Sesión de Trading",
            None,
            "[2] Probar Transferencias entre Cuentas",
            "[3] Probar Apertura/Cierre de Posiciones",
            None,
            "[4] Configuración General",
            "[5] Configuración de la Sesión",
            "[6] Ver Logs de la Aplicación",
            None,
            "[7] Salir del Bot"
        ]
        
        action_map = {
            0: 'start_session', 2: 'test_transfers', 3: 'test_positions',
            5: 'edit_general_config', 6: 'edit_session_config', 7: 'view_logs', 9: 'exit'
        }
        
        welcome_menu_options = MENU_STYLE.copy()
        welcome_menu_options['clear_screen'] = False
        
        terminal_menu = TerminalMenu(menu_items, title="\nAcciones:", **welcome_menu_options)
        choice = action_map.get(terminal_menu.show())
        
        if choice == 'start_session':
            print("\nCreando nueva sesión de trading...")
            session_manager = bot_controller.create_session()
            if session_manager:
                print("Sesión creada con éxito. Lanzando dashboard...")
                time.sleep(2)
                _dashboard.show_dashboard_screen(session_manager)
                # session_manager.stop() # Comentado, el dashboard ya gestiona la parada
            else:
                print("\nERROR: No se pudo crear la sesión. Revisa los logs.")
                press_enter_to_continue()
        
        elif choice == 'test_transfers': _run_transfer_test(bot_controller)
        elif choice == 'test_positions': _run_position_test(bot_controller)
        elif choice == 'edit_general_config': show_general_config_editor_screen(config_module)
        elif choice == 'edit_session_config': show_session_config_editor_screen(config_module)
        elif choice == 'view_logs': _log_viewer.show_log_viewer()
        elif choice == 'exit' or choice is None:
            confirm_menu = TerminalMenu(["[1] Sí, apagar el bot", "[2] No, continuar"], title="\n¿Confirmas apagar el bot?", **MENU_STYLE)
            if confirm_menu.show() == 0:
                print("\nIniciando apagado ordenado...")
                bot_controller.shutdown_bot()
                print("Apagado completado. ¡Hasta luego!")
                time.sleep(1)
                break