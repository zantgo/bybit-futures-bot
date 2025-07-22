"""
Módulo para la Pantalla del Modo Automático por Hitos (Árbol de Decisiones).

Permite al usuario crear, visualizar y eliminar 'Hitos', que son triggers
condicionales basados en el precio y que se organizan en un árbol jerárquico.
"""
import time
from typing import Any, Dict, List, Optional

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

        # Visualizar el árbol de decisiones actual con la nueva lógica jerárquica
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
        else: # Salir o ESC
            break

def _display_decision_tree(pm_api: Any):
    """Muestra una representación textual y jerárquica del árbol de decisiones."""
    print("\n--- Árbol de Decisiones Activo ---")
    
    milestones = pm_api.get_all_milestones()

    if not milestones:
        print("  (No hay hitos definidos)")
        return

    # Organizar hitos en una estructura de árbol para facilitar la impresión
    tree = {None: []} # Usamos None como la clave para los hitos raíz (Nivel 1)
    for m in milestones:
        pid = m.parent_id
        if pid not in tree:
            tree[pid] = []
        tree[pid].append(m)
        
    # Función recursiva para imprimir el árbol
    def print_branch(parent_id, prefix=""):
        if parent_id not in tree:
            return
        
        # Ordenar los hijos para una visualización consistente
        children = sorted(tree[parent_id], key=lambda m: m.created_at)
        
        for i, milestone in enumerate(children):
            is_last = (i == len(children) - 1)
            connector = "└─" if is_last else "├─"
            
            # Formatear la información del hito
            status_color_map = {
                "ACTIVE": "\x1b[92m", # Verde
                "PENDING": "\x1b[93m", # Amarillo
                "COMPLETED": "\x1b[90m", # Gris
                "CANCELLED": "\x1b[91m"  # Rojo
            }
            color = status_color_map.get(milestone.status, "")
            reset_color = "\x1b[0m"
            
            status_str = f"[{color}{milestone.status}{reset_color}]"
            cond_str = f"SI Precio {milestone.condition.type.replace('_', ' ')} {milestone.condition.value}"
            
            print(f"{prefix}{connector} (Lvl {milestone.level}) {status_str} {cond_str} (ID: ...{milestone.id[-6:]})")
            
            # Preparar el prefijo para los hijos de este nodo
            child_prefix = prefix + ("    " if is_last else "│   ")
            print_branch(milestone.id, child_prefix)

    # Iniciar la impresión desde la raíz
    print_branch(None)


def _create_milestone_wizard(pm_api: Any):
    """Asistente paso a paso para crear un nuevo hito, permitiendo seleccionar un padre."""
    clear_screen()
    print_tui_header("Crear Nuevo Hito")
    
    current_price = pm_api.get_current_price_for_exit() or 0.0
    print(f"\nPrecio de Mercado Actual: {current_price:.4f} USDT\n")

    # 0. Seleccionar Padre
    parent_id: Optional[str] = None
    all_milestones = pm_api.get_all_milestones()
    # Solo se pueden seleccionar como padres los hitos que no están en un estado final
    selectable_parents = [m for m in all_milestones if m.status in ['PENDING', 'ACTIVE']]

    if selectable_parents:
        parent_menu_items = ["[1] Hito de Nivel 1 (Sin padre)"]
        parent_menu_items.extend(
            f"[{i+2}] Padre: Lvl {m.level} - SI Precio {m.condition.type.replace('_', ' ')} {m.condition.value} (ID: ...{m.id[-6:]})"
            for i, m in enumerate(selectable_parents)
        )
        parent_choice = TerminalMenu(parent_menu_items, title="¿Este hito depende de otro existente?").show()
        
        if parent_choice is None: return
        if parent_choice > 0:
            parent_id = selectable_parents[parent_choice - 1].id

    # 1. Definir la Condición (Lógica existente, sin cambios)
    cond_type_idx = TerminalMenu(["[1] Precio SUBE POR ENCIMA DE", "[2] Precio BAJA POR DEBAJO DE"], title="\nElige la condición del hito:").show()
    if cond_type_idx is None: return
    cond_type = "PRICE_ABOVE" if cond_type_idx == 0 else "PRICE_BELOW"
    cond_value = get_input(f"Introduce el precio objetivo para '{cond_type.replace('_', ' ')}'", float, min_val=0.0)
    condition_data = {"type": cond_type, "value": cond_value}

    # 2. Definir la Acción (Lógica existente, sin cambios)
    action_menu_items = [
        "[1] Iniciar Nueva Tendencia Guiada",
        "[2] Cambiar a Modo de Trading Simple",
        "[3] Forzar Cierre de TODAS las posiciones LONG",
        "[4] Forzar Cierre de TODAS las posiciones SHORT"
    ]
    action_type_idx = TerminalMenu(action_menu_items, title="\nElige la acción a ejecutar:").show()
    if action_type_idx is None: return

    action_data = {}
    # (El código para definir los parámetros de la acción es idéntico al original,
    # solo se cambia el nombre de la variable final a `action_data`)
    if action_type_idx == 0:
        print("\n--- Configurando la Tendencia para este Hito ---")
        mode_idx = TerminalMenu(["[1] LONG_ONLY", "[2] SHORT_ONLY"], title="Elige el modo de la tendencia:").show()
        if mode_idx is None: return
        trend_mode = "LONG_ONLY" if mode_idx == 0 else "SHORT_ONLY"
        trade_limit = get_input("Límite de trades (0 para ilimitado)", int, default=0, min_val=0)
        duration = get_input("Duración máxima (min, 0 para ilimitado)", int, default=0, min_val=0)
        tp_roi = get_input("Objetivo de TP por ROI (%, ej: 2.5, 0 para desactivar)", float, default=0.0, min_val=0.0)
        sl_roi = get_input("Objetivo de SL por ROI (%, ej: -1.5, 0 para desactivar)", float, default=0.0, max_val=0.0)
        action_data = {"type": "START_MANUAL_TREND", "params": {"mode": trend_mode, "trade_limit": trade_limit or None, "duration_limit": duration or None, "tp_roi_limit": tp_roi or None, "sl_roi_limit": sl_roi or None}}
    elif action_type_idx == 1:
        mode_idx = TerminalMenu(["[1] LONG_SHORT", "[2] LONG_ONLY", "[3] SHORT_ONLY", "[4] NEUTRAL"], title="Elige el nuevo modo:").show()
        if mode_idx is None: return
        mode_str = ["LONG_SHORT", "LONG_ONLY", "SHORT_ONLY", "NEUTRAL"][mode_idx]
        action_data = {"type": "SET_MODE", "params": {"mode": mode_str}}
    elif action_type_idx == 2:
        action_data = {"type": "CLOSE_ALL_LONGS", "params": {}}
    elif action_type_idx == 3:
        action_data = {"type": "CLOSE_ALL_SHORTS", "params": {}}

    # 3. Llamar a la nueva API del PM
    if action_data:
        success, msg = pm_api.add_milestone(
            condition_data=condition_data,
            action_data=action_data,
            parent_id=parent_id
        )
        print(f"\n{msg}")
        time.sleep(2.5)

def _delete_milestone_wizard(pm_api: Any):
    """Asistente para seleccionar y eliminar un hito existente."""
    milestones = pm_api.get_all_milestones()
    if not milestones:
        print("\nNo hay hitos para eliminar.")
        time.sleep(1.5)
        return

    # Mostrar todos los hitos para que el usuario pueda seleccionar cuál eliminar
    menu_items = [
        f"Lvl {m.level} - SI Precio {m.condition.type.replace('_', ' ')} {m.condition.value} (ID: ...{m.id[-12:]})"
        for m in milestones
    ]

    title = "Selecciona el hito que deseas eliminar:"
    delete_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
    choice_index = delete_menu.show()

    if choice_index is not None:
        milestone_to_delete_id = milestones[choice_index].id
        # Confirmación
        confirm_menu = TerminalMenu(["[1] Sí, eliminar este hito", "[2] No, cancelar"], title=f"¿Confirmas eliminar el hito ...{milestone_to_delete_id[-12:]}?\n(Nota: Los hitos hijos no se eliminarán, pero quedarán huérfanos y nunca se activarán. Elimínalos primero si es necesario)").show()
        if confirm_menu == 0:
            success, msg = pm_api.remove_milestone(milestone_to_delete_id)
            print(f"\n{msg}")
            time.sleep(2)