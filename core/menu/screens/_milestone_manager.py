"""
Módulo para la Pantalla de Gestión de Operaciones y Hitos (Centro de Control Estratégico).

v5.1 (Refactor de UI):
- Reescrito para presentar un panel de control denso centrado en la operación activa.
- La gestión de hitos se mueve a un submenú para una experiencia más fluida.
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


_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

# --- LÓGICA DE LA PANTALLA PRINCIPAL (NUEVA VERSIÓN) ---
def show_milestone_manager_screen():
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return

    pm_api = _deps.get("position_manager_api_module")
    if not pm_api:
        print("ERROR CRÍTICO: PM API no inyectada."); time.sleep(3); return

    while True:
        clear_screen()
        print_tui_header("Gestión de Operación")
        
        # Obtener todos los datos necesarios al inicio del bucle
        summary = pm_api.get_position_summary()
        current_price = pm_api.get_current_market_price() or 0.0

        if not summary or 'error' in summary:
            print(f"Error obteniendo datos del PM: {summary.get('error', 'Desconocido')}")
            time.sleep(2)
            continue

        # Renderizar todas las secciones de la nueva UI
        _display_operation_details(summary)
        _display_capital_stats(summary)
        _display_positions_tables(summary, current_price)
        _display_upcoming_milestone_summary(pm_api.get_all_milestones())

        # Construir y mostrar el menú de acciones
        menu_items = [
            "[1] Refrescar Pantalla",
            "[2] Ver/Gestionar Hitos",
            "[3] Finalizar Operación Actual",
            None,
            "[h] Ayuda",
            "[b] Volver al Dashboard"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        main_menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
        choice = main_menu.show()

        if choice == 0: # Refrescar
            continue
        elif choice == 1: # Gestionar Hitos
            _show_manage_milestones_list_screen(pm_api)
        elif choice == 2: # Finalizar Operación
            _end_operation_wizard(pm_api)
        elif choice == 4: # Ayuda
            show_help_popup("auto_mode")
        else: # Volver o ESC
            break

# --- (COMENTADO) Versión anterior de la pantalla principal ---
# La siguiente función `show_milestone_manager_screen_v5_0` ha sido reemplazada
# por la nueva versión anterior para cumplir con el nuevo diseño de UI. Se mantiene
# aquí comentada para referencia y para cumplir con la solicitud de "no eliminar".
"""
def show_milestone_manager_screen_v5_0():
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
        
        if operation_state.get('configuracion', {}).get('tendencia', 'NEUTRAL') != 'NEUTRAL':
            menu_items.append("[3] Gestionar Operación Activa (En Vivo)")
        else:
            menu_items.append("[Operación Actual: NEUTRAL (En espera)]")

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
        elif choice == 2 and operation_state.get('configuracion', {}).get('tendencia', 'NEUTRAL') != 'NEUTRAL':
            _show_manage_active_operation_screen(pm_api, all_milestones)
        elif choice == 4:
            show_help_popup("auto_mode")
        elif choice == 5:
            continue
        else:
            break
