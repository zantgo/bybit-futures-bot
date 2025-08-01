# core/menu/screens/_dashboard.py

"""
Módulo para la Pantalla del Dashboard de Sesión.

v7.1 (Dashboard Enriquecido):
- La pantalla ahora muestra el estado de las operaciones LONG/SHORT, la última
  señal de bajo nivel, y la fecha/hora de inicio de la sesión.
- Se ha simplificado la vista eliminando parámetros de configuración estáticos.
- Al finalizar, se muestra un resumen completo de la sesión.

v7.0 (Arquitectura de Controladores):
- Esta pantalla ha sido reescrita para actuar como la "Vista" del SessionManager.
- Recibe una instancia del SessionManager y obtiene todos los datos a través de él.
- Controla el ciclo de vida de una única sesión de trading.
"""
import time
import datetime
from datetime import timezone
from typing import Dict, Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen,
    print_tui_header,
    press_enter_to_continue # <-- AÑADIDO
)
from .. import _helpers as helpers_module
from . import _log_viewer, operation_manager, _position_viewer

try:
    from core.exchange._models import StandardBalance
    from core.strategy.sm import api as sm_api
    from core.strategy.pm import api as pm_api # Aún necesario para el visor de posiciones
except ImportError:
    StandardBalance = sm_api = pm_api = None


# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- INICIO DE LA MODIFICACIÓN: Función para el resumen final ---
def _display_final_summary(summary: Dict[str, Any]):
    """Muestra una pantalla de resumen clara al finalizar la sesión."""
    clear_screen()
    print_tui_header("Resumen Final de la Sesión")

    if not summary or summary.get('error'):
        print("\nNo se pudo generar el resumen final.")
        press_enter_to_continue()
        return

    # Extraer datos clave
    realized_pnl = summary.get('total_realized_pnl_session', 0.0)
    initial_capital = summary.get('initial_total_capital', 0.0)
    final_roi = (realized_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
    start_time = pm_api.get_session_start_time()
    duration_str = "N/A"
    if start_time:
        duration = datetime.datetime.now(timezone.utc) - start_time
        duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))

    # Imprimir resumen
    print("\n--- Rendimiento General ---")
    print(f"  PNL Realizado Total: {realized_pnl:+.4f} USDT")
    print(f"  ROI Final (Realizado): {final_roi:+.2f}%")
    print(f"  Duración Total: {duration_str}")

    # Mostrar posiciones que quedaron abiertas
    open_longs = summary.get('open_long_positions', [])
    open_shorts = summary.get('open_short_positions', [])
    
    if open_longs or open_shorts:
        print("\n--- Posiciones que Quedaron Abiertas ---")
        if open_longs:
            print(f"  LONGs ({len(open_longs)}):")
            for pos in open_longs:
                print(f"    - ID: {pos.get('id', 'N/A')}, Entrada: {pos.get('entry_price', 0.0):.4f}, Tamaño: {pos.get('size_contracts', 0.0):.4f}")
        if open_shorts:
            print(f"  SHORTs ({len(open_shorts)}):")
            for pos in open_shorts:
                print(f"    - ID: {pos.get('id', 'N/A')}, Entrada: {pos.get('entry_price', 0.0):.4f}, Tamaño: {pos.get('size_contracts', 0.0):.4f}")
    else:
        print("\n--- No quedaron posiciones abiertas ---")

    press_enter_to_continue()
# --- FIN DE LA MODIFICACIÓN ---

