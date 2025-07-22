# core/menu/screens/_dashboard.py

"""
Módulo para la Pantalla del Dashboard Principal.

Esta pantalla actúa como el menú principal y centro de estado una vez que el
bot está operativo. Muestra información en tiempo real y proporciona acceso
a todas las demás pantallas de gestión.
"""
import time
import datetime
from typing import Dict, Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Menú ---
from .._helpers import clear_screen, print_tui_header, press_enter_to_continue, print_section, MENU_STYLE
from . import _config_editor, _manual_mode, _auto_mode, _position_viewer, _log_viewer

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- Lógica de la Pantalla ---

def show_dashboard_screen():
    """
    Muestra el dashboard principal en un bucle. El bucle solo termina cuando
    el usuario elige salir del programa.
    """
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado.")
        time.sleep(2)
        return

    # Extraer el position_manager de las dependencias para un acceso más fácil
    pm_api = _deps.get("position_manager").api

    while True:
        clear_screen()
        
        # --- Recopilación de Datos en Tiempo Real ---
        try:
            summary = pm_api.get_position_summary()
            if not summary or summary.get('error'):
                print(f"\nError al obtener el estado del bot: {summary.get('error', 'Desconocido')}")
                press_enter_to_continue()
                continue

            current_price = pm_api.get_current_price_for_exit() or 0.0
            unrealized_pnl = pm_api.get_unrealized_pnl(current_price)
            realized_pnl = summary.get('total_realized_pnl_session', 0.0)
            total_pnl = realized_pnl + unrealized_pnl
            initial_capital = summary.get('initial_total_capital', 0.0)
            current_roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
            
            session_start_time = pm_api.get_session_start_time()
            duration_seconds = (datetime.datetime.now() - session_start_time).total_seconds() if session_start_time else 0
            duration_hours = duration_seconds / 3600
            roi_per_hour = (current_roi / duration_hours) if duration_hours > 0 else 0.0
            
            manual_state = summary.get('manual_mode_status', {})
            session_limits = summary.get('session_limits', {})
            trade_limit = session_limits.get('trade_limit')
            trades_executed = session_limits.get('trades_executed', 0)
            
            time_limit_cfg = session_limits.get('time_limit', {})
            duration_limit_mins = time_limit_cfg.get('duration', 0)
            
            # Formatear strings para visualización
            duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))
            trade_limit_str = f"{trades_executed}/{trade_limit}" if trade_limit else f"{trades_executed}/Ilimitados"
            time_remaining_str = "N/A"
            if duration_limit_mins > 0:
                secs_remaining = (duration_limit_mins * 60) - duration_seconds
                if secs_remaining > 0:
                    time_remaining_str = str(datetime.timedelta(seconds=int(secs_remaining)))
                else:
                    time_remaining_str = "Límite alcanzado"
            
            sl_roi_pct = pm_api.get_global_sl_pct()
            tp_roi_pct = pm_api.get_global_tp_pct()

        except Exception as e:
            print(f"Error al recopilar datos para el dashboard: {e}")
            time.sleep(2)
            continue
        
        # --- Renderizado del Dashboard ---
        print_tui_header("Dashboard de Sesión")
        
        status_data = {
            "Tiempo de Operación": duration_str,
            "Precio Actual": f"{current_price:.4f} USDT",
            "Capital Inicial Total": f"{initial_capital:.2f} USDT",
            "PNL Total (Realizado + No Realizado)": f"{total_pnl:+.4f} USDT",
            "ROI Actual (Estimado)": f"{current_roi:+.2f}%",
            "ROI Promedio por Hora": f"{roi_per_hour:+.2f}%/h",
            "Trades de Sesión": trade_limit_str,
            "Tiempo Restante de Sesión": time_remaining_str,
            "Límite SL de Sesión (ROI)": f"-{sl_roi_pct:.2f}%" if sl_roi_pct else "N/A",
            "Límite TP de Sesión (ROI)": f"+{tp_roi_pct:.2f}%" if tp_roi_pct else "N/A",
        }
        print_section("Estado General de la Sesión", status_data)
        
        # --- Menú de Acciones ---
        menu_items = [
            "[1] Refrescar Dashboard",
            "[2] Ver/Gestionar Posiciones Lógicas",
            None,
            "[3] Modo Manual Guiado",
            "[4] Modo Automático (Árbol de Decisiones)",
            None,
            "[5] Editar Configuración de la Sesión",
            "[6] Ver Logs en Tiempo Real",
            None,
            "[q] Salir del Bot (Apagado Completo)"
        ]
        
        menu = TerminalMenu(
            menu_items,
            title="\nMenú Principal de Acciones",
            menu_cursor_style=("fg_cyan", "bold"),
            clear_screen=False # No limpiar para que el dashboard permanezca visible
        )
        choice = menu.show()
        
        if choice == 0:
            continue # Simplemente refresca el bucle
        elif choice == 1:
            _position_viewer.show_position_viewer_screen(pm_api)
        elif choice == 2:
            _manual_mode.show_manual_mode_screen(pm_api)
        elif choice == 3:
            _auto_mode.show_auto_mode_screen(pm_api)
        elif choice == 4:
            _config_editor.show_config_editor_screen(_deps["config"])
        elif choice == 5:
            _log_viewer.show_log_viewer()
        elif choice == 7 or choice is None:
            # Preguntar confirmación antes de salir
            confirm_menu = TerminalMenu(["[1] Sí, salir y apagar el bot", "[2] No, continuar operando"], title="¿Estás seguro de que deseas salir?", **MENU_STYLE)
            if confirm_menu.show() == 0:
                break # Rompe el bucle while y permite que el controlador principal apague el bot