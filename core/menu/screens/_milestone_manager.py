"""
Módulo para la Pantalla de Gestión de Hitos (Centro de Control Estratégico).

v4.2: Corregido el renderizado de las pantallas de detalle para evitar "parpadeos".
- Las pantallas de detalle ahora imprimen la información estática y luego
  muestran el menú de acciones sin limpiar la pantalla, creando una vista estable.
"""
import time
from typing import Any, Dict, Optional, List
from dataclasses import asdict, fields

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen,
    print_tui_header,
    get_input,
    MENU_STYLE,
    show_help_popup,
    CancelInput 
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
        
        all_milestones = pm_api.get_all_milestones()
        trend_state = pm_api.get_trend_state()
        
        _display_current_status(pm_api)
        _display_decision_tree(all_milestones)

        menu_items = [
            "[1] Crear Nuevo Hito Futuro",
            "[2] Gestionar Hitos Futuros",
        ]
        
        if trend_state.get('mode', 'NEUTRAL') != 'NEUTRAL':
            menu_items.append("[3] Gestionar Hito Actual (En Vivo)")
        else:
            menu_items.append("[Hito Actual (Ninguno activo)]")


        menu_items.extend([
            None,
            "[h] Ayuda", "[r] Refrescar",
            None,
            "[b] Volver al Dashboard"
        ])
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False

        main_menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
        choice = main_menu.show()

        if choice == 0:
            _create_milestone_wizard(pm_api, all_milestones)
        elif choice == 1:
            _show_manage_future_milestones_screen(pm_api)
        elif choice == 2 and trend_state.get('mode', 'NEUTRAL') != 'NEUTRAL':
            _show_manage_active_milestone_screen(pm_api, all_milestones)
        elif choice == 4:
            show_help_popup("auto_mode")
        elif choice == 5:
            continue
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
        trades_executed = trend_state.get('trades_executed', 0)
        config = trend_state.get('config', {})
        trade_limit = config.get('limit_trade_count') or '∞'
        
        print(f"  Activado por Hito: ...{milestone_id[-6:]}")
        print(f"  Trades en Tendencia: {trades_executed} / {trade_limit}")
        
def _display_decision_tree(milestones: List[Any]):
    print("\n--- Árbol de Decisiones " + "-"*57)
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

# --- PANTALLAS SECUNDARIAS ---
def _show_manage_future_milestones_screen(pm_api: Any):
    while True:
        clear_screen()
        print_tui_header("Gestión de Hitos Futuros")
        
        all_milestones = pm_api.get_all_milestones()
        future_milestones = [m for m in all_milestones if m.status in ['PENDING', 'ACTIVE']]
        
        if not future_milestones:
            print("\nNo hay hitos futuros planificados.")
            menu_items = ["[b] Volver"]
        else:
            print("\nSelecciona un hito para ver sus detalles y acciones:")
            menu_items = [f"Lvl {m.level} - {m.status} - SI Precio {m.condition.type.replace('_', ' ')} {m.condition.value} (...{m.id[-6:]})" for m in future_milestones]
            menu_items.extend([
                None,
                "[Eliminar TODOS los Hitos Futuros]",
                "[b] Volver"
            ])

        menu_options = MENU_STYLE.copy()
        # Se establece clear_screen en False para que el texto anterior no se borre.
        menu_options['clear_screen'] = False
        
        choice = TerminalMenu(menu_items, title="\nHitos Planificados:", **menu_options).show()

        if choice is None or menu_items[choice] == "[b] Volver":
            break
        elif menu_items[choice] == "[Eliminar TODOS los Hitos Futuros]":
            if TerminalMenu(["[1] Sí, eliminar todos", "[2] No, cancelar"], title="¿Estás seguro? Esta acción no se puede deshacer.").show() == 0:
                for m in future_milestones:
                    pm_api.remove_milestone(m.id)
                print("\nTodos los hitos futuros han sido eliminados."); time.sleep(2)
        else:
            selected_milestone = future_milestones[choice]
            _show_milestone_detail_screen(pm_api, selected_milestone)
        
        # Al volver de una sub-pantalla, el bucle se repetirá, refrescando la lista.

