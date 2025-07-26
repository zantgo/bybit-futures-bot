"""
Módulo para la Pantalla de Bienvenida y Configuración Inicial.

v2.3: Añadida la funcionalidad de prueba de transferencias y visualización de balances.
"""
from typing import Dict, Any, Tuple
import time

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Menú ---
from .._helpers import clear_screen, print_tui_header, MENU_STYLE, press_enter_to_continue
from ._config_editor import show_config_editor_screen
# --- INICIO: Nuevas importaciones para la nueva funcionalidad ---
from connection import manager as connection_manager
from core import api as live_operations
from core.exchange._bybit_adapter import BybitAdapter
# --- FIN: Nuevas importaciones ---

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- Funciones de Ayuda para la Pantalla ---

def _display_balances(config_module: Any):
    """Obtiene y muestra los balances de todas las cuentas configuradas."""
    print("\nObteniendo balances actuales de las cuentas...")
    accounts_to_check = getattr(config_module, 'ACCOUNTS_TO_INITIALIZE', [])
    
    if not connection_manager.get_initialized_accounts():
        print("  -> Advertencia: Las conexiones API aún no están inicializadas.")
        return

    for account_name in accounts_to_check:
        balance_info = live_operations.get_unified_account_balance_info(account_name)
        if balance_info:
            equity = balance_info.get('totalEquity', 0.0)
            print(f"  - Cuenta '{account_name}': {equity:.4f} USD")
        else:
            print(f"  - Cuenta '{account_name}': No se pudo obtener el balance.")

def _run_transfer_test() -> Tuple[bool, str]:
    """
    Orquesta la prueba de transferencia utilizando una instancia del BybitAdapter.
    """
    # 1. Necesitamos una instancia del adaptador para usar su método transfer_funds
    adapter = BybitAdapter()
    
    # El adaptador necesita ser "inicializado" para cargar su mapa de cuentas.
    # No necesitamos un símbolo real para esto, ya que transfer_funds no lo usa.
    adapter.initialize(symbol="TEST")
    
    test_amount = 0.001
    
    # Lista de cuentas a probar
    accounts_to_test = ["longs", "shorts"]
    profit_account = "profit"
    
    for source_purpose in accounts_to_test:
        # --- Transferencia de Ida (Fuente -> Profit) ---
        print(f"  -> Probando: {source_purpose} -> {profit_account} ({test_amount} USDT)... ", end="", flush=True)
        success_fwd = adapter.transfer_funds(test_amount, from_purpose=source_purpose, to_purpose=profit_account)
        if not success_fwd:
            print("FALLO.")
            return False, f"Fallo en la transferencia de '{source_purpose}' a '{profit_account}'. Revisa los logs para más detalles."
        
        print("ÉXITO.")
        time.sleep(1)

        # --- Transferencia de Vuelta (Profit -> Fuente) ---
        print(f"  -> Devolviendo: {profit_account} -> {source_purpose} ({test_amount} USDT)... ", end="", flush=True)
        success_bwd = adapter.transfer_funds(test_amount, from_purpose=profit_account, to_purpose=source_purpose)
        if not success_bwd:
            print("FALLO.")
            return False, f"¡CRÍTICO! Fallo en la transferencia de retorno a '{source_purpose}'. Mueve {test_amount} USDT manualmente."
            
        print("ÉXITO.")
        time.sleep(1)

    return True, "Prueba de transferencias completada con éxito."

# --- Lógica Principal de la Pantalla ---

def show_welcome_screen() -> bool:
    """
    Muestra la pantalla de bienvenida con opciones para iniciar, configurar o probar transferencias.
    """
    config_module = _deps.get("config_module")
    if not TerminalMenu or not config_module:
        print("ERROR CRÍTICO: Dependencias (TerminalMenu o config) no disponibles.")
        time.sleep(3)
        return False

    while True:
        clear_screen()
        print_tui_header("Bienvenido al Asistente de Trading")
        print("\nConfiguración actual para la sesión:")
        
        if hasattr(config_module, 'print_initial_config'):
             config_module.print_initial_config("live_interactive")
        else:
            print("  (Error: No se pudo cargar la función de impresión de config)")

        _display_balances(config_module)

        menu_items = [
            "[1] Iniciar Bot con esta configuración",
            "[2] Modificar configuración para esta sesión",
            "[3] Probar Transferencias entre Subcuentas",
            None,
            "[4] Salir"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        
        terminal_menu = TerminalMenu(menu_items, title="\n¿Qué deseas hacer?", **menu_options)
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            return True
        
        elif choice_index == 1:
            show_config_editor_screen(config_module)
            continue
            
        elif choice_index == 2:
            print("\n" + "-"*50)
            print("INICIANDO PRUEBA DE TRANSFERENCIAS...")
            
            success, message = _run_transfer_test()
            
            print("-" * 50)
            print(f"Resultado: {message}")
            
            if success:
                print("\n-> Los UIDs y permisos de transferencia son CORRECTOS.")
            else:
                print("\n-> ¡ERROR! Revisa los UIDs en tu .env, los permisos de la API principal y los logs.")
            
            _display_balances(config_module)
            press_enter_to_continue()
            continue
            
        elif choice_index == 4 or choice_index is None:
            return False