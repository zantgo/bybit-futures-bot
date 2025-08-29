# core/menu/screens/operation_manager/position_editor/__init__.py

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


# --- INICIO DE LA MODIFICACIÓN (Paso 3 del Plan - Simplificación del Editor) ---
def show_position_editor_screen(operacion: Operacion, side: str) -> bool:
    """
    Muestra la pantalla interactiva para configurar la lista de posiciones PENDIENTES
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

    # Guardamos el estado original para poder cancelar los cambios
    original_positions_state = copy.deepcopy(operacion.posiciones)
    params_changed = False
    
    while True:
        clear_screen()
        print_tui_header(f"Editor de Posiciones y Riesgo - {side.upper()}")
        
        current_price = pm_api.get_current_market_price() or 0.0

        risk_metrics = calc.calculate_projected_risk_metrics(
            operacion,
            current_price,
            side
        )

        disp.display_positions_table(operacion, current_price, side)
        disp.display_strategy_parameters(operacion)
        disp.display_risk_panel(risk_metrics, current_price, side, operacion=operacion)
        
        has_pending = any(p.estado == 'PENDIENTE' for p in operacion.posiciones)
        
        # Menú simplificado enfocado solo en la configuración
        menu_items = [
            "[1] Añadir nueva posición PENDIENTE",
            "[2] Modificar capital de TODAS las PENDIENTES",
            "[3] Eliminar la última PENDIENTE",
            None,
            "[b] Volver al Asistente (Guardar Cambios)"
        ]

        if not has_pending:
            menu_items[1] = "[2] Modificar capital... (No hay posiciones PENDIENTES)"
            menu_items[2] = "[3] Eliminar última... (No hay posiciones PENDIENTES)"
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nAcciones de Configuración:", **menu_options)
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
                # Encontrar el índice de la última posición pendiente
                last_pending_index = -1
                for i in range(len(operacion.posiciones) - 1, -1, -1):
                    if operacion.posiciones[i].estado == 'PENDIENTE':
                        last_pending_index = i
                        break
                
                if last_pending_index != -1:
                    operacion.posiciones.pop(last_pending_index)
                    print("\nÚltima posición PENDIENTE eliminada."); time.sleep(1.5)
                    params_changed = True

            elif choice == 4 or choice is None:
                # Si el usuario elige volver, preguntamos si quiere descartar si hubo cambios
                if params_changed:
                    cancel_menu = TerminalMenu(["[1] Guardar y Volver", "[2] Descartar Cambios y Volver"], title="\nHay cambios sin guardar. ¿Qué deseas hacer?").show()
                    if cancel_menu == 1: # Descartar
                        operacion.posiciones = original_positions_state
                        return False
                return params_changed # Devuelve True si hubo cambios y se guardan, False si no hubo cambios

        except UserInputCancelled:
            print("\nAcción cancelada."); time.sleep(1)

# --- FIN DE LA MODIFICACIÓN ---