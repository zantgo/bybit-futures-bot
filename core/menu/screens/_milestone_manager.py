"""
Módulo para la Pantalla de Gestión de Hitos (Árbol de Decisiones).

Esta pantalla centraliza toda la interacción del usuario con la estrategia del bot.
Permite crear, visualizar, actualizar y eliminar 'Hitos' (CRUD), que son triggers
condicionales organizados en un árbol jerárquico.
"""
import time
from typing import Any, Dict, Optional, List

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen,
    print_tui_header,
    get_input,
    MENU_STYLE,
    show_help_popup
)

# --- INYECCIÓN DE DEPENDENCIAS ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el paquete de pantallas."""
    global _deps
    _deps = dependencies

# --- LÓGICA DE LA PANTALLA PRINCIPAL ---

def show_milestone_manager_screen():
    """
    Muestra el menú principal para la gestión del Árbol de Decisiones,
    con una vista persistente del árbol en la parte superior.
    """
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado.")
        time.sleep(2)
        return

    pm_api = _deps.get("position_manager_api_module")
    if not pm_api:
        print("ERROR CRÍTICO: PM API no inyectada en Milestone Manager.")
        time.sleep(3)
        return

    while True:
        # 1. Limpiar la pantalla y dibujar la información estática
        clear_screen()
        print_tui_header("Gestor de Hitos (Árbol de Decisiones)")
        _display_decision_tree(pm_api)

        # 2. Crear y mostrar el menú interactivo
        menu_items = [
            "[1] Crear Nuevo Hito",
            "[2] Eliminar un Hito existente",
            # "[3] Modificar un Hito existente", # Funcionalidad futura
            None,
            "[h] Ayuda sobre esta pantalla",
            "[r] Refrescar vista del árbol",
            None,
            "[b] Volver al Dashboard Principal"
        ]
        
        # Usamos el estilo base y le decimos que no limpie la pantalla
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False

        main_menu = TerminalMenu(menu_items, title="\nAcciones del Árbol de Decisiones", **menu_options)
        choice = main_menu.show()

        # Mapeo de acciones basado en los índices del menú
        if choice == 0:
            _create_milestone_wizard(pm_api)
        elif choice == 1:
            _delete_milestone_wizard(pm_api)
        elif choice == 3:
            show_help_popup("auto_mode")
        elif choice == 4:
            continue
        else: # Salir, ESC o [b]
            break

# --- FUNCIONES DE VISUALIZACIÓN Y ASISTENTES (PRIVADOS) ---

def _display_decision_tree(pm_api: Any):
    """Muestra una representación textual y jerárquica del árbol de decisiones."""
    print("\n--- Árbol de Decisiones Activo ---")
    
    milestones = pm_api.get_all_milestones()

    if not milestones:
        print("  (No hay hitos definidos. Crea uno para empezar a operar.)")
        return

    tree = {None: []}
    for m in milestones:
        pid = m.parent_id
        if pid not in tree:
            tree[pid] = []
        tree[pid].append(m)
        
    def print_branch(parent_id, prefix=""):
        if parent_id not in tree:
            return
        
        children = sorted(tree[parent_id], key=lambda m: m.created_at)
        
        for i, milestone in enumerate(children):
            is_last = (i == len(children) - 1)
            connector = "└─" if is_last else "├─"
            
            status_color_map = {
                "ACTIVE": "\x1b[92m", # Verde
                "PENDING": "\x1b[93m", # Amarillo
                "COMPLETED": "\x1b[90m", # Gris
                "CANCELLED": "\x1b[91m"  # Rojo
            }
            color = status_color_map.get(milestone.status, "")
            reset_color = "\x1b[0m"
            
            status_str = f"[{color}{milestone.status:<9}{reset_color}]"
            cond_str = f"SI Precio {milestone.condition.type.replace('_', ' ')} {milestone.condition.value}"
            
            print(f"{prefix}{connector} (Lvl {milestone.level}) {status_str} {cond_str} (ID: ...{milestone.id[-6:]})")
            
            child_prefix = prefix + ("    " if is_last else "│   ")
            print_branch(milestone.id, child_prefix)

    print_branch(None)


def _create_milestone_wizard(pm_api: Any):
    """Asistente paso a paso para crear un nuevo hito y configurar su tendencia."""
    clear_screen()
    print_tui_header("Asistente de Creación de Hitos")
    
    current_price = pm_api.get_current_price_for_exit() or 0.0
    print(f"\nPrecio de Mercado Actual: {current_price:.4f} USDT\n")

    # Paso 1: Seleccionar Padre (si aplica)
    parent_id: Optional[str] = None
    all_milestones = pm_api.get_all_milestones()
    selectable_parents = [m for m in all_milestones if m.status in ['PENDING', 'ACTIVE']]
    
    if selectable_parents:
        parent_menu_items = ["[1] Hito de Nivel 1 (Sin padre)"]
        parent_menu_items.extend(
            f"[{i+2}] Anidar bajo: Lvl {m.level} (...{m.id[-6:]})"
            for i, m in enumerate(selectable_parents)
        )
        parent_choice = TerminalMenu(parent_menu_items, title="Paso 1/3: ¿Dónde crear el nuevo hito?").show()
        
        if parent_choice is None: return
        if parent_choice > 0:
            parent_id = selectable_parents[parent_choice - 1].id

    # Paso 2: Definir la Condición
    cond_type_idx = TerminalMenu(["[1] Precio SUBE POR ENCIMA DE", "[2] Precio BAJA POR DEBAJO DE"], title="\nPaso 2/3: Elige la condición que activará el hito:").show()
    if cond_type_idx is None: return
    cond_type = "PRICE_ABOVE" if cond_type_idx == 0 else "PRICE_BELOW"
    cond_value = get_input(f"Introduce el precio objetivo para '{cond_type.replace('_', ' ')}'", float, min_val=0.0)
    condition_data = {"type": cond_type, "value": cond_value}

    # Paso 3: Definir la Acción (Configuración de la Tendencia)
    print("\n" + "="*80)
    print("Paso 3/3: Configura la TENDENCIA que se iniciará cuando se cumpla la condición.")
    print("="*80)
    
    mode_idx = TerminalMenu(["[1] LONG_ONLY", "[2] SHORT_ONLY", "[3] LONG_SHORT", "[4] NEUTRAL (Pausa)"], title="\nElige el modo de operación para esta tendencia:").show()
    if mode_idx is None: return
    trend_mode = ["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT", "NEUTRAL"][mode_idx]
    
    print("\n--- Parámetros de Riesgo para las posiciones de esta Tendencia ---")
    ind_sl = get_input("Stop Loss Individual (%) (0 para desactivar)", float, default=0.0, min_val=0.0)
    ts_act = get_input("Activación de Trailing Stop (%) (0 para desactivar)", float, default=0.0, min_val=0.0)
    ts_dist = get_input("Distancia de Trailing Stop (%)", float, default=0.0, min_val=0.0)
    
    print("\n--- Condiciones de finalización para esta Tendencia ---")
    trade_limit = get_input("Límite de trades (0 para ilimitado)", int, default=0, min_val=0)
    duration = get_input("Duración máxima (min, 0 para ilimitado)", int, default=0, min_val=0)
    tp_roi = get_input("Objetivo de TP por ROI (%, ej: 2.5, 0 para desactivar)", float, default=0.0, min_val=0.0)
    sl_roi = get_input("Stop Loss por ROI (%, ej: -1.5, 0 para desactivar)", float, default=0.0, max_val=0.0)

    # Paso 4: Ensamblar y enviar a la API del PM
    trend_config = {
        "mode": trend_mode,
        "individual_sl_pct": ind_sl,
        "trailing_stop_activation_pct": ts_act,
        "trailing_stop_distance_pct": ts_dist,
        "limit_trade_count": trade_limit or None,
        "limit_duration_minutes": duration or None,
        "limit_tp_roi_pct": tp_roi or None,
        "limit_sl_roi_pct": sl_roi or None,
    }
    action_data = {"type": "START_TREND", "params": trend_config}

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

    menu_items = [
        f"Lvl {m.level} - SI Precio {m.condition.type.replace('_', ' ')} {m.condition.value} (ID: ...{m.id[-12:]})"
        for m in milestones
    ]
    menu_items.append(None)
    menu_items.append("[b] Cancelar")

    title = "Selecciona el hito que deseas eliminar:"
    delete_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
    choice_index = delete_menu.show()

    if choice_index is not None and choice_index < len(milestones):
        milestone_to_delete_id = milestones[choice_index].id
        confirm_title = f"¿Confirmas eliminar el hito ...{milestone_to_delete_id[-12:]}?\n(ADVERTENCIA: Todos sus hitos hijos también serán eliminados en cascada)"
        confirm_menu = TerminalMenu(["[1] Sí, eliminar este hito y sus descendientes", "[2] No, cancelar"], title=confirm_title).show()
        if confirm_menu == 0:
            success, msg = pm_api.remove_milestone(milestone_to_delete_id)
            print(f"\n{msg}")
            time.sleep(2)