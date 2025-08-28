# Contenido completo y corregido para: core/menu/screens/operation_manager/_wizard_setup.py

import time
from typing import Any, Dict, List
import copy
import uuid

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from ..._helpers import (
    clear_screen,
    print_tui_header,
    get_input,
    MENU_STYLE,
    UserInputCancelled,
    _get_terminal_width,
    _create_config_box_line,
    _truncate_text,
    _clean_ansi_codes,
)

try:
    from core.strategy.entities import Operacion, LogicalPosition
    from core.strategy.pm import api as pm_api
    from core.strategy.om import api as om_api 
    from . import position_editor
except ImportError:
    position_editor = None
    pm_api = None
    om_api = None
    class Operacion: pass
    class LogicalPosition: pass

_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies
    if position_editor and hasattr(position_editor, 'init'):
        position_editor.init(dependencies)

def _edit_operation_risk_submenu(temp_op: Operacion):
    """Submenú para editar los parámetros de riesgo a nivel de operación."""
    print("\n--- Editando Gestión de Riesgo de Operación (Acción Forzosa: DETENER) ---")
    
    risk_mode_title = "\nSelecciona el modo para el Límite SL/TP por ROI:"
    risk_mode_menu = TerminalMenu(
        ["[1] Límite Manual (Fijo)", "[2] Límite Dinámico (Automático)", "[d] Desactivar por completo"],
        title=risk_mode_title,
        **MENU_STYLE
    )
    choice = risk_mode_menu.show()

    if choice == 0: # Modo Manual
        temp_op.dynamic_roi_sl_enabled = False
        temp_op.dynamic_roi_sl_trail_pct = None
        temp_op.sl_roi_pct = get_input("Límite SL/TP por ROI (%) [Manual]", float, temp_op.sl_roi_pct)
    
    elif choice == 1: # Modo Dinámico
        temp_op.dynamic_roi_sl_enabled = True
        temp_op.sl_roi_pct = None
        default_trail = temp_op.dynamic_roi_sl_trail_pct
        temp_op.dynamic_roi_sl_trail_pct = get_input(
            "Distancia del Trailing Stop al ROI Realizado (%)", 
            float, 
            default_trail,
            min_val=0.1
        )
    
    elif choice == 2: # Desactivar
        temp_op.dynamic_roi_sl_enabled = False
        temp_op.dynamic_roi_sl_trail_pct = None
        temp_op.sl_roi_pct = None

    # La lógica para el TSL-ROI se mantiene igual
    tsl_act = get_input("Límite TSL-ROI Activación (%)", float, temp_op.tsl_roi_activacion_pct, min_val=0.0, is_optional=True)
    if tsl_act:
        temp_op.tsl_roi_activacion_pct = tsl_act
        temp_op.tsl_roi_distancia_pct = get_input("Límite TSL-ROI Distancia (%)", float, temp_op.tsl_roi_distancia_pct, min_val=0.01)
    else:
        temp_op.tsl_roi_activacion_pct, temp_op.tsl_roi_distancia_pct = None, None


