"""
Módulo para la Pantalla del Dashboard de Sesión.

v8.1 (Refactor de Configuración):
- Adaptado para leer el `TICKER_SYMBOL` desde la nueva estructura de `config.py`.

v8.0 (Capital Lógico y Nuevo UI):
- La pantalla ha sido rediseñada completamente para mostrar el estado de la sesión
  y los balances lógicos de las operaciones LONG y SHORT de forma separada y clara.
- El menú de acciones ahora permite el acceso directo a la gestión de la operación
  LONG o SHORT, eliminando menús intermedios.
- Se añade una opción para refrescar la vista del dashboard en tiempo real.
- La opción "Ver/Gestionar Posiciones" se elimina del dashboard.
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
    press_enter_to_continue
)
from .. import _helpers as helpers_module
from . import _log_viewer, operation_manager
# --- INICIO DE LA MODIFICACIÓN --- (Mantenida desde tu código original)
# Se comenta la importación de _position_viewer ya que no se usará desde aquí.
# from . import _position_viewer
# --- FIN DE LA MODIFICACIÓN ---


try:
    # from core.exchange._models import StandardBalance # No se usa directamente aquí
    from core.strategy.sm import api as sm_api
    from core.strategy.pm import api as pm_api # Aún necesario para algunos datos como el start time
except ImportError:
    # StandardBalance = None # Comentado
    sm_api = pm_api = None


# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies


def _display_final_summary(summary: Dict[str, Any]):
    """Muestra una pantalla de resumen clara al finalizar la sesión."""
    clear_screen()
    print_tui_header("Resumen Final de la Sesión")

    if not summary or summary.get('error'):
        print("\nNo se pudo generar el resumen final.")
        press_enter_to_continue()
        return

    # --- INICIO DE LA MODIFICACIÓN --- (Mantenida desde tu código original)
    # Usar los nuevos datos agregados por el SessionManager
    realized_pnl = summary.get('total_session_pnl', 0.0)
    initial_capital = summary.get('total_session_initial_capital', 0.0)
    # --- FIN DE LA MODIFICACIÓN --- (Mantenida desde tu código original)
    final_roi = (realized_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
    start_time = pm_api.get_session_start_time()
    duration_str = "N/A"
    if start_time:
        duration = datetime.datetime.now(timezone.utc) - start_time
        duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))

    print("\n--- Rendimiento General ---")
    print(f"  PNL Realizado Total: {realized_pnl:+.4f} USDT")
    print(f"  ROI Final (Realizado): {final_roi:+.2f}%")
    print(f"  Duración Total: {duration_str}")

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


def _render_dashboard_view(summary: Dict[str, Any], config_module: Any):
    """Función dedicada a imprimir el layout completo del dashboard."""
    # --- 1. Extraer datos del resumen ---
    current_price = summary.get('current_market_price', 0.0)
    
    # Datos de sesión
    total_pnl = summary.get('total_session_pnl', 0.0)
    total_roi = summary.get('total_session_roi', 0.0)
    session_start_time = pm_api.get_session_start_time()
    
    start_time_str = "N/A"
    duration_str = "00:00:00"
    if session_start_time:
        start_time_str = session_start_time.strftime('%Y-%m-%d %H:%M:%S (UTC)')
        duration_seconds = (datetime.datetime.now(timezone.utc) - session_start_time).total_seconds()
        duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))

    # Datos de operaciones
    op_infos = summary.get('operations_info', {})
    long_op_info = op_infos.get('long', {})
    short_op_info = op_infos.get('short', {})
    long_op_status = f"LONG: {long_op_info.get('estado', 'N/A')}"
    short_op_status = f"SHORT: {short_op_info.get('estado', 'N/A')}"

    # Datos de señal
    latest_signal_info = summary.get('latest_signal', {})
    signal_str = latest_signal_info.get('signal', 'N/A')
    signal_reason = latest_signal_info.get('signal_reason', '')

    # Datos de posiciones
    longs_count = summary.get('open_long_positions_count', 0)
    shorts_count = summary.get('open_short_positions_count', 0)
    
    # Datos de balances lógicos
    logical_balances = summary.get('logical_balances', {})
    long_balance = logical_balances.get('long', {})
    short_balance = logical_balances.get('short', {})
    long_pnl = summary.get('operation_long_pnl', 0.0)
    short_pnl = summary.get('operation_short_pnl', 0.0)

    # --- 2. Renderizar la pantalla ---
    # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
    # --- (COMENTADO) ---
    # ticker_symbol = getattr(config_module, 'TICKER_SYMBOL', 'N/A')
    # --- (CORREGIDO) ---
    ticker_symbol = config_module.BOT_CONFIG["TICKER"]["SYMBOL"]
    # --- FIN DE LA MODIFICACIÓN ---
    header_title = f"Dashboard Sesión: {ticker_symbol} @ {current_price:.4f} USDT"
    print_tui_header(header_title)
    
    print("\n--- Estado de la Sesión en Tiempo Real " + "-"*40)
    print(f"  Inicio Sesión: {start_time_str}  |  Duración: {duration_str}")
    pnl_color = "\033[92m" if total_pnl >= 0 else "\033[91m"
    print(f"  PNL Total: {pnl_color}{total_pnl:+.4f} USDT\033[0m  |  ROI Sesión: {pnl_color}{total_roi:+.2f}%\033[0m")
    
    print(f"\n  Operaciones: [{long_op_status}] | [{short_op_status}]")
    print(f"  Última Señal: {signal_str} ({signal_reason})")
    print(f"  Posiciones Abiertas: LONGs: {longs_count} | SHORTs: {shorts_count}")

    print("\n--- Balances de Operaciones Lógicas " + "-"*45)
    header = f"  {'Operación':<15} | {'Capital Lógico':>15} | {'Usado':>15} | {'Disponible':>15} | {'PNL Op.':>15}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    
    pnl_long_color = "\033[92m" if long_pnl >= 0 else "\033[91m"
    print(f"  {'LONG':<15} | {long_balance.get('operational_margin', 0.0):15.2f} | {long_balance.get('used_margin', 0.0):15.2f} | {long_balance.get('available_margin', 0.0):15.2f} | {pnl_long_color}{long_pnl:15.4f}\033[0m")
    
    pnl_short_color = "\033[92m" if short_pnl >= 0 else "\033[91m"
    print(f"  {'SHORT':<15} | {short_balance.get('operational_margin', 0.0):15.2f} | {short_balance.get('used_margin', 0.0):15.2f} | {short_balance.get('available_margin', 0.0):15.2f} | {pnl_short_color}{short_pnl:15.4f}\033[0m")
    
    # --- INICIO DE LA MODIFICACIÓN: Añadir la sección del último TICK ---
    print("\n--- Último Evento Procesado " + "-"*53)
    
    if latest_signal_info:
        # Extraer datos de la señal. Usar .get con valores por defecto por seguridad.
        # El timestamp y el precio ahora vienen formateados desde el SessionManager
        ts_str = latest_signal_info.get('timestamp', 'N/A')
        price_str = latest_signal_info.get('price', 'N/A')
        
        # El estado de las operaciones ya lo tenemos extraído arriba
        op_display_long = f"L: {long_op_info.get('tendencia', 'N/A') if long_op_info.get('estado') == 'ACTIVA' else long_op_info.get('estado', 'N/A')}"
        op_display_short = f"S: {short_op_info.get('tendencia', 'N/A') if short_op_info.get('estado') == 'ACTIVA' else short_op_info.get('estado', 'N/A')}"

        header_line = f"  TICK @ {ts_str} | Precio: {price_str} | Ops: {op_display_long}, {op_display_short}"
        
        print(header_line)
        print(f"  TA:  EMA={latest_signal_info.get('ema', 'N/A'):<15} W.Inc={latest_signal_info.get('weighted_increment', 'N/A'):<8} W.Dec={latest_signal_info.get('weighted_decrement', 'N/A'):<8}")
        # La razón de la señal ya la tenemos extraída arriba
        print(f"  SIG: {signal_str:<15} | Razón: {signal_reason}")

        # Máximas posiciones lógicas de las operaciones
        max_pos_l = long_op_info.get('max_posiciones_logicas', 'N/A') if long_op_info.get('estado') != 'DETENIDA' else 'N/A'
        max_pos_s = short_op_info.get('max_posiciones_logicas', 'N/A') if short_op_info.get('estado') != 'DETENIDA' else 'N/A'
        
        # El PNL de la sesión se obtiene del resumen general
        pnl_sesion_str = f"{summary.get('total_realized_pnl_session', 0.0):+.4f} USDT"
        print(f"  POS: Longs={longs_count}/{max_pos_l} | Shorts={shorts_count}/{max_pos_s} | PNL Sesión: {pnl_sesion_str}")
    else:
        print("  (Esperando primer evento de precio...)")
    # --- FIN DE LA MODIFICACIÓN ---


# --- Lógica Principal de la Pantalla ---
def show_dashboard_screen(session_manager: Any):
    from ._session_config_editor import show_session_config_editor_screen

    config_module = _deps.get("config_module")
    if not TerminalMenu or not config_module or not sm_api or not session_manager:
        print("ERROR CRÍTICO: Dependencias del Dashboard no disponibles.")
        time.sleep(3)
        return

    sm_api.init_sm_api(session_manager)
    session_manager.start()

    clear_screen()
    print("Dashboard: Esperando la recepción del primer tick de precio del mercado...")
    
    wait_animation = ['|', '/', '-', '\\']
    i = 0
    while True:
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
            summary = sm_api.get_session_summary()
            if not summary or summary.get('error'):
                error_message = f"ADVERTENCIA: No se pudo obtener el estado de la sesión: {summary.get('error', 'Reintentando...')}"
        except Exception as e:
            error_message = f"ERROR CRÍTICO: Excepción inesperada en el dashboard: {e}"
        
        clear_screen()
        if error_message:
            print(f"\033[91m{error_message}\033[0m")
        
        if summary and not summary.get('error'):
            _render_dashboard_view(summary, config_module)
        
        menu_items = [
            "[1] Gestionar Operación LONG", 
            "[2] Gestionar Operación SHORT",
            "[3] Editar Configuración de Sesión", 
            "[4] Ver Logs en Tiempo Real",
            None,
            "[r] Refrescar",
            "[h] Ayuda", 
            "[q] Finalizar Sesión y Volver al Menú Principal"
        ]
        action_map = {
            0: 'manage_long', 1: 'manage_short', 2: 'edit_config', 3: 'view_logs',
            5: 'refresh', 6: 'help', 7: 'exit_session'
        }
        
        menu_options = helpers_module.MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu_options['menu_cursor_style'] = ("fg_cyan", "bold")

        menu = TerminalMenu(menu_items, title="\nAcciones de la Sesión:", **menu_options)
        choice = menu.show()
        action = action_map.get(choice)
        
        if action == 'manage_long':
            operation_manager.show_operation_manager_screen(side_filter='long')
        elif action == 'manage_short':
            operation_manager.show_operation_manager_screen(side_filter='short')
        elif action == 'edit_config':
            changes_made = show_session_config_editor_screen(config_module)
            if changes_made:
                # Al guardar, notificamos al SessionManager. Pasamos el dict de claves que cambiaron.
                sm_api.update_session_parameters(changes_made) 
        elif action == 'view_logs': 
            _log_viewer.show_log_viewer()
        elif action == 'refresh':
            time.sleep(0.1)
            continue
        elif action == 'help': 
            helpers_module.show_help_popup("dashboard_main")
        elif action == 'exit_session' or choice is None:
            confirm_menu = TerminalMenu(["[1] Sí, finalizar sesión", "[2] No, continuar"], title="¿Confirmas finalizar la sesión actual?", **helpers_module.MENU_STYLE)
            if confirm_menu.show() == 0: 
                break
    
    final_summary_data = sm_api.get_session_summary()
    _display_final_summary(final_summary_data)
    
    if session_manager.is_running():
        session_manager.stop()
    
    from runner import shutdown_session_backend
    shutdown_session_backend(
        session_manager=session_manager,
        final_summary=final_summary_data,
        config_module=_deps.get("config_module"),
        open_snapshot_logger_module=_deps.get("open_snapshot_logger_module")
    )