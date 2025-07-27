# core/menu/screens/_milestone_manager.py

"""
Módulo para la Pantalla de Gestión de Hitos (Centro de Control Estratégico).

v4.2: Corregido el renderizado de las pantallas de detalle para evitar "parpadeos".
- Las pantallas de detalle ahora imprimen la información estática y luego
  muestran el menú de acciones sin limpiar la pantalla, creando una vista estable.

v5.0 (Modelo de Operaciones):
- Completamente reescrito para soportar el nuevo modelo de Operaciones y Hitos
  de Inicialización/Finalización.
- Los asistentes y visualizaciones ahora reflejan la nueva estructura lógica.
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

# --- INICIO DE LA MODIFICACIÓN: Importar nuevas entidades ---
try:
    from core.strategy.pm._entities import (
        Hito, CondicionHito, AccionHito, ConfiguracionOperacion, CondicionPrecioDosPasos
    )
except ImportError:
    class Hito: pass
    class CondicionHito: pass
    class AccionHito: pass
    class ConfiguracionOperacion: pass
    class CondicionPrecioDosPasos: pass
# --- FIN DE LA MODIFICACIÓN ---


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
        operation_state = pm_api.get_operation_state()
        
        _display_current_status(pm_api)
        _display_decision_tree(all_milestones)

        menu_items = [
            "[1] Crear Nuevo Hito Futuro",
            "[2] Gestionar Hitos Futuros",
        ]
        
        # --- INICIO DE LA MODIFICACIÓN: Adaptar al estado de la operación ---
        if operation_state.get('configuracion', {}).get('tendencia', 'NEUTRAL') != 'NEUTRAL':
            menu_items.append("[3] Gestionar Operación Activa (En Vivo)")
        else:
            menu_items.append("[Operación Actual: NEUTRAL (En espera)]")
        # --- FIN DE LA MODIFICACIÓN ---

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
        # --- INICIO DE LA MODIFICACIÓN: Adaptar al estado de la operación ---
        elif choice == 2 and operation_state.get('configuracion', {}).get('tendencia', 'NEUTRAL') != 'NEUTRAL':
            _show_manage_active_operation_screen(pm_api, all_milestones)
        # --- FIN DE LA MODIFICACIÓN ---
        elif choice == 4:
            show_help_popup("auto_mode")
        elif choice == 5:
            continue
        else:
            break

# --- FUNCIONES DE VISUALIZACIÓN ---
def _display_current_status(pm_api: Any):
    print("\n--- Estado Operativo Actual " + "-"*50)
    # --- INICIO DE LA MODIFICACIÓN: Mostrar estado de la Operación ---
    op_summary = pm_api.get_position_summary()
    operation_state = op_summary.get('operation_status', {})
    tendencia = operation_state.get('configuracion', {}).get('tendencia', 'NEUTRAL')
    
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m", 'LONG_SHORT': "\033[96m", 'NEUTRAL': "\033[90m"}
    color = color_map.get(tendencia, "")
    reset = "\033[0m"

    print(f"  Operación Actual: {color}{tendencia}{reset} (ID: ...{operation_state.get('id', 'N/A')[-6:]})")
    if tendencia != 'NEUTRAL':
        op_pnl = op_summary.get('operation_pnl', 0.0)
        op_roi = op_summary.get('operation_roi', 0.0)
        pnl_color = "\033[92m" if op_pnl >= 0 else "\033[91m"

        print(f"  Duración: {operation_state.get('tiempo_ejecucion_str', 'N/A')}")
        print(f"  PNL / ROI (Op): {pnl_color}{op_pnl:+.4f} USDT / {op_roi:+.2f}%{reset}")
        print(f"  Trades Cerrados: {operation_state.get('comercios_cerrados_contador', 0)}")
    # --- FIN DE LA MODIFICACIÓN ---
        
def _display_decision_tree(milestones: List[Any]):
    print("\n--- Árbol de Decisiones Secuenciales " + "-"*45)
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
        for i, hito in enumerate(children):
            is_last = (i == len(children) - 1)
            connector = "└─" if is_last else "├─"
            status_color_map = {"ACTIVE": "\x1b[92m", "PENDING": "\x1b[93m", "COMPLETED": "\x1b[90m", "CANCELLED": "\x1b[91m"}
            color, reset = status_color_map.get(hito.status, ""), "\x1b[0m"
            status_str = f"[{color}{hito.status:<9}{reset}]"
            
            # --- INICIO DE LA MODIFICACIÓN: Mostrar info del nuevo Hito ---
            tipo_str = f"({hito.tipo_hito[:4]})"
            
            cond_str = ""
            if hito.condicion.condicion_precio:
                cp = hito.condicion.condicion_precio
                cond_str = f"SI Precio > {cp.activacion_mayor_a} Y LUEGO < {cp.activacion_menor_a}"
            else:
                cond_str = "Se finalizará por límites internos (ROI, Tiempo, etc.)"
            
            print(f"{prefix}{connector} {tipo_str} {status_str} {cond_str} (ID: ...{hito.id[-6:]})")
            # --- FIN DE LA MODIFICACIÓN ---

            child_prefix = prefix + ("    " if is_last else "│   ")
            print_branch(hito.id, child_prefix)
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
            # --- INICIO DE LA MODIFICACIÓN: Mostrar info del nuevo Hito en el menú ---
            menu_items = []
            for m in future_milestones:
                tipo_str = m.tipo_hito[:6]
                cond_str = ""
                if m.condicion.condicion_precio:
                    cp = m.condicion.condicion_precio
                    cond_str = f"Precio > {cp.activacion_mayor_a} -> < {cp.activacion_menor_a}"
                else:
                    cond_str = "Límites Internos"
                menu_items.append(f"Lvl {m.level} - {m.status} - [{tipo_str}] {cond_str} (...{m.id[-6:]})")
            # --- FIN DE LA MODIFICACIÓN ---
            menu_items.extend([
                None,
                "[Eliminar TODOS los Hitos Futuros]",
                "[b] Volver"
            ])

        menu_options = MENU_STYLE.copy()
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

def _show_milestone_detail_screen(pm_api: Any, hito: Any):
    clear_screen()
    print_tui_header(f"Detalle del Hito (...{hito.id[-6:]})")
    
    print("\n--- Detalles del Hito Seleccionado ---")
    print(f"  ID Completo: {hito.id}")
    print(f"  Tipo: {hito.tipo_hito}")
    print(f"  Estado: {hito.status}")
    print(f"  Nivel en el Árbol: {hito.level}")
    print(f"  ID Padre: {hito.parent_id or 'N/A (Nivel 1)'}")
    
    # --- INICIO DE LA MODIFICACIÓN: Mostrar detalles de la nueva estructura ---
    print(f"\n  CONDICIÓN DE ACTIVACIÓN:")
    if hito.condicion.condicion_precio:
        cp = hito.condicion.condicion_precio
        print(f"    - Paso 1: Precio debe superar {cp.activacion_mayor_a} (Estado: {'Cumplido' if cp.estado_mayor_a_cumplido else 'Pendiente'})")
        print(f"    - Paso 2: Precio debe bajar de {cp.activacion_menor_a} (Estado: {'Cumplido' if cp.estado_menor_a_cumplido else 'Pendiente'})")
    if hito.tipo_hito == 'FINALIZACION':
        if hito.condicion.tp_roi_pct: print(f"    - TP de Operación por ROI >= {hito.condicion.tp_roi_pct}%")
        if hito.condicion.sl_roi_pct: print(f"    - SL de Operación por ROI <= {hito.condicion.sl_roi_pct}%")
        if hito.condicion.tiempo_maximo_min: print(f"    - Duración de Operación >= {hito.condicion.tiempo_maximo_min} min")
        if hito.condicion.max_comercios: print(f"    - Trades en Operación >= {hito.condicion.max_comercios}")
    
    print(f"\n  ACCIÓN A EJECUTAR:")
    if hito.tipo_hito == 'INICIALIZACION' and hito.accion.configuracion_nueva_operacion:
        print("    - Iniciar nueva Operación con la siguiente configuración:")
        config_op = asdict(hito.accion.configuracion_nueva_operacion)
        for key, value in config_op.items():
             print(f"      - {key.replace('_', ' ').title()}: {value}")
    elif hito.tipo_hito == 'FINALIZACION':
        print("    - Finalizar operación actual y transicionar a modo NEUTRAL.")
        print(f"    - ¿Cerrar posiciones abiertas al finalizar?: {'Sí' if hito.accion.cerrar_posiciones_al_finalizar else 'No'}")
    # --- FIN DE LA MODIFICACIÓN ---

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
        _create_milestone_wizard(pm_api, pm_api.get_all_milestones(), update_mode=True, milestone_to_update=hito)
    elif choice == 1:
        _delete_milestone_wizard(pm_api, hito)
    elif choice == 2:
        _force_trigger_wizard(pm_api, hito)

def _show_manage_active_operation_screen(pm_api: Any, all_milestones: List[Any]):
    # --- INICIO DE LA MODIFICACIÓN: Adaptar a la Operación Activa ---
    operation_state = pm_api.get_operation_state()
    if operation_state.get('configuracion', {}).get('tendencia') == 'NEUTRAL':
        print("\nNo hay una operación activa para gestionar."); time.sleep(2); return
    
    clear_screen()
    print_tui_header(f"Gestionando Operación Activa (...{operation_state.get('id')[-6:]})")
    
    print("\n--- Parámetros de la Operación en Curso ---")
    config_op = operation_state.get('configuracion', {})
    for key, value in config_op.items():
        print(f"  - {key.replace('_', ' ').title()}: {value if value is not None else 'N/A'}")

    menu_items = [
        "[1] Modificar Parámetros de la Operación (en vivo)",
        "[2] Finalizar Operación Ahora (Ir a NEUTRAL)",
        None,
        "[b] Volver al Centro de Control"
    ]
    
    menu_options = MENU_STYLE.copy()
    menu_options['clear_screen'] = False
    
    choice = TerminalMenu(menu_items, title="\nAcciones en Tiempo Real:", **menu_options).show()

    if choice == 0:
        _create_milestone_wizard(pm_api, all_milestones, is_active_operation_update=True)
    elif choice == 1:
        title = "¿Cómo deseas finalizar la operación actual?"
        end_menu_items = [
            "[1] Volver a NEUTRAL (mantener posiciones abiertas)",
            "[2] Cierre forzoso de TODAS las posiciones y volver a NEUTRAL",
            None,
            "[c] Cancelar"
        ]
        end_choice = TerminalMenu(end_menu_items, title=title).show()
        if end_choice == 0:
            pm_api.force_end_operation(close_positions=False)
            print("\nOperación finalizada. Las posiciones se mantienen."); time.sleep(2)
        elif end_choice == 1:
            pm_api.force_end_operation(close_positions=True)
            print("\nOperación finalizada. Todas las posiciones han sido cerradas."); time.sleep(2)
    # --- FIN DE LA MODIFICACIÓN ---

# --- ASISTENTES Y FUNCIONES DE APOYO ---
def _create_milestone_wizard(pm_api: Any, all_milestones: List[Any], update_mode: bool = False, milestone_to_update: Any = None, is_active_operation_update: bool = False):
    title = "Modificar Operación Activa" if is_active_operation_update else ("Asistente de Modificación de Hitos" if update_mode else "Asistente de Creación de Hitos")
    clear_screen(); print_tui_header(title)
    
    config_module = _deps.get("config_module")
    if not config_module:
        print("Error: Módulo de configuración no encontrado."); time.sleep(2); return

    current_price = pm_api.get_current_market_price() or 0.0
    print(f"\nPrecio de Mercado Actual: {current_price:.4f} USDT\n")
    
    # --- INICIO DE LA MODIFICACIÓN: Lógica del nuevo asistente ---
    if is_active_operation_update:
        # Lógica para modificar la operación activa
        op_state = pm_api.get_operation_state()
        current_config_op = op_state.get('configuracion', {})
        
        # Recolectar nuevos valores para los parámetros
        print("--- Modificar Parámetros de la Operación (deja en blanco para no cambiar) ---")
        new_sl = get_input("SL Individual (%)", float, default=current_config_op.get('sl_posicion_individual_pct'))
        if isinstance(new_sl, CancelInput): return
        
        new_ts_act = get_input("Activación TSL (%)", float, default=current_config_op.get('tsl_activacion_pct'))
        if isinstance(new_ts_act, CancelInput): return
        
        new_ts_dist = get_input("Distancia TSL (%)", float, default=current_config_op.get('tsl_distancia_pct'))
        if isinstance(new_ts_dist, CancelInput): return
        
        params_to_update = {
            'sl_posicion_individual_pct': new_sl,
            'tsl_activacion_pct': new_ts_act,
            'tsl_distancia_pct': new_ts_dist,
        }
        success, msg = pm_api.update_active_operation_parameters(params_to_update)
        print(f"\n{msg}"); time.sleep(2)
        return

    # Lógica para crear o modificar un hito
    
    # 1. Determinar tipo de hito
    parent_id = None
    if update_mode:
        tipo_hito = milestone_to_update.tipo_hito
        parent_id = milestone_to_update.parent_id
    else:
        parent_choice_made = False
        selectable_parents = [m for m in all_milestones if m.status in ['PENDING', 'ACTIVE']]
        if selectable_parents:
            parent_menu_items = ["[1] Hito de Nivel 1 (Sin padre)"]
            parent_menu_items.extend(f"[{i+2}] Anidar bajo Hito ...{m.id[-6:]} (Lvl {m.level})" for i, m in enumerate(selectable_parents))
            parent_menu_items.extend([None, "[c] Cancelar"])
            parent_choice = TerminalMenu(parent_menu_items, title="Paso 1: ¿Dónde crear el nuevo hito?").show()
            if parent_choice is None or parent_choice >= len(parent_menu_items) - 2: return
            if parent_choice > 0:
                parent_id = selectable_parents[parent_choice - 1].id
                parent_hito = selectable_parents[parent_choice - 1]
                # Invertir el tipo de hito del padre
                tipo_hito = 'FINALIZACION' if parent_hito.tipo_hito == 'INICIALIZACION' else 'INICIALIZACION'
                print(f"\n-> Se creará un hito de '{tipo_hito}' como hijo.")
                time.sleep(1.5)
            else: # Nivel 1
                tipo_hito = 'INICIALIZACION'
        else:
            tipo_hito = 'INICIALIZACION' # El primer hito siempre es de inicialización
    
    # 2. Recolectar datos de Condición y Acción
    if tipo_hito == 'INICIALIZACION':
        # Asistente para Hito de Inicialización
        clear_screen(); print_tui_header(f"Crear Hito de Inicialización (Lvl {1 if not parent_id else [p for p in all_milestones if p.id==parent_id][0].level+1})")
        print(f"\nPrecio Actual: {current_price:.4f} USDT\n")
        print("Define la condición de precio de dos pasos. Usa 'market_price' para una activación inmediata.")
        
        mayor_a_def = milestone_to_update.condicion.condicion_precio.activacion_mayor_a if update_mode else 'market_price'
        menor_a_def = milestone_to_update.condicion.condicion_precio.activacion_menor_a if update_mode else current_price
        
        mayor_a = get_input("Activar si precio SUPERA", str, default=mayor_a_def)
        if isinstance(mayor_a, CancelInput): return
        menor_a = get_input("Y LUEGO BAJA DE", str, default=menor_a_def)
        if isinstance(menor_a, CancelInput): return
        
        cond_precio = CondicionPrecioDosPasos(
            activacion_mayor_a=float(mayor_a) if mayor_a != 'market_price' else 'market_price',
            activacion_menor_a=float(menor_a) if menor_a != 'market_price' else 'market_price'
        )
        condicion = CondicionHito(condicion_precio=cond_precio)

        # Recolectar configuración de la operación a iniciar
        print("\n--- Configura la Operación que se iniciará ---")
        tendencia = ["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT"][TerminalMenu(["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT"]).show()]
        base_size = get_input("Tamaño base por posición (USDT)", float, default=1.0)
        max_pos = get_input("Máx. posiciones simultáneas", int, default=5)
        leverage = get_input("Apalancamiento", float, default=10.0)
        sl_ind = get_input("SL individual (%)", float, default=10.0)
        tsl_act = get_input("Activación TSL (%)", float, default=0.4)
        tsl_dist = get_input("Distancia TSL (%)", float, default=0.1)

        config_op = ConfiguracionOperacion(tendencia, base_size, max_pos, leverage, sl_ind, tsl_act, tsl_dist)
        accion = AccionHito(configuracion_nueva_operacion=config_op)

    else: # tipo_hito == 'FINALIZACION'
        clear_screen(); print_tui_header(f"Crear Hito de Finalización (Lvl {[p for p in all_milestones if p.id==parent_id][0].level+1})")
        print("\nDefine las condiciones que finalizarán la operación actual.")
        
        tp_roi = get_input("TP por ROI de operación (%) [0 para desactivar]", float, default=2.5)
        sl_roi = get_input("SL por ROI de operación (%) [0 para desactivar]", float, default=-1.5)
        max_trades = get_input("Máx. trades en operación [0 para ilimitado]", int, default=0)
        max_duracion = get_input("Duración máx. en minutos [0 para ilimitado]", int, default=0)

        condicion = CondicionHito(
            tp_roi_pct=tp_roi if tp_roi != 0 else None,
            sl_roi_pct=sl_roi if sl_roi != 0 else None,
            max_comercios=max_trades if max_trades != 0 else None,
            tiempo_maximo_min=max_duracion if max_duracion != 0 else None
        )
        
        cerrar_pos = TerminalMenu(["No (Recomendado)", "Sí"]).show() == 1
        accion = AccionHito(cerrar_posiciones_al_finalizar=cerrar_pos)

    # 3. Confirmar y guardar
    if TerminalMenu(["[1] Confirmar y Guardar", "[2] Cancelar"]).show() == 0:
        if update_mode:
            success, msg = pm_api.update_milestone(milestone_to_update.id, condicion, accion)
        else:
            success, msg = pm_api.add_milestone(tipo_hito, condicion, accion, parent_id)
        print(f"\n{msg}"); time.sleep(2)
    # --- FIN DE LA MODIFICACIÓN ---

def _delete_milestone_wizard(pm_api: Any, hito_to_delete: Optional[Any] = None):
    if not hito_to_delete:
        print("\nError: No se ha especificado un hito para eliminar."); time.sleep(2); return
    
    title = f"¿Eliminar hito ...{hito_to_delete.id[-6:]}?\n(ADVERTENCIA: Todos sus descendientes también serán eliminados)"
    if TerminalMenu(["[1] Sí, eliminar", "[2] No, cancelar"], title=title).show() == 0:
        success, msg = pm_api.remove_milestone(hito_to_delete.id)
        print(f"\n{msg}"); time.sleep(2)

def _force_trigger_wizard(pm_api: Any, hito_to_trigger: Optional[Any] = None):
    if not hito_to_trigger:
        print("\nError: No se ha especificado un hito para activar."); time.sleep(2); return
    
    hito_id = hito_to_trigger.id
    
    # --- INICIO DE LA MODIFICACIÓN: Adaptar al nuevo modelo ---
    if hito_to_trigger.tipo_hito == 'FINALIZACION':
        new_tendencia = 'NEUTRAL'
    else:
        new_tendencia = hito_to_trigger.accion.configuracion_nueva_operacion.tendencia
    # --- FIN DE LA MODIFICACIÓN ---

    summary = pm_api.get_position_summary()
    has_longs = summary.get('open_long_positions_count', 0) > 0
    has_shorts = summary.get('open_short_positions_count', 0) > 0

    long_pos_action = 'keep'
    short_pos_action = 'keep'

    if has_longs or has_shorts:
        clear_screen()
        print_tui_header("Gestión de Posiciones Existentes")
        print(f"\nSe activará una nueva operación en modo '{new_tendencia}'.")
        print("¿Qué deseas hacer con las posiciones actualmente abiertas?")
        
        # Lógica de menú para gestionar posiciones (se mantiene mayormente igual)
        pos_management_menu_items = []
        action_options = {}
        idx = 0
        if has_longs:
            if new_tendencia in ['LONG_ONLY', 'LONG_SHORT']:
                pos_management_menu_items.append(f"[{idx+1}] Mantener posiciones LONG abiertas")
                action_options[idx] = ('long', 'keep'); idx += 1
            pos_management_menu_items.append(f"[{idx+1}] Cerrar todas las posiciones LONG")
            action_options[idx] = ('long', 'close'); idx += 1
        if has_shorts:
            if new_tendencia in ['SHORT_ONLY', 'LONG_SHORT']:
                pos_management_menu_items.append(f"[{idx+1}] Mantener posiciones SHORT abiertas")
                action_options[idx] = ('short', 'keep'); idx += 1
            pos_management_menu_items.append(f"[{idx+1}] Cerrar todas las posiciones SHORT")
            action_options[idx] = ('short', 'close'); idx += 1
        pos_management_menu_items.extend([None, "[c] Cancelar activación"])
        
        pos_choice = TerminalMenu(pos_management_menu_items, title="\nElige una acción para cada tipo de posición:").show()
        if pos_choice is None or pos_choice >= len(action_options):
            print("\nActivación cancelada."); time.sleep(1.5); return
        
        side_to_act_on, action_to_take = action_options[pos_choice]
        if side_to_act_on == 'long': long_pos_action = action_to_take
        else: short_pos_action = action_to_take

    success, msg = pm_api.force_trigger_milestone_with_pos_management(
        hito_id,
        long_pos_action=long_pos_action,
        short_pos_action=short_pos_action
    )
    print(f"\n{msg}"); time.sleep(2.5)