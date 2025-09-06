# ./core/menu/screens/operation_manager/wizard_setup/_main_logic.py

import time
import uuid
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
    _get_terminal_width,
    _create_config_box_line
)

try:
    from core.strategy.entities import Operacion, LogicalPosition
    from core.strategy.om import api as om_api 
    from ..position_editor import show_position_editor_screen
    from . import _submenus_entry, _submenus_exit, _submenus_risk
except ImportError:
    om_api, show_position_editor_screen = None, None
    _submenus_entry, _submenus_exit, _submenus_risk = None, None, None
    class Operacion: pass
    class LogicalPosition: pass

_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe y almacena las dependencias para este módulo."""
    global _deps
    _deps = dependencies

def _edit_strategy_global_submenu(temp_op: Operacion) -> bool:
    from ...._helpers import show_help_popup # <-- Importación añadida
    params_changed_in_submenu = False
    
    while True:
        clear_screen(); print_tui_header("Editando Estrategia Global")
        
        menu_items = [
            f"[1] Apalancamiento ({temp_op.apalancamiento:.1f}x)",
            f"[2] Distancia de Promediación ({temp_op.averaging_distance_pct:.2f}%)",
            f"[3] Reinversión Automática ({'Activada' if temp_op.auto_reinvest_enabled else 'Desactivada'})",
            None,
            "[h] Ayuda", # Botón de ayuda añadido
            "[b] Volver"
        ]
        choice = TerminalMenu(menu_items, **MENU_STYLE).show()
        
        if choice is None or choice == 5: break # El índice de "Volver" ahora es 5
        
        try:
            if choice == 0:
                new_val = get_input("Nuevo Apalancamiento", float, temp_op.apalancamiento, min_val=1.0)
                if new_val != temp_op.apalancamiento:
                    temp_op.apalancamiento = new_val
                    params_changed_in_submenu = True
                    
                    for pos in temp_op.posiciones:
                        pos.valor_nominal = pos.capital_asignado * new_val
                    
            elif choice == 1:
                new_val = get_input("Nueva Distancia de Promediación (%)", float, temp_op.averaging_distance_pct, min_val=0.01)
                if new_val != temp_op.averaging_distance_pct: temp_op.averaging_distance_pct = new_val; params_changed_in_submenu = True
            
            elif choice == 2:
                reinvest_choice = TerminalMenu(["[1] Activar", "[2] Desactivar"], title="\n¿Activar Reinversión Automática?").show()
                if reinvest_choice is not None:
                    new_val = reinvest_choice == 0
                    if new_val != temp_op.auto_reinvest_enabled: temp_op.auto_reinvest_enabled = new_val; params_changed_in_submenu = True
            
            elif choice == 4: # Índice de Ayuda
                show_help_popup('wizard_strategy_global')

        except UserInputCancelled: continue
        
    return params_changed_in_submenu

def _edit_individual_risk_submenu(temp_op: Operacion) -> bool:
    from ...._helpers import show_help_popup # <-- Importación añadida
    params_changed_in_submenu = False
    
    while True:
        clear_screen(); print_tui_header("Editando Riesgo por Posición Individual")
        
        menu_items = [
            f"[1] SL Individual ({temp_op.sl_posicion_individual_pct or 'Desactivado'}%)",
            f"[2] Activación TSL ({temp_op.tsl_activacion_pct or 'Desactivado'}%)",
            f"[3] Distancia TSL ({temp_op.tsl_distancia_pct or 'N/A'}%)",
            None,
            "[h] Ayuda", # Botón de ayuda añadido
            "[b] Volver"
        ]
        if temp_op.tsl_activacion_pct is None:
            menu_items[2] = "[3] Distancia TSL (N/A - Activa TSL primero)"

        choice = TerminalMenu(menu_items, **MENU_STYLE).show()
        if choice is None or choice == 5: break # El índice de "Volver" ahora es 5
        
        try:
            if choice == 0:
                new_val = get_input("Nuevo SL Individual (%)", float, temp_op.sl_posicion_individual_pct, min_val=0.0, is_optional=True)
                if new_val != temp_op.sl_posicion_individual_pct: temp_op.sl_posicion_individual_pct = new_val; params_changed_in_submenu = True
            
            elif choice == 1:
                new_val = get_input("Nueva Activación TSL (%)", float, temp_op.tsl_activacion_pct, min_val=0.0, is_optional=True)
                if new_val != temp_op.tsl_activacion_pct: temp_op.tsl_activacion_pct = new_val; params_changed_in_submenu = True
                if temp_op.tsl_activacion_pct is None: temp_op.tsl_distancia_pct = None
            
            elif choice == 2 and temp_op.tsl_activacion_pct is not None:
                new_val = get_input("Nueva Distancia TSL (%)", float, temp_op.tsl_distancia_pct, min_val=0.01)
                if new_val != temp_op.tsl_distancia_pct: temp_op.tsl_distancia_pct = new_val; params_changed_in_submenu = True
            
            elif choice == 4: # Índice de Ayuda
                show_help_popup('wizard_risk_individual')
            
        except UserInputCancelled: continue
        
    return params_changed_in_submenu

# Reemplaza esta función completa en core/menu/screens/operation_manager/wizard_setup/_main_logic.py

def _display_setup_box(operacion: Operacion, box_width: int, is_modification: bool):
    action = "Modificando" if is_modification else "Creando Nueva"
    tendencia = "LONG" if operacion.tendencia == 'LONG_ONLY' else "SHORT"
    print(f"\n{action} Operación {tendencia}:")
    print("┌" + "─" * (box_width - 2) + "┐")

    def _print_line(label, value, key_len):
        content = f"  {label:<{key_len}} : {value}"
        print(_create_config_box_line(content, box_width))

    def _print_section_header(title):
        print(_create_config_box_line(f"\033[96m{title.center(box_width - 6)}\033[0m", box_width))

    _print_section_header("Capital y Posiciones")
    capital_data = { "Capital Operativo Total": f"${operacion.capital_operativo_logico_actual:.2f} USDT", "Total de Posiciones": f"{len(operacion.posiciones)} ({operacion.posiciones_abiertas_count} Abiertas, {len(operacion.posiciones_pendientes)} Pendientes)", }
    max_key = max(len(k) for k in capital_data.keys()) if capital_data else 0
    for label, value in capital_data.items(): _print_line(label, value, max_key)

    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Estrategia Global")
    strategy_data = { "Apalancamiento (Fijo)": f"{operacion.apalancamiento:.1f}x", "Distancia Promediación (%)": f"{operacion.averaging_distance_pct:.2f}%" if isinstance(operacion.averaging_distance_pct, (int, float)) else "Desactivado", "Reinvertir Ganancias": "Activado" if getattr(operacion, 'auto_reinvest_enabled', False) else "Desactivado", }
    max_key = max(len(k) for k in strategy_data.keys()) if strategy_data else 0
    for label, value in strategy_data.items(): _print_line(label, value, max_key)

    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Riesgo por Posición Individual")
    leverage = operacion.apalancamiento if operacion.apalancamiento > 0 else 1.0
    sl_ind_str = f"{operacion.sl_posicion_individual_pct}% (Mov. Precio: {operacion.sl_posicion_individual_pct / leverage:.4f}%)" if operacion.sl_posicion_individual_pct is not None else "Desactivado"
    tsl_act_str = f"{operacion.tsl_activacion_pct}% (Mov. Precio: {operacion.tsl_activacion_pct / leverage:.4f}%)" if operacion.tsl_activacion_pct is not None else "Desactivado"
    risk_data = { "SL Individual (%)": sl_ind_str, "Activación TSL (%)": tsl_act_str, "Distancia TSL (%)": f"{operacion.tsl_distancia_pct}% (Mov. Precio: {operacion.tsl_distancia_pct / leverage:.4f}%)" if operacion.tsl_activacion_pct else "N/A", }
    max_key = max(len(k) for k in risk_data.keys()) if risk_data else 0
    for label, value in risk_data.items(): _print_line(label, value, max_key)
    
    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Gestión de Riesgo de Operación")

    # --- INICIO DE LA MODIFICACIÓN ---
    # La lógica para mostrar el riesgo de operación se refactoriza completamente
    op_risk_data = {}
    
    if operacion.dynamic_roi_sl:
        op_risk_data["SL Dinámico por ROI"] = f"Dist: {operacion.dynamic_roi_sl['distancia']}% (Acción: {operacion.dynamic_roi_sl['accion']})"
    if operacion.roi_sl:
        op_risk_data["Stop Loss por ROI"] = f"{operacion.roi_sl['valor']}% (Acción: {operacion.roi_sl['accion']})"
    if operacion.roi_tp:
        op_risk_data["Take Profit por ROI"] = f"{operacion.roi_tp['valor']}% (Acción: {operacion.roi_tp['accion']})"
    if operacion.roi_tsl:
        op_risk_data["TSL por ROI"] = f"Act: {operacion.roi_tsl['activacion']}%, Dist: {operacion.roi_tsl['distancia']}% (Acción: {operacion.roi_tsl['accion']})"
    if operacion.be_sl:
        op_risk_data["SL por Break-Even"] = f"Dist: {operacion.be_sl['distancia']}% (Acción: {operacion.be_sl['accion']})"
    if operacion.be_tp:
        op_risk_data["TP por Break-Even"] = f"Dist: {operacion.be_tp['distancia']}% (Acción: {operacion.be_tp['accion']})"
        
    if not op_risk_data:
        _print_line("Límites de Riesgo", "Ninguno configurado", 20)
    else:
        max_key = max(len(k) for k in op_risk_data.keys())
        for label, value in op_risk_data.items():
            _print_line(label, value, max_key)
    # --- FIN DE LA MODIFICACIÓN ---
    
    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Condiciones de Entrada")
    
    max_key_entry = len("Precio SUPERIOR a")
    if all(v is None for v in [operacion.cond_entrada_above, operacion.cond_entrada_below, operacion.tiempo_espera_minutos]):
        _print_line("Modo de Entrada", "Inmediata (Market)", max_key_entry)
    else:
        if operacion.cond_entrada_above is not None: _print_line("Precio SUPERIOR a", f"{operacion.cond_entrada_above:.4f}", max_key_entry)
        if operacion.cond_entrada_below is not None: _print_line("Precio INFERIOR a", f"{operacion.cond_entrada_below:.4f}", max_key_entry)
        if operacion.tiempo_espera_minutos: _print_line("Temporizador", f"{operacion.tiempo_espera_minutos} min", max_key_entry)

    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Condiciones de Salida")
    
    exit_labels = []
    if operacion.cond_salida_above: exit_labels.append("Salida Superior")
    if operacion.cond_salida_below: exit_labels.append("Salida Inferior")
    exit_labels.extend(["Límite Duración (min)", "Límite Máx. Trades"])
    max_key_exit = max(len(k) for k in exit_labels) if exit_labels else 20

    has_exit_cond = False
    if operacion.cond_salida_above:
        has_exit_cond = True
        _print_line("Salida Superior", f"Precio > {operacion.cond_salida_above['valor']:.4f} (Acción: {operacion.cond_salida_above['accion']})", max_key_exit)
    if operacion.cond_salida_below:
        has_exit_cond = True
        _print_line("Salida Inferior", f"Precio < {operacion.cond_salida_below['valor']:.4f} (Acción: {operacion.cond_salida_below['accion']})", max_key_exit)
    if operacion.tiempo_maximo_min:
        has_exit_cond = True
        _print_line("Límite Duración (min)", f"{operacion.tiempo_maximo_min} (Acción: {operacion.accion_por_limite_tiempo})", max_key_exit)
    if operacion.max_comercios:
        has_exit_cond = True
        _print_line("Límite Máx. Trades", f"{operacion.max_comercios} (Acción: {operacion.accion_por_limite_trades})", max_key_exit)
        
    if not has_exit_cond:
        _print_line("Límites de Salida", "Ninguno configurado", max_key_exit)

    print("└" + "─" * (box_width - 2) + "┘")

# Reemplaza esta función completa en core/menu/screens/operation_manager/wizard_setup/_main_logic.py

def operation_setup_wizard(om_api: Any, side: str, is_modification: bool):
    from ...._helpers import show_help_popup
    config_module = _deps.get("config_module")
    if not config_module:
        print("ERROR CRÍTICO: Módulo de configuración no encontrado."); time.sleep(3); return

    if is_modification:
        temp_op = om_api.get_operation_by_side(side)
        if not temp_op:
            print(f"\nError: No se encontró operación para {side.upper()}."); time.sleep(2); return
    else:
        defaults = config_module.OPERATION_DEFAULTS
        temp_op = Operacion(id=f"op_{side}_{uuid.uuid4().hex[:8]}")
        temp_op.tendencia = "LONG_ONLY" if side == 'long' else "SHORT_ONLY"
        temp_op.apalancamiento = defaults["CAPITAL"]["LEVERAGE"]
        temp_op.averaging_distance_pct = defaults["RISK"]["AVERAGING"]["DISTANCE_PCT_LONG"] if side == 'long' else defaults["RISK"]["AVERAGING"]["DISTANCE_PCT_SHORT"]
        temp_op.sl_posicion_individual_pct = defaults["RISK"]["INDIVIDUAL_SL"]["PERCENTAGE"] if defaults["RISK"]["INDIVIDUAL_SL"]["ENABLED"] else None
        if defaults["RISK"]["INDIVIDUAL_TSL"]["ENABLED"]: temp_op.tsl_activacion_pct, temp_op.tsl_distancia_pct = defaults["RISK"]["INDIVIDUAL_TSL"]["TSL_ACTIVATION_PCT"], defaults["RISK"]["INDIVIDUAL_TSL"]["TSL_DISTANCE_PCT"]
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Refactorización de la inicialización de los parámetros de riesgo de operación
        
        # --- (SECCIÓN ORIGINAL COMENTADA PARA REFERENCIA) ---
        # dynamic_sl_config = defaults["OPERATION_RISK"].get("DYNAMIC_ROI_SL", {})
        # temp_op.dynamic_roi_sl_enabled = dynamic_sl_config.get("ENABLED", False)
        # temp_op.dynamic_roi_sl_trail_pct = dynamic_sl_config.get("TRAIL_PCT")
        # if temp_op.dynamic_roi_sl_enabled: temp_op.sl_roi_pct = None
        # else: temp_op.sl_roi_pct = defaults["OPERATION_RISK"]["ROI_SL_TP"]["PERCENTAGE"] if defaults["OPERATION_RISK"]["ROI_SL_TP"]["ENABLED"] else None
        # if defaults["OPERATION_RISK"]["ROI_TSL"]["ENABLED"]: temp_op.tsl_roi_activacion_pct, temp_op.tsl_roi_distancia_pct = defaults["OPERATION_RISK"]["ROI_TSL"].get("ACTIVATION_PCT"), defaults["OPERATION_RISK"]["ROI_TSL"].get("DISTANCE_PCT")
        # temp_op.accion_por_sl_tp_roi = defaults["OPERATION_RISK"]["AFTER_STATE"]
        # temp_op.accion_por_tsl_roi = 'PAUSAR'
        # be_sl_tp_config = defaults["OPERATION_RISK"].get("BE_SL_TP", {})
        # temp_op.be_sl_tp_enabled = be_sl_tp_config.get("ENABLED", False)
        # if temp_op.be_sl_tp_enabled:
        #     temp_op.be_sl_distance_pct = be_sl_tp_config.get("SL_DISTANCE_PCT")
        #     temp_op.be_tp_distance_pct = be_sl_tp_config.get("TP_DISTANCE_PCT")
        # temp_op.accion_por_be_sl_tp = defaults["OPERATION_RISK"].get("BE_SL_TP_AFTER_STATE", 'DETENER')

        # --- LÓGICA NUEVA Y CORREGIDA ---
        op_risk_defaults = defaults["OPERATION_RISK"]
        default_action = op_risk_defaults.get("AFTER_STATE", 'DETENER')

        # ROI SL (Manual)
        roi_sl_config = op_risk_defaults.get("ROI_SL", {})
        if roi_sl_config.get("ENABLED", False):
            temp_op.roi_sl = {
                'valor': roi_sl_config.get("PERCENTAGE"),
                'accion': default_action
            }

        # ROI TP (Manual)
        roi_tp_config = op_risk_defaults.get("ROI_TP", {})
        if roi_tp_config.get("ENABLED", False):
            temp_op.roi_tp = {
                'valor': roi_tp_config.get("PERCENTAGE"),
                'accion': default_action
            }

        # ROI TSL
        roi_tsl_config = op_risk_defaults.get("ROI_TSL", {})
        if roi_tsl_config.get("ENABLED", False):
            temp_op.roi_tsl = {
                'activacion': roi_tsl_config.get("ACTIVATION_PCT"),
                'distancia': roi_tsl_config.get("DISTANCE_PCT"),
                'accion': default_action
            }

        # Dynamic ROI SL
        dynamic_roi_config = op_risk_defaults.get("DYNAMIC_ROI_SL", {})
        if dynamic_roi_config.get("ENABLED", False):
            temp_op.dynamic_roi_sl = {
                'distancia': dynamic_roi_config.get("TRAIL_PCT"),
                'accion': default_action
            }

        # Break-Even SL/TP
        be_sl_tp_config = op_risk_defaults.get("BE_SL_TP", {})
        if be_sl_tp_config.get("ENABLED", False):
            sl_dist = be_sl_tp_config.get("SL_DISTANCE_PCT")
            tp_dist = be_sl_tp_config.get("TP_DISTANCE_PCT")
            if sl_dist is not None:
                temp_op.be_sl = {'distancia': sl_dist, 'accion': default_action}
            if tp_dist is not None:
                temp_op.be_tp = {'distancia': tp_dist, 'accion': default_action}
        # --- FIN DE LA MODIFICACIÓN ---

        temp_op.auto_reinvest_enabled = defaults.get("PROFIT_MANAGEMENT", {}).get("AUTO_REINVEST_ENABLED", False)
        temp_op.max_comercios = defaults["OPERATION_LIMITS"]["MAX_TRADES"].get("VALUE") if defaults["OPERATION_LIMITS"]["MAX_TRADES"]["ENABLED"] else None
        temp_op.tiempo_maximo_min = defaults["OPERATION_LIMITS"]["MAX_DURATION"].get("MINUTES") if defaults["OPERATION_LIMITS"]["MAX_DURATION"]["ENABLED"] else None
        default_action_limits = defaults["OPERATION_LIMITS"]["AFTER_STATE"]
        temp_op.accion_por_limite_tiempo = default_action_limits
        temp_op.accion_por_limite_trades = default_action_limits
        base_size = defaults["CAPITAL"]["BASE_SIZE_USDT"]
        max_pos = defaults["CAPITAL"]["MAX_POSITIONS"]
        for _ in range(max_pos): temp_op.posiciones.append(LogicalPosition(id=f"pos_{uuid.uuid4().hex[:8]}", estado='PENDIENTE', capital_asignado=base_size, valor_nominal=base_size * temp_op.apalancamiento))

    params_changed = False

    while True:
        if is_modification:
            latest_op_state = om_api.get_operation_by_side(side)
            if latest_op_state:
                latest_positions_map = {p.id: p for p in latest_op_state.posiciones}
                for pos in temp_op.posiciones:
                    if pos.id in latest_positions_map:
                        real_pos = latest_positions_map[pos.id]
                        pos.estado, pos.entry_price, pos.entry_timestamp, pos.size_contracts = real_pos.estado, real_pos.entry_price, real_pos.entry_timestamp, real_pos.size_contracts
        
        clear_screen()
        print_tui_header(f"Asistente de Operación {side.upper()}")
        _display_setup_box(temp_op, _get_terminal_width(), is_modification)

        menu_items = [
            "[1] Gestionar Lista de Posiciones y Simular Riesgo",
            "[2] Editar Estrategia Global",
            "[3] Editar Riesgo por Posición Individual",
            "[4] Editar Gestión de Riesgo de Operación",
            "[5] Editar Condiciones de Entrada",
            "[6] Editar Condiciones de Salida",
            None,
            "[h] Ayuda",
            "[s] Guardar Cambios",
            "[c] Cancelar y Volver"
        ]
        if is_modification and temp_op.estado == 'ACTIVA':
            menu_items[4] = "[5] Editar Condiciones de Entrada (No disponible en estado ACTIVA)"
        
        menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nSelecciona una categoría para editar:", **menu_options)
        choice = menu.show()

        try:
            if choice == 0:
                if show_position_editor_screen:
                    if show_position_editor_screen(temp_op, side): params_changed = True
            elif choice == 1:
                if _edit_strategy_global_submenu(temp_op): params_changed = True
            elif choice == 2:
                if _edit_individual_risk_submenu(temp_op): params_changed = True
            elif choice == 3:
                if _submenus_risk._edit_operation_risk_submenu(temp_op): params_changed = True
            elif choice == 4:
                if is_modification and temp_op.estado == 'ACTIVA':
                    print("\nNo se pueden editar las condiciones de entrada."); time.sleep(2.5); continue
                if _submenus_entry._edit_entry_conditions_submenu(temp_op): params_changed = True
            elif choice == 5:
                if _submenus_exit._edit_exit_conditions_submenu(temp_op): params_changed = True
            
            elif choice == 7:
                show_help_popup('wizard_main')
            
            elif choice == 8: # Índice de Guardar
                if not params_changed and is_modification:
                    print("\nNo se realizaron cambios."); time.sleep(1.5); break
                clear_screen(); print_tui_header("Confirmar Cambios")
                _display_setup_box(temp_op, _get_terminal_width(), is_modification)
                if TerminalMenu(["[1] Sí, guardar y aplicar", "[2] No, seguir editando"], title="\n¿Confirmas estos parámetros?").show() == 0:
                    success, msg = om_api.create_or_update_operation(side, temp_op.__dict__)

                    from core.strategy.sm import api as sm_api
                    if not sm_api.is_running():
                        new_op_state = om_api.get_operation_by_side(side)
                        if new_op_state and new_op_state.estado != 'DETENIDA':
                            print("\n\033[93mReactivando Ticker de precios...\033[0m")
                            sm_api.start()
                            time.sleep(1) 

                    print(f"\n{msg}"); time.sleep(2.5); break
            
            elif choice == 9 or choice is None: # Índice de Cancelar
                if params_changed:
                    if TerminalMenu(["[1] Sí, descartar", "[2] No, seguir editando"], title="\n¿Descartar cambios?").show() == 0:
                        print("\nCambios descartados."); time.sleep(1.5); break
                else:
                    print("\nAsistente cancelado."); time.sleep(1.5); break
        except UserInputCancelled:
            print("\nEdición de campo cancelada."); time.sleep(1)