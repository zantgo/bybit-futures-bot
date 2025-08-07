"""
Módulo del Asistente Unificado para la Creación y Modificación de Operaciones.
"""
import time
from typing import Any, Dict
import copy

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
    _create_config_box_line
)

try:
    from core.strategy.entities import Operacion
except ImportError:
    class Operacion: pass

_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

def _display_setup_box(params: Dict, box_width: int, is_modification: bool):
    """Muestra la caja con la configuración actual de la operación."""
    action = "Modificando" if is_modification else "Creando Nueva"
    tendencia = "LONG" if params.get('tendencia') == 'LONG_ONLY' else "SHORT"
    print(f"\n{action} Operación {tendencia}:")
    print("┌" + "─" * (box_width - 2) + "┐")

    max_key_len = 0 

    def _print_line(label, value, key_len):
        content = f"  {label:<{key_len}} : {value}"
        print(_create_config_box_line(content, box_width))
    
    # --- Lógica de cálculo y validación visual ---
    capital_operativo = params.get('operational_margin', 0.0)
    tamaño_base = params.get('tamaño_posicion_base_usdt', 0.0)
    max_pos = params.get('max_posiciones_logicas', 0)
    capital_requerido = tamaño_base * max_pos

    capital_suficiente = capital_operativo >= capital_requerido
    color_requerido = "\033[92m" if capital_suficiente else "\033[91m"
    reset_color = "\033[0m"
    
    print(_create_config_box_line("Capital y Apalancamiento", box_width))
    capital_data = {
        "Capital Operativo Asignado": f"${capital_operativo:.2f} USDT",
        "Tamaño Base por Posición": f"${tamaño_base:.2f} USDT",
        "Máximo de Posiciones": max_pos,
        "Capital Requerido (Tamaño*Pos)": f"{color_requerido}${capital_requerido:.2f} USDT{reset_color}",
        "Apalancamiento": f"{params.get('apalancamiento', 0.0):.1f}x",
    }
    max_key_len = max(len(k) for k in capital_data.keys())
    for label, value in capital_data.items():
        _print_line(label, value, max_key_len)
    
    print("├" + "─" * (box_width - 2) + "┤")
    print(_create_config_box_line("Riesgo por Posición", box_width))
    risk_data = {
        "SL Individual (%)": params.get('sl_posicion_individual_pct') or "Desactivado",
        "Activación TSL (%)": params.get('tsl_activacion_pct') or "Desactivado",
        "Distancia TSL (%)": params.get('tsl_distancia_pct') if params.get('tsl_activacion_pct') else "N/A",
    }
    max_key_len = max(len(k) for k in risk_data.keys())
    for label, value in risk_data.items():
        _print_line(label, value, max_key_len)

    print("├" + "─" * (box_width - 2) + "┤")
    print(_create_config_box_line("Condición de Entrada", box_width))
    if params.get('tipo_cond_entrada') == 'MARKET':
        entry_cond_str = "Inmediata (Precio de Mercado)"
    elif params.get('tipo_cond_entrada') == 'PRICE_ABOVE':
        entry_cond_str = f"Precio > {params.get('valor_cond_entrada', 0.0):.4f}"
    elif params.get('tipo_cond_entrada') == 'PRICE_BELOW':
        entry_cond_str = f"Precio < {params.get('valor_cond_entrada', 0.0):.4f}"
    else:
        entry_cond_str = "No definida"
    _print_line("Condición", entry_cond_str, len("Condición"))
    
    print("├" + "─" * (box_width - 2) + "┤")
    print(_create_config_box_line("Condiciones y Límites de Salida (Cualquiera activa la salida)", box_width))
    
    if params.get('tipo_cond_salida'):
        op = ">" if params.get('tipo_cond_salida') == 'PRICE_ABOVE' else "<"
        exit_price_str = f"Precio {op} {params.get('valor_cond_salida', 0.0):.4f}"
    else:
        exit_price_str = "Desactivado"
        
    sl_roi_val = params.get('sl_roi_pct')
    tsl_act_val = params.get('tsl_roi_activacion_pct')
    
    exit_conditions_data = {
        "Salida por Precio": exit_price_str,
        "Límite SL/TP por ROI (%)": f"{sl_roi_val}" if sl_roi_val is not None else "Desactivado",
        "Límite TSL-ROI (Act/Dist %)": f"+{tsl_act_val}% / {params.get('tsl_roi_distancia_pct')}%" if tsl_act_val else "Desactivado",
        "Límite de Duración (min)": params.get('tiempo_maximo_min') or "Ilimitado",
        "Límite de Trades": params.get('max_comercios') or "Ilimitado",
    }
    max_key_len = max(len(k) for k in exit_conditions_data.keys())
    for label, value in exit_conditions_data.items():
        _print_line(label, value, max_key_len)
    
    print("├" + "─" * (box_width - 2) + "┤")
    _print_line("Acción al Finalizar", params.get('accion_al_finalizar', 'PAUSAR'), max_key_len)

    print("└" + "─" * (box_width - 2) + "┘")

