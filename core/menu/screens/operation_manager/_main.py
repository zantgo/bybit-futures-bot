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
                # Actualizado para el nuevo ciclo de vida
                if op.estado == 'DETENIDA':
                    return "Estado: DETENIDA"
                return f"Tendencia: {op.tendencia} (Estado: {op.estado})"

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

            _displayers._display_operation_details(summary, operacion, side)
            _displayers._display_capital_stats(summary, operacion, side, current_price)
            _displayers._display_positions_tables(summary, current_price, side) 
            _displayers._display_operation_conditions(operacion)

            # --- INICIO DE LA MODIFICACIÓN: Menú de acciones 100% dinámico ---
            menu_items, action_map = [], {}
            current_state = operacion.estado

            # 1. Construir menú basado en el estado
            if current_state == 'DETENIDA':
                menu_items.append("[1] Configurar e Iniciar Nueva Operación")
                action_map = {0: "start_new"}
            
            elif current_state == 'PAUSADA':
                menu_items.append("[1] Reanudar Operación")
                menu_items.append("[2] Modificar Parámetros")
                menu_items.append("[3] Detener Operación (Cierre Forzoso)")
                action_map = {0: "resume", 1: "modify", 2: "stop"}

            elif current_state == 'EN_ESPERA':
                menu_items.append("[1] Pausar Operación")
                menu_items.append("[2] Forzar Inicio (Activar Manualmente)")
                menu_items.append("[3] Modificar Parámetros")
                menu_items.append("[4] Detener Operación (Cierre Forzoso)")
                action_map = {0: "pause", 1: "force_start", 2: "modify", 3: "stop"}

            elif current_state == 'ACTIVA':
                menu_items.append("[1] Pausar Operación")
                menu_items.append("[2] Modificar Parámetros")
                menu_items.append("[3] Detener Operación (Cierre Forzoso)")
                action_map = {0: "pause", 1: "modify", 2: "stop"}

            # 2. Añadir acción de pánico condicionalmente
            open_positions_count = summary.get(f'open_{side}_positions_count', 0)
            if open_positions_count > 0 and current_state != 'DETENIDA':
                next_idx = len(menu_items)
                menu_items.append(f"[{next_idx + 1}] CIERRE DE PÁNICO (Cerrar {open_positions_count} Posiciones)")
                action_map[next_idx] = "panic_close"

            # 3. Añadir acciones comunes
            menu_items.extend([None, "[r] Refrescar", "[h] Ayuda", "[b] Volver"])
            common_actions_keys = ["refresh", "help", "back"]
            offset = len(action_map)
            if any(action in action_map.values() for action in ["panic_close"]):
                 offset = len(action_map)

            # Calcular el índice inicial correcto para las acciones comunes
            current_index = len(menu_items) - len(common_actions_keys)
            for key in common_actions_keys:
                action_map[current_index] = key
                current_index += 1


            # 4. Mostrar menú y procesar acción
            menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
            main_menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
            choice = main_menu.show()
            
            action = action_map.get(choice)
            
            if action == "start_new": 
                _wizards._operation_setup_wizard(om_api, side, is_modification=False)
            elif action == "modify": 
                _wizards._operation_setup_wizard(om_api, side, is_modification=True)
            elif action == "pause":
                om_api.pausar_operacion(side)
                time.sleep(1.5)
            elif action == "resume":
                om_api.reanudar_operacion(side)
                time.sleep(1.5)
            elif action == "force_start":
                confirm_menu = TerminalMenu(["[1] Sí, forzar inicio", "[2] No, cancelar"], title="¿Activar la operación ignorando la condición de entrada?").show()
                if confirm_menu == 0:
                    om_api.forzar_activacion_manual(side)
            elif action == "stop":
                confirm_menu = TerminalMenu(["[1] Sí, detener todo", "[2] No, cancelar"], title="¿Seguro? Se cerrarán todas las posiciones y se reseteará la operación.").show()
                if confirm_menu == 0:
                    om_api.detener_operacion(side, forzar_cierre_posiciones=True)
            elif action == "panic_close": 
                _wizards._force_close_all_wizard(pm_api, side)
            elif action == "refresh": 
                continue
            elif action == "help": 
                show_help_popup("auto_mode")
            elif action == "back" or choice is None:
                break
            # --- FIN DE LA MODIFICACIÓN ---
        
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