# --- Lógica Principal de la Pantalla ---
def show_dashboard_screen(session_manager: Any):
    from ._session_config_editor import show_session_config_editor_screen

    """
    Muestra el dashboard y gestiona el ciclo de vida de la sesión de trading.

    Args:
        session_manager: La instancia activa del SessionManager para esta sesión.
    """
    config_module = _deps.get("config_module")
    if not TerminalMenu or not config_module or not sm_api or not session_manager:
        print("ERROR CRÍTICO: Dependencias del Dashboard no disponibles.")
        time.sleep(3)
        return

    # Inyectar la instancia de la sesión en la API para que sea accesible globalmente
    sm_api.init_sm_api(session_manager)

    # --- INICIO DE LA SESIÓN ---
    session_manager.start()

    clear_screen()
    print("Dashboard: Esperando la recepción del primer tick de precio del mercado...")
    
    wait_animation = ['|', '/', '-', '\\']
    i = 0
    # Esperar a que el ticker (iniciado por la sesión) proporcione el primer precio
    while True:
        # El PM API todavía puede darnos el precio actual rápidamente
        current_price = pm_api.get_current_market_price()
        if current_price and current_price > 0:
            print("\n¡Precio recibido! Cargando dashboard...")
            time.sleep(1.5)
            break
        
        print(f"\rEsperando... {wait_animation[i % len(wait_animation)]}", end="")
        i += 1
        time.sleep(0.2)

    # --- BUCLE PRINCIPAL DEL DASHBOARD (CICLO DE VIDA DE LA SESIÓN) ---
    while True:
        error_message = None
        summary = {}
        try:
            # La única fuente de verdad para el dashboard ahora es el SessionManager
            summary = sm_api.get_session_summary()
            
            if not summary or summary.get('error'):
                error_message = f"ADVERTENCIA: No se pudo obtener el estado de la sesión: {summary.get('error', 'Reintentando...')}"
            
            # Extraer datos del resumen para la visualización
            current_price = summary.get('current_market_price', 0.0)
            realized_pnl = summary.get('total_realized_pnl_session', 0.0)
            unrealized_pnl = pm_api.get_unrealized_pnl(current_price) # El cálculo de PNL no realizado sigue siendo útil
            total_pnl = realized_pnl + unrealized_pnl
            initial_capital = summary.get('initial_total_capital', 0.0)
            current_roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
            
            session_start_time = pm_api.get_session_start_time() # PM aún gestiona el inicio de su parte
            # --- INICIO DE LA MODIFICACIÓN: Formato de fecha/hora de inicio y duración ---
            start_time_str = "N/A"
            duration_str = "00:00:00"
            if session_start_time:
                start_time_str = session_start_time.strftime('%Y-%m-%d %H:%M:%S (UTC)')
                duration_seconds = (datetime.datetime.now(timezone.utc) - session_start_time).total_seconds()
                duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))
            # --- FIN DE LA MODIFICACIÓN ---
            
            ticker_symbol = getattr(config_module, 'TICKER_SYMBOL', 'N/A')
            
            # --- INICIO DE LA MODIFICACIÓN: Extraer nuevos datos del resumen ---
            op_infos = summary.get('operations_info', {})
            long_op_info = op_infos.get('long', {})
            short_op_info = op_infos.get('short', {})
            long_op_status = f"LONG: {long_op_info.get('estado', 'N/A')}"
            short_op_status = f"SHORT: {short_op_info.get('estado', 'N/A')}"
            
            latest_signal_info = summary.get('latest_signal', {})
            signal_str = latest_signal_info.get('signal', 'N/A')
            signal_reason = latest_signal_info.get('signal_reason', '')
            # --- FIN DE LA MODIFICACIÓN ---

            real_balances = summary.get('real_account_balances', {})

        except Exception as e:
            error_message = f"ERROR CRÍTICO: Excepción inesperada en el dashboard: {e}"
            current_price = 0.0 # Asegurar que las variables existan
        
        clear_screen()
        
        if error_message:
            print(f"\033[91m{error_message}\033[0m")
        
        # --- INICIO DE LA MODIFICACIÓN: Cabecera simplificada ---
        header_title = f"Dashboard Sesión: {ticker_symbol} @ {current_price:.4f} USDT"
        print_tui_header(header_title)
        
        # --- RENDERIZADO DE LA PANTALLA ---
        print("\n--- Estado de la Sesión en Tiempo Real " + "-"*40)
        
        # Panel de Rendimiento
        print(f"  Inicio Sesión: {start_time_str}  |  Duración: {duration_str}")
        print(f"  PNL Total: {total_pnl:+.4f} USDT  |  ROI Sesión: {current_roi:+.2f}%")
        
        # Panel de Operaciones y Señal
        print(f"\n  Operaciones: [{long_op_status}] | [{short_op_status}]")
        print(f"  Última Señal: {signal_str} ({signal_reason})")

        # Panel de Posiciones
        longs_count = summary.get('open_long_positions_count', 0)
        shorts_count = summary.get('open_short_positions_count', 0)
        print(f"  Posiciones Abiertas: LONGs: {longs_count} | SHORTs: {shorts_count}")
        # --- FIN DE LA MODIFICACIÓN ---
        
        print("\n--- Balances de Cuentas Reales " + "-"*50)
        if not real_balances: print("  (No hay datos de balance disponibles)")
        else:
            for acc_name, balance_info in real_balances.items():
                if isinstance(balance_info, StandardBalance): print(f"  {acc_name.upper():<15}: Equity: {balance_info.total_equity_usd:9.2f}$")
                else: print(f"  {acc_name.upper():<15}: ({str(balance_info)})")
        
        # --- MENÚ DE ACCIONES ---
        menu_items = [
            "[1] Gestionar Operación Activa", 
            "[2] Ver/Gestionar Posiciones",
            "[3] Editar Configuración de Sesión", 
            "[4] Ver Logs en Tiempo Real",
            None,
            "[h] Ayuda", 
            "[q] Finalizar Sesión y Volver al Menú Principal"
        ]
        action_map = {0: 'manage_operation', 1: 'manage_positions', 2: 'edit_config', 3: 'view_logs', 5: 'help', 6: 'exit_session'}
        
        menu_options = helpers_module.MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu_options['menu_cursor_style'] = ("fg_cyan", "bold")

        menu = TerminalMenu(menu_items, title="\nAcciones de la Sesión:", **menu_options)
        choice = menu.show()
        action = action_map.get(choice)
        
        if action == 'manage_operation': 
            operation_manager.show_operation_manager_screen()
        elif action == 'manage_positions':
            _position_viewer.show_position_viewer_screen(pm_api)
        elif action == 'edit_config':
            # La variable debe llamarse como la función importada para poder llamarla
            changes_saved = show_session_config_editor_screen(config_module)
            if changes_saved:
                # Si se guardaron cambios, los notificamos al SessionManager para que los aplique
                # Esta es una simplificación; idealmente, el editor devolvería los cambios.
                sm_api.update_session_parameters({}) # Dispara una re-evaluación
        elif action == 'view_logs': 
            _log_viewer.show_log_viewer()
        elif action == 'help': 
            helpers_module.show_help_popup("dashboard_main")
        elif action == 'exit_session' or choice is None:
            confirm_menu = TerminalMenu(["[1] Sí, finalizar sesión", "[2] No, continuar"], title="¿Confirmas finalizar la sesión actual?", **helpers_module.MENU_STYLE)
            if confirm_menu.show() == 0: 
                break # Rompe el bucle del dashboard, devolviendo el control a la pantalla de bienvenida
    
    # --- INICIO DE LA MODIFICACIÓN: Lógica de final de sesión ---
    # Al salir del bucle, obtenemos el resumen final y lo mostramos.
    final_summary_data = sm_api.get_session_summary()
    _display_final_summary(final_summary_data)
    
    # Detener el ticker después de mostrar el resumen
    # (Ya estaba siendo detenido por el shutdown_session_backend, pero es más explícito aquí)
    if session_manager.is_running():
        session_manager.stop()
    
    # Informar a la lógica de backend para que haga su propia limpieza
    from runner import shutdown_session_backend
    shutdown_session_backend(
        session_manager=session_manager,
        final_summary=final_summary_data, # Pasamos el resumen para logging
        config_module=_deps.get("config_module"),
        open_snapshot_logger_module=_deps.get("open_snapshot_logger_module")
    )
    # --- FIN DE LA MODIFICACIÓN ---