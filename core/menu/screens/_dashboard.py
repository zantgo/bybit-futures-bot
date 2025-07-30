"""
Módulo para la Pantalla del Dashboard de Sesión.

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
            duration_seconds = (datetime.datetime.now(timezone.utc) - session_start_time).total_seconds() if session_start_time else 0
            duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))
            
            ticker_symbol = getattr(config_module, 'TICKER_SYMBOL', 'N/A')
            
            op_status = summary.get('operation_status', {})
            op_tendencia = op_status.get('tendencia', 'NEUTRAL')
            op_estado = 'ACTIVA' if op_tendencia != 'NEUTRAL' else 'EN ESPERA'
            status_display = f"Modo Op: {op_tendencia} ({op_estado})"

            leverage_val = op_status.get('apalancamiento', 0.0)
            base_size_val = op_status.get('tamaño_posicion_base_usdt', 0.0)
            max_pos_val = op_status.get('max_posiciones_logicas', 0)
            
            sl_roi_enabled = getattr(config_module, 'SESSION_ROI_SL_ENABLED', False)
            tp_roi_enabled = getattr(config_module, 'SESSION_ROI_TP_ENABLED', False)
            sl_roi_val = pm_api.get_global_sl_pct() or 0.0
            tp_roi_val = pm_api.get_global_tp_pct() or 0.0
            sl_roi_str = f"Activo (-{sl_roi_val:.1f}%)" if sl_roi_enabled else "Desactivado"
            tp_roi_str = f"Activo (+{tp_roi_val:.1f}%)" if tp_roi_enabled else "Desactivado"

            real_balances = summary.get('real_account_balances', {})

        except Exception as e:
            error_message = f"ERROR CRÍTICO: Excepción inesperada en el dashboard: {e}"
            current_price = 0.0 # Asegurar que las variables existan
        
        clear_screen()
        
        if error_message:
            print(f"\033[91m{error_message}\033[0m")
        
        header_title = f"Dashboard Sesión: {ticker_symbol} @ {current_price:.4f} USDT | {status_display}"
        print_tui_header(header_title)
        
        # --- RENDERIZADO DE LA PANTALLA (Lógica de visualización sin cambios) ---
        print("\n--- Estado General y Configuración de la Sesión " + "-"*31)
        col1_data = {
            "Duración Sesión": duration_str, "Capital Inicial": f"{initial_capital:.2f} USDT",
            "PNL Realizado": f"{realized_pnl:+.4f} USDT", "PNL No Realizado": f"{unrealized_pnl:+.4f} USDT",
            "PNL Total": f"{total_pnl:+.4f} USDT", "ROI Sesión": f"{current_roi:+.2f}%",
        }
        col2_data = {
            "Apalancamiento": f"{leverage_val:.1f}x", "Tamaño Base / Max Pos": f"{base_size_val:.2f}$ / {max_pos_val}",
            "Límite Duración Op.": f"{op_status.get('tiempo_maximo_min') or 'N/A'} min", "Límite Trades Op.": f"{op_status.get('max_comercios') or 'N/A'}",
            "SL Sesión (ROI)": sl_roi_str, "TP Sesión (ROI)": tp_roi_str,
        }
        max_key_len1 = max(len(k) for k in col1_data.keys())
        max_key_len2 = max(len(k) for k in col2_data.keys())
        for i in range(len(col1_data)):
            k1, v1 = list(col1_data.items())[i]
            k2, v2 = list(col2_data.items())[i]
            print(f"  {k1:<{max_key_len1}} : {v1:<22}|  {k2:<{max_key_len2}} : {v2}")

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
            changes_saved = _config_editor.show_session_config_editor_screen(config_module)
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