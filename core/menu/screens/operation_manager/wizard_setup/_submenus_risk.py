# core/menu/screens/operation_manager/wizard_setup/_submenus_risk.py

import time
from typing import Any

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

def _edit_operation_risk_submenu(temp_op: Operacion):
    from ...._helpers import show_help_popup # <-- Importación añadida
    params_changed_in_submenu = False
    
    while True:
        clear_screen()
        print_tui_header("Editor de Riesgo de Operación")
        
        sl_roi_str = "Desactivado"
        if getattr(temp_op, 'dynamic_roi_sl_enabled', False):
            sl_roi_str = f"DINÁMICO (ROI Realizado - {getattr(temp_op, 'dynamic_roi_sl_trail_pct', 0)}%)"
        elif temp_op.sl_roi_pct is not None:
            sl_roi_str = f"MANUAL ({temp_op.sl_roi_pct}%)"
        
        tsl_roi_str = "Desactivado"
        if temp_op.tsl_roi_activacion_pct is not None:
             tsl_roi_str = f"Activación a +{temp_op.tsl_roi_activacion_pct}%, Distancia {temp_op.tsl_roi_distancia_pct}%"

        be_sl_tp_str = "Desactivado"
        if getattr(temp_op, 'be_sl_tp_enabled', False):
            sl_str = f"SL: {getattr(temp_op, 'be_sl_distance_pct', 'N/A')}%"
            tp_str = f"TP: {getattr(temp_op, 'be_tp_distance_pct', 'N/A')}%"
            be_sl_tp_str = f"{sl_str}, {tp_str}"

        risk_mode_title = "\nSelecciona una opción para editar:"
        
        menu_items = [
            f"[1] Límite SL/TP por ROI ({sl_roi_str})", 
            f"[2] Límite TSL por ROI ({tsl_roi_str})",
            f"[3] SL/TP Fijos sobre Break-Even por Precio ({be_sl_tp_str})",
            None,
            f"[4] Acción al alcanzar SL/TP por ROI ({temp_op.accion_por_sl_tp_roi})",
            f"[5] Acción al alcanzar TSL por ROI ({temp_op.accion_por_tsl_roi})",
            f"[6] Acción al alcanzar SL/TP por Break-Even ({temp_op.accion_por_be_sl_tp})",
            None,
            "[h] Ayuda",
            "[b] Volver al menú anterior"
        ]
        
        risk_mode_menu = TerminalMenu(
            menu_items,
            title=risk_mode_title,
            **MENU_STYLE
        )
        choice = risk_mode_menu.show()

        if choice is None or choice == 9: # El índice de "Volver" ahora es 9
            break

        try:
            if choice == 0:
                sl_tp_menu = TerminalMenu(["[1] Límite Manual (Fijo)", "[2] Límite Dinámico (Automático)", "[d] Desactivar por completo"], title="\nModo para SL/TP por ROI:").show()
                if sl_tp_menu == 0:
                    temp_op.dynamic_roi_sl_enabled = False
                    temp_op.dynamic_roi_sl_trail_pct = None
                    new_val = get_input("Límite SL/TP por ROI (%)", float, temp_op.sl_roi_pct, context_info="Valores negativos son SL, positivos son TP.")
                    if new_val != temp_op.sl_roi_pct: temp_op.sl_roi_pct = new_val; params_changed_in_submenu = True
                elif sl_tp_menu == 1:
                    temp_op.dynamic_roi_sl_enabled = True
                    temp_op.sl_roi_pct = None
                    new_val = get_input("Distancia del Trailing Stop al ROI Realizado (%)", float, temp_op.dynamic_roi_sl_trail_pct, min_val=0.1)
                    if new_val != temp_op.dynamic_roi_sl_trail_pct: temp_op.dynamic_roi_sl_trail_pct = new_val; params_changed_in_submenu = True
                elif sl_tp_menu == 2:
                    if temp_op.dynamic_roi_sl_enabled or temp_op.sl_roi_pct is not None:
                        temp_op.dynamic_roi_sl_enabled, temp_op.dynamic_roi_sl_trail_pct, temp_op.sl_roi_pct = False, None, None
                        params_changed_in_submenu = True

            elif choice == 1:
                tsl_act = get_input("Límite TSL-ROI Activación (%)", float, temp_op.tsl_roi_activacion_pct, min_val=0.0, is_optional=True, context_info="Introduce un valor para activar o deja vacío para desactivar.")
                if tsl_act is not None:
                    dist = get_input("Límite TSL-ROI Distancia (%)", float, temp_op.tsl_roi_distancia_pct, min_val=0.01)
                    if tsl_act != temp_op.tsl_roi_activacion_pct or dist != temp_op.tsl_roi_distancia_pct:
                        temp_op.tsl_roi_activacion_pct, temp_op.tsl_roi_distancia_pct = tsl_act, dist
                        params_changed_in_submenu = True
                else:
                    if temp_op.tsl_roi_activacion_pct is not None:
                        temp_op.tsl_roi_activacion_pct, temp_op.tsl_roi_distancia_pct = None, None
                        params_changed_in_submenu = True
            
            elif choice == 2:
                new_sl = get_input(
                    "Distancia SL desde Break-Even (%)", 
                    float, 
                    temp_op.be_sl_distance_pct, 
                    min_val=0.1, 
                    is_optional=True, 
                    context_info="Pérdida máxima desde break-even. Deja vacío para desactivar."
                )
                
                new_tp = get_input(
                    "Distancia TP desde Break-Even (%)", 
                    float, 
                    temp_op.be_tp_distance_pct, 
                    min_val=0.1, 
                    is_optional=True, 
                    context_info="Ganancia objetivo desde break-even. Deja vacío para desactivar."
                )

                if new_sl is not None or new_tp is not None:
                    if new_sl != temp_op.be_sl_distance_pct or new_tp != temp_op.be_tp_distance_pct:
                        temp_op.be_sl_tp_enabled = True
                        temp_op.be_sl_distance_pct = new_sl
                        temp_op.be_tp_distance_pct = new_tp
                        params_changed_in_submenu = True
                elif temp_op.be_sl_tp_enabled:
                    temp_op.be_sl_tp_enabled = False
                    temp_op.be_sl_distance_pct = None
                    temp_op.be_tp_distance_pct = None
                    params_changed_in_submenu = True
            
            # --- INICIO DE LA MODIFICACIÓN ---
            # Se han corregido los índices para que coincidan con el menú actualizado.
            elif choice == 4: # El índice [4] ahora es Acción al alcanzar SL/TP por ROI
                new_action = get_action_menu("Acción al alcanzar SL/TP por ROI", temp_op.accion_por_sl_tp_roi)
                if new_action != temp_op.accion_por_sl_tp_roi:
                    temp_op.accion_por_sl_tp_roi = new_action
                    params_changed_in_submenu = True

            elif choice == 5: # El índice [5] ahora es Acción al alcanzar TSL por ROI
                new_action = get_action_menu("Acción al alcanzar TSL por ROI", temp_op.accion_por_tsl_roi)
                if new_action != temp_op.accion_por_tsl_roi:
                    temp_op.accion_por_tsl_roi = new_action
                    params_changed_in_submenu = True
            
            elif choice == 6: # El índice [6] ahora es la nueva Acción por Break-Even
                new_action = get_action_menu(
                    "Acción al alcanzar SL/TP por Break-Even", 
                    temp_op.accion_por_be_sl_tp
                )
                if new_action != temp_op.accion_por_be_sl_tp:
                    temp_op.accion_por_be_sl_tp = new_action
                    params_changed_in_submenu = True
            
            elif choice == 8: # El índice [h] Ayuda ahora es 8
                show_help_popup('wizard_risk_operation')
            # --- FIN DE LA MODIFICACIÓN ---

        except UserInputCancelled:
            print("\nEdición cancelada."); time.sleep(1)
            
    return params_changed_in_submenu