# core/menu/screens/_auto_mode.py

"""
Módulo para la Pantalla del Modo Automático por Hitos (Árbol de Decisiones).

Permite al usuario crear, visualizar y eliminar 'Hitos', que son triggers
condicionales basados en el precio y que se organizan en un árbol jerárquico.
"""
import time
from typing import Any, Dict, List

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Menú ---
from .._helpers import clear_screen, print_tui_header, get_input, MENU_STYLE

def show_auto_mode_screen(pm_api: Any):
    """
    Muestra el menú principal para la gestión del Árbol de Decisiones.

    Args:
        pm_api: El objeto API del Position Manager para interactuar con él.
    """
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado.")
        time.sleep(2)
        return

    while True:
        clear_screen()
        print_tui_header("Modo Automático: Árbol de Decisiones por Hitos")

        # Visualizar el árbol de decisiones actual
        _display_decision_tree(pm_api)

        menu_items = [
            "[1] Crear Nuevo Hito",
            "[2] Eliminar un Hito existente",
            None,
            "[r] Refrescar vista del árbol",
            "[b] Volver al Dashboard Principal"
        ]
        main_menu = TerminalMenu(menu_items, title="\nAcciones del Árbol de Decisiones", **MENU_STYLE)
        choice = main_menu.show()

        if choice == 0:
            _create_milestone_wizard(pm_api)
        elif choice == 1:
            _delete_milestone_wizard(pm_api)
        elif choice == 3: # Refrescar
            continue
        else: # Salir
            break

def _display_decision_tree(pm_api: Any):
    """Muestra una representación textual del árbol de decisiones."""
    print("\n--- Árbol de Decisiones Activo ---")
    
    # En esta versión, los "Hitos" son los "Triggers" del Position Manager.
    # Una versión más avanzada podría tener su propia estructura de datos para el árbol.
    triggers = pm_api.get_all_triggers()

    if not triggers:
        print("  (No hay hitos definidos)")
        return

    # Por ahora, mostramos una lista simple.
    # La lógica de niveles requeriría un modelo de datos más complejo.
    for i, trigger in enumerate(triggers):
        cond = trigger.get('condition', {})
        act = trigger.get('action', {})
        status = "ACTIVO" if trigger.get('is_active') else "INACTIVO/CUMPLIDO"
        
        cond_str = f"SI Precio {cond.get('type', '').replace('_', ' ')} {cond.get('value')}"
        action_str = f"ENTONCES {act.get('type', '').replace('_', ' ')} con params {act.get('params', {})}"
        
        print(f"  (Hito {i+1}) [{status}] ID: ...{trigger.get('id', '')[-6:]}")
        print(f"    └─ Condición: {cond_str}")
        print(f"       └─ Acción: {action_str}")

def _create_milestone_wizard(pm_api: Any):
    """Asistente paso a paso para crear un nuevo hito (trigger)."""
    clear_screen()
    print_tui_header("Crear Nuevo Hito")
    
    current_price = pm_api.get_current_price_for_exit() or 0.0
    print(f"\nPrecio de Mercado Actual: {current_price:.4f} USDT\n")

    # 1. Definir la Condición
    cond_type_idx = TerminalMenu(["[1] Precio SUBE POR ENCIMA DE", "[2] Precio BAJA POR DEBAJO DE"], title="Elige la condición del hito:").show()
    if cond_type_idx is None: return
    cond_type = "PRICE_ABOVE" if cond_type_idx == 0 else "PRICE_BELOW"
    cond_value = get_input(f"Introduce el precio objetivo para '{cond_type.replace('_', ' ')}'", float, min_val=0.0)

    # 2. Definir la Acción
    action_menu_items = [
        "[1] Iniciar Nueva Tendencia Guiada",
        "[2] Cambiar a Modo de Trading Simple (sin límites)",
        "[3] Forzar Cierre de TODAS las posiciones LONG",
        "[4] Forzar Cierre de TODAS las posiciones SHORT"
    ]
    action_type_idx = TerminalMenu(action_menu_items, title="\nElige la acción a ejecutar cuando se cumpla la condición:").show()
    if action_type_idx is None: return

    action = {}
    if action_type_idx == 0: # Iniciar Nueva Tendencia Guiada
        print("\n--- Configurando la Tendencia para este Hito ---")
        mode_idx = TerminalMenu(["[1] LONG_ONLY", "[2] SHORT_ONLY"], title="Elige el modo de la tendencia:").show()
        if mode_idx is None: return
        trend_mode = "LONG_ONLY" if mode_idx == 0 else "SHORT_ONLY"
        
        trade_limit = get_input("Límite de trades (0 para ilimitado)", int, default=0, min_val=0)
        duration = get_input("Duración máxima (min, 0 para ilimitado)", int, default=0, min_val=0)
        tp_roi = get_input("Objetivo de TP por ROI (%, ej: 2.5, 0 para desactivar)", float, default=0.0, min_val=0.0)
        sl_roi = get_input("Objetivo de SL por ROI (%, ej: -1.5, 0 para desactivar)", float, default=0.0, max_val=0.0)

        action = {
            "type": "START_MANUAL_TREND", 
            "params": {
                "mode": trend_mode,
                "trade_limit": trade_limit if trade_limit > 0 else None,
                "duration_limit": duration if duration > 0 else None,
                "tp_roi_limit": tp_roi if tp_roi > 0 else None,
                "sl_roi_limit": sl_roi if sl_roi < 0 else None
            }
        }

    elif action_type_idx == 1: # Cambiar Modo Simple
        mode_idx = TerminalMenu(["[1] LONG_SHORT", "[2] LONG_ONLY", "[3] SHORT_ONLY", "[4] NEUTRAL"], title="Elige el nuevo modo:").show()
        if mode_idx is None: return
        mode_str = ["LONG_SHORT", "LONG_ONLY", "SHORT_ONLY", "NEUTRAL"][mode_idx]
        action = {"type": "SET_MODE", "params": {"mode": mode_str}}
    
    elif action_type_idx == 2:
        action = {"type": "CLOSE_ALL_LONGS", "params": {}}
    elif action_type_idx == 3:
        action = {"type": "CLOSE_ALL_SHORTS", "params": {}}

    if action:
        success, msg = pm_api.add_conditional_trigger(
            condition={"type": cond_type, "value": cond_value},
            action=action
        )
        print(f"\n{msg}")
        time.sleep(2)

def _delete_milestone_wizard(pm_api: Any):
    """Asistente para seleccionar y eliminar un hito existente."""
    triggers = pm_api.get_all_triggers()
    if not triggers:
        print("\nNo hay hitos para eliminar.")
        time.sleep(1.5)
        return

    menu_items = []
    for trigger in triggers:
        cond = trigger.get('condition', {})
        menu_items.append(f"ID: ...{trigger.get('id', '')[-12:]} | SI Precio {cond.get('type', '').replace('_', ' ')} {cond.get('value')}")

    title = "Selecciona el hito que deseas eliminar:"
    delete_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
    choice_index = delete_menu.show()

    if choice_index is not None:
        trigger_to_delete_id = triggers[choice_index]['id']
        success, msg = pm_api.remove_conditional_trigger(trigger_to_delete_id)
        print(f"\n{msg}")
        time.sleep(2)