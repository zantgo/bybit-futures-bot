# core/menu/screens/operation_manager/_main.py

"""
Módulo Principal del Panel de Control de Operación.
"""
import time
import datetime
from typing import Any, Dict, Optional
import traceback

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from . import _displayers
from . import _wizards
# --- INICIO DE LA MODIFICACIÓN (Paso 4 del Plan) ---
# Importar el nuevo módulo del gestor manual
from . import manual_position_manager
# --- FIN DE LA MODIFICACIÓN ---

from ..._helpers import (
    clear_screen,
    print_tui_header,
    press_enter_to_continue,
    MENU_STYLE,
    show_help_popup
)

try:
    from core.strategy.entities import Operacion
    import config as config_module
except ImportError:
    class Operacion: pass
    config_module = None

_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el __init__.py del módulo."""
    global _deps
    _deps = dependencies

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
        # Añadir clear_screen para una transición limpia desde el dashboard
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
                if not op or op.estado == 'DETENIDA':
                    return "Estado: DETENIDA"
                return f"Tendencia: {op.tendencia} (Estado: {op.estado})"

            menu_items = [
                f"[1] Gestionar Operación LONG  | {get_op_status_str(long_op)}",
                f"[2] Gestionar Operación SHORT | {get_op_status_str(short_op)}",
                None,
                "[b] Volver al Dashboard"
            ]
            
            # El menú principal sí debe limpiar la pantalla
            menu_options = MENU_STYLE.copy()
            menu_options['clear_screen'] = True
            
            selector_menu = TerminalMenu(menu_items, title="Selecciona qué operación deseas gestionar:", **menu_options)
            choice = selector_menu.show()

            if choice == 0:
                _show_single_operation_view('long')
            elif choice == 1:
                _show_single_operation_view('short')
            elif choice == 3 or choice is None:
                break
        
        except Exception as e:
            print(f"\n\033[91mERROR CRÍTICO en el selector de operaciones: {e}\033[0m")
            press_enter_to_continue()
            break


# Reemplaza esta función completa en core/menu/screens/operation_manager/_main.py

# Reemplaza la función _show_single_operation_view completa en core/menu/screens/operation_manager/_main.py

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
            
            operation_status = operacion.estado if operacion.estado else "DESCONOCIDO"
            header_title = f"Panel de Operación {side.upper()}: {operation_status.upper()} @ {current_price:.4f} USDT"
            
            now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S %d-%m-%Y (UTC)')
            
            clear_screen()
            print_tui_header(title=header_title, subtitle=now_str)

            if not summary or summary.get('error'):
                error_msg = summary.get('error', 'No se pudo obtener el estado de la operación.')
                print(f"\n\033[91mADVERTENCIA: {error_msg}\033[0m")
                menu_items = ["[r] Reintentar", "[b] Volver"]
                menu_options = MENU_STYLE.copy()
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
            else:
                menu_items.append("[1] Gestionar Posiciones Manualmente (Abrir/Cerrar)")
                actions.append("manual_manage")
                
                if current_state == 'PAUSADA':
                    menu_items.append("[2] Reanudar Operación")
                    actions.append("resume")
                elif current_state in ['ACTIVA', 'EN_ESPERA']:
                    menu_items.append("[2] Pausar Operación")
                    actions.append("pause")

                menu_items.append("[3] Modificar Parámetros de la Operación")
                actions.append("modify")
                menu_items.append("[4] Detener Operación (Cierre Forzoso de Posiciones)")
                actions.append("stop")

            if current_state == 'EN_ESPERA':
                menu_items.insert(2, "[*] Forzar Inicio (Activar Manualmente)")
                actions.insert(2, "force_start")

            if current_state == 'DETENIENDO':
                print("\n\033[93m⏳  ...DETENIENDO OPERACIÓN...\033[0m")
                print("   Cerrando posiciones y reseteando estado. La pantalla se refrescará automáticamente.")
                time.sleep(2)
                continue
            
            # --- INICIO DE LA MODIFICACIÓN ---
            # La lógica para construir el menú se mueve aquí para que sea más clara.
            # Tu código original para esto era un poco complejo, lo he simplificado
            # manteniendo exactamente el mismo resultado final.

            menu_items.extend([
                None,
                "[r] Refrescar",
                "[h] Ayuda", # Botón de ayuda añadido
                "[b] Volver"
            ])
            
            menu_options = MENU_STYLE.copy()
            
            # El bucle principal del menú
            # Elige el ítem y mapea a la acción correcta
            final_menu_items = [item for item in menu_items if item is not None and not item.startswith("[ ]")]
            
            # Se crea un mapa de acciones basado en la posición en el menú final
            # para evitar errores de índice.
            action_map = {}
            action_idx = 0
            for item in menu_items:
                if item is None or item.startswith("[ ]"):
                    continue
                
                if "[r]" in item: action_map[action_idx] = "refresh"
                elif "[h]" in item: action_map[action_idx] = "help"
                elif "[b]" in item: action_map[action_idx] = "back"
                else:
                    if action_idx < len(actions):
                         action_map[action_idx] = actions[action_idx]
                action_idx += 1

            main_menu = TerminalMenu(final_menu_items, title="\nAcciones:", **menu_options)
            choice_index = main_menu.show()
            action = action_map.get(choice_index)
            # --- FIN DE LA MODIFICACIÓN ---

            if action == "start_new": _wizards.operation_setup_wizard(om_api, side, is_modification=False)
            elif action == "modify": _wizards.operation_setup_wizard(om_api, side, is_modification=True)
            elif action == "manual_manage": manual_position_manager.show_manual_position_manager_screen(side)
            elif action == "pause": om_api.pausar_operacion(side); time.sleep(0.2)
            elif action == "resume": om_api.reanudar_operacion(side); time.sleep(0.2)
            elif action == "force_start":
                if TerminalMenu(["[1] Sí, forzar inicio", "[2] No, cancelar"], title="¿Activar la operación ignorando la condición de entrada?").show() == 0:
                    om_api.forzar_activacion_manual(side); time.sleep(0.2)
            elif action == "stop":
                title = "¿Seguro? Se cerrarán todas las posiciones y se reseteará la operación."
                if TerminalMenu(["[1] Sí, detener todo", "[2] No, cancelar"], title=title).show() == 0:
                    print("\n\033[93mProcesando solicitud de detención, por favor espere...\033[0m")
                    success, message = om_api.detener_operacion(side, forzar_cierre_posiciones=True)
                    print(f"\nResultado: {'ÉXITO' if success else 'FALLO'} - {message}"); time.sleep(2.5)
            elif action == "refresh": continue
            elif action == "help": show_help_popup("auto_mode")
            elif action == "back" or action is None: break
        
        except Exception as e:
            clear_screen()
            header_title = f"Panel de Operación {side.upper()} - ERROR"
            print_tui_header(title=header_title, subtitle="Ocurrió un error crítico")
            print(f"\n\033[91mERROR CRÍTICO: {e}\033[0m\nOcurrió un error inesperado al renderizar la pantalla.")
            traceback.print_exc()
            press_enter_to_continue()
            break