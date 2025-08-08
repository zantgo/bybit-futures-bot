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
    from dataclasses import asdict
    from core.strategy.pm import api as pm_api
except ImportError:
    asdict = lambda x: x
    pm_api = None
    class Operacion: pass
    class LogicalPosition: pass


_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

def _display_setup_box(params: Dict, box_width: int, is_modification: bool):
    action = "Modificando" if is_modification else "Creando Nueva"
    tendencia = "LONG" if params.get('tendencia') == 'LONG_ONLY' else "SHORT"
    print(f"\n{action} Operación {tendencia}:")
    print("┌" + "─" * (box_width - 2) + "┐")

    def _print_line(label, value, key_len):
        content = f"  {label:<{key_len}} : {value}"
        print(_create_config_box_line(content, box_width))

    title_capital = "Configuración de Capital y Posiciones"
    print(_create_config_box_line(title_capital.center(box_width - 4), box_width))
    
    posiciones = params.get('posiciones', [])
    capital_operativo_total = sum(p.capital_asignado for p in posiciones)
    
    print("├" + "─" * (box_width - 2) + "┤")
    header = f"  {'ID':<10} {'Estado':<12} {'Capital Asignado':>20}"
    print(_create_config_box_line(_truncate_text(header, box_width-4), box_width))
    print("├" + "─" * (box_width - 2) + "┤")
    
    for pos in posiciones:
        estado_val = pos.estado
        color = "\033[92m" if estado_val == 'ABIERTA' else "\033[96m" if estado_val == 'PENDIENTE' else ""
        reset = "\033[0m"
        line = (
            f"  {str(pos.id)[-6:]:<10} "
            f"{color}{estado_val:<12}{reset} "
            f"{pos.capital_asignado:>20.2f} USDT"
        )
        print(_create_config_box_line(_truncate_text(line, box_width - 4), box_width))
    
    print("├" + "─" * (box_width - 2) + "┤")

    capital_data = {
        "Capital Operativo Total": f"${capital_operativo_total:.2f} USDT",
        "Total de Posiciones": f"{len(posiciones)} ({sum(1 for p in posiciones if p.estado == 'ABIERTA')} Abiertas, {sum(1 for p in posiciones if p.estado == 'PENDIENTE')} Pendientes)",
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

def _manage_position_list(params: Dict, side: str) -> bool:
    while True:
        clear_screen()
        print_tui_header("Gestor de Lista de Posiciones")
        
        # Pasamos el diccionario `params` directamente. _display_setup_box ahora espera objetos.
        # Para ello, creamos un objeto Operacion temporal solo para la visualización.
        temp_op = Operacion(id='temp_wizard')
        for key, value in params.items():
            if hasattr(temp_op, key):
                setattr(temp_op, key, value)
        _display_setup_box(temp_op.__dict__, _get_terminal_width(), True)

        posiciones = params.get('posiciones', [])
        has_pending = any(p.estado == 'PENDIENTE' for p in posiciones)
        has_open = any(p.estado == 'ABIERTA' for p in posiciones)

        menu_items = [
            "[1] Añadir nueva posición PENDIENTE",
            "[2] Modificar capital de TODAS las PENDIENTES",
            "[3] Eliminar la última PENDIENTE",
            None,
            "[4] Cerrar posición ABIERTA específica",
            None,
            "[b] Volver al menú anterior"
        ]

        if not has_pending:
            menu_items[1] = "[2] Modificar capital... (No hay posiciones PENDIENTES)"
            menu_items[2] = "[3] Eliminar última... (No hay posiciones PENDIENTES)"
        if not has_open:
            menu_items[4] = "[4] Cerrar posición... (No hay posiciones ABIERTAS)"
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
        choice = menu.show()

        try:
            if choice == 0:
                capital = get_input("Capital a asignar para la nueva posición (USDT)", float, 1.0, min_val=0.1)
                apalancamiento = params.get('apalancamiento', 10.0)
                new_pos = LogicalPosition(
                    id=f"pos_{uuid.uuid4().hex[:8]}", estado='PENDIENTE', 
                    capital_asignado=capital, valor_nominal=capital * apalancamiento
                )
                params['posiciones'].append(new_pos)
                return True
            
            elif choice == 1:
                if not has_pending:
                    print("\nNo hay posiciones PENDIENTES para modificar."); time.sleep(2)
                    continue
                nuevo_capital = get_input("Nuevo capital para TODAS las PENDIENTES (USDT)", float, 1.0, min_val=0.1)
                for pos in params['posiciones']:
                    if pos.estado == 'PENDIENTE':
                        pos.capital_asignado = nuevo_capital
                        pos.valor_nominal = nuevo_capital * params.get('apalancamiento', 10.0)
                return True

            elif choice == 2:
                if not has_pending:
                    print("\nNo hay posiciones PENDIENTES para eliminar."); time.sleep(2)
                    continue
                for i in range(len(params['posiciones']) - 1, -1, -1):
                    if params['posiciones'][i].estado == 'PENDIENTE':
                        params['posiciones'].pop(i)
                        print("\nÚltima posición PENDIENTE eliminada."); time.sleep(1.5)
                        return True
            
            elif choice == 4:
                if not has_open:
                    print("\nNo hay posiciones ABIERTAS para cerrar."); time.sleep(2)
                    continue
                
                open_positions = [p for p in posiciones if p.estado == 'ABIERTA']
                
                submenu_items = [
                    f"Cerrar Posición ID: ...{p.id[-6:]} (Capital: ${p.capital_asignado:.2f})" 
                    for p in open_positions
                ]
                submenu_items.append("[c] Cancelar")
                
                close_menu = TerminalMenu(submenu_items, title="Selecciona la posición ABIERTA a cerrar:", **MENU_STYLE)
                selected_index_in_submenu = close_menu.show()
                
                if selected_index_in_submenu is not None and selected_index_in_submenu < len(open_positions):
                    # --- INICIO DE LA CORRECCIÓN CLAVE ---
                    # El índice del menú ya es el índice relativo que necesita la API.
                    api_index_to_close = selected_index_in_submenu
                    pos_to_close = open_positions[api_index_to_close]
                    
                    print(f"\nEnviando orden de cierre para la posición ...{pos_to_close.id[-6:]}...")
                    
                    success, msg = pm_api.manual_close_logical_position_by_index(side, api_index_to_close)
                    
                    if success:
                        print(f"\033[92mÉXITO:\033[0m {msg}")
                        # Actualizamos el estado en nuestra copia local para que la UI se refresque
                        pos_to_close.estado = 'PENDIENTE'
                        pos_to_close.entry_timestamp = None
                        pos_to_close.entry_price = None
                        pos_to_close.margin_usdt = 0.0
                        pos_to_close.size_contracts = 0.0
                        pos_to_close.ts_is_active = False
                        pos_to_close.stop_loss_price = None
                        pos_to_close.est_liq_price = None
                        pos_to_close.api_order_id = None
                        
                        time.sleep(2.5)
                        return True # Indicamos que hubo un cambio
                    else:
                        print(f"\033[91mFALLO:\033[0m {msg}")
                        time.sleep(2.5)
                    # --- FIN DE LA CORRECCIÓN CLAVE ---

            elif choice == 6 or choice is None:
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
    else:
        defaults = config_module.OPERATION_DEFAULTS
        base_size = defaults["CAPITAL"]["BASE_SIZE_USDT"]
        max_pos = defaults["CAPITAL"]["MAX_POSITIONS"]
        apalancamiento = defaults["CAPITAL"]["LEVERAGE"]
        
        default_positions = []
        for _ in range(max_pos):
            new_pos = LogicalPosition(
                id=f"pos_{uuid.uuid4().hex[:8]}", estado='PENDIENTE', capital_asignado=base_size,
                valor_nominal=base_size * apalancamiento
            )
            default_positions.append(new_pos)

        temp_params = {
            'tendencia': "LONG_ONLY" if side == 'long' else "SHORT_ONLY", 'posiciones': default_positions,
            'apalancamiento': apalancamiento, 'sl_posicion_individual_pct': defaults["RISK"]["INDIVIDUAL_SL_PCT"],
            'tsl_activacion_pct': defaults["RISK"]["TSL_ACTIVATION_PCT"], 'tsl_distancia_pct': defaults["RISK"]["TSL_DISTANCE_PCT"],
            'sl_roi_pct': defaults["OPERATION_LIMITS"]["ROI_SL_PCT"]["PERCENTAGE"] if defaults["OPERATION_LIMITS"]["ROI_SL_PCT"]["ENABLED"] else None,
            'tsl_roi_activacion_pct': defaults["OPERATION_LIMITS"]["ROI_TSL"].get("ACTIVATION_PCT") if defaults["OPERATION_LIMITS"]["ROI_TSL"]["ENABLED"] else None,
            'tsl_roi_distancia_pct': defaults["OPERATION_LIMITS"]["ROI_TSL"].get("DISTANCE_PCT") if defaults["OPERATION_LIMITS"]["ROI_TSL"]["ENABLED"] else None,
            'max_comercios': defaults["OPERATION_LIMITS"]["MAX_TRADES"].get("VALUE") if defaults["OPERATION_LIMITS"]["MAX_TRADES"]["ENABLED"] else None,
            'tiempo_maximo_min': defaults["OPERATION_LIMITS"]["MAX_DURATION"].get("MINUTES") if defaults["OPERATION_LIMITS"]["MAX_DURATION"]["ENABLED"] else None,
            'accion_al_finalizar': defaults["OPERATION_LIMITS"]["AFTER_STATE"], 'tipo_cond_entrada': 'MARKET',
            'valor_cond_entrada': 0.0, 'tipo_cond_salida': None, 'valor_cond_salida': None
        }

    params_changed = False

    while True:
        clear_screen()
        print_tui_header(f"Asistente de Operación {side.upper()}")
        
        # Convertimos a un objeto temporal para la visualización
        temp_op_display = Operacion(id='temp_wizard')
        for key, value in temp_params.items():
            if hasattr(temp_op_display, key):
                setattr(temp_op_display, key, value)
        _display_setup_box(temp_op_display.__dict__, _get_terminal_width(), is_modification)
        
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
                if _manage_position_list(temp_params, side):
                    params_changed = True
            
            elif choice == 1:
                nuevo_apalancamiento = get_input("Nuevo Apalancamiento (se aplicará a todas las posiciones)", float, temp_params['apalancamiento'], min_val=1.0)
                if nuevo_apalancamiento != temp_params['apalancamiento']:
                    temp_params['apalancamiento'] = nuevo_apalancamiento
                    for pos in temp_params['posiciones']:
                        pos.valor_nominal = pos.capital_asignado * nuevo_apalancamiento
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
                    success, msg = om_api.create_or_update_operation(side, temp_params)
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