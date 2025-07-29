"""
Módulo para la Pantalla del Dashboard Principal.

v6.2 (Refactor de Modularización):
- Se actualizan las importaciones y llamadas para usar el nuevo módulo
  `operation_manager` en lugar del archivo obsoleto `_milestone_manager`.
"""
# (COMENTARIO) Docstring de la versión anterior (v6.1) para referencia:
# """
# Módulo para la Pantalla del Dashboard Principal.
# 
# v6.1 (Manejo de Errores en UI):
# - El dashboard ahora es resiliente a fallos al obtener el resumen de estado (summary).
# - Si ocurre un error de red o de API, se muestra una advertencia en la parte
#   superior de la pantalla y los datos se muestran como 'Error' o 'N/A',
#   permitiendo al usuario refrescar o salir sin que el bot se detenga.
# """
import time
import datetime
from datetime import timezone
from typing import Dict, Any, List

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

# --- INICIO DE LA MODIFICACIÓN: Importar el nuevo módulo ---
from . import _config_editor, _log_viewer, operation_manager
# (COMENTARIO) Se elimina la importación del archivo obsoleto.
# from . import _config_editor, _log_viewer, _milestone_manager
# --- FIN DE LA MODIFICACIÓN ---

try:
    from core.exchange._models import StandardBalance
except ImportError:
    class StandardBalance: pass

_deps: Dict[str, Any] = {}

def _handle_ticker_change(config_module: Any):
    exchange_adapter = _deps.get('exchange_adapter')
    logger = _deps.get('memory_logger_module')
    if not exchange_adapter or not logger:
        if logger:
            logger.log("ERROR INTERNO: No se pudo acceder al adaptador de exchange para validar el ticker.", level="ERROR")
        print("\nERROR INTERNO: No se pudo acceder al adaptador de exchange para validar el ticker.")
        time.sleep(3)
        return

    new_symbol = getattr(config_module, 'TICKER_SYMBOL', 'BTCUSDT')
    default_symbol = "BTCUSDT"

    print(f"\nValidando nuevo ticker '{new_symbol}' con el exchange...")
    time.sleep(1) 

    validation_ticker = exchange_adapter.get_ticker(new_symbol)

    if validation_ticker and validation_ticker.price > 0:
        logger.log(f"TICKER UPDATE: Símbolo cambiado exitosamente a '{new_symbol}'.", "WARN")
        print(f"ÉXITO: Ticker '{new_symbol}' validado y aplicado correctamente.")
        time.sleep(2)
    else:
        logger.log(f"TICKER UPDATE FAILED: El símbolo '{new_symbol}' no es válido. Revertiendo a '{default_symbol}'.", "ERROR")
        print(f"\nERROR: El ticker '{new_symbol}' no es válido o no se pudo obtener su precio.")
        print(f"Revirtiendo al ticker por defecto: '{default_symbol}'.")
        setattr(config_module, 'TICKER_SYMBOL', default_symbol)
        time.sleep(3.5)

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

def show_dashboard_screen():
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado.")
        time.sleep(2)
        return

    pm_api = _deps.get("position_manager_api_module")
    config_module = _deps.get("config_module")
    
    if not pm_api or not config_module:
        print("ERROR CRÍTICO: Dependencias (PM API o Config) no inyectadas en el Dashboard.")
        time.sleep(3)
        return

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

    while True:
        pm_api.force_balance_update()

        error_message = None
        try:
            current_price = pm_api.get_current_market_price() or 0.0
            
            summary = pm_api.get_position_summary()
            
            if not summary or summary.get('error'):
                error_message = f"ADVERTENCIA: No se pudo obtener el estado del bot: {summary.get('error', 'Reintentando...')}"
                unrealized_pnl, realized_pnl, total_pnl, initial_capital, current_roi = (0.0,) * 5
                duration_str, ticker_symbol, status_display = "Error", "Error", "Error"
                op_tendencia, leverage_val, base_size_val, max_pos_val = "Error", 0.0, 0.0, 0
                sl_roi_str, tp_roi_str = "Error", "Error"
                real_balances = {}
            else:
                unrealized_pnl = pm_api.get_unrealized_pnl(current_price)
                realized_pnl = summary.get('total_realized_pnl_session', 0.0)
                total_pnl = realized_pnl + unrealized_pnl
                initial_capital = summary.get('initial_total_capital', 0.0)
                current_roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
                
                session_start_time = pm_api.get_session_start_time()
                duration_seconds = (datetime.datetime.now(timezone.utc) - session_start_time).total_seconds() if session_start_time else 0
                duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))
                
                ticker_symbol = getattr(config_module, 'TICKER_SYMBOL', 'N/A')
                
                op_status = summary.get('operation_status', {})
                op_tendencia = op_status.get('tendencia', 'NEUTRAL')
                op_estado = 'ACTIVA' if op_tendencia != 'NEUTRAL' else 'EN ESPERA'
                status_display = f"Modo: {op_tendencia} ({op_estado})"

                op_params = summary.get('operation_status', {})
                leverage_val = op_params.get('apalancamiento', 0.0)
                base_size_val = op_params.get('tamaño_posicion_base_usdt', 0.0)
                max_pos_val = op_params.get('max_posiciones_logicas', 0)
                
                sl_roi_enabled = getattr(config_module, 'SESSION_ROI_SL_ENABLED', False)
                tp_roi_enabled = getattr(config_module, 'SESSION_ROI_TP_ENABLED', False)
                sl_roi_val = pm_api.get_global_sl_pct() or 0.0
                tp_roi_val = pm_api.get_global_tp_pct() or 0.0
                sl_roi_str = f"Activo (-{sl_roi_val:.1f}%)" if sl_roi_enabled else "Desactivado"
                tp_roi_str = f"Activo (+{tp_roi_val:.1f}%)" if tp_roi_enabled else "Desactivado"

                real_balances = summary.get('real_account_balances', {})

        except Exception as e:
            error_message = f"ERROR CRÍTICO: Excepción inesperada en el dashboard: {e}"
            unrealized_pnl, realized_pnl, total_pnl, initial_capital, current_roi = (0.0,) * 5
            duration_str, ticker_symbol, status_display = "Error", "Error", "Error"
            op_tendencia, leverage_val, base_size_val, max_pos_val = "Error", 0.0, 0.0, 0
            sl_roi_str, tp_roi_str = "Error", "Error"
            real_balances, current_price = {}, 0.0
        
        clear_screen()
        
        if error_message:
            print(f"\033[91m{error_message}\033[0m")
        
        header_title = f"Dashboard: {ticker_symbol} @ {current_price:.4f} USDT | {status_display}"
        print_tui_header(header_title)
        
        print("\n--- Estado General y Configuración de la Sesión " + "-"*31)
        
        col1_data = {
            "Duración Sesión": duration_str, "Capital Inicial": f"{initial_capital:.2f} USDT",
            "PNL Realizado": f"{realized_pnl:+.4f} USDT", "PNL No Realizado": f"{unrealized_pnl:+.4f} USDT",
            "PNL Total": f"{total_pnl:+.4f} USDT", "ROI Sesión": f"{current_roi:+.2f}%",
        }

        col2_data = {
            "Apalancamiento": f"{leverage_val:.1f}x",
            "Tamaño Base / Max Pos": f"{base_size_val:.2f}$ / {max_pos_val}",
            "Límite de Duración": "N/A", 
            "Límite de Trades": "N/A",
            "SL Sesión (ROI)": sl_roi_str,
            "TP Sesión (ROI)": tp_roi_str,
        }

        max_key_len1 = max(len(k) for k in col1_data.keys())
        max_key_len2 = max(len(k) for k in col2_data.keys())
        keys1, keys2 = list(col1_data.keys()), list(col2_data.keys())
        num_rows = max(len(keys1), len(keys2))
        
        for i in range(num_rows):
            line = ""
            if i < len(keys1):
                key = keys1[i]
                line += f"  {key:<{max_key_len1}} : {col1_data[key]:<22}"
            else:
                line += " " * (max_key_len1 + 25)
            if i < len(keys2):
                key = keys2[i]
                line += f"|  {key:<{max_key_len2}} : {col2_data[key]}"
            print(line)

        print("\n--- Balances de Cuentas Reales " + "-"*50)
        if not real_balances:
            print("  (No hay datos de balance disponibles o hubo un error)")
        else:
            for acc_name, balance_info in real_balances.items():
                if isinstance(balance_info, StandardBalance):
                    equity = balance_info.total_equity_usd
                    print(f"  {acc_name.upper():<15}: Equity: {equity:9.2f}$")
                else:
                    print(f"  {acc_name.upper():<15}: ({str(balance_info)})")
        
        print("\n--- Operación " + "-"*70)
        print(f"  ESTADO: {op_tendencia}")
        
        menu_items = [
            "[1] Refrescar", 
            "[2] Gestionar Operación", 
            None,
            "[3] Editar Configuración de Sesión", 
            "[4] Ver Logs en Tiempo Real",
            None,
            "[h] Ayuda", 
            "[q] Salir del Bot"
        ]
        
        action_map = {
            0: 'refresh', 1: 'manage_operation',
            3: 'edit_config', 4: 'view_logs',
            6: 'help', 7: 'exit'
        }
        
        menu_options = helpers_module.MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu_options['menu_cursor_style'] = ("fg_cyan", "bold")

        menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
        choice = menu.show()
        
        action = action_map.get(choice)
        
        if action == 'refresh': 
            continue
        # --- INICIO DE LA MODIFICACIÓN: Llamar a la nueva función ---
        elif action == 'manage_operation': 
            operation_manager.show_operation_manager_screen()
        # (COMENTADO) Se elimina la llamada a la función obsoleta.
        # elif action == 'manage_operation': 
        #     _milestone_manager.show_milestone_manager_screen()
        # --- FIN DE LA MODIFICACIÓN ---
        elif action == 'edit_config':
            original_symbol = getattr(config_module, 'TICKER_SYMBOL', 'BTCUSDT')
            changes_saved = _config_editor.show_config_editor_screen(config_module, context='session')
            if changes_saved:
                new_symbol = getattr(config_module, 'TICKER_SYMBOL', 'BTCUSDT')
                if new_symbol != original_symbol:
                    _handle_ticker_change(config_module)
            continue
        elif action == 'view_logs': 
            _log_viewer.show_log_viewer()
        elif action == 'help': 
            helpers_module.show_help_popup("dashboard_main")
        elif action == 'exit' or choice is None:
            confirm_menu = TerminalMenu(["[1] Sí, apagar el bot", "[2] No, continuar"], title="¿Confirmas apagar el bot?", **helpers_module.MENU_STYLE)
            if confirm_menu.show() == 0: 
                break