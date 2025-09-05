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

# Reemplaza la función _edit_operation_risk_submenu completa en core/menu/screens/operation_manager/wizard_setup/_submenus_risk.py

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

        # --- INICIO DE LA MODIFICACIÓN (Paso 2.1) ---
        # Se añade la lógica para mostrar el estado del nuevo modo BE-SL/TP
        be_sl_tp_str = "Desactivado"
        if getattr(temp_op, 'be_sl_tp_enabled', False):
            sl_str = f"SL: {getattr(temp_op, 'be_sl_distance_pct', 'N/A')}%"
            tp_str = f"TP: {getattr(temp_op, 'be_tp_distance_pct', 'N/A')}%"
            be_sl_tp_str = f"{sl_str}, {tp_str}"
        # --- FIN DE LA MODIFICACIÓN ---

        risk_mode_title = "\nSelecciona una opción para editar:"
        
        # --- INICIO DE LA MODIFICACIÓN (Paso 2.1) ---
        # Se actualiza la lista de ítems del menú para incluir la nueva opción
        menu_items = [
            f"[1] Límite SL/TP por ROI ({sl_roi_str})", 
            f"[2] Límite TSL por ROI ({tsl_roi_str})",
            f"[3] SL/TP Fijos sobre Break-Even por Precio ({be_sl_tp_str})", # <-- NUEVA LÍNEA
            None,
            f"[4] Acción al alcanzar SL/TP por ROI ({temp_op.accion_por_sl_tp_roi})", # <-- Índice cambiado
            f"[5] Acción al alcanzar TSL por ROI ({temp_op.accion_por_tsl_roi})", # <-- Índice cambiado
            None,
            "[h] Ayuda", # Botón de ayuda añadido
            "[b] Volver al menú anterior"
        ]
        
        risk_mode_menu = TerminalMenu(
            menu_items,
            title=risk_mode_title,
            **MENU_STYLE
        )
        choice = risk_mode_menu.show()

        if choice is None or choice == 8: # El índice de "Volver" ahora es 8
            break
        # --- FIN DE LA MODIFICACIÓN (COMENTARIO): La sección eliminada se movió y adaptó arriba
        # --- (LÍNEA ORIGINAL ELIMINADA) ---
        # menu_items = [ ... ]
        # --- (LÍNEA ORIGINAL ELIMINADA) ---
        # risk_mode_menu = TerminalMenu( ... )
        # --- (LÍNEA ORIGINAL ELIMINADA) ---
        # choice = risk_mode_menu.show()
        # --- (LÍNEA ORIGINAL ELIMINADA) ---
        # if choice is None or choice == 7: break
        # --- FIN DE LA MODIFICACIÓN ---

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
            
            # --- INICIO DE LA MODIFICACIÓN (Paso 2.2) ---
            # Se añade la lógica para la nueva opción del menú
            elif choice == 2: # Lógica para la nueva opción
                # Preguntamos primero por el SL
                new_sl = get_input(
                    "Distancia SL desde Break-Even (%)", 
                    float, 
                    getattr(temp_op, 'be_sl_distance_pct', None), 
                    min_val=0.1, 
                    is_optional=True, 
                    context_info="Pérdida máxima desde break-even. Deja vacío para desactivar."
                )
                
                # Luego preguntamos por el TP
                new_tp = get_input(
                    "Distancia TP desde Break-Even (%)", 
                    float, 
                    getattr(temp_op, 'be_tp_distance_pct', None), 
                    min_val=0.1, 
                    is_optional=True, 
                    context_info="Ganancia objetivo desde break-even. Deja vacío para desactivar."
                )

                # Si se ha establecido al menos uno de los dos, se activa el modo.
                if new_sl is not None or new_tp is not None:
                    # Si los valores cambiaron, actualizamos y marcamos como cambiado
                    if new_sl != getattr(temp_op, 'be_sl_distance_pct', None) or new_tp != getattr(temp_op, 'be_tp_distance_pct', None):
                        temp_op.be_sl_tp_enabled = True
                        temp_op.be_sl_distance_pct = new_sl
                        temp_op.be_tp_distance_pct = new_tp
                        params_changed_in_submenu = True
                # Si ambos campos se dejaron vacíos, se desactiva el modo.
                elif getattr(temp_op, 'be_sl_tp_enabled', False):
                    temp_op.be_sl_tp_enabled = False
                    temp_op.be_sl_distance_pct = None
                    temp_op.be_tp_distance_pct = None
                    params_changed_in_submenu = True
            # --- FIN DE LA MODIFICACIÓN ---

            elif choice == 3: # Índice de "Acción SL/TP"
                new_action = get_action_menu("Acción al alcanzar SL/TP por ROI o Break-Even", temp_op.accion_por_sl_tp_roi)
                if new_action != temp_op.accion_por_sl_tp_roi:
                    temp_op.accion_por_sl_tp_roi = new_action
                    params_changed_in_submenu = True

            elif choice == 4: # Índice de "Acción TSL"
                new_action = get_action_menu("Acción al alcanzar TSL por ROI", temp_op.accion_por_tsl_roi)
                if new_action != temp_op.accion_por_tsl_roi:
                    temp_op.accion_por_tsl_roi = new_action
                    params_changed_in_submenu = True

            elif choice == 6: # Índice de Ayuda
                show_help_popup('wizard_risk_operation')

        except UserInputCancelled:
            print("\nEdición cancelada."); time.sleep(1)
            
    return params_changed_in_submenu