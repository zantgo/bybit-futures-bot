"""
Módulo para la Pantalla de Bienvenida (Vista del BotController).

v4.1 (Menú de Diagnóstico):
- Esta pantalla ya no inicializa las conexiones automáticamente al arrancar.
- Se ha rediseñado el menú principal para incluir opciones explícitas de
  diagnóstico y prueba que el usuario puede ejecutar bajo demanda.
- El inicio de una sesión ahora comprueba si las conexiones han sido
  previamente validadas.
"""
from typing import Dict, Any

import time

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen, print_tui_header, MENU_STYLE,
    press_enter_to_continue
)
from ._config_editor import show_config_editor_screen
from . import _log_viewer, _dashboard

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies


# --- Funciones de Ayuda para la Pantalla ---

def _run_connection_test(bot_controller: Any):
    """Orquesta la prueba de conexión y muestra los balances."""
    clear_screen()
    print_tui_header("Prueba de Conexión y Balances")
    print("\nValidando conexiones API...")
    
    success, message = bot_controller.initialize_connections()
    print(f"-> Resultado: {message}")

    if success:
        print("\nObteniendo balances de las cuentas...")
        balances = bot_controller.get_balances()
        if balances:
            for acc_name, balance_info in balances.items():
                if balance_info:
                    equity = balance_info.get('totalEquity', 0.0)
                    print(f"  - Cuenta '{acc_name}': {float(equity):.4f} USD")
                else:
                    print(f"  - Cuenta '{acc_name}': No se pudo obtener el balance.")
        else:
            print("  -> No se pudieron obtener los balances.")
    
    press_enter_to_continue()

def _run_transfer_test(bot_controller: Any):
    """Orquesta la prueba de transferencias."""
    clear_screen()
    print_tui_header("Prueba de Transferencias entre Cuentas")
    
    if not bot_controller.are_connections_initialized():
        print("\nERROR: Las conexiones API deben ser probadas y validadas primero.")
        print("Por favor, usa la opción 'Probar Conexión y Ver Balances' antes de continuar.")
        press_enter_to_continue()
        return

    print("\nIniciando secuencia de prueba de transferencias...")
    success, message = bot_controller.run_transfer_test()
    print("\n" + "-"*50)
    print(f"Resultado: {message}")
    if success:
        print("\n-> Los UIDs, permisos y la lógica de transferencia son CORRECTOS.")
    else:
        print("\n-> ¡ERROR! Revisa los UIDs, permisos y logs para más detalles.")
    press_enter_to_continue()

def _run_position_test(bot_controller: Any):
    """Orquesta la prueba de apertura y cierre de posiciones."""
    clear_screen()
    print_tui_header("Asistente de Prueba de Trading")

    if not bot_controller.are_connections_initialized():
        print("\nERROR: Las conexiones API deben ser probadas y validadas primero.")
        print("Por favor, usa la opción 'Probar Conexión y Ver Balances' antes de continuar.")
        press_enter_to_continue()
        return

    success, message = bot_controller.run_position_test()
    print("\n" + "="*50)
    print("RESULTADO FINAL DE LA PRUEBA DE TRADING")
    print(f"Estado: {'ÉXITO' if success else 'FALLO'}")
    print(f"Mensaje: {message}")
    print("="*50)
    press_enter_to_continue()


# --- Lógica Principal de la Pantalla ---

def show_welcome_screen(bot_controller: Any):
    """
    Muestra la pantalla de bienvenida y gestiona el ciclo de vida de la aplicación.
    """
    config_module = _deps.get("config_module")
    if not TerminalMenu or not config_module:
        print("ERROR CRÍTICO: Dependencias no disponibles.")
        time.sleep(3)
        return

    while True:
        clear_screen()
        print_tui_header("Menú Principal del Bot")
        
        general_config = bot_controller.get_general_config()
        connections_ready = bot_controller.are_connections_initialized()
        status_color = "\033[92m" if connections_ready else "\033[93m"
        status_text = "CONECTADO Y VALIDADO" if connections_ready else "NO CONECTADO"
        
        print(f"\nEstado de Conexión: {status_color}{status_text}\033[0m")
        print("Configuración General de la Aplicación:")
        for key, value in general_config.items():
            print(f"  - {key}: {value}")

        menu_items = [
            "[1] Iniciar Nueva Sesión de Trading",
            None,
            "[2] Probar Conexión y Ver Balances",
            "[3] Probar Transferencias entre Cuentas",
            "[4] Probar Apertura/Cierre de Posiciones",
            None,
            "[5] Modificar Configuración General",
            "[6] Ver Logs de la Aplicación",
            None,
            "[7] Salir del Bot"
        ]
        
        action_map = {
            0: 'start_session', 2: 'test_connection', 3: 'test_transfers',
            4: 'test_positions', 6: 'edit_config', 7: 'view_logs', 9: 'exit'
        }
        
        terminal_menu = TerminalMenu(menu_items, title="\nAcciones:", **MENU_STYLE)
        choice = action_map.get(terminal_menu.show())
        
        if choice == 'start_session':
            if not bot_controller.are_connections_initialized():
                print("\nERROR: Debes probar la conexión antes de iniciar una sesión.")
                press_enter_to_continue()
                continue
            
            print("\nCreando nueva sesión de trading...")
            session_manager = bot_controller.create_session()
            if session_manager:
                print("Sesión creada con éxito. Lanzando dashboard...")
                time.sleep(1.5)
                _dashboard.show_dashboard_screen(session_manager)
                print("Sesión finalizada. Volviendo al menú principal...")
                session_manager.stop()
                time.sleep(2)
            else:
                print("\nERROR: No se pudo crear la sesión. Revisa los logs.")
                press_enter_to_continue()
        
        elif choice == 'test_connection':
            _run_connection_test(bot_controller)
        
        elif choice == 'test_transfers':
            _run_transfer_test(bot_controller)
            
        elif choice == 'test_positions':
            _run_position_test(bot_controller)

        elif choice == 'edit_config':
            show_config_editor_screen(config_module, context='general')
            
        elif choice == 'view_logs':
            _log_viewer.show_log_viewer()

        elif choice == 'exit' or choice is None:
            confirm_menu = TerminalMenu(["[1] Sí, apagar el bot", "[2] No, continuar"], title="¿Confirmas apagar el bot?", **MENU_STYLE)
            if confirm_menu.show() == 0:
                print("\nIniciando apagado ordenado...")
                bot_controller.shutdown_bot()
                print("Apagado completado. ¡Hasta luego!")
                time.sleep(1)
                break