"""
# --- FUNCIONES DE VISUALIZACIÓN MODULARES PARA LA NUEVA UI ---

def _display_operation_details(summary: Dict[str, Any]):
    print("\n--- Detalles de la Operación " + "-"*55)
    op_state = summary.get('operation_status', {})
    config_op = op_state.get('configuracion', {})
    tendencia = config_op.get('tendencia', 'NEUTRAL')
    
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m", 'LONG_SHORT': "\033[96m", 'NEUTRAL': "\033[90m"}
    color = color_map.get(tendencia, "")
    reset = "\033[0m"

    price_at_start = "N/A" # Este dato no se almacena actualmente en la entidad Operacion
    
    pos_abiertas = op_state.get('posiciones_long_count', 0) + op_state.get('posiciones_short_count', 0)
    pos_total = config_op.get('max_posiciones_logicas', 0)

    # Calcular capital en uso desde el resumen
    capital_en_uso = 0.0
    if summary.get('open_long_positions'):
        capital_en_uso += sum(p.get('margin_usdt', 0) for p in summary['open_long_positions'])
    if summary.get('open_short_positions'):
        capital_en_uso += sum(p.get('margin_usdt', 0) for p in summary['open_short_positions'])
    
    capital_total_op = config_op.get('tamaño_posicion_base_usdt', 0) * pos_total

    print(f"  Tendencia: {color}{tendencia:<12}{reset} | Precio Entrada (Op): {price_at_start:<15} | Precio Salida (Op): N/A")
    print(f"  Tamaño Posición Base: {config_op.get('tamaño_posicion_base_usdt', 0):.2f}$")
    print(f"  Posiciones Abiertas / Total: {pos_abiertas} / {pos_total}")
    print(f"  Capital en Uso / Total Op:   {capital_en_uso:.2f}$ / {capital_total_op:.2f}$")

def _display_capital_stats(summary: Dict[str, Any]):
    print("\n--- Capital y Rendimiento " + "-"*58)
    op_state = summary.get('operation_status', {})
    op_pnl = summary.get('operation_pnl', 0.0)
    op_roi = summary.get('operation_roi', 0.0)
    pnl_color = "\033[92m" if op_pnl >= 0 else "\033[91m"
    reset = "\033[0m"

    col1 = {
        "Capital Inicial": f"{op_state.get('capital_inicial_usdt', 0.0):.2f}$",
        "Capital Actual": f"{op_state.get('capital_actual_usdt', 0.0):.2f}$",
        "Tiempo Ejecución": op_state.get('tiempo_ejecucion_str', 'N/A')
    }
    col2 = {
        "PNL": f"{pnl_color}{op_pnl:+.4f}${reset}",
        "ROI": f"{pnl_color}{op_roi:+.2f}%{reset}",
        "Comercios Cerrados": op_state.get('comercios_cerrados_contador', 0)
    }

    max_key_len = max(len(k) for k in col1.keys())
    for (k1, v1), (k2, v2) in zip(col1.items(), col2.items()):
        print(f"  {k1:<{max_key_len}}: {v1:<20} |  {k2:<18}: {v2}")

def _display_positions_tables(summary: Dict[str, Any], current_price: float):
    print("\n--- Posiciones " + "-"*69)
    
    def print_table(side: str):
        positions = summary.get(f'open_{side}_positions', [])
        title = f"  Tabla {side.upper()} ({len(positions)})"
        print(title)

        if not positions:
            print("    (No hay posiciones abiertas)")
            return

        header = f"    {'Entrada':>10} {'SL':>10} {'TSL':>15} {'PNL (U)':>15} {'ROI (%)':>10}"
        print(header)
        print("    " + "-" * (len(header)-4))

        COLOR_GREEN = "\033[92m"
        COLOR_RED = "\033[91m"
        COLOR_RESET = "\033[0m"

        for pos in positions:
            entry = pos.get('entry_price', 0.0)
            sl = pos.get('stop_loss_price')
            margin = pos.get('margin_usdt', 0.0)
            size = pos.get('size_contracts', 0.0)
            
            ts_info = "Inactivo"
            # ts_is_active no está en el resumen, así que lo omitimos por ahora o lo asumimos
            # Para mostrarlo, necesitaríamos añadirlo al `format_pos_for_summary` en pm/_helpers.py
            
            pnl = (current_price - entry) * size if side == 'long' else (entry - current_price) * size
            roi = (pnl / margin) * 100 if margin > 0 else 0.0
            pnl_color = COLOR_GREEN if pnl >= 0 else COLOR_RED

            entry_str = f"{entry:10.4f}"
            sl_str = f"{sl:10.4f}" if sl else f"{'N/A':>10}"
            tsl_str = f"{ts_info:>15}"
            pnl_str = f"{pnl_color}{pnl:14.4f}${COLOR_RESET}"
            roi_str = f"{pnl_color}{roi:9.2f}%{COLOR_RESET}"

            print(f"    {entry_str} {sl_str} {tsl_str} {pnl_str} {roi_str}")
        print() # Add a blank line for spacing

    print_table('long')
    print_table('short')

def _display_upcoming_milestone_summary(all_milestones: List[Any]):
    print("--- Hitos " + "-"*72)
    active_milestones = [m for m in all_milestones if m.status == 'ACTIVE']
    if not active_milestones:
        print("  (No hay hitos activos. La operación actual finalizará por sus límites internos o manualmente)")
    else:
        for hito in active_milestones:
            tipo_str = f"({hito.tipo_hito[:4]})"
            cond_str = "Condición de Precio" if hito.condicion.condicion_precio else "Límites Internos"
            print(f"  -> Esperando Hito {tipo_str} ...{hito.id[-6:]} (Nivel {hito.level}). Activación por: {cond_str}")

# --- ASISTENTES Y SUBMENÚS (REUTILIZADOS Y REUBICADOS) ---

def _end_operation_wizard(pm_api: Any):
    title = "¿Cómo deseas finalizar la operación actual?"
    end_menu_items = [
        "[1] Volver a NEUTRAL (mantener posiciones abiertas)",
        "[2] Cierre forzoso de TODAS las posiciones y volver a NEUTRAL",
        None,
        "[c] Cancelar"
    ]
    # Usar default NO para la opción más segura
    end_choice = TerminalMenu(end_menu_items, title=title, menu_cursor_style=("fg_yellow", "bold"), menu_cursor="> ", menu_highlight_style=("bg_yellow", "fg_black")).show()
    if end_choice == 0:
        success, msg = pm_api.force_end_operation(close_positions=False)
        print(f"\n{msg}"); time.sleep(2)
    elif end_choice == 1:
        success, msg = pm_api.force_end_operation(close_positions=True)
        print(f"\n{msg}"); time.sleep(2)

def _show_manage_milestones_list_screen(pm_api: Any):
    while True:
        clear_screen()
        print_tui_header("Gestión del Árbol de Hitos")
        
        all_milestones = pm_api.get_all_milestones()
        _display_decision_tree(all_milestones) # Muestra el árbol completo
        
        future_milestones = [m for m in all_milestones if m.status in ['PENDING', 'ACTIVE']]
        
        menu_items = ["[1] Crear Nuevo Hito"]
        if future_milestones:
            menu_items.append("[2] Seleccionar un Hito para Gestionar")
            menu_items.append("[3] Eliminar TODOS los Hitos Futuros")
        
        menu_items.extend([None, "[b] Volver al Panel Principal"])
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()

        if choice == 0:
            _create_milestone_wizard(pm_api, all_milestones)
        elif choice == 1 and future_milestones:
            select_items = [f"Lvl {m.level} - {m.status} - ...{m.id[-6:]}" for m in future_milestones]
            select_items.append("[c] Cancelar")
            select_choice = TerminalMenu(select_items, title="Selecciona un hito:").show()
            if select_choice is not None and select_choice < len(future_milestones):
                _show_milestone_detail_screen(pm_api, future_milestones[select_choice])
        elif choice == 2 and future_milestones:
            if TerminalMenu(["[1] Sí, eliminar todos", "[2] No, cancelar"], title="¿Estás seguro?").show() == 0:
                # Se eliminan en reversa para evitar problemas de dependencia si la lógica fuera síncrona
                for m in reversed(future_milestones):
                    pm_api.remove_milestone(m.id)
                print("\nTodos los hitos futuros eliminados."); time.sleep(2)
        else:
            break

# Las siguientes funciones son los "wizards" y pantallas de detalle.
# Su lógica interna ya es correcta para el modelo de Operaciones/Hitos,
# por lo que se mantienen sin cambios, solo se llaman desde el nuevo flujo.

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
            
            tipo_str = f"({hito.tipo_hito[:4]})"
            cond_str = ""
            if hito.condicion.condicion_precio:
                cp = hito.condicion.condicion_precio
                cond_str = f"SI Precio > {cp.activacion_mayor_a} Y LUEGO < {cp.activacion_menor_a}"
            else:
                cond_str = "Finaliza por límites internos (ROI, Tiempo, etc.)"
            
            print(f"{prefix}{connector} {tipo_str} {status_str} {cond_str} (ID: ...{hito.id[-6:]})")

            child_prefix = prefix + ("    " if is_last else "│   ")
            print_branch(hito.id, child_prefix)
    print_branch(None)

def _show_milestone_detail_screen(pm_api: Any, hito: Any):
    clear_screen()
    print_tui_header(f"Detalle del Hito (...{hito.id[-6:]})")
    
    print("\n--- Detalles del Hito Seleccionado ---")
    print(f"  ID Completo: {hito.id}")
    print(f"  Tipo: {hito.tipo_hito}")
    print(f"  Estado: {hito.status}")
    print(f"  Nivel en el Árbol: {hito.level}")
    print(f"  ID Padre: {hito.parent_id or 'N/A (Nivel 1)'}")
    
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

def _create_milestone_wizard(pm_api: Any, all_milestones: List[Any], update_mode: bool = False, milestone_to_update: Any = None):
    title = "Asistente de Modificación de Hitos" if update_mode else "Asistente de Creación de Hitos"
    clear_screen(); print_tui_header(title)
    
    current_price = pm_api.get_current_market_price() or 0.0
    print(f"\nPrecio de Mercado Actual: {current_price:.4f} USDT\n")
    
    parent_id = None
    if update_mode:
        tipo_hito = milestone_to_update.tipo_hito
        parent_id = milestone_to_update.parent_id
    else:
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
                tipo_hito = 'FINALIZACION' if parent_hito.tipo_hito == 'INICIALIZACION' else 'INICIALIZACION'
                print(f"\n-> Se creará un hito de '{tipo_hito}' como hijo.")
                time.sleep(1.5)
            else:
                tipo_hito = 'INICIALIZACION'
        else:
            tipo_hito = 'INICIALIZACION'
    
    if tipo_hito == 'INICIALIZACION':
        clear_screen(); print_tui_header(f"Crear Hito de Inicialización")
        print(f"\nPrecio Actual: {current_price:.4f} USDT\n")
        print("Define la condición de precio. Usa 'market_price' para una activación inmediata.")
        
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

        print("\n--- Configura la Operación que se iniciará ---")
        tendencia_idx = TerminalMenu(["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT"]).show()
        if tendencia_idx is None: return
        tendencia = ["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT"][tendencia_idx]
        
        base_size = get_input("Tamaño base por posición (USDT)", float, default=1.0)
        if isinstance(base_size, CancelInput): return
        max_pos = get_input("Máx. posiciones simultáneas", int, default=5)
        if isinstance(max_pos, CancelInput): return
        leverage = get_input("Apalancamiento", float, default=10.0)
        if isinstance(leverage, CancelInput): return
        sl_ind = get_input("SL individual (%)", float, default=10.0)
        if isinstance(sl_ind, CancelInput): return
        tsl_act = get_input("Activación TSL (%)", float, default=0.4)
        if isinstance(tsl_act, CancelInput): return
        tsl_dist = get_input("Distancia TSL (%)", float, default=0.1)
        if isinstance(tsl_dist, CancelInput): return

        config_op = ConfiguracionOperacion(tendencia, base_size, max_pos, leverage, sl_ind, tsl_act, tsl_dist)
        accion = AccionHito(configuracion_nueva_operacion=config_op)

    else: # tipo_hito == 'FINALIZACION'
        clear_screen(); print_tui_header(f"Crear Hito de Finalización")
        print("\nDefine las condiciones que finalizarán la operación actual.")
        
        tp_roi = get_input("TP por ROI de operación (%) [0 para desactivar]", float, default=2.5)
        if isinstance(tp_roi, CancelInput): return
        sl_roi = get_input("SL por ROI de operación (%) [0 para desactivar]", float, default=-1.5)
        if isinstance(sl_roi, CancelInput): return
        max_trades = get_input("Máx. trades en operación [0 para ilimitado]", int, default=0)
        if isinstance(max_trades, CancelInput): return
        max_duracion = get_input("Duración máx. en minutos [0 para ilimitado]", int, default=0)
        if isinstance(max_duracion, CancelInput): return

        condicion = CondicionHito(
            tp_roi_pct=tp_roi if tp_roi != 0 else None,
            sl_roi_pct=sl_roi if sl_roi != 0 else None,
            max_comercios=max_trades if max_trades != 0 else None,
            tiempo_maximo_min=max_duracion if max_duracion != 0 else None
        )
        
        cerrar_pos_idx = TerminalMenu(["No (Recomendado)", "Sí"]).show()
        if cerrar_pos_idx is None: return
        cerrar_pos = cerrar_pos_idx == 1
        accion = AccionHito(cerrar_posiciones_al_finalizar=cerrar_pos)

    if TerminalMenu(["[1] Confirmar y Guardar", "[2] Cancelar"]).show() == 0:
        if update_mode:
            success, msg = pm_api.update_milestone(milestone_to_update.id, condicion, accion)
        else:
            success, msg = pm_api.add_milestone(tipo_hito, condicion, accion, parent_id)
        print(f"\n{msg}"); time.sleep(2)

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
    
    if hito_to_trigger.tipo_hito == 'FINALIZACION':
        new_tendencia = 'NEUTRAL'
    else:
        new_tendencia = hito_to_trigger.accion.configuracion_nueva_operacion.tendencia

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
        
        if has_longs:
            long_choice_idx = TerminalMenu(["[1] Mantener posiciones LONG", "[2] Cerrar posiciones LONG"], title="Acción para posiciones LONG:").show()
            if long_choice_idx == 1: long_pos_action = 'close'
        
        if has_shorts:
            short_choice_idx = TerminalMenu(["[1] Mantener posiciones SHORT", "[2] Cerrar posiciones SHORT"], title="Acción para posiciones SHORT:").show()
            if short_choice_idx == 1: short_pos_action = 'close'

    success, msg = pm_api.force_trigger_milestone_with_pos_management(
        hito_id,
        long_pos_action=long_pos_action,
        short_pos_action=short_pos_action
    )
    print(f"\n{msg}"); time.sleep(2.5)