# core/menu/screens/operation_manager/wizard_setup/_submenus_risk.py

import time
from typing import Any, Dict

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from ...._helpers import (
    clear_screen,
    print_tui_header,
    get_input,
    MENU_STYLE,
    UserInputCancelled,
)
from core.strategy.entities import Operacion

def get_action_menu(prompt: str, current_action: str) -> str:
    clear_screen()
    print_tui_header("Selección de Acción")
    print(f"\n{prompt}")
    
    action_menu = TerminalMenu(
        ["[1] Pausar Operación", "[2] Detener y Resetear Operación"], 
        title=f"Acción actual: {current_action}\nSelecciona la nueva acción a realizar:", 
        **MENU_STYLE
    )
    choice = action_menu.show()
    
    if choice == 0: return 'PAUSAR'
    if choice == 1: return 'DETENER'
    return current_action

# --- INICIO DE LA MODIFICACIÓN ---
# La función _edit_operation_risk_submenu ha sido completamente refactorizada.
def _edit_operation_risk_submenu(temp_op: Operacion):
    """
    Submenú rediseñado para la gestión granular de cada tipo de riesgo de operación.
    """
    from ...._helpers import show_help_popup
    params_changed_in_submenu = False
    
    while True:
        clear_screen()
        print_tui_header("Editor de Riesgo de Operación")

        # --- Funciones de ayuda para formatear el estado actual ---
        def format_sl_tp(data: Dict, label: str) -> str:
            if data:
                return f"{data.get('valor', 'N/A')}% (Acción: {data.get('accion', 'N/A')})"
            return "Desactivado"

        def format_tsl(data: Dict) -> str:
            if data:
                return f"Act: {data.get('activacion', 'N/A')}%, Dist: {data.get('distancia', 'N/A')}% (Acción: {data.get('accion', 'N/A')})"
            return "Desactivado"
        
        def format_dynamic_sl(data: Dict) -> str:
            if data:
                return f"Dist: {data.get('distancia', 'N/A')}% del ROI Realizado (Acción: {data.get('accion', 'N/A')})"
            return "Desactivado"

        def format_be_sl_tp(data: Dict, label: str) -> str:
            if data:
                return f"{data.get('distancia', 'N/A')}% (Acción: {data.get('accion', 'N/A')})"
            return "Desactivado"

        # --- Creación de los ítems del menú ---
        menu_items = [
            f"[1] Stop Loss por ROI: {format_sl_tp(temp_op.roi_sl, 'SL')}",
            f"[2] Take Profit por ROI: {format_sl_tp(temp_op.roi_tp, 'TP')}",
            f"[3] Trailing Stop Loss por ROI: {format_tsl(temp_op.roi_tsl)}",
            f"[4] Stop Loss Dinámico por ROI: {format_dynamic_sl(temp_op.dynamic_roi_sl)}",
            None,
            f"[5] Stop Loss por Break-Even: {format_be_sl_tp(temp_op.be_sl, 'SL')}",
            f"[6] Take Profit por Break-Even: {format_be_sl_tp(temp_op.be_tp, 'TP')}",
            None,
            "[d] Desactivar TODOS los límites de riesgo",
            "[h] Ayuda",
            "[b] Volver al menú anterior"
        ]
        
        risk_mode_menu = TerminalMenu(
            menu_items,
            title="\nSelecciona un límite de riesgo para configurar:",
            **MENU_STYLE
        )
        choice = risk_mode_menu.show()

        if choice is None or choice == 10:
            break

        try:
            # Opción 1: SL por ROI
            if choice == 0:
                current_val = temp_op.roi_sl.get('valor') if temp_op.roi_sl else None
                current_act = temp_op.roi_sl.get('accion', 'DETENER') if temp_op.roi_sl else 'DETENER'
                new_val = get_input("Nuevo SL por ROI (%)", float, current_val, is_optional=True, context_info="Valor negativo. Deja vacío para desactivar.")
                if new_val is not None:
                    new_act = get_action_menu("Acción al alcanzar el SL por ROI", current_act)
                    temp_op.roi_sl = {'valor': new_val, 'accion': new_act}
                else:
                    temp_op.roi_sl = None
                params_changed_in_submenu = True

            # Opción 2: TP por ROI
            elif choice == 1:
                current_val = temp_op.roi_tp.get('valor') if temp_op.roi_tp else None
                current_act = temp_op.roi_tp.get('accion', 'PAUSAR') if temp_op.roi_tp else 'PAUSAR'
                new_val = get_input("Nuevo TP por ROI (%)", float, current_val, is_optional=True, context_info="Valor positivo. Deja vacío para desactivar.")
                if new_val is not None:
                    new_act = get_action_menu("Acción al alcanzar el TP por ROI", current_act)
                    temp_op.roi_tp = {'valor': new_val, 'accion': new_act}
                else:
                    temp_op.roi_tp = None
                params_changed_in_submenu = True

            # Opción 3: TSL por ROI
            elif choice == 2:
                current_act = temp_op.roi_tsl.get('activacion') if temp_op.roi_tsl else None
                current_dist = temp_op.roi_tsl.get('distancia') if temp_op.roi_tsl else None
                current_action = temp_op.roi_tsl.get('accion', 'PAUSAR') if temp_op.roi_tsl else 'PAUSAR'
                new_act = get_input("Nueva Activación TSL (%)", float, current_act, min_val=0.1, is_optional=True, context_info="Deja vacío para desactivar.")
                if new_act is not None:
                    new_dist = get_input("Nueva Distancia TSL (%)", float, current_dist, min_val=0.1)
                    new_action = get_action_menu("Acción al alcanzar el TSL", current_action)
                    temp_op.roi_tsl = {'activacion': new_act, 'distancia': new_dist, 'accion': new_action}
                else:
                    temp_op.roi_tsl = None
                params_changed_in_submenu = True
            
            # Opción 4: SL Dinámico
            elif choice == 3:
                current_val = temp_op.dynamic_roi_sl.get('distancia') if temp_op.dynamic_roi_sl else None
                current_act = temp_op.dynamic_roi_sl.get('accion', 'DETENER') if temp_op.dynamic_roi_sl else 'DETENER'
                new_val = get_input("Nueva Distancia del SL Dinámico (%)", float, current_val, min_val=0.1, is_optional=True, context_info="Distancia desde ROI realizado. Deja vacío para desactivar.")
                if new_val is not None:
                    new_act = get_action_menu("Acción al alcanzar el SL Dinámico", current_act)
                    temp_op.dynamic_roi_sl = {'distancia': new_val, 'accion': new_act}
                else:
                    temp_op.dynamic_roi_sl = None
                params_changed_in_submenu = True

            # Opción 5: SL por Break-Even
            elif choice == 5:
                current_val = temp_op.be_sl.get('distancia') if temp_op.be_sl else None
                current_act = temp_op.be_sl.get('accion', 'DETENER') if temp_op.be_sl else 'DETENER'
                new_val = get_input("Nueva Distancia SL desde Break-Even (%)", float, current_val, min_val=0.1, is_optional=True, context_info="Deja vacío para desactivar.")
                if new_val is not None:
                    new_act = get_action_menu("Acción al alcanzar SL por Break-Even", current_act)
                    temp_op.be_sl = {'distancia': new_val, 'accion': new_act}
                else:
                    temp_op.be_sl = None
                params_changed_in_submenu = True
            
            # Opción 6: TP por Break-Even
            elif choice == 6:
                current_val = temp_op.be_tp.get('distancia') if temp_op.be_tp else None
                current_act = temp_op.be_tp.get('accion', 'PAUSAR') if temp_op.be_tp else 'PAUSAR'
                new_val = get_input("Nueva Distancia TP desde Break-Even (%)", float, current_val, min_val=0.1, is_optional=True, context_info="Deja vacío para desactivar.")
                if new_val is not None:
                    new_act = get_action_menu("Acción al alcanzar TP por Break-Even", current_act)
                    temp_op.be_tp = {'distancia': new_val, 'accion': new_act}
                else:
                    temp_op.be_tp = None
                params_changed_in_submenu = True

            # Opción Desactivar Todo
            elif choice == 8:
                temp_op.roi_sl, temp_op.roi_tp, temp_op.roi_tsl, temp_op.dynamic_roi_sl, temp_op.be_sl, temp_op.be_tp = None, None, None, None, None, None
                print("\nTodos los límites de riesgo de operación han sido desactivados.")
                time.sleep(1.5)
                params_changed_in_submenu = True

            # Opción Ayuda
            elif choice == 9:
                show_help_popup('wizard_risk_operation')

        except UserInputCancelled:
            print("\nEdición cancelada."); time.sleep(1)
            
    return params_changed_in_submenu
# --- FIN DE LA MODIFICACIÓN ---