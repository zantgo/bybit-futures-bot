"""
Módulo Principal del Panel de Control de Operación.

v8.5 (Corrección de Argumentos):
- Se corrige el orden de los argumentos en las llamadas a las funciones
  de `_displayers` para que coincidan con sus definiciones, solucionando
  errores de `TypeError` y `AttributeError` al renderizar la pantalla.
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
    press_enter_to_continue,
    MENU_STYLE,
    show_help_popup
)

try:
    from core.strategy.om._entities import Operacion
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
    Presenta un selector para gestionar las operaciones LONG y SHORT de forma independiente.
    """
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return

    om_api = _deps.get("operation_manager_api_module")
    if not om_api:
        print("ERROR CRÍTICO: OM API no inyectada."); time.sleep(3); return

    while True:
        clear_screen()
        print_tui_header("Panel de Control de Operaciones")

        try:
            long_op = om_api.get_operation_by_side('long')
            short_op = om_api.get_operation_by_side('short')
            
            if not long_op or not short_op:
                 print("\nError: No se pudieron obtener los objetos de operación. Reintentando...")
                 time.sleep(2)
                 continue

            def get_op_status_str(op: Operacion) -> str:
                tendencia = op.tendencia if op.tendencia != 'NEUTRAL' else 'INACTIVA'
                estado = op.estado
                return f"Tendencia: {tendencia} (Estado: {estado})"

            menu_items = [
                f"[1] Gestionar Operación LONG  | {get_op_status_str(long_op)}",
                f"[2] Gestionar Operación SHORT | {get_op_status_str(short_op)}",
                None,
                "[b] Volver al Dashboard"
            ]
            
            selector_menu = TerminalMenu(menu_items, title="Selecciona qué operación deseas gestionar:", **MENU_STYLE)
            choice = selector_menu.show()

            if choice == 0:
                _show_single_operation_view('long')
            elif choice == 1:
                _show_single_operation_view('short')
            else: # Si el usuario presiona ESC o selecciona Volver
                break
        
        except Exception as e:
            print(f"\n\033[91mERROR CRÍTICO en el selector de operaciones: {e}\033[0m")
            press_enter_to_continue()
            break

def _show_single_operation_view(side: str):
    """
    Muestra la vista de detalles y acciones para una única operación (LONG o SHORT).
    """
    pm_api = _deps.get("position_manager_api_module")
    om_api = _deps.get("operation_manager_api_module")
    
    if not pm_api or not om_api: return

    while True:
        try:
            operacion = om_api.get_operation_by_side(side)
            if not operacion:
                print(f"\nError al cargar la operación para el lado {side.upper()}.")
                time.sleep(2)
                return

            summary = pm_api.get_position_summary()
            current_price = pm_api.get_current_market_price() or 0.0
            
            ticker_symbol = getattr(config_module, 'TICKER_SYMBOL', 'N/A') if config_module else 'N/A'
            header_title = f"Panel de Operación {side.upper()}: {ticker_symbol} @ {current_price:.4f} USDT"
            clear_screen()
            print_tui_header(header_title)

            if not summary or summary.get('error'):
                error_msg = summary.get('error', 'No se pudo obtener el estado de la operación.')
                print(f"\n\033[91mADVERTENCIA: {error_msg}\033[0m")
                menu_items = ["[r] Reintentar", "[b] Volver al Selector"]
                menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
                choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()
                if choice == 0: continue
                else: break

            # --- INICIO DE LA CORRECCIÓN ---
            # Se corrige el orden de los argumentos para que coincida con las definiciones
            # en el módulo _displayers.py.
            _displayers._display_operation_details(summary, operacion, side)
            _displayers._display_capital_stats(summary, operacion, side, current_price)
            _displayers._display_positions_tables(summary, current_price, side) 
            _displayers._display_operation_conditions(operacion)
            # --- FIN DE LA CORRECCIÓN ---

            # --- Construcción de Menú Contextual Mejorada ---
            menu_items, action_map = [], {}
            is_trading_active = operacion.tendencia != 'NEUTRAL'

            # Acción principal: Iniciar, Modificar o Detener
            if is_trading_active:
                menu_items.append(f"[1] Modificar Operación {side.upper()} en Curso")
                menu_items.append(f"[2] Detener Operación {side.upper()}")
                action_map = {0: "modify", 1: "stop"}
            else: # Operación Inactiva
                menu_items.append(f"[1] Iniciar Nueva Operación {side.upper()}")
                action_map = {0: "start_new"}

            # Acción secundaria: Cierre de pánico (si hay posiciones)
            open_positions_count = summary.get(f'open_{side}_positions_count', 0)
            if open_positions_count > 0:
                next_idx = len(menu_items)
                menu_items.append(f"[{next_idx + 1}] Forzar Cierre de {open_positions_count} Posiciones {side.upper()}")
                action_map[next_idx] = "panic_close"

            # Acciones comunes
            next_action_index = len(menu_items)
            menu_items.extend([None, "[r] Refrescar", "[h] Ayuda", "[b] Volver al Selector"])
            action_map.update({
                next_action_index + 1: "refresh",
                next_action_index + 2: "help",
                next_action_index + 3: "back"
            })

            menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
            main_menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
            choice = main_menu.show()
            
            action = action_map.get(choice)
            
            # Llamadas a los wizards ahora siempre son contextuales
            if action == "start_new": 
                _wizards._operation_setup_wizard(om_api, side, is_modification=False)
            elif action == "modify": 
                _wizards._operation_setup_wizard(om_api, side, is_modification=True)
            elif action == "stop": 
                _wizards._force_stop_wizard(om_api, pm_api, side)
            elif action == "panic_close": 
                _wizards._force_close_all_wizard(pm_api, side)
            elif action == "refresh": 
                continue
            elif action == "help": 
                show_help_popup("auto_mode")
            else: # "back" o None (ESC)
                break
        
        except Exception as e:
            clear_screen(); print_tui_header(f"Panel de Operación {side.upper()}")
            print(f"\n\033[91mERROR CRÍTICO: {e}\033[0m\nOcurrió un error inesperado al renderizar la pantalla.")
            import traceback
            traceback.print_exc() # Añadido para obtener más detalles del error
            menu_items = ["[r] Reintentar", "[b] Volver al Selector"]
            menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
            choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()
            if choice == 0: continue
            else: break