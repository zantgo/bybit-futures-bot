"""
Módulo para la Pantalla de Bienvenida y Configuración Inicial.

v3.1 (Manejo de Cancelación por Excepción):
- Se actualiza la importación de `_helpers` para usar la nueva excepción
  `UserInputCancelled`.
- La función `_run_position_test` ahora maneja la cancelación del usuario
  a través de un bloque try-except, haciéndola más robusta.
"""
# (COMENTARIO) Docstring de la versión anterior (v3.0) para referencia:
# """
# Módulo para la Pantalla de Bienvenida y Configuración Inicial.
# 
# v3.0 (Refactor de Contexto):
# - Se separa la configuración en "General" (pre-sesión) y "Sesión" (en-vivo).
# - Este menú ahora llama al editor en modo 'general'.
# """
from typing import Dict, Any, Tuple
import time

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Menú ---
# --- INICIO DE LA MODIFICACIÓN: Importación corregida ---
from .._helpers import (
    clear_screen, print_tui_header, MENU_STYLE, 
    press_enter_to_continue, get_input, UserInputCancelled
)
# (COMENTARIO) Importación anterior para referencia histórica.
# from .._helpers import clear_screen, print_tui_header, MENU_STYLE, press_enter_to_continue, get_input, CancelInput
# --- FIN DE LA MODIFICACIÓN ---
from ._config_editor import show_config_editor_screen
from . import _log_viewer
# --- INICIO: Nuevas importaciones para las nuevas funcionalidades ---
from connection import manager as connection_manager
from core import api as live_operations
from core.exchange._bybit_adapter import BybitAdapter
# --- FIN: Nuevas importaciones ---
import config
# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- Funciones de Ayuda para la Pantalla (sin cambios) ---

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
            print(f"  - Cuenta '{account_name}': {float(equity):.4f} USD")
        else:
            print(f"  - Cuenta '{account_name}': No se pudo obtener el balance.")

def _run_transfer_test() -> Tuple[bool, str]:
    """Orquesta la prueba de transferencia utilizando una instancia del BybitAdapter."""
    adapter = BybitAdapter()
    adapter.initialize(symbol="TEST")
    test_amount = 0.001
    accounts_to_test = ["longs", "shorts"]
    profit_account = "profit"
    
    for source_purpose in accounts_to_test:
        print(f"  -> Probando: {source_purpose} -> {profit_account} ({test_amount} USDT)... ", end="", flush=True)
        if not adapter.transfer_funds(test_amount, from_purpose=source_purpose, to_purpose=profit_account):
            print("FALLO.")
            return False, f"Fallo en la transferencia de '{source_purpose}' a '{profit_account}'. Revisa los logs."
        print("ÉXITO.")
        time.sleep(1)

    return True, "Prueba de transferencias completada con éxito."