def _edit_entry_conditions_submenu(temp_op: Operacion):
    """
    Submenú dedicado a editar únicamente las Condiciones de Entrada de la operación.
    """
    print("\n--- Editando Condiciones de Entrada ---")
    
    # --- INICIO DE LA MODIFICACIÓN: Mostrar valor actual en el título ---
    entry_cond_str = "No definida"
    if temp_op.tipo_cond_entrada == 'MARKET': 
        entry_cond_str = "Inmediata (Market)"
    elif temp_op.tipo_cond_entrada == 'PRICE_ABOVE' and temp_op.valor_cond_entrada is not None: 
        entry_cond_str = f"Precio > {temp_op.valor_cond_entrada:.4f}"
    elif temp_op.tipo_cond_entrada == 'PRICE_BELOW' and temp_op.valor_cond_entrada is not None: 
        entry_cond_str = f"Precio < {temp_op.valor_cond_entrada:.4f}"
    elif temp_op.tipo_cond_entrada == 'TIME_DELAY' and temp_op.tiempo_espera_minutos is not None:
        entry_cond_str = f"Activar después de {temp_op.tiempo_espera_minutos} min"
    
    menu_title = f"\nCondición de Entrada Actual: {entry_cond_str}\nSelecciona una nueva condición:"
    # --- FIN DE LA MODIFICACIÓN ---

    entry_menu_items = [
        "[1] Inmediata (Market)", 
        "[2] Precio SUPERIOR a", 
        "[3] Precio INFERIOR a",
        "[4] Activar después de X minutos",
        None,
        "[c] Cancelar y Volver"
    ]
    
    menu_options = MENU_STYLE.copy()
    
    entry_menu = TerminalMenu(entry_menu_items, title=menu_title, **menu_options).show()
    
    if entry_menu is None or entry_menu == 5:
        return

    try:
        if entry_menu == 0:
            temp_op.tipo_cond_entrada = 'MARKET'
            temp_op.valor_cond_entrada = 0.0
            temp_op.tiempo_espera_minutos = None
        elif entry_menu == 1:
            temp_op.tipo_cond_entrada = 'PRICE_ABOVE'
            temp_op.valor_cond_entrada = get_input("Activar si precio >", float)
            temp_op.tiempo_espera_minutos = None
        elif entry_menu == 2:
            temp_op.tipo_cond_entrada = 'PRICE_BELOW'
            temp_op.valor_cond_entrada = get_input("Activar si precio <", float)
            temp_op.tiempo_espera_minutos = None
        elif entry_menu == 3:
            temp_op.tipo_cond_entrada = 'TIME_DELAY'
            temp_op.tiempo_espera_minutos = get_input("Activar después de (minutos)", int, min_val=1)
            temp_op.valor_cond_entrada = None
    except UserInputCancelled:
        print("\nEdición de campo cancelada.")
        time.sleep(1)

def _edit_exit_conditions_submenu(temp_op: Operacion):
    """
    Submenú dedicado a editar los Límites y Condiciones de Salida de la operación.
    """
    print("\n--- Editando Límites y Condiciones de Salida ---")

    while True:
        # --- INICIO DE LA MODIFICACIÓN: Crear etiquetas dinámicas para el menú ---
        exit_price_str = "Desactivado"
        if temp_op.tipo_cond_salida:
            op = ">" if temp_op.tipo_cond_salida == 'PRICE_ABOVE' else "<"
            exit_price_str = f"Precio {op} {temp_op.valor_cond_salida:.4f}"
        
        exit_menu_items = [
            f"[1] Condición de Salida por Precio ({exit_price_str})", # Etiqueta dinámica
            f"[2] Límite de Duración (min) ({temp_op.tiempo_maximo_min or 'Ilimitado'})",
            f"[3] Límite de Trades ({temp_op.max_comercios or 'Ilimitado'})",
            f"[4] Acción al Cumplir Límite ({temp_op.accion_al_finalizar})",
            None,
            "[b] Volver al menú anterior"
        ]
        # --- FIN DE LA MODIFICACIÓN ---
        
        menu_options = MENU_STYLE.copy()
        
        exit_main_menu = TerminalMenu(exit_menu_items, title="\nSelecciona un parámetro de salida para editar:", **menu_options).show()

        if exit_main_menu is None or exit_main_menu == 5:
            break
        
        try:
            if exit_main_menu == 0:
                exit_price_menu = TerminalMenu(["[1] Sin condición de precio", "[2] Salir si precio SUPERIOR a", "[3] Salir si precio INFERIOR a", None, "[c] Cancelar"], title="\nCondición de Salida por Precio:").show()
                if exit_price_menu == 0:
                    temp_op.tipo_cond_salida, temp_op.valor_cond_salida = None, None
                elif exit_price_menu == 1:
                    temp_op.tipo_cond_salida, temp_op.valor_cond_salida = 'PRICE_ABOVE', get_input("Salir si precio >", float)
                elif exit_price_menu == 2:
                    temp_op.tipo_cond_salida, temp_op.valor_cond_salida = 'PRICE_BELOW', get_input("Salir si precio <", float)
            
            elif exit_main_menu == 1:
                temp_op.tiempo_maximo_min = get_input("Límite de Duración (min)", int, temp_op.tiempo_maximo_min, min_val=1, is_optional=True)
            
            elif exit_main_menu == 2:
                temp_op.max_comercios = get_input("Límite de Trades", int, temp_op.max_comercios, min_val=1, is_optional=True)
            
            elif exit_main_menu == 3:
                action_menu = TerminalMenu(["[1] Pausar Operación", "[2] Detener y Resetear"], title="\nAcción al Cumplir CUALQUIER Límite:").show()
                if action_menu == 0:
                    temp_op.accion_al_finalizar = 'PAUSAR'
                elif action_menu == 1:
                    temp_op.accion_al_finalizar = 'DETENER'

        except UserInputCancelled:
            print("\nEdición de campo cancelada.")
            time.sleep(1)

