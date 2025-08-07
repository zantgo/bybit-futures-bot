# ./core/menu/screens/operation_manager/_wizard_setup.py

"""
Módulo del Asistente Unificado para la Creación y Modificación de Operaciones.
Actualizado para gestionar una lista de posiciones individuales.
"""
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
    _create_config_box_line, # La función importada
    _truncate_text,
    _clean_ansi_codes,
)

try:
    from core.strategy.entities import Operacion, LogicalPosition
    from dataclasses import asdict
except ImportError:
    asdict = lambda x: x
    class Operacion: pass
    class LogicalPosition: pass


_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

def _display_setup_box(params: Dict, box_width: int, is_modification: bool):
    """
    Muestra la caja con la configuración actual de la operación, con formato de tabla corregido.
    """
    action = "Modificando" if is_modification else "Creando Nueva"
    tendencia = "LONG" if params.get('tendencia') == 'LONG_ONLY' else "SHORT"
    print(f"\n{action} Operación {tendencia}:")
    print("┌" + "─" * (box_width - 2) + "┐")

    def _print_line(label, value, key_len):
        content = f"  {label:<{key_len}} : {value}"
        print(_create_config_box_line(content, box_width))

    # --- INICIO DE LA CORRECCIÓN ---
    # La función _create_config_box_line ya no acepta 'alignment'.
    # Para centrar el texto, lo hacemos manualmente antes de pasar el contenido.
    title_capital = "Configuración de Capital y Posiciones"
    print(_create_config_box_line(title_capital.center(box_width - 4), box_width))
    # --- FIN DE LA CORRECCIÓN ---
    
    posiciones = params.get('posiciones', [])
    capital_operativo_total = sum(p.get('capital_asignado', 0.0) for p in posiciones)
    
    print("├" + "─" * (box_width - 2) + "┤")
    header = f"  {'ID':<10} {'Estado':<12} {'Capital Asignado':>20}"
    print(_create_config_box_line(_truncate_text(header, box_width-4), box_width))
    print("├" + "─" * (box_width - 2) + "┤")
    
    for pos in posiciones:
        estado_val = pos.get('estado', 'N/A')
        color = "\033[92m" if estado_val == 'ABIERTA' else "\033[96m"
        reset = "\033[0m"
        line = (
            f"  {str(pos.get('id', ''))[-6:]:<10} "
            f"{color}{estado_val:<12}{reset} "
            f"{pos.get('capital_asignado', 0.0):>20.2f} USDT"
        )
        print(_create_config_box_line(_truncate_text(line, box_width - 4), box_width))
    
    print("├" + "─" * (box_width - 2) + "┤")

    capital_data = {
        "Capital Operativo Total": f"${capital_operativo_total:.2f} USDT",
        "Total de Posiciones": f"{len(posiciones)} ({sum(1 for p in posiciones if p.get('estado') == 'ABIERTA')} Abiertas, {sum(1 for p in posiciones if p.get('estado') == 'PENDIENTE')} Pendientes)",
        "Apalancamiento (Fijo)": f"{params.get('apalancamiento', 0.0):.1f}x",
    }
    max_key_len = max(len(k) for k in capital_data.keys())
    for label, value in capital_data.items():
        _print_line(label, value, max_key_len)
    
    print("├" + "─" * (box_width - 2) + "┤")
    title_riesgo = "Riesgo por Posición"
    print(_create_config_box_line(title_riesgo.center(box_width - 4), box_width))
    risk_data = {
        "SL Individual (%)": params.get('sl_posicion_individual_pct') or "Desactivado",
        "Activación TSL (%)": params.get('tsl_activacion_pct') or "Desactivado",
        "Distancia TSL (%)": params.get('tsl_distancia_pct') if params.get('tsl_activacion_pct') else "N/A",
    }
    max_key_len = max(len(k) for k in risk_data.keys())
    for label, value in risk_data.items():
        _print_line(label, value, max_key_len)

    print("├" + "─" * (box_width - 2) + "┤")
    title_entrada = "Condición de Entrada"
    print(_create_config_box_line(title_entrada.center(box_width - 4), box_width))
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
    title_salida = "Condiciones y Límites de Salida"
    print(_create_config_box_line(title_salida.center(box_width - 4), box_width))
    
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
    _print_line("Acción al Finalizar", params.get('accion_al_finalizar', 'PAUSAR').upper(), max_key_len)

    print("└" + "─" * (box_width - 2) + "┘")