def _show_milestone_detail_screen(pm_api: Any, milestone: Any):
    # --- INICIO DE LA MODIFICACIÓN (Evitar parpadeo) ---
    # Ya no usamos un bucle while aquí. La pantalla se muestra una vez.
    # Si el usuario elige una acción, se ejecuta y la función termina.
    # El bucle de la pantalla anterior se encargará de refrescar la lista.

    clear_screen()
    print_tui_header(f"Detalle del Hito (...{milestone.id[-6:]})")
    
    print("\n--- Detalles del Hito Seleccionado ---")
    print(f"  ID Completo: {milestone.id}")
    print(f"  Estado: {milestone.status}")
    print(f"  Nivel en el Árbol: {milestone.level}")
    print(f"  ID Padre: {milestone.parent_id or 'N/A (Nivel 1)'}")
    print(f"\n  CONDICIÓN:")
    print(f"    - Se activará si: Precio {milestone.condition.type.replace('_', ' ')} {milestone.condition.value}")
    
    trend_config = asdict(milestone.action.params)
    print(f"\n  ACCIÓN (iniciará la siguiente Tendencia):")
    for field in fields(milestone.action.params):
        value = trend_config.get(field.name)
        print(f"    - {field.name.replace('_', ' ').title()}: {value if value is not None else 'N/A'}")

    menu_items = [
        "[1] Modificar este Hito",
        "[2] Eliminar este Hito",
        "[3] Forzar Activación Ahora",
        None,
        "[b] Volver a la lista de hitos"
    ]
    
    menu_options = MENU_STYLE.copy()
    menu_options['clear_screen'] = False

    choice = TerminalMenu(menu_items, title="\nAcciones para este hito:", **menu_options).show()

    if choice == 0:
        _create_milestone_wizard(pm_api, pm_api.get_all_milestones(), update_mode=True, milestone_to_update=milestone)
    elif choice == 1:
        _delete_milestone_wizard(pm_api, pm_api.get_all_milestones(), milestone_to_delete=milestone)
    elif choice == 2:
        _force_trigger_wizard(pm_api, pm_api.get_all_milestones(), milestone_to_trigger=milestone)
    # Si se elige "Volver" o se presiona ESC (choice is None), la función simplemente termina.
    # --- FIN DE LA MODIFICACIÓN ---

def _show_manage_active_milestone_screen(pm_api: Any, all_milestones: List[Any]):
    trend_state = pm_api.get_trend_state()
    if trend_state.get('mode', 'NEUTRAL') == 'NEUTRAL':
        print("\nNo hay un hito activo para gestionar."); time.sleep(2); return
    
    active_milestone_id = trend_state.get('milestone_id')
    active_milestone = next((m for m in all_milestones if m.id == active_milestone_id), None)

    # --- INICIO DE LA MODIFICACIÓN (Evitar parpadeo) ---
    clear_screen()
    print_tui_header(f"Gestionando Hito Activo (...{active_milestone_id[-6:]})")
    
    print("\n--- Detalles de la Tendencia en Curso ---")
    if active_milestone:
        trend_config = asdict(active_milestone.action.params)
        for key, value in trend_config.items():
            print(f"  - {key.replace('_', ' ').title()}: {value if value is not None else 'N/A'}")
    else:
        print("  Error: No se encontró el objeto del hito activo.")

    menu_items = [
        "[1] Modificar Parámetros de la Tendencia (en vivo)",
        "[2] Finalizar Tendencia (Cancelar Hito)",
        None,
        "[b] Volver al Centro de Control"
    ]
    
    menu_options = MENU_STYLE.copy()
    menu_options['clear_screen'] = False
    
    choice = TerminalMenu(menu_items, title="\nAcciones en Tiempo Real:", **menu_options).show()
    # --- FIN DE LA MODIFICACIÓN ---

    if choice == 0:
        _create_milestone_wizard(pm_api, all_milestones, update_mode=True, milestone_to_update=active_milestone, is_active_trend_update=True)
    elif choice == 1:
        title = "¿Cómo deseas finalizar la tendencia actual?"
        end_menu_items = [
            "[1] Volver a NEUTRAL (mantener posiciones abiertas)",
            "[2] Cierre forzoso de TODAS las posiciones y volver a NEUTRAL",
            None,
            "[c] Cancelar"
        ]
        end_choice = TerminalMenu(end_menu_items, title=title).show()
        if end_choice == 0:
            pm_api.force_end_trend(close_positions=False)
            print("\nTendencia finalizada. Las posiciones se mantienen."); time.sleep(2)
        elif end_choice == 1:
            pm_api.force_end_trend(close_positions=True)
            print("\nTendencia finalizada. Todas las posiciones han sido cerradas."); time.sleep(2)