def operation_setup_wizard(om_api: Any, side: str, is_modification: bool):
    config_module = _deps.get("config_module")
    if not config_module:
        print("ERROR CRÍTICO: Módulo de configuración no encontrado.")
        time.sleep(3)
        return

    if is_modification:
        temp_op = om_api.get_operation_by_side(side)
        if not temp_op:
            print(f"\nError: No se encontró operación para {side.upper()}.")
            time.sleep(2)
            return
    else:
        defaults = config_module.OPERATION_DEFAULTS
        base_size = defaults["CAPITAL"]["BASE_SIZE_USDT"]
        max_pos = defaults["CAPITAL"]["MAX_POSITIONS"]
        apalancamiento = defaults["CAPITAL"]["LEVERAGE"]
        
        temp_op = Operacion(id=f"op_{side}_{uuid.uuid4().hex[:8]}")
        temp_op.tendencia = "LONG_ONLY" if side == 'long' else "SHORT_ONLY"
        temp_op.apalancamiento = apalancamiento
        
        if defaults["RISK"]["AVERAGING"]["ENABLED"]:
            if side == 'long':
                temp_op.averaging_distance_pct = defaults["RISK"]["AVERAGING"]["DISTANCE_PCT_LONG"]
            else:
                temp_op.averaging_distance_pct = defaults["RISK"]["AVERAGING"]["DISTANCE_PCT_SHORT"]
        else:
            temp_op.averaging_distance_pct = 0.5
        
        temp_op.sl_posicion_individual_pct = defaults["RISK"]["INDIVIDUAL_SL"]["PERCENTAGE"] if defaults["RISK"]["INDIVIDUAL_SL"]["ENABLED"] else None
        
        if defaults["RISK"]["INDIVIDUAL_TSL"]["ENABLED"]:
            temp_op.tsl_activacion_pct = defaults["RISK"]["INDIVIDUAL_TSL"]["TSL_ACTIVATION_PCT"]
            temp_op.tsl_distancia_pct = defaults["RISK"]["INDIVIDUAL_TSL"]["TSL_DISTANCE_PCT"]
        else:
            temp_op.tsl_activacion_pct = None
            temp_op.tsl_distancia_pct = None
        
        dynamic_sl_config = defaults["OPERATION_RISK"].get("DYNAMIC_ROI_SL", {})
        temp_op.dynamic_roi_sl_enabled = dynamic_sl_config.get("ENABLED", False)
        temp_op.dynamic_roi_sl_trail_pct = dynamic_sl_config.get("TRAIL_PCT")
        
        if temp_op.dynamic_roi_sl_enabled:
            temp_op.sl_roi_pct = None
        else:
            temp_op.sl_roi_pct = defaults["OPERATION_RISK"]["ROI_SL_TP"]["PERCENTAGE"] if defaults["OPERATION_RISK"]["ROI_SL_TP"]["ENABLED"] else None

        if defaults["OPERATION_RISK"]["ROI_TSL"]["ENABLED"]:
            temp_op.tsl_roi_activacion_pct = defaults["OPERATION_RISK"]["ROI_TSL"].get("ACTIVATION_PCT")
            temp_op.tsl_roi_distancia_pct = defaults["OPERATION_RISK"]["ROI_TSL"].get("DISTANCE_PCT")
        else:
            temp_op.tsl_roi_activacion_pct = None
            temp_op.tsl_roi_distancia_pct = None
        
        temp_op.auto_reinvest_enabled = defaults.get("PROFIT_MANAGEMENT", {}).get("AUTO_REINVEST_ENABLED", False)

        temp_op.max_comercios = defaults["OPERATION_LIMITS"]["MAX_TRADES"].get("VALUE") if defaults["OPERATION_LIMITS"]["MAX_TRADES"]["ENABLED"] else None
        temp_op.tiempo_maximo_min = defaults["OPERATION_LIMITS"]["MAX_DURATION"].get("MINUTES") if defaults["OPERATION_LIMITS"]["MAX_DURATION"]["ENABLED"] else None
        
        temp_op.accion_al_finalizar = defaults["OPERATION_LIMITS"]["AFTER_STATE"]
        
        for _ in range(max_pos):
            new_pos = LogicalPosition(
                id=f"pos_{uuid.uuid4().hex[:8]}", estado='PENDIENTE', capital_asignado=base_size,
                valor_nominal=base_size * apalancamiento
            )
            temp_op.posiciones.append(new_pos)

    params_changed = False

    while True:
        if is_modification:
            latest_op_state = om_api.get_operation_by_side(side)
            if latest_op_state:
                latest_positions_map = {p.id: p for p in latest_op_state.posiciones}
                for pos_in_editor in temp_op.posiciones:
                    if pos_in_editor.id in latest_positions_map:
                        real_pos_state = latest_positions_map[pos_in_editor.id]
                        pos_in_editor.estado = real_pos_state.estado
                        pos_in_editor.entry_price = real_pos_state.entry_price
                        pos_in_editor.entry_timestamp = real_pos_state.entry_timestamp
                        pos_in_editor.size_contracts = real_pos_state.size_contracts
        
        clear_screen()
        print_tui_header(f"Asistente de Operación {side.upper()}")
        
        _display_setup_box(temp_op, _get_terminal_width(), is_modification)

        menu_items = [
            "[1] Gestionar Lista de Posiciones y Simular Riesgo",
            "[2] Editar Estrategia Global (Apalancamiento, Promediación, Reinversión)",
            "[3] Editar Riesgo por Posición Individual (SL/TSL)",
            "[4] Editar Gestión de Riesgo de Operación (SL/TP por ROI)",
            "[5] Editar Condiciones de Entrada",
            "[6] Editar Condiciones y Límites de Salida",
            None,
            "[s] Guardar Cambios",
            "[c] Cancelar y Volver"
        ]
        
        # Lógica para deshabilitar la edición de condiciones de entrada si la operación está activa.
        if is_modification and temp_op.estado == 'ACTIVA':
            menu_items[4] = "[5] Editar Condiciones de Entrada (No disponible en estado ACTIVA)"
        # --- FIN CÓDIGO NUEVO Y CORREGIDO ---
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nSelecciona una categoría para editar:", **menu_options)
        choice = menu.show()

        try:
            if choice == 0:
                if position_editor:
                    changes_made_in_editor = position_editor.show_position_editor_screen(temp_op, side)
                    if changes_made_in_editor:
                        params_changed = True
                else:
                    print("Error: El módulo editor de posiciones no está disponible.")
                    time.sleep(2)
            
            elif choice == 1:
                print("\n--- Editando Estrategia Global ---")
                
                nuevo_apalancamiento = get_input("Nuevo Apalancamiento (afecta a todas las posiciones)", float, temp_op.apalancamiento, min_val=1.0)
                if nuevo_apalancamiento != temp_op.apalancamiento:
                    temp_op.apalancamiento = nuevo_apalancamiento
                    for pos in temp_op.posiciones:
                        pos.valor_nominal = pos.capital_asignado * nuevo_apalancamiento
                    params_changed = True

                prompt_text = f"Nueva Distancia de Promediación para {side.upper()} (%)"
                nuevo_valor_distancia = get_input(
                    prompt_text, float, temp_op.averaging_distance_pct, 
                    min_val=0.01, is_optional=False
                )
                if nuevo_valor_distancia != temp_op.averaging_distance_pct:
                    temp_op.averaging_distance_pct = nuevo_valor_distancia
                    params_changed = True

                reinvest_menu_title = "\n¿Activar Reinversión Automática de Ganancias?"
                reinvest_choice = TerminalMenu(["[1] Sí, activar", "[2] No, desactivar"], title=reinvest_menu_title, **MENU_STYLE).show()
                if reinvest_choice == 0:
                    temp_op.auto_reinvest_enabled = True
                elif reinvest_choice == 1:
                    temp_op.auto_reinvest_enabled = False
                params_changed = True

            elif choice == 2:
                print("\n--- Editando Riesgo por Posición Individual ---")
                temp_op.sl_posicion_individual_pct = get_input("Nuevo SL Individual (%)", float, temp_op.sl_posicion_individual_pct, min_val=0.0, is_optional=True)
                temp_op.tsl_activacion_pct = get_input("Nueva Activación TSL (%)", float, temp_op.tsl_activacion_pct, min_val=0.0, is_optional=True)
                if temp_op.tsl_activacion_pct:
                    temp_op.tsl_distancia_pct = get_input("Nueva Distancia TSL (%)", float, temp_op.tsl_distancia_pct, min_val=0.01)
                else:
                    temp_op.tsl_distancia_pct = None
                params_changed = True

            elif choice == 3:
                _edit_operation_risk_submenu(temp_op)
                params_changed = True

            elif choice == 4:
                if is_modification and temp_op.estado == 'ACTIVA':
                    print("\nNo se pueden editar las condiciones de entrada mientras la operación está ACTIVA.")
                    time.sleep(2.5)
                    continue
                _edit_entry_conditions_submenu(temp_op)
                params_changed = True

            elif choice == 5:
                _edit_exit_conditions_submenu(temp_op)
                params_changed = True
            # --- FIN CÓDIGO NUEVO Y CORREGIDO ---

            elif choice == 7:
                if not params_changed and is_modification:
                    print("\nNo se realizaron cambios."); time.sleep(1.5)
                    break
                
                clear_screen()
                print_tui_header("Confirmar Cambios")
                _display_setup_box(temp_op, _get_terminal_width(), is_modification)
                
                confirm_menu = TerminalMenu(["[1] Sí, guardar y aplicar", "[2] No, seguir editando"], title="\n¿Confirmas estos parámetros?")
                if confirm_menu.show() == 0:
                    success, msg = om_api.create_or_update_operation(side, temp_op.__dict__)
                    print(f"\n{msg}"); time.sleep(2.5)
                    break
            
            elif choice == 8 or choice is None:
                if params_changed:
                    cancel_confirm = TerminalMenu(["[1] Sí, descartar cambios", "[2] No, seguir editando"], title="\nDescartar cambios no guardados?").show()
                    if cancel_confirm == 0:
                        print("\nCambios descartados."); time.sleep(1.5)
                        break
                else:
                    print("\nAsistente cancelado."); time.sleep(1.5)
                    break

        except UserInputCancelled:
            print("\nEdición de campo cancelada."); time.sleep(1)