def _manage_position_list(params: Dict) -> bool:
    while True:
        clear_screen()
        print_tui_header("Gestor de Lista de Posiciones")
        _display_setup_box(params, _get_terminal_width(), True)

        posiciones = params.get('posiciones', [])
        has_pending = any(p.get('estado') == 'PENDIENTE' for p in posiciones)

        menu_items = [
            "[1] Añadir nueva posición PENDIENTE",
            "[2] Modificar capital de TODAS las posiciones PENDIENTES",
            "[3] Eliminar la última posición PENDIENTE",
            None,
            "[b] Volver al menú anterior"
        ]

        if not has_pending:
            menu_items[1] = "[2] Modificar capital... (No hay posiciones pendientes)"
            menu_items[2] = "[3] Eliminar última... (No hay posiciones pendientes)"
        
        menu = TerminalMenu(menu_items, title="\nAcciones:", **MENU_STYLE)
        choice = menu.show()

        try:
            if choice == 0:
                capital = get_input("Capital a asignar para la nueva posición (USDT)", float, 1.0, min_val=0.1)
                apalancamiento = params.get('apalancamiento', 10.0)
                new_pos = {
                    'id': f"pos_{uuid.uuid4().hex[:8]}",
                    'estado': 'PENDIENTE',
                    'capital_asignado': capital,
                    'valor_nominal': capital * apalancamiento,
                    'entry_timestamp': None, 'entry_price': None, 'margin_usdt': 0.0,
                    'size_contracts': 0.0, 'tsl_activation_pct_at_open': 0.0,
                    'tsl_distance_pct_at_open': 0.0, 'ts_is_active': False
                }
                params['posiciones'].append(new_pos)
                return True
            
            elif choice == 1:
                if not has_pending:
                    print("\nNo hay posiciones pendientes para modificar."); time.sleep(2)
                    continue
                nuevo_capital = get_input("Nuevo capital para TODAS las posiciones pendientes (USDT)", float, 1.0, min_val=0.1)
                for pos in params['posiciones']:
                    if pos.get('estado') == 'PENDIENTE':
                        pos['capital_asignado'] = nuevo_capital
                        pos['valor_nominal'] = nuevo_capital * params.get('apalancamiento', 10.0)
                return True

            elif choice == 2:
                if not has_pending:
                    print("\nNo hay posiciones pendientes para eliminar."); time.sleep(2)
                    continue
                for i in range(len(params['posiciones']) - 1, -1, -1):
                    if params['posiciones'][i].get('estado') == 'PENDIENTE':
                        params['posiciones'].pop(i)
                        print("\nÚltima posición pendiente eliminada."); time.sleep(1.5)
                        return True
            
            elif choice == 4 or choice is None:
                return False

        except UserInputCancelled:
            print("\nAcción cancelada."); time.sleep(1)