def operation_setup_wizard(om_api: Any, side: str, is_modification: bool):
    """Asistente unificado para crear o modificar una operación."""
    config_module = _deps.get("config_module")
    if not config_module:
        print("ERROR CRÍTICO: Módulo de configuración no encontrado.")
        time.sleep(3)
        return

    if is_modification:
        original_op = om_api.get_operation_by_side(side)
        if not original_op:
            print(f"\nError: No se encontró operación para {side.upper()}.")
            time.sleep(2)
            return
        temp_params = copy.deepcopy(original_op.__dict__)
        if 'operational_margin' not in temp_params:
            temp_params['operational_margin'] = temp_params.get('capital_actual_usdt', 0.0)
    else:
        defaults = config_module.OPERATION_DEFAULTS
        base_size = defaults["CAPITAL"]["BASE_SIZE_USDT"]
        max_pos = defaults["CAPITAL"]["MAX_POSITIONS"]
        temp_params = {
            'tendencia': "LONG_ONLY" if side == 'long' else "SHORT_ONLY",
            'tamaño_posicion_base_usdt': base_size,
            'operational_margin': base_size * max_pos,
            'max_posiciones_logicas': max_pos,
            'apalancamiento': defaults["CAPITAL"]["LEVERAGE"],
            'sl_posicion_individual_pct': defaults["RISK"]["INDIVIDUAL_SL_PCT"],
            'tsl_activacion_pct': defaults["RISK"]["TSL_ACTIVATION_PCT"],
            'tsl_distancia_pct': defaults["RISK"]["TSL_DISTANCE_PCT"],
            'sl_roi_pct': defaults["OPERATION_LIMITS"]["ROI_SL_PCT"]["PERCENTAGE"] if defaults["OPERATION_LIMITS"]["ROI_SL_PCT"]["ENABLED"] else None,
            'tsl_roi_activacion_pct': defaults["OPERATION_LIMITS"]["ROI_TSL"].get("ACTIVATION_PCT") if defaults["OPERATION_LIMITS"]["ROI_TSL"]["ENABLED"] else None,
            'tsl_roi_distancia_pct': defaults["OPERATION_LIMITS"]["ROI_TSL"].get("DISTANCE_PCT") if defaults["OPERATION_LIMITS"]["ROI_TSL"]["ENABLED"] else None,
            'max_comercios': defaults["OPERATION_LIMITS"]["MAX_TRADES"].get("VALUE") if defaults["OPERATION_LIMITS"]["MAX_TRADES"]["ENABLED"] else None,
            'tiempo_maximo_min': defaults["OPERATION_LIMITS"]["MAX_DURATION"].get("MINUTES") if defaults["OPERATION_LIMITS"]["MAX_DURATION"]["ENABLED"] else None,
            'accion_al_finalizar': defaults["OPERATION_LIMITS"]["AFTER_STATE"],
            'tipo_cond_entrada': 'MARKET',
            'valor_cond_entrada': 0.0,
            'tipo_cond_salida': None,
            'valor_cond_salida': None
        }

    params_changed = False

    while True:
        clear_screen()
        print_tui_header(f"Asistente de Operación {side.upper()}")
        
        box_width = _get_terminal_width()
        _display_setup_box(temp_params, box_width, is_modification)

        menu_items = [
            "[1] Editar Capital y Apalancamiento",
            "[2] Editar Riesgo por Posición (SL/TSL)",
            "[3] Editar Condición de Entrada",
            "[4] Editar Condiciones y Límites de Salida",
            None,
            "[s] Guardar Cambios",
            "[c] Cancelar y Volver"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nSelecciona una categoría para editar:", **menu_options)
        choice = menu.show()

        try:
            # --- INICIO DE LA MODIFICACIÓN #3: Corrección de controles y lógica ---
            if choice == 0: # Capital y Apalancamiento
                while True:
                    print("\n--- Editando Capital y Apalancamiento ---")
                    temp_params['operational_margin'] = get_input("Nuevo Capital Operativo (USDT)", float, temp_params['operational_margin'], min_val=0.1)
                    temp_params['tamaño_posicion_base_usdt'] = get_input("Nuevo Tamaño Base por Posición (USDT)", float, temp_params['tamaño_posicion_base_usdt'], min_val=0.1)
                    temp_params['max_posiciones_logicas'] = get_input("Nuevo Máx. de Posiciones", int, temp_params['max_posiciones_logicas'], min_val=1)
                    temp_params['apalancamiento'] = get_input("Nuevo Apalancamiento", float, temp_params['apalancamiento'], min_val=1.0)
                    
                    capital_requerido = temp_params['tamaño_posicion_base_usdt'] * temp_params['max_posiciones_logicas']
                    
                    if temp_params['operational_margin'] >= capital_requerido:
                        params_changed = True
                        break 
                    else:
                        print(f"\n\033[91mERROR DE VALIDACIÓN:\033[0m")
                        print(f"El Capital Requerido (${capital_requerido:.2f}) no puede ser mayor que el Capital Asignado (${temp_params['operational_margin']:.2f}).")
                        print("Por favor, ajusta los valores.")
                        time.sleep(4)
                        # Limpia la pantalla para volver a preguntar
                        clear_screen()
                        print_tui_header(f"Asistente de Operación {side.upper()}")
                        _display_setup_box(temp_params, box_width, is_modification)


            elif choice == 1: # Riesgo por Posición
                print("\n--- Editando Riesgo por Posición ---")
                temp_params['sl_posicion_individual_pct'] = get_input("Nuevo SL Individual (%)", float, temp_params.get('sl_posicion_individual_pct'), min_val=0.0, is_optional=True)
                temp_params['tsl_activacion_pct'] = get_input("Nueva Activación TSL (%)", float, temp_params.get('tsl_activacion_pct'), min_val=0.0, is_optional=True)
                if temp_params.get('tsl_activacion_pct'):
                    temp_params['tsl_distancia_pct'] = get_input("Nueva Distancia TSL (%)", float, temp_params.get('tsl_distancia_pct'), min_val=0.01, is_optional=False)
                else:
                    temp_params['tsl_distancia_pct'] = None
                params_changed = True

            elif choice == 2: # Condición de Entrada
                entry_menu = TerminalMenu(["[1] Inmediata (Market)", "[2] Precio SUPERIOR a", "[3] Precio INFERIOR a"], title="\nSelecciona la Condición de Entrada:").show()
                if entry_menu == 0: temp_params.update({'tipo_cond_entrada': 'MARKET', 'valor_cond_entrada': 0.0})
                elif entry_menu == 1: temp_params.update({'tipo_cond_entrada': 'PRICE_ABOVE', 'valor_cond_entrada': get_input("Activar si precio >", float)})
                elif entry_menu == 2: temp_params.update({'tipo_cond_entrada': 'PRICE_BELOW', 'valor_cond_entrada': get_input("Activar si precio <", float)})
                params_changed = True

            elif choice == 3: # Condiciones y Límites de Salida
                print("\n--- Editando Condiciones y Límites de Salida ---")
                exit_price_menu = TerminalMenu(["[1] Sin condición de precio", "[2] Salir si precio SUPERIOR a", "[3] Salir si precio INFERIOR a"], title="Condición de Salida por Precio:").show()
                if exit_price_menu == 0: temp_params.update({'tipo_cond_salida': None, 'valor_cond_salida': None})
                elif exit_price_menu == 1: temp_params.update({'tipo_cond_salida': 'PRICE_ABOVE', 'valor_cond_salida': get_input("Salir si precio >", float)})
                elif exit_price_menu == 2: temp_params.update({'tipo_cond_salida': 'PRICE_BELOW', 'valor_cond_salida': get_input("Salir si precio <", float)})
                
                sl_roi_val = get_input("Límite SL/TP por ROI (%) (negativo para SL, positivo para TP)", float, temp_params.get('sl_roi_pct'), is_optional=True)
                temp_params['sl_roi_pct'] = sl_roi_val
                
                tsl_act = get_input("Límite TSL-ROI Activación (%)", float, temp_params.get('tsl_roi_activacion_pct'), min_val=0.0, is_optional=True)
                if tsl_act:
                    temp_params['tsl_roi_activacion_pct'] = tsl_act
                    temp_params['tsl_roi_distancia_pct'] = get_input("Límite TSL-ROI Distancia (%)", float, temp_params.get('tsl_roi_distancia_pct'), min_val=0.01)
                else:
                    temp_params['tsl_roi_activacion_pct'] = None
                    temp_params['tsl_roi_distancia_pct'] = None
                
                temp_params['tiempo_maximo_min'] = get_input("Límite de Duración (min)", int, temp_params.get('tiempo_maximo_min'), min_val=1, is_optional=True)
                temp_params['max_comercios'] = get_input("Límite de Trades", int, temp_params.get('max_comercios'), min_val=1, is_optional=True)
                
                action_menu = TerminalMenu(["[1] Pausar Operación", "[2] Detener y Resetear"], title="Acción al Cumplir CUALQUIER Límite:").show()
                if action_menu == 0: temp_params['accion_al_finalizar'] = 'PAUSAR'
                elif action_menu == 1: temp_params['accion_al_finalizar'] = 'DETENER'
                
                params_changed = True

            elif choice == 5: # Guardar
                if not params_changed and is_modification:
                    print("\nNo se realizaron cambios."); time.sleep(1.5)
                    break
                
                capital_requerido = temp_params['tamaño_posicion_base_usdt'] * temp_params['max_posiciones_logicas']
                if temp_params['operational_margin'] < capital_requerido:
                    print("\n\033[91mERROR: No se puede guardar. El capital asignado es insuficiente.\033[0m")
                    time.sleep(4)
                    continue
                
                clear_screen()
                print_tui_header("Confirmar Cambios")
                _display_setup_box(temp_params, _get_terminal_width(), is_modification)
                
                confirm_menu = TerminalMenu(["[1] Sí, guardar y aplicar", "[2] No, seguir editando"], title="\n¿Confirmas estos parámetros?")
                if confirm_menu.show() == 0:
                    success, msg = om_api.create_or_update_operation(side, temp_params)
                    print(f"\n{msg}"); time.sleep(2.5)
                    break
            
            elif choice == 6 or choice is None: # Cancelar
                if params_changed:
                    cancel_confirm = TerminalMenu(["[1] Sí, descartar cambios", "[2] No, seguir editando"], title="\nDescartar cambios no guardados?").show()
                    if cancel_confirm == 0:
                        print("\nCambios descartados."); time.sleep(1.5)
                        break
                else:
                    print("\nAsistente cancelado."); time.sleep(1.5)
                    break
            # --- FIN DE LA MODIFICACIÓN #3 ---

        except UserInputCancelled:
            print("\nEdición de campo cancelada."); time.sleep(1)