def _display_setup_box(operacion: Operacion, box_width: int, is_modification: bool):
    """
    Muestra la caja con la configuración actual de la operación.
    """
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
    capital_data = {
        "Capital Operativo Total": f"${operacion.capital_operativo_logico_actual:.2f} USDT",
        "Total de Posiciones": f"{len(operacion.posiciones)} ({operacion.posiciones_abiertas_count} Abiertas, {operacion.posiciones_pendientes_count} Pendientes)",
    }
    max_key_len = max(len(k) for k in capital_data.keys()) if capital_data else 0
    for label, value in capital_data.items():
        _print_line(label, value, max_key_len)

    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Estrategia Global")
    strategy_data = {
        "Apalancamiento (Fijo)": f"{operacion.apalancamiento:.1f}x",
        "Distancia Promediación (%)": f"{operacion.averaging_distance_pct:.2f}%" if isinstance(operacion.averaging_distance_pct, (int, float)) else "Desactivado",
        "Reinvertir Ganancias": "Activado" if getattr(operacion, 'auto_reinvest_enabled', False) else "Desactivado",
    }
    max_key_len = max(len(k) for k in strategy_data.keys()) if strategy_data else 0
    for label, value in strategy_data.items():
        _print_line(label, value, max_key_len)

    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Riesgo por Posición Individual")
    
    leverage = operacion.apalancamiento if operacion.apalancamiento > 0 else 1.0

    sl_individual_str = "Desactivado"
    if operacion.sl_posicion_individual_pct is not None:
        price_move_pct = operacion.sl_posicion_individual_pct / leverage
        # --- MODIFICACIÓN: Aumentar decimales a 4 ---
        sl_individual_str = f"{operacion.sl_posicion_individual_pct}% (Mov. Precio: {price_move_pct:.4f}%)"

    tsl_act_str = "Desactivado"
    if operacion.tsl_activacion_pct is not None:
        price_move_pct = operacion.tsl_activacion_pct / leverage
        # --- MODIFICACIÓN: Aumentar decimales a 4 ---
        tsl_act_str = f"{operacion.tsl_activacion_pct}% (Mov. Precio: {price_move_pct:.4f}%)"
        
    tsl_dist_str = "N/A"
    if operacion.tsl_distancia_pct is not None:
        price_move_pct = operacion.tsl_distancia_pct / leverage
        # --- MODIFICACIÓN: Aumentar decimales a 4 ---
        tsl_dist_str = f"{operacion.tsl_distancia_pct}% (Mov. Precio: {price_move_pct:.4f}%)"

    risk_data = {
        "SL Individual (%)": sl_individual_str,
        "Activación TSL (%)": tsl_act_str,
        "Distancia TSL (%)": tsl_dist_str if operacion.tsl_activacion_pct else "N/A",
    }
    
    max_key_len = max(len(k) for k in risk_data.keys()) if risk_data else 0
    for label, value in risk_data.items():
        _print_line(label, value, max_key_len)
    
    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Gestión de Riesgo de Operación (Acción: DETENER)")
    
    op_risk_data = {}
    if getattr(operacion, 'dynamic_roi_sl_enabled', False):
        trail_pct = getattr(operacion, 'dynamic_roi_sl_trail_pct', 0) or 0
        op_risk_data["Límite SL/TP por ROI (%)"] = f"DINÁMICO (ROI Realizado - {trail_pct}%)"
    else:
        sl_roi_str = "Desactivado"
        if operacion.sl_roi_pct is not None:
            price_move_pct = operacion.sl_roi_pct / leverage
            # --- MODIFICACIÓN: Aumentar decimales a 4 ---
            sl_roi_str = f"{operacion.sl_roi_pct}% (Mov. Precio Total: {price_move_pct:.4f}%)"
        op_risk_data["Límite SL/TP por ROI (%)"] = sl_roi_str

    op_risk_data["Límite TSL-ROI (Act/Dist %)"] = f"+{operacion.tsl_roi_activacion_pct}% / {operacion.tsl_roi_distancia_pct}%" if operacion.tsl_roi_activacion_pct else "Desactivado"
    
    max_key_len = max(len(k) for k in op_risk_data.keys()) if op_risk_data else 0
    for label, value in op_risk_data.items():
        _print_line(label, value, max_key_len)
    
    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Condición de Entrada")
    
    entry_cond_str = "No definida"
    if operacion.tipo_cond_entrada == 'MARKET': 
        entry_cond_str = "Inmediata (Precio de Mercado)"
    elif operacion.tipo_cond_entrada == 'PRICE_ABOVE' and operacion.valor_cond_entrada is not None: 
        entry_cond_str = f"Precio > {operacion.valor_cond_entrada:.4f}"
    elif operacion.tipo_cond_entrada == 'PRICE_BELOW' and operacion.valor_cond_entrada is not None: 
        entry_cond_str = f"Precio < {operacion.valor_cond_entrada:.4f}"
    elif operacion.tipo_cond_entrada == 'TIME_DELAY' and operacion.tiempo_espera_minutos is not None:
        entry_cond_str = f"Activar después de {operacion.tiempo_espera_minutos} minutos"
    
    _print_line("Condición de Activación", entry_cond_str, 25)

    print("├" + "─" * (box_width - 2) + "┤")
    _print_section_header("Límites de Salida")

    if operacion.tipo_cond_salida:
        op = ">" if operacion.tipo_cond_salida == 'PRICE_ABOVE' else "<"
        exit_price_str = f"Precio {op} {operacion.valor_cond_salida:.4f}"
    else: 
        exit_price_str = "Desactivado"
        
    exit_limits_data = {
        "Salida por Precio": exit_price_str,
        "Duración Máxima (min)": operacion.tiempo_maximo_min or "Ilimitado",
        "Máximo de Trades": operacion.max_comercios or "Ilimitado",
        "Acción al Cumplir Límite": operacion.accion_al_finalizar.upper()
    }
    max_key_len = max(len(k) for k in exit_limits_data.keys()) if exit_limits_data else 0
    for label, value in exit_limits_data.items():
        _print_line(label, value, max_key_len)

    print("└" + "─" * (box_width - 2) + "┘")