def operation_setup_wizard(om_api: Any, side: str, is_modification: bool):
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
        temp_params['posiciones'] = [asdict(p) for p in temp_params['posiciones']]
    else:
        defaults = config_module.OPERATION_DEFAULTS
        base_size = defaults["CAPITAL"]["BASE_SIZE_USDT"]
        max_pos = defaults["CAPITAL"]["MAX_POSITIONS"]
        apalancamiento = defaults["CAPITAL"]["LEVERAGE"]
        
        default_positions = []
        for _ in range(max_pos):
            new_pos = {
                'id': f"pos_{uuid.uuid4().hex[:8]}",
                'estado': 'PENDIENTE', 'capital_asignado': base_size,
                'valor_nominal': base_size * apalancamiento,
                'entry_timestamp': None, 'entry_price': None, 'margin_usdt': 0.0,
                'size_contracts': 0.0, 'tsl_activation_pct_at_open': 0.0,
                'tsl_distance_pct_at_open': 0.0, 'ts_is_active': False
            }
            default_positions.append(new_pos)

        temp_params = {
            'tendencia': "LONG_ONLY" if side == 'long' else "SHORT_ONLY",
            'posiciones': default_positions,
            'apalancamiento': apalancamiento,
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
            "[1] Gestionar Lista de Posiciones",
            "[2] Editar Apalancamiento (Fijo para toda la operación)",
            "[3] Editar Riesgo por Posición (SL/TSL)",
            "[4] Editar Condición de Entrada",
            "[5] Editar Límites y Salida de Operación",
            None,
            "[s] Guardar Cambios",
            "[c] Cancelar y Volver"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nSelecciona una categoría para editar:", **menu_options)
        choice = menu.show()

        try:
            if choice == 0:
                if _manage_position_list(temp_params):
                    params_changed = True
            
            elif choice == 1:
                nuevo_apalancamiento = get_input("Nuevo Apalancamiento (se aplicará a todas las posiciones)", float, temp_params['apalancamiento'], min_val=1.0)
                if nuevo_apalancamiento != temp_params['apalancamiento']:
                    temp_params['apalancamiento'] = nuevo_apalancamiento
                    for pos in temp_params['posiciones']:
                        pos['valor_nominal'] = pos['capital_asignado'] * nuevo_apalancamiento
                    params_changed = True

            elif choice == 2:
                print("\n--- Editando Riesgo por Posición ---")
                temp_params['sl_posicion_individual_pct'] = get_input("Nuevo SL Individual (%)", float, temp_params.get('sl_posicion_individual_pct'), min_val=0.0, is_optional=True)
                temp_params['tsl_activacion_pct'] = get_input("Nueva Activación TSL (%)", float, temp_params.get('tsl_activacion_pct'), min_val=0.0, is_optional=True)
                if temp_params.get('tsl_activacion_pct'):
                    temp_params['tsl_distancia_pct'] = get_input("Nueva Distancia TSL (%)", float, temp_params.get('tsl_distancia_pct'), min_val=0.01, is_optional=False)
                else:
                    temp_params['tsl_distancia_pct'] = None
                params_changed = True

            elif choice == 3:
                entry_menu = TerminalMenu(["[1] Inmediata (Market)", "[2] Precio SUPERIOR a", "[3] Precio INFERIOR a"], title="\nSelecciona la Condición de Entrada:").show()
                if entry_menu == 0: temp_params.update({'tipo_cond_entrada': 'MARKET', 'valor_cond_entrada': 0.0})
                elif entry_menu == 1: temp_params.update({'tipo_cond_entrada': 'PRICE_ABOVE', 'valor_cond_entrada': get_input("Activar si precio >", float)})
                elif entry_menu == 2: temp_params.update({'tipo_cond_entrada': 'PRICE_BELOW', 'valor_cond_entrada': get_input("Activar si precio <", float)})
                params_changed = True

            elif choice == 4:
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

            elif choice == 6:
                if not params_changed and is_modification:
                    print("\nNo se realizaron cambios."); time.sleep(1.5)
                    break
                
                clear_screen()
                print_tui_header("Confirmar Cambios")
                _display_setup_box(temp_params, _get_terminal_width(), is_modification)
                
                confirm_menu = TerminalMenu(["[1] Sí, guardar y aplicar", "[2] No, seguir editando"], title="\n¿Confirmas estos parámetros?")
                if confirm_menu.show() == 0:
                    params_to_save = copy.deepcopy(temp_params)
                    success, msg = om_api.create_or_update_operation(side, params_to_save)
                    print(f"\n{msg}"); time.sleep(2.5)
                    break
            
            elif choice == 7 or choice is None:
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