def _run_position_test(config_module: Any) -> Tuple[bool, str]:
    """Orquesta la prueba completa de apertura y cierre de posiciones."""
    print("\n--- Asistente de Prueba de Trading ---")
    
    # --- INICIO DE LA MODIFICACIÓN: Envolver en try-except ---
    try:
        # 1. Obtener parámetros del usuario
        ticker = get_input("Introduce el Ticker a probar", str, getattr(config_module, 'TICKER_SYMBOL', 'BTCUSDT'))
        ticker = ticker.upper()

        size_usdt = get_input("Introduce el tamaño de la posición en USDT", float, 1.0, min_val=0.5)

        leverage = get_input("Introduce el apalancamiento a usar", float, 10.0, min_val=1.0)
    
    except UserInputCancelled:
        return False, "Prueba cancelada por el usuario."
    # --- FIN DE LA MODIFICACIÓN ---
    
    # 2. Obtener precio actual (necesario para calcular la cantidad de la orden)
    print(f"\nObteniendo precio de mercado para {ticker}... ", end="", flush=True)
    adapter = BybitAdapter()
    adapter.initialize(symbol=ticker)
    ticker_info = adapter.get_ticker(ticker)
    if not ticker_info or not ticker_info.price > 0:
        print("FALLO.")
        return False, f"No se pudo obtener un precio válido para {ticker}."
    current_price = ticker_info.price
    print(f"ÉXITO. Precio actual: {current_price:.4f} USD")
    
    qty_to_trade = (size_usdt * leverage) / current_price

    # 3. Ejecutar la secuencia de trading en un bloque try/finally para seguridad
    try:
        # --- PASO A: Establecer Apalancamiento ---
        print("\nEstableciendo apalancamiento en las cuentas de trading...")
        if not live_operations.set_leverage(symbol=ticker, buy_leverage=str(leverage), sell_leverage=str(leverage)):
            return False, "Fallo al establecer el apalancamiento. Revisa los permisos de la API."
        print("  -> Apalancamiento establecido con éxito.")
        time.sleep(1)

        # --- PASO B: Abrir Posición LONG ---
        print(f"Abriendo posición LONG en la cuenta '{config.ACCOUNT_LONGS}'...")
        long_res = live_operations.place_market_order(symbol=ticker, side="Buy", quantity=qty_to_trade, account_name=config.ACCOUNT_LONGS)
        if not long_res or long_res.get('retCode') != 0:
            return False, f"Fallo al abrir LONG. Razón: {long_res.get('retMsg', 'Error desconocido') if long_res else 'Sin respuesta'}"
        print(f"  -> Posición LONG abierta con éxito. OrderID: {long_res.get('result', {}).get('orderId')}")
        time.sleep(1)

        # --- PASO C: Abrir Posición SHORT ---
        print(f"Abriendo posición SHORT en la cuenta '{config.ACCOUNT_SHORTS}'...")
        short_res = live_operations.place_market_order(symbol=ticker, side="Sell", quantity=qty_to_trade, account_name=config.ACCOUNT_SHORTS)
        if not short_res or short_res.get('retCode') != 0:
            return False, f"Fallo al abrir SHORT. Razón: {short_res.get('retMsg', 'Error desconocido') if short_res else 'Sin respuesta'}"
        print(f"  -> Posición SHORT abierta con éxito. OrderID: {short_res.get('result', {}).get('orderId')}")
        time.sleep(2)

    finally:
        # --- PASO DE SEGURIDAD: Limpieza Final ---
        print("\n--- Fase de Limpieza (Cierre de todas las posiciones de prueba) ---")
        print(f"Cerrando cualquier posición de {ticker} en la cuenta '{config.ACCOUNT_LONGS}'...")
        live_operations.close_all_symbol_positions(symbol=ticker, account_name=config.ACCOUNT_LONGS)
        
        print(f"Cerrando cualquier posición de {ticker} en la cuenta '{config.ACCOUNT_SHORTS}'...")
        live_operations.close_all_symbol_positions(symbol=ticker, account_name=config.ACCOUNT_SHORTS)
        print("Limpieza completada.")

    return True, f"Prueba de trading completada con éxito para el ticker {ticker}."

# --- Lógica Principal de la Pantalla ---

def show_welcome_screen() -> bool:
    """Muestra la pantalla de bienvenida con opciones para iniciar, configurar o probar."""
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

        menu_items = [
            "[1] Iniciar Bot con esta configuración",
            "[2] Modificar configuración general del bot",
            "[3] Probar Transferencias entre Subcuentas",
            "[4] Probar Apertura/Cierre de Posiciones",
            "[5] Ver Logs de la Sesión",
            None,
            "[6] Salir"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        
        terminal_menu = TerminalMenu(menu_items, title="\n¿Qué deseas hacer?", **menu_options)
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            return True
        
        elif choice_index == 1:
            show_config_editor_screen(config_module, context='general')
            continue
            
        elif choice_index == 2:
            print("\n" + "-"*50)
            print("INICIANDO PRUEBA DE TRANSFERENCIAS...")
            success, message = _run_transfer_test()
            print("-" * 50)
            print(f"Resultado: {message}")
            if success: print("\n-> Los UIDs y permisos de transferencia son CORRECTOS.")
            else: print("\n-> ¡ERROR! Revisa los UIDs, permisos y logs.")
            press_enter_to_continue()
            continue

        elif choice_index == 3:
            success, message = _run_position_test(config_module)
            print("\n" + "="*50)
            print("RESULTADO FINAL DE LA PRUEBA DE TRADING")
            print(f"Estado: {'ÉXITO' if success else 'FALLO'}")
            print(f"Mensaje: {message}")
            print("="*50)
            press_enter_to_continue()
            continue
            
        elif choice_index == 4:
            _log_viewer.show_log_viewer()
            continue

        elif choice_index == 6 or choice_index is None:
            return False