# Contenido completo y corregido para: core/menu/screens/operation_manager/position_editor/__init__.py

import time
import uuid
import copy
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

try:
    from core.strategy.entities import Operacion, LogicalPosition
    from core.strategy.pm import api as pm_api
    from core.strategy.om import api as om_api
    from . import _calculations as calc
    from . import _displayers as disp
except ImportError:
    # Fallbacks para análisis estático y resiliencia
    pm_api = None
    om_api = None
    calc = None
    disp = None
    class Operacion: pass
    class LogicalPosition: pass


# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función Única) ---
# ==============================================================================

def show_position_editor_screen(operacion: Operacion, side: str) -> bool:
    """
    Muestra la pantalla interactiva para gestionar la lista de posiciones
    y visualizar el impacto en el riesgo en tiempo real.

    Args:
        operacion (Operacion): El objeto de operación que se está editando.
        side (str): El lado de la operación ('long' o 'short').

    Returns:
        bool: True si se realizaron cambios en la lista de posiciones, False en caso contrario.
    """
    if not all([TerminalMenu, pm_api, om_api, calc, disp]):
        print("Error: Dependencias críticas para el editor de posiciones no están disponibles.")
        time.sleep(3)
        return False

    original_positions_state = copy.deepcopy(operacion.posiciones)
    params_changed = False
    
    while True:
        clear_screen()
        
        # --- INICIO DE LA CORRECCIÓN: Corregir el nombre de la función ---
        # Original: print_t_ui_header(...)
        # Corregido:
        print_tui_header(f"Editor de Posiciones y Riesgo - {side.upper()}")
        # --- FIN DE LA CORRECCIÓN ---
        
        current_price = pm_api.get_current_market_price() or 0.0

        risk_metrics = calc.calculate_projected_risk_metrics(
            operacion,
            current_price,
            side
        )

        disp.display_positions_table(operacion, current_price, side)
        disp.display_strategy_parameters(operacion)
        
        disp.display_risk_panel(risk_metrics, current_price, side, operacion=operacion)
        
        has_pending = operacion.posiciones_pendientes_count > 0
        has_open = operacion.posiciones_abiertas_count > 0
        
        menu_items = [
            "[1] Añadir nueva posición PENDIENTE",
            "[2] Modificar capital de TODAS las PENDIENTES",
            "[3] Eliminar la última PENDIENTE",
            None,
            "[4] Cerrar posición ABIERTA específica",
            None,
            "[s] Guardar Cambios y Volver",
            "[c] Cancelar y Volver (Descartar Cambios)"
        ]

        if not has_pending:
            menu_items[1] = "[2] Modificar capital... (No hay posiciones PENDIENTES)"
            menu_items[2] = "[3] Eliminar última... (No hay posiciones PENDIENTES)"
        if not has_open:
            menu_items[4] = "[4] Cerrar posición... (No hay posiciones ABIERTAS)"
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
        choice = menu.show()

        try:
            if choice == 0:
                capital = get_input("Capital a asignar para la nueva posición (USDT)", float, 1.0, min_val=0.1)
                new_pos = LogicalPosition(
                    id=f"pos_{uuid.uuid4().hex[:8]}", estado='PENDIENTE', 
                    capital_asignado=capital, valor_nominal=capital * operacion.apalancamiento
                )
                operacion.posiciones.append(new_pos)
                params_changed = True
            
            elif choice == 1:
                if not has_pending: continue
                nuevo_capital = get_input("Nuevo capital para TODAS las PENDIENTES (USDT)", float, 1.0, min_val=0.1)
                for pos in operacion.posiciones:
                    if pos.estado == 'PENDIENTE':
                        pos.capital_asignado = nuevo_capital
                        pos.valor_nominal = nuevo_capital * operacion.apalancamiento
                params_changed = True

            elif choice == 2:
                if not has_pending: continue
                last_pending_index = -1
                for i in range(len(operacion.posiciones) - 1, -1, -1):
                    if operacion.posiciones[i].estado == 'PENDIENTE':
                        last_pending_index = i
                        break
                if last_pending_index != -1:
                    operacion.posiciones.pop(last_pending_index)
                    print("\nÚltima posición PENDIENTE eliminada."); time.sleep(1.5)
                    params_changed = True

            elif choice == 4:
                if not has_open: continue
                open_positions = operacion.posiciones_abiertas
                submenu_items = [f"Cerrar ID: ...{p.id[-6:]}" for p in open_positions] + ["[c] Cancelar"]
                
                close_menu = TerminalMenu(submenu_items, title="Selecciona la posición ABIERTA a cerrar:", **MENU_STYLE)
                idx_to_close = close_menu.show()
                
                if idx_to_close is not None and idx_to_close < len(open_positions):
                    success, msg = pm_api.manual_close_logical_position_by_index(side, idx_to_close)
                    print(f"\nResultado: {msg}"); time.sleep(2.5)
                    if success:
                        temp_op_refreshed = om_api.get_operation_by_side(side)
                        if temp_op_refreshed:
                            operacion.posiciones = temp_op_refreshed.posiciones
                        params_changed = True

            elif choice == 6:
                return params_changed

            elif choice == 7 or choice is None:
                operacion.posiciones = original_positions_state
                print("\nCambios descartados.")
                time.sleep(1.5)
                return False

        except UserInputCancelled:
            print("\nAcción cancelada."); time.sleep(1)

# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================