# --- ASISTENTES Y FUNCIONES DE APOYO ---
# (El resto de funciones (_create_milestone_wizard, _delete_milestone_wizard, etc.)
# no necesitan cambios, ya que la nueva estructura las llama correctamente)
def _create_milestone_wizard(pm_api: Any, all_milestones: List[Any], update_mode: bool = False, milestone_to_update: Any = None, is_active_trend_update: bool = False):
    title = "Modificar Tendencia Activa" if is_active_trend_update else ("Asistente de Modificación de Hitos" if update_mode else "Asistente de Creación de Hitos")
    clear_screen(); print_tui_header(title)
    
    config_module = _deps.get("config_module")
    if not config_module:
        print("Error: Módulo de configuración no encontrado."); time.sleep(2); return

    current_price = pm_api.get_current_market_price() or 0.0
    print(f"\nPrecio de Mercado Actual: {current_price:.4f} USDT\n")
    
    if update_mode and milestone_to_update:
        cond_value = milestone_to_update.condition.value
        trend_config_dict = asdict(milestone_to_update.action.params)
    else:
        cond_value = current_price
        trend_config_dict = {
            'individual_sl_pct': getattr(config_module, 'DEFAULT_TREND_INDIVIDUAL_SL_PCT', 10.0),
            'trailing_stop_activation_pct': getattr(config_module, 'DEFAULT_TREND_TS_ACTIVATION_PCT', 0.4),
            'trailing_stop_distance_pct': getattr(config_module, 'DEFAULT_TREND_TS_DISTANCE_PCT', 0.1),
            'limit_trade_count': getattr(config_module, 'DEFAULT_TREND_LIMIT_TRADE_COUNT', 0),
            'limit_duration_minutes': getattr(config_module, 'DEFAULT_TREND_LIMIT_DURATION_MINUTES', 0),
            'limit_tp_roi_pct': getattr(config_module, 'DEFAULT_TREND_LIMIT_TP_ROI_PCT', 2.5),
            'limit_sl_roi_pct': getattr(config_module, 'DEFAULT_TREND_LIMIT_SL_ROI_PCT', -1.5)
        }
    
    ind_sl = trend_config_dict.get('individual_sl_pct', 0.0)
    ts_act = trend_config_dict.get('trailing_stop_activation_pct', 0.0)
    ts_dist = trend_config_dict.get('trailing_stop_distance_pct', 0.0)
    trade_limit = trend_config_dict.get('limit_trade_count', 0) or 0
    duration = trend_config_dict.get('limit_duration_minutes', 0) or 0
    tp_roi = trend_config_dict.get('limit_tp_roi_pct', 0.0) or 0.0
    sl_roi = trend_config_dict.get('limit_sl_roi_pct', 0.0) or 0.0
    
    parent_id: Optional[str] = None
    condition_data = {}
    
    if not is_active_trend_update:
        if not update_mode:
            selectable_parents = [m for m in all_milestones if m.status in ['PENDING', 'ACTIVE']]
            if selectable_parents:
                parent_menu_items = ["[1] Hito de Nivel 1 (Sin padre)"]
                parent_menu_items.extend(f"[{i+2}] Anidar bajo: Lvl {m.level} (...{m.id[-6:]})" for i, m in enumerate(selectable_parents))
                parent_menu_items.extend([None, "[b] Cancelar y Volver"])
                parent_choice = TerminalMenu(parent_menu_items, title="Paso 1/3: ¿Dónde crear el nuevo hito?").show()
                if parent_choice is None or parent_choice >= len(parent_menu_items) - 2: return
                if parent_choice > 0: parent_id = selectable_parents[parent_choice - 1].id
        
        cond_menu_items = ["[1] Precio SUBE POR ENCIMA DE", "[2] Precio BAJA POR DEBAJO DE", None, "[b] Cancelar y Volver"]
        cond_type_idx = TerminalMenu(cond_menu_items, title="\nPaso 2/3: Elige la condición que activará el hito:").show()
        if cond_type_idx is None or cond_type_idx >= 2: return
        cond_type = "PRICE_ABOVE" if cond_type_idx == 0 else "PRICE_BELOW"
        
        temp_val = get_input(f"Introduce el precio objetivo para '{cond_type.replace('_', ' ')}'", float, default=cond_value, min_val=0.0)
        if isinstance(temp_val, CancelInput): return
        cond_value = temp_val
        condition_data = {"type": cond_type, "value": cond_value}

    print("\n" + "="*80); print("Paso 3/3: Configura los Parámetros de la Tendencia"); print("="*80)
    
    mode_map = ["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT", "NEUTRAL"]
    if is_active_trend_update:
        mode_idx = mode_map.index(trend_config_dict.get('mode', 'NEUTRAL'))
        print(f"\nModo de operación (no modificable): {mode_map[mode_idx]}")
    else:
        mode_menu_items = ["[1] LONG_ONLY", "[2] SHORT_ONLY", "[3] LONG_SHORT", "[4] NEUTRAL (Pausa)", None, "[b] Cancelar y Volver"]
        mode_idx = TerminalMenu(mode_menu_items, title="\nModo de operación:").show()
        if mode_idx is None or mode_idx >= 4: return

    print("\n--- Parámetros de Riesgo para esta Tendencia ---")
    temp_val = get_input("SL Individual (%)", float, default=ind_sl, min_val=0.0);
    if isinstance(temp_val, CancelInput): return
    ind_sl = temp_val

    temp_val = get_input("Activación TS (%)", float, default=ts_act, min_val=0.0)
    if isinstance(temp_val, CancelInput): return
    ts_act = temp_val

    temp_val = get_input("Distancia TS (%)", float, default=ts_dist, min_val=0.0)
    if isinstance(temp_val, CancelInput): return
    ts_dist = temp_val
    
    print("\n--- Condiciones de finalización para esta Tendencia ---")
    temp_val = get_input("Límite de trades", int, default=trade_limit, min_val=0)
    if isinstance(temp_val, CancelInput): return
    trade_limit = temp_val

    temp_val = get_input("Duración máxima (min)", int, default=duration, min_val=0)
    if isinstance(temp_val, CancelInput): return
    duration = temp_val

    temp_val = get_input("Objetivo de TP por ROI (%)", float, default=tp_roi, min_val=0.0)
    if isinstance(temp_val, CancelInput): return
    tp_roi = temp_val

    temp_val = get_input("Stop Loss por ROI (%)", float, default=sl_roi, max_val=0.0)
    if isinstance(temp_val, CancelInput): return
    sl_roi = temp_val
    
    clear_screen(); print_tui_header("Confirmación")
    print("\nPor favor, revisa la configuración antes de guardarla:\n")
    if not is_active_trend_update:
        print(f"  CONDICIÓN:")
        print(f"    - Se activará si: Precio {cond_type.replace('_', ' ')} {cond_value}\n")
    
    print(f"  ACCIÓN (Parámetros de la Tendencia):")
    print(f"    - Modo de Operación: {mode_map[mode_idx]}")
    print(f"    - Riesgo por Posición:")
    print(f"      - SL Individual: {ind_sl}%")
    print(f"      - Trailing Stop: Activación al {ts_act}%, Distancia del {ts_dist}%")
    print(f"    - Límites de la Tendencia:")
    print(f"      - Máximo de Trades: {'Ilimitado' if (trade_limit or 0) == 0 else trade_limit}")
    print(f"      - Duración Máxima: {'Ilimitada' if (duration or 0) == 0 else f'{duration} min'}")
    print(f"      - TP por ROI: {'Desactivado' if (tp_roi or 0.0) == 0.0 else f'+{tp_roi}%'}")
    print(f"      - SL por ROI: {'Desactivado' if (sl_roi or 0.0) == 0.0 else f'{sl_roi}%'}")
    
    confirm_choice = TerminalMenu(["[1] Confirmar y Guardar", "[2] Cancelar y Descartar"], title="\n¿Confirmas los cambios?").show()

    if confirm_choice == 0:
        updated_params = {
            "individual_sl_pct": ind_sl, "trailing_stop_activation_pct": ts_act,
            "trailing_stop_distance_pct": ts_dist, "limit_trade_count": trade_limit or None,
            "limit_duration_minutes": duration or None, "limit_tp_roi_pct": tp_roi or None,
            "limit_sl_roi_pct": sl_roi or None
        }
        
        if is_active_trend_update:
            success, msg = pm_api.update_active_trend_parameters(updated_params)
        else:
            trend_config = {"mode": mode_map[mode_idx], **updated_params}
            action_data = {"type": "START_TREND", "params": trend_config}
            if update_mode:
                success, msg = pm_api.update_milestone(milestone_to_update.id, condition_data, action_data)
            else:
                success, msg = pm_api.add_milestone(condition_data, action_data, parent_id)
        
        print(f"\n{msg}"); time.sleep(2.0)
    else:
        print("\nOperación cancelada."); time.sleep(1.5)

