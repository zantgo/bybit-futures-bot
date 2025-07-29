"""
Módulo Principal del Panel de Control de Operación.

Contiene la lógica central de la pantalla, incluyendo el bucle principal,
la obtención de datos desde la API del Position Manager y la gestión del menú
de acciones del usuario.
"""
import time
from typing import Any, Dict, Optional

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# Importar los submódulos de displayers y wizards que contienen las funciones auxiliares
from . import _displayers
from . import _wizards

# Importar helpers y entidades necesarios
from ..._helpers import (
    clear_screen,
    print_tui_header,
    MENU_STYLE,
    show_help_popup
)

try:
    from core.strategy.pm._entities import Operacion
    import config as config_module
except ImportError:
    class Operacion: pass
    config_module = None

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el __init__.py del módulo."""
    global _deps
    _deps = dependencies

# --- LÓGICA DE LA PANTALLA PRINCIPAL ---

def show_operation_manager_screen():
    """
    Función principal que muestra el Panel de Control de Operación.
    (Anteriormente conocida como show_milestone_manager_screen).
    """
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return

    pm_api = _deps.get("position_manager_api_module")
    om_api = _deps.get("operation_manager_api_module")
    if not pm_api or not om_api:
        print("ERROR CRÍTICO: PM o OM API no inyectada."); time.sleep(3); return

    while True:
        try:
            operacion = om_api.get_operation()
            if not operacion:
                print("\n\033[93mEsperando inicialización de la operación...\033[0m")
                time.sleep(2)
                continue

            summary = pm_api.get_position_summary()
            current_price = pm_api.get_current_market_price() or 0.0
            
            ticker_symbol = getattr(config_module, 'TICKER_SYMBOL', 'N/A') if config_module else 'N/A'
            header_title = f"Panel de Control: {ticker_symbol} @ {current_price:.4f} USDT"
            clear_screen()
            print_tui_header(header_title)

            if not summary or summary.get('error'):
                error_msg = summary.get('error', 'No se pudo obtener el estado de la operación.')
                print(f"\n\033[91mADVERTENCIA: {error_msg}\033[0m")
                menu_items = ["[r] Reintentar", "[b] Volver al Dashboard"]
                menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
                choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()
                if choice == 0: continue
                else: break
            
            # Llamadas a funciones del módulo de displayers
            _displayers._display_operation_details(summary)
            _displayers._display_capital_stats(summary)
            _displayers._display_positions_tables(summary, current_price)
            _displayers._display_operation_conditions(operacion)

            menu_items, action_map = [], {}
            is_trading_active = operacion.tendencia != 'NEUTRAL'

            if is_trading_active:
                menu_items.extend(["[1] Modificar Operación en Curso", "[2] Detener Operación"])
                action_map = {0: "modify", 1: "stop"}
            else:
                menu_items.extend(["[1] Iniciar Nueva Operación", "[2] Forzar Cierre de Posiciones"])
                action_map = {0: "start_new", 1: "panic_close"}

            next_action_index = len(menu_items)
            menu_items.extend([None, "[r] Refrescar", "[h] Ayuda", "[b] Volver al Dashboard"])
            action_map.update({
                next_action_index + 1: "refresh",
                next_action_index + 2: "help",
                next_action_index + 3: "back"
            })

            menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
            main_menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
            choice = main_menu.show()
            
            action = action_map.get(choice)

            # Llamadas a funciones del módulo de wizards
            if action == "start_new": _wizards._operation_setup_wizard(om_api, operacion)
            elif action == "modify": _wizards._operation_setup_wizard(om_api, operacion, is_modification=True)
            elif action == "stop": _wizards._force_stop_wizard(om_api, pm_api)
            elif action == "panic_close": _wizards._force_close_all_wizard(pm_api)
            elif action == "refresh": continue
            elif action == "help": show_help_popup("auto_mode")
            else: break
        
        except Exception as e:
            clear_screen(); print_tui_header("Panel de Control de Operación")
            print(f"\n\033[91mERROR CRÍTICO: {e}\033[0m\nOcurrió un error inesperado al renderizar la pantalla.")
            menu_items = ["[r] Reintentar", "[b] Volver al Dashboard"]
            menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
            choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()
            if choice == 0: continue
            else: break