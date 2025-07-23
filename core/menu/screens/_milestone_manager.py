"""
Módulo para la Pantalla de Gestión de Hitos (Centro de Control Estratégico).

v2.2: Corregida la lógica de filtrado para el asistente de modificación de hitos.
"""
import time
from typing import Any, Dict, Optional, List
from dataclasses import asdict

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

_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

# --- LÓGICA DE LA PANTALLA PRINCIPAL ---
def show_milestone_manager_screen():
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return

    pm_api = _deps.get("position_manager_api_module")
    if not pm_api:
        print("ERROR CRÍTICO: PM API no inyectada."); time.sleep(3); return

    while True:
        clear_screen()
        print_tui_header("Centro de Control Estratégico")
        
        _display_current_status(pm_api)
        _display_decision_tree(pm_api)

        menu_items = [
            "[1] Crear Nuevo Hito",
            "[2] Modificar un Hito existente",
            "[3] Eliminar un Hito existente",
            None,
            "[4] Forzar Activación de un Hito",
            "[5] Finalizar Tendencia Actual",
            None,
            "[h] Ayuda", "[r] Refrescar",
            None,
            "[b] Volver al Dashboard"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False

        main_menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
        choice = main_menu.show()

        action_map = {
            0: _create_milestone_wizard, 1: _update_milestone_wizard,
            2: _delete_milestone_wizard, 4: _force_trigger_wizard,
            5: _force_end_trend, 7: lambda api: show_help_popup("auto_mode"),
            8: 'refresh'
        }
        
        action = action_map.get(choice)
        if action:
            if action == 'refresh': continue
            action(pm_api)
        else:
            break

# --- FUNCIONES DE VISUALIZACIÓN ---
def _display_current_status(pm_api: Any):
    print("\n--- Estado Operativo Actual " + "-"*50)
    trend_state = pm_api.get_trend_state()
    mode = trend_state.get('mode', 'NEUTRAL')
    
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m", 'LONG_SHORT': "\033[96m", 'NEUTRAL': "\033[90m"}
    color = color_map.get(mode, "")
    reset = "\033[0m"

    print(f"  Modo Actual: {color}{mode}{reset}")
    if mode != 'NEUTRAL':
        milestone_id = trend_state.get('milestone_id', 'N/A')
        start_time = trend_state.get('start_time')
        trades_executed = trend_state.get('trades_executed', 0)
        config = trend_state.get('config', {})
        trade_limit = config.get('limit_trade_count') or '∞'
        
        print(f"  Activado por Hito: ...{milestone_id[-6:]}")
        print(f"  Trades en Tendencia: {trades_executed} / {trade_limit}")
        
def _display_decision_tree(pm_api: Any):
    print("\n--- Árbol de Decisiones " + "-"*57)
    milestones = pm_api.get_all_milestones()
    if not milestones:
        print("  (No hay hitos definidos)"); return
    tree = {None: []}
    for m in milestones:
        pid = m.parent_id
        if pid not in tree: tree[pid] = []
        tree[pid].append(m)
    def print_branch(parent_id, prefix=""):
        if parent_id not in tree: return
        children = sorted(tree[parent_id], key=lambda m: m.created_at)
        for i, milestone in enumerate(children):
            is_last = (i == len(children) - 1)
            connector = "└─" if is_last else "├─"
            status_color_map = {"ACTIVE": "\x1b[92m", "PENDING": "\x1b[93m", "COMPLETED": "\x1b[90m", "CANCELLED": "\x1b[91m"}
            color, reset = status_color_map.get(milestone.status, ""), "\x1b[0m"
            status_str = f"[{color}{milestone.status:<9}{reset}]"
            cond_str = f"SI Precio {milestone.condition.type.replace('_', ' ')} {milestone.condition.value}"
            print(f"{prefix}{connector} (Lvl {milestone.level}) {status_str} {cond_str} (ID: ...{milestone.id[-6:]})")
            child_prefix = prefix + ("    " if is_last else "│   ")
            print_branch(milestone.id, child_prefix)
    print_branch(None)

# --- ASISTENTES DE ACCIÓN (WIZARDS) ---
def _create_milestone_wizard(pm_api: Any, update_mode: bool = False, milestone_to_update: Any = None):
    """Asistente genérico para crear o modificar un hito."""
    title = "Asistente de Modificación de Hitos" if update_mode else "Asistente de Creación de Hitos"
    clear_screen(); print_tui_header(title)
    
    current_price = pm_api.get_current_price_for_exit() or 0.0
    print(f"\nPrecio de Mercado Actual: {current_price:.4f} USDT\n")
    
    default_cond_value = 0.0
    default_trend_config = {}
    if update_mode and milestone_to_update:
        default_cond_value = milestone_to_update.condition.value
        default_trend_config = asdict(milestone_to_update.action.params)

    parent_id: Optional[str] = None
    if not update_mode:
        all_milestones = pm_api.get_all_milestones()
        selectable_parents = [m for m in all_milestones if m.status in ['PENDING', 'ACTIVE']]
        if selectable_parents:
            parent_menu_items = ["[1] Hito de Nivel 1 (Sin padre)"]
            parent_menu_items.extend(f"[{i+2}] Anidar bajo: Lvl {m.level} (...{m.id[-6:]})" for i, m in enumerate(selectable_parents))
            parent_choice = TerminalMenu(parent_menu_items, title="Paso 1/3: ¿Dónde crear el nuevo hito?").show()
            if parent_choice is None: return
            if parent_choice > 0: parent_id = selectable_parents[parent_choice - 1].id
    
    cond_type_idx = TerminalMenu(["[1] Precio SUBE POR ENCIMA DE", "[2] Precio BAJA POR DEBAJO DE"], title="\nPaso 2/3: Elige la condición que activará el hito:").show()
    if cond_type_idx is None: return
    cond_type = "PRICE_ABOVE" if cond_type_idx == 0 else "PRICE_BELOW"
    cond_value = get_input(f"Introduce el precio objetivo para '{cond_type.replace('_', ' ')}'", float, default=default_cond_value, min_val=0.0)
    condition_data = {"type": cond_type, "value": cond_value}

    print("\n" + "="*80); print("Paso 3/3: Configura la TENDENCIA resultante."); print("="*80)
    
    mode_map = ["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT", "NEUTRAL"]
    mode_idx = TerminalMenu(["[1] LONG_ONLY", "[2] SHORT_ONLY", "[3] LONG_SHORT", "[4] NEUTRAL (Pausa)"], title="\nModo de operación:").show()
    if mode_idx is None: return
    
    print("\n--- Parámetros de Riesgo para esta Tendencia ---")
    ind_sl = get_input("SL Individual (%)", float, default=default_trend_config.get('individual_sl_pct', 0.0), min_val=0.0)
    ts_act = get_input("Activación TS (%)", float, default=default_trend_config.get('trailing_stop_activation_pct', 0.0), min_val=0.0)
    ts_dist = get_input("Distancia TS (%)", float, default=default_trend_config.get('trailing_stop_distance_pct', 0.0), min_val=0.0)
    
    print("\n--- Condiciones de finalización para esta Tendencia ---")
    trade_limit = get_input("Límite de trades", int, default=default_trend_config.get('limit_trade_count', 0), min_val=0)
    duration = get_input("Duración máxima (min)", int, default=default_trend_config.get('limit_duration_minutes', 0), min_val=0)
    tp_roi = get_input("Objetivo de TP por ROI (%)", float, default=default_trend_config.get('limit_tp_roi_pct', 0.0), min_val=0.0)
    sl_roi = get_input("Stop Loss por ROI (%)", float, default=default_trend_config.get('limit_sl_roi_pct', 0.0), max_val=0.0)

    trend_config = {"mode": mode_map[mode_idx], "individual_sl_pct": ind_sl, "trailing_stop_activation_pct": ts_act, "trailing_stop_distance_pct": ts_dist, "limit_trade_count": trade_limit or None, "limit_duration_minutes": duration or None, "limit_tp_roi_pct": tp_roi or None, "limit_sl_roi_pct": sl_roi or None}
    action_data = {"type": "START_TREND", "params": trend_config}

    if update_mode:
        success, msg = pm_api.update_milestone(milestone_to_update.id, condition_data, action_data)
    else:
        success, msg = pm_api.add_milestone(condition_data, action_data, parent_id)
    
    print(f"\n{msg}"); time.sleep(2.5)

def _update_milestone_wizard(pm_api: Any):
    """Selecciona un hito y lanza el asistente de creación en modo edición."""
    # --- INICIO DE LA CORRECCIÓN ---
    # La lista de hitos modificables son aquellos que AÚN NO han terminado.
    milestones = [m for m in pm_api.get_all_milestones() if m.status not in ['COMPLETED', 'CANCELLED']]
    # --- FIN DE LA CORRECCIÓN ---
    if not milestones: print("\nNo hay hitos modificables (pendientes o activos)."); time.sleep(2); return
    
    menu_items = [f"Lvl {m.level} - ...{m.id[-12:]}" for m in milestones] + [None, "[b] Cancelar"]
    choice = TerminalMenu(menu_items, title="Selecciona el hito a modificar:", **MENU_STYLE).show()

    if choice is not None and choice < len(milestones):
        _create_milestone_wizard(pm_api, update_mode=True, milestone_to_update=milestones[choice])

def _delete_milestone_wizard(pm_api: Any):
    milestones = pm_api.get_all_milestones()
    if not milestones: print("\nNo hay hitos para eliminar."); time.sleep(1.5); return

    menu_items = [f"Lvl {m.level} - ...{m.id[-12:]}" for m in milestones] + [None, "[b] Cancelar"]
    choice = TerminalMenu(menu_items, title="Selecciona el hito a eliminar:", **MENU_STYLE).show()

    if choice is not None and choice < len(milestones):
        milestone_to_delete = milestones[choice]
        title = f"¿Eliminar hito ...{milestone_to_delete.id[-12:]}?\n(ADVERTENCIA: Todos sus descendientes también serán eliminados)"
        if TerminalMenu(["[1] Sí, eliminar", "[2] No, cancelar"], title=title).show() == 0:
            success, msg = pm_api.remove_milestone(milestone_to_delete.id)
            print(f"\n{msg}"); time.sleep(2)

def _force_trigger_wizard(pm_api: Any):
    milestones = [m for m in pm_api.get_all_milestones() if m.status == 'ACTIVE']
    if not milestones: print("\nNo hay hitos activos para forzar."); time.sleep(2); return
    
    menu_items = [f"Lvl {m.level} - ...{m.id[-12:]} (Cond: {m.condition.type} {m.condition.value})" for m in milestones] + [None, "[b] Cancelar"]
    choice = TerminalMenu(menu_items, title="Selecciona el hito a activar AHORA:", **MENU_STYLE).show()

    if choice is not None and choice < len(milestones):
        milestone_id = milestones[choice].id
        if TerminalMenu(["[1] Sí, forzar activación", "[2] No, cancelar"], title=f"¿Confirmas activar el hito ...{milestone_id[-6:]} inmediatamente?").show() == 0:
            success, msg = pm_api.force_trigger_milestone(milestone_id)
            print(f"\n{msg}"); time.sleep(2)

def _force_end_trend(pm_api: Any):
    trend_state = pm_api.get_trend_state()
    if trend_state.get('mode', 'NEUTRAL') == 'NEUTRAL':
        print("\nNo hay ninguna tendencia activa para finalizar."); time.sleep(2); return
    
    title = f"¿Finalizar la tendencia '{trend_state['mode']}' y volver a NEUTRAL?"
    if TerminalMenu(["[1] Sí, finalizar tendencia", "[2] No, cancelar"], title=title).show() == 0:
        success, msg = pm_api.force_end_trend()
        print(f"\n{msg}"); time.sleep(2)