def _delete_milestone_wizard(pm_api: Any, all_milestones: List[Any], milestone_to_delete: Optional[Any] = None):
    if not milestone_to_delete:
        print("\nError: No se ha especificado un hito para eliminar."); time.sleep(2); return
    
    title = f"¿Eliminar hito ...{milestone_to_delete.id[-6:]}?\n(ADVERTENCIA: Todos sus descendientes también serán eliminados)"
    if TerminalMenu(["[1] Sí, eliminar", "[2] No, cancelar"], title=title).show() == 0:
        success, msg = pm_api.remove_milestone(milestone_to_delete.id)
        print(f"\n{msg}"); time.sleep(2)

def _force_trigger_wizard(pm_api: Any, all_milestones: List[Any], milestone_to_trigger: Optional[Any] = None):
    if not milestone_to_trigger:
        print("\nError: No se ha especificado un hito para activar."); time.sleep(2); return
    
    milestone_id = milestone_to_trigger.id
    new_trend_mode = milestone_to_trigger.action.params.mode
    
    summary = pm_api.get_position_summary()
    has_longs = summary.get('open_long_positions_count', 0) > 0
    has_shorts = summary.get('open_short_positions_count', 0) > 0

    long_pos_action = 'keep'
    short_pos_action = 'keep'

    if has_longs or has_shorts:
        clear_screen()
        print_tui_header("Gestión de Posiciones Existentes")
        print(f"\nSe activará una nueva tendencia en modo '{new_trend_mode}'.")
        print("¿Qué deseas hacer con las posiciones actualmente abiertas?")
        
        pos_management_menu_items = []
        action_options = {}
        idx = 0

        if has_longs:
            if new_trend_mode in ['LONG_ONLY', 'LONG_SHORT']:
                pos_management_menu_items.append(f"[{idx+1}] Mantener posiciones LONG abiertas (Recomendado)")
                action_options[idx] = ('long', 'keep')
                idx += 1
            pos_management_menu_items.append(f"[{idx+1}] Cerrar todas las posiciones LONG")
            action_options[idx] = ('long', 'close')
            idx += 1

        if has_shorts:
            if new_trend_mode in ['SHORT_ONLY', 'LONG_SHORT']:
                pos_management_menu_items.append(f"[{idx+1}] Mantener posiciones SHORT abiertas (Recomendado)")
                action_options[idx] = ('short', 'keep')
                idx += 1
            pos_management_menu_items.append(f"[{idx+1}] Cerrar todas las posiciones SHORT")
            action_options[idx] = ('short', 'close')
            idx += 1
        
        pos_management_menu_items.extend([None, "[c] Cancelar activación"])
        
        pos_choice = TerminalMenu(pos_management_menu_items, title="\nElige una acción para cada tipo de posición:").show()

        if pos_choice is None or pos_choice >= len(action_options):
            print("\nActivación cancelada."); time.sleep(1.5); return
        
        selected_action = action_options[pos_choice]
        side_to_act_on, action_to_take = selected_action
        
        if side_to_act_on == 'long':
            long_pos_action = action_to_take
        else:
            short_pos_action = action_to_take

    success, msg = pm_api.force_trigger_milestone_with_pos_management(
        milestone_id,
        long_pos_action=long_pos_action,
        short_pos_action=short_pos_action
    )
    print(f"\n{msg}"); time.sleep(2.5)