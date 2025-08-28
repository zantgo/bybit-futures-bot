# core/menu/screens/operation_manager/_main.py

"""
Módulo Principal del Panel de Control de Operación.

v9.3 (Corrección de UI en Detener Operación):
- Se añade un bloque de renderizado para el nuevo estado 'DETENIENDO',
  evitando que el menú de acciones desaparezca y proporcionando feedback
  visual al usuario durante el proceso de cierre.
"""
import time
import datetime
from typing import Any, Dict, Optional
import traceback

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
    # Se corrige la importación para usar la entidad correcta desde su ubicación central
    from core.strategy.entities import Operacion
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

def show_operation_manager_screen(side_filter: Optional[str] = None):
    """
    Función principal que muestra el Panel de Control de Operación.
    """
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return

    om_api = _deps.get("operation_manager_api_module")
    if not om_api:
        print("ERROR CRÍTICO: OM API no inyectada."); time.sleep(3); return

    if side_filter in ['long', 'short']:
        _show_single_operation_view(side_filter)
        return

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
            elif choice == 3 or choice is None:
                break
            else:
                continue
        
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
    sm_api = _deps.get("session_manager_api_module")
    
    if not pm_api or not om_api or not sm_api: 
        print("ERROR CRÍTICO: Faltan dependencias de API (PM, OM, o SM)."); time.sleep(3); return

    while True:
        try:
            operacion = om_api.get_operation_by_side(side)
            if not operacion:
                print(f"\nError al cargar la operación para el lado {side.upper()}.")
                time.sleep(2)
                return

            summary = sm_api.get_session_summary()
            current_price = summary.get('current_market_price', 0.0)
            
            ticker_symbol = "N/A"
            if config_module and hasattr(config_module, 'BOT_CONFIG'):
                 ticker_symbol = config_module.BOT_CONFIG.get("TICKER", {}).get("SYMBOL", "N/A")

            operation_status = operacion.estado if operacion.estado else "DESCONOCIDO"
            header_title = f"Panel de Operación {side.upper()}: {operation_status.upper()} @ {current_price:.4f} USDT"
            
            now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S %d-%m-%Y (UTC)')
            
            clear_screen()
            print_tui_header(title=header_title, subtitle=now_str)

            if not summary or summary.get('error'):
                error_msg = summary.get('error', 'No se pudo obtener el estado de la operación.')
                print(f"\n\033[91mADVERTENCIA: {error_msg}\033[0m")
                menu_items = ["[r] Reintentar", "[b] Volver"]
                menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
                choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()
                if choice == 0: continue
                else: break

            _displayers._display_operation_details(summary, operacion, side)
            _displayers._display_capital_stats(summary, operacion, side, current_price)
            _displayers._display_positions_tables(summary, operacion, current_price, side) 
            _displayers._display_operation_conditions(operacion)
            
            menu_items = []
            actions = []
            current_state = operacion.estado

            if current_state == 'DETENIDA':
                menu_items.append("[1] Configurar e Iniciar Nueva Operación")
                actions.append("start_new")
            elif current_state == 'PAUSADA':
                menu_items.append("[1] Reanudar Operación")
                actions.append("resume")
                menu_items.append("[2] Modificar Parámetros")
                actions.append("modify")
                menu_items.append("[3] Detener Operación (Cierre Forzoso)")
                actions.append("stop")
            elif current_state == 'EN_ESPERA':
                menu_items.append("[1] Pausar Operación")
                actions.append("pause")
                menu_items.append("[2] Forzar Inicio (Activar Manualmente)")
                actions.append("force_start")
                menu_items.append("[3] Modificar Parámetros")
                actions.append("modify")
                menu_items.append("[4] Detener Operación (Cierre Forzoso)")
                actions.append("stop")
            elif current_state == 'ACTIVA':
                menu_items.append("[1] Pausar Operación")
                actions.append("pause")
                menu_items.append("[2] Modificar Parámetros")
                actions.append("modify")
                menu_items.append("[3] Detener Operación (Cierre Forzoso)")
                actions.append("stop")
            elif current_state == 'DETENIENDO':
                print("\n\033[93m⏳  ...DETENIENDO OPERACIÓN...\033[0m")
                print("   Cerrando posiciones y reseteando estado. La pantalla se refrescará automáticamente.")
                time.sleep(2)
                continue

            open_positions_count = operacion.posiciones_abiertas_count
            if open_positions_count > 0 and current_state not in ['DETENIDA', 'DETENIENDO']:
                next_idx = len(menu_items)
                menu_items.append(f"[{next_idx + 1}] CIERRE DE PÁNICO (Cerrar {open_positions_count} Posiciones)")
                actions.append("panic_close")

            menu_items.extend([None, "[r] Refrescar", "[h] Ayuda", "[b] Volver"])
            actions.extend([None, "refresh", "help", "back"])
            
            menu_options = MENU_STYLE.copy()
            menu_options['clear_screen'] = False
            
            main_menu = TerminalMenu(
                [item for item in menu_items if item is not None],
                title="\nAcciones:", 
                **menu_options
            )
            choice_index = main_menu.show()
            
            action = None
            if choice_index is not None:
                selectable_actions = [act for act in actions if act is not None]
                if choice_index < len(selectable_actions):
                    action = selectable_actions[choice_index]
            
            # --- INICIO DE LA MODIFICACIÓN (Paso Final) ---
            # Se cambia la llamada para usar el nombre de función público correcto.
            if action == "start_new": 
                _wizards.operation_setup_wizard(om_api, side, is_modification=False)
            elif action == "modify": 
                _wizards.operation_setup_wizard(om_api, side, is_modification=True)
            # --- FIN DE LA MODIFICACIÓN ---
            elif action == "pause":
                om_api.pausar_operacion(side)
                time.sleep(0.2)
            elif action == "resume":
                om_api.reanudar_operacion(side)
                time.sleep(0.2)
            elif action == "force_start":
                confirm_menu = TerminalMenu(["[1] Sí, forzar inicio", "[2] No, cancelar"], title="¿Activar la operación ignorando la condición de entrada?").show()
                if confirm_menu == 0:
                    om_api.forzar_activacion_manual(side)
                    time.sleep(0.2)
            
            elif action == "stop":
                title = "¿Seguro? Se cerrarán todas las posiciones y se reseteará la operación."
                confirm_menu = TerminalMenu(["[1] Sí, detener todo", "[2] No, cancelar"], title=title)
                
                if confirm_menu.show() == 0:
                    print("\n\033[93mProcesando solicitud de detención, por favor espere...\033[0m")
                    try:
                        success, message = om_api.detener_operacion(side, forzar_cierre_posiciones=True)
                        if success:
                            print(f"\033[92mÉXITO:\033[0m {message}")
                        else:
                            print(f"\033[91mERROR:\033[0m {message}")
                    except Exception as e:
                        print(f"\033[91mERROR CRÍTICO:\033[0m Excepción inesperada: {e}")
                    
                    time.sleep(2.5)

            elif action == "panic_close": 
                _wizards.force_close_all_wizard(pm_api, side)
            elif action == "refresh": 
                continue
            elif action == "help": 
                show_help_popup("auto_mode")
            elif action == "back" or action is None:
                break
        
        except Exception as e:
            clear_screen()
            header_title = f"Panel de Operación {side.upper()} - ERROR"
            print_tui_header(title=header_title, subtitle="Ocurrió un error crítico")
            print(f"\n\033[91mERROR CRÍTICO: {e}\033[0m\nOcurrió un error inesperado al renderizar la pantalla.")
            traceback.print_exc()
            press_enter_to_continue()
            break