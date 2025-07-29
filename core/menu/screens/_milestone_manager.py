"""
Módulo para la Pantalla de Gestión de la Operación Estratégica.

v6.10 (Feedback Visual en Asistente):
- El asistente de configuración ahora proporciona feedback visual inmediato
  después de cada entrada del usuario, confirmando el valor seleccionado.
- Se mejora la claridad y el flujo del asistente para una experiencia
  de usuario superior.
"""
# (COMENTARIO) Docstring de la versión anterior (v6.9) para referencia:
# """
# Módulo para la Pantalla de Gestión de la Operación Estratégica.
# 
# v6.9 (Refinamiento de UI):
# - Se corrige la lógica de los valores por defecto en el asistente para que
#   los límites opcionales desactivados (valor 0) muestren [DESACTIVADO]
#   en el prompt, en lugar de [0], mejorando la claridad.
# """
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
    show_help_popup,
    UserInputCancelled
)

try:
    from core.strategy.pm._entities import Operacion
    import config as config_module
except ImportError:
    class Operacion: pass
    config_module = None


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
        try:
            operacion = pm_api.get_operation()
            if not operacion:
                print("\n\033[93mEsperando inicialización de la operación...\033[0m")
                time.sleep(2)
                continue

            summary = pm_api.get_position_summary()
            current_price = pm_api.get_current_market_price() or 0.0
            
            ticker_symbol = getattr(config_module, 'TICKER_SYMBOL', 'N/A') if config_module else 'N/A'
            header_title = f"Panel de Control: {ticker_symbol} @ {current_price:.4f} USDT"
            clear_screen()
            print_tui_header(header_title)

            if not summary or summary.get('error'):
                error_msg = summary.get('error', 'No se pudo obtener el estado de la operación.')
                print(f"\n\033[91mADVERTENCIA: {error_msg}\033[0m")
                menu_items = ["[r] Reintentar", "[b] Volver al Dashboard"]
                menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
                choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()
                if choice == 0: continue
                else: break
            
            _display_operation_details(summary)
            _display_capital_stats(summary)
            _display_positions_tables(summary, current_price)
            _display_operation_conditions(operacion)

            menu_items, action_map = [], {}
            is_trading_active = operacion.tendencia != 'NEUTRAL'

            if is_trading_active:
                menu_items.extend(["[1] Modificar Operación en Curso", "[2] Detener Operación"])
                action_map = {0: "modify", 1: "stop"}
            else:
                menu_items.extend(["[1] Iniciar Nueva Operación", "[2] Forzar Cierre de Posiciones"])
                action_map = {0: "start_new", 1: "panic_close"}

            next_action_index = len(menu_items)
            menu_items.extend([None, "[r] Refrescar", "[h] Ayuda", "[b] Volver al Dashboard"])
            action_map.update({
                next_action_index + 1: "refresh",
                next_action_index + 2: "help",
                next_action_index + 3: "back"
            })

            menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
            main_menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
            choice = main_menu.show()
            
            action = action_map.get(choice)

            if action == "start_new": _operation_setup_wizard(pm_api, operacion)
            elif action == "modify": _operation_setup_wizard(pm_api, operacion, is_modification=True)
            elif action == "stop": _force_stop_wizard(pm_api)
            elif action == "panic_close": _force_close_all_wizard(pm_api)
            elif action == "refresh": continue
            elif action == "help": show_help_popup("auto_mode")
            else: break
        
        except Exception as e:
            clear_screen(); print_tui_header("Panel de Control de Operación")
            print(f"\n\033[91mERROR CRÍTICO: {e}\033[0m\nOcurrió un error inesperado al renderizar la pantalla.")
            menu_items = ["[r] Reintentar", "[b] Volver al Dashboard"]
            menu_options = MENU_STYLE.copy(); menu_options['clear_screen'] = False
            choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()
            if choice == 0: continue
            else: break

# --- FUNCIONES DE VISUALIZACIÓN Y ASISTENTES ---

def _display_operation_details(summary: Dict[str, Any]):
    print("\n--- Parámetros de la Operación " + "-"*54)
    op_state = summary.get('operation_status', {})
    tendencia = op_state.get('tendencia', 'NEUTRAL')
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m", 'LONG_SHORT': "\033[96m", 'NEUTRAL': "\033[90m"}
    color, reset = color_map.get(tendencia, ""), "\033[0m"
    pos_abiertas = len(summary.get('open_long_positions', [])) + len(summary.get('open_short_positions', []))
    pos_total = op_state.get('max_posiciones_logicas', 0)
    col1 = {
        "Tendencia": f"{color}{tendencia}{reset}",
        "Tamaño Base": f"{op_state.get('tamaño_posicion_base_usdt', 0):.2f}$",
        "Apalancamiento": f"{op_state.get('apalancamiento', 0.0):.1f}x",
        "Posiciones": f"{pos_abiertas} / {pos_total}"
    }
    col2 = {
        "TSL Activación": f"{op_state.get('tsl_activacion_pct', 0.0)}%",
        "TSL Distancia": f"{op_state.get('tsl_distancia_pct', 0.0)}%",
        "SL Individual": f"{op_state.get('sl_posicion_individual_pct', 0.0)}%",
        " ": " "
    }
    max_key_len1 = max(len(k) for k in col1.keys())
    max_key_len2 = max(len(k) for k in col2.keys())
    keys1, keys2 = list(col1.keys()), list(col2.keys())
    for i in range(len(keys1)):
        k1, v1, k2, v2 = keys1[i], col1[keys1[i]], keys2[i], col2[keys2[i]]
        print(f"  {k1:<{max_key_len1}}: {v1:<22} |  {k2:<{max_key_len2}}: {v2}")

def _display_operation_conditions(operacion: Operacion):
    print("\n--- Condiciones de la Operación " + "-"*54)
    estado = 'ACTIVA' if operacion.tendencia != 'NEUTRAL' else 'EN_ESPERA'
    cond_in_str = "No definida"
    if operacion.tipo_cond_entrada == 'MARKET': cond_in_str = "Inmediata (Precio de Mercado)"
    elif operacion.tipo_cond_entrada and operacion.valor_cond_entrada is not None:
        op = ">" if operacion.tipo_cond_entrada == 'PRICE_ABOVE' else "<"
        cond_in_str = f"Precio {op} {operacion.valor_cond_entrada:.4f}"
    status_color_map = {'EN_ESPERA': "\033[93m", 'ACTIVA': "\033[92m"}
    color, reset = status_color_map.get(estado, ""), "\033[0m"
    print(f"  Estado: {color}{estado}{reset}")
    print(f"  Condición de Entrada: {cond_in_str}")
    print(f"  Condiciones de Salida:")
    exit_conditions = []
    if operacion.tipo_cond_salida and operacion.valor_cond_salida is not None:
        op = ">" if operacion.tipo_cond_salida == 'PRICE_ABOVE' else "<"
        exit_conditions.append(f"Precio {op} {operacion.valor_cond_salida:.4f}")
    if operacion.tp_roi_pct is not None: exit_conditions.append(f"TP-ROI >= {operacion.tp_roi_pct}%")
    if operacion.sl_roi_pct is not None: exit_conditions.append(f"SL-ROI <= {operacion.sl_roi_pct}%")
    if operacion.tiempo_maximo_min is not None: exit_conditions.append(f"Tiempo >= {operacion.tiempo_maximo_min} min")
    if operacion.max_comercios is not None: exit_conditions.append(f"Trades >= {operacion.max_comercios}")
    if not exit_conditions: print("    - Ninguna (finalización manual)")
    else: print(f"    - {', '.join(exit_conditions)}")

def _operation_setup_wizard(pm_api: Any, current_op: Operacion, is_modification: bool = False):
    """Asistente único para configurar o modificar la operación estratégica."""
    title = "Modificar Operación Activa" if is_modification else "Configurar Nueva Operación"
    clear_screen(); print_tui_header(title)
    print("\n(Deja un campo en blanco para mantener el valor actual)")
    params_to_update = {}
    
    try:
        if not is_modification:
            print("\n--- 1. Condición de Entrada ---")
            cond_menu_items = ["[1] Activación Inmediata", "[2] Precio SUPERIOR a", "[3] Precio INFERIOR a", None, "[c] Cancelar y Volver"]
            cond_choice = TerminalMenu(cond_menu_items, title="Elige la condición de activación:").show()
            if cond_choice == 0: 
                new_cond_type, new_cond_value = 'MARKET', 0.0
                print("  -> Condición seleccionada: Activación Inmediata")
            elif cond_choice == 1:
                new_cond_type = 'PRICE_ABOVE'
                new_cond_value = get_input("Activar si precio SUPERA", float, default=current_op.valor_cond_entrada)
                print(f"  -> Condición seleccionada: Precio > {new_cond_value}")
            elif cond_choice == 2:
                new_cond_type = 'PRICE_BELOW'
                new_cond_value = get_input("Activar si precio BAJA DE", float, default=current_op.valor_cond_entrada)
                print(f"  -> Condición seleccionada: Precio < {new_cond_value}")
            else: return
            params_to_update['tipo_cond_entrada'] = new_cond_type
            params_to_update['valor_cond_entrada'] = new_cond_value

            print("\n--- 2. Tendencia de Trading ---")
            tendencia_options = ["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT"]
            tendencia_idx = TerminalMenu(tendencia_options, title=f"Elige la Tendencia [Actual: {current_op.tendencia}]").show()
            if tendencia_idx is None: return
            params_to_update['tendencia'] = tendencia_options[tendencia_idx]
            print(f"  -> Tendencia seleccionada: {params_to_update['tendencia']}")
        else:
            print(f"\nModificando Operación ACTIVA (Tendencia: {current_op.tendencia}).")
        
        use_config_defaults = not is_modification
        default_base_size = getattr(config_module, 'POSITION_BASE_SIZE_USDT', 1.0) if use_config_defaults else current_op.tamaño_posicion_base_usdt
        default_max_pos = getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS', 5) if use_config_defaults else current_op.max_posiciones_logicas
        default_leverage = getattr(config_module, 'POSITION_LEVERAGE', 10.0) if use_config_defaults else current_op.apalancamiento
        default_sl_ind = None if use_config_defaults else current_op.sl_posicion_individual_pct
        default_tsl_act = getattr(config_module, 'DEFAULT_TREND_TS_ACTIVATION_PCT', 0.4) if use_config_defaults else current_op.tsl_activacion_pct
        default_tsl_dist = getattr(config_module, 'DEFAULT_TREND_TS_DISTANCE_PCT', 0.1) if use_config_defaults else current_op.tsl_distancia_pct
        default_tp_roi = getattr(config_module, 'DEFAULT_TREND_LIMIT_TP_ROI_PCT', 2.5) if use_config_defaults else current_op.tp_roi_pct
        default_sl_roi = getattr(config_module, 'DEFAULT_TREND_LIMIT_SL_ROI_PCT', -1.5) if use_config_defaults else current_op.sl_roi_pct
        
        max_trades_val = getattr(config_module, 'DEFAULT_TREND_LIMIT_TRADE_COUNT', 0) if use_config_defaults else current_op.max_comercios
        default_max_trades = max_trades_val if max_trades_val else None
        max_duracion_val = getattr(config_module, 'DEFAULT_TREND_LIMIT_DURATION_MINUTES', 0) if use_config_defaults else current_op.tiempo_maximo_min
        default_max_duracion = max_duracion_val if max_duracion_val else None
        
        default_exit_val = current_op.valor_cond_salida
        
        section_num_trading = 3 if not is_modification else 1
        
        print(f"\n--- {section_num_trading}. Parámetros de Trading (Obligatorios) ---")
        base_size = get_input("Tamaño base (USDT)", float, default=default_base_size, min_val=0.01)
        print(f"  -> Tamaño Base establecido en: {base_size:.2f} USDT")
        params_to_update['tamaño_posicion_base_usdt'] = base_size
        max_pos = get_input("Máx. posiciones", int, default=default_max_pos, min_val=1)
        print(f"  -> Máx. Posiciones establecido en: {max_pos}")
        params_to_update['max_posiciones_logicas'] = max_pos
        leverage = get_input("Apalancamiento", float, default=default_leverage, min_val=1.0)
        print(f"  -> Apalancamiento establecido en: {leverage:.1f}x")
        params_to_update['apalancamiento'] = leverage

        section_num_risk = section_num_trading + 1
        print(f"\n--- {section_num_risk}. Riesgo por Posición (Opcional) ---")
        tsl_act = get_input("Activación TSL (%)", float, default=default_tsl_act, disable_value=None)
        print(f"  -> Activación TSL: {'DESACTIVADO' if tsl_act is None else f'{tsl_act}%'}")
        params_to_update['tsl_activacion_pct'] = tsl_act
        tsl_dist = get_input("Distancia TSL (%)", float, default=default_tsl_dist, disable_value=None)
        print(f"  -> Distancia TSL: {'DESACTIVADO' if tsl_dist is None else f'{tsl_dist}%'}")
        params_to_update['tsl_distancia_pct'] = tsl_dist
        sl_ind = get_input("SL individual (%)", float, default=default_sl_ind, disable_value=None)
        print(f"  -> SL Individual: {'DESACTIVADO' if sl_ind is None else f'{sl_ind}%'}")
        params_to_update['sl_posicion_individual_pct'] = sl_ind
        
        section_num_limits = section_num_risk + 1
        print(f"\n--- {section_num_limits}. Condiciones de Salida por Límites (Opcional) ---")
        tp_roi = get_input("TP por ROI (%)", float, default=default_tp_roi, disable_value=None)
        print(f"  -> TP por ROI: {'DESACTIVADO' if tp_roi is None else f'{tp_roi}%'}")
        params_to_update['tp_roi_pct'] = tp_roi
        sl_roi = get_input("SL por ROI (%)", float, default=default_sl_roi, disable_value=None)
        print(f"  -> SL por ROI: {'DESACTIVADO' if sl_roi is None else f'{sl_roi}%'}")
        params_to_update['sl_roi_pct'] = sl_roi
        max_trades = get_input("Máx. trades", int, default=default_max_trades, min_val=1, disable_value=None)
        print(f"  -> Máx. Trades: {'DESACTIVADO' if max_trades is None else max_trades}")
        params_to_update['max_comercios'] = max_trades
        max_duracion = get_input("Duración máx. (min)", int, default=default_max_duracion, min_val=1, disable_value=None)
        print(f"  -> Duración Máx.: {'DESACTIVADA' if max_duracion is None else f'{max_duracion} min'}")
        params_to_update['tiempo_maximo_min'] = max_duracion

        section_num_exit_price = section_num_limits + 1
        print(f"\n--- {section_num_exit_price}. Condición de Salida por Precio (Opcional) ---")
        exit_cond_choice = TerminalMenu(["[1] Sin condición de precio", "[2] Salir si Precio SUPERIOR a", "[3] Salir si Precio INFERIOR a"], title="Añadir/Modificar condición de salida por precio:").show()
        if exit_cond_choice == 0:
            params_to_update['tipo_cond_salida'], params_to_update['valor_cond_salida'] = None, None
            print("  -> Condición de Salida por Precio: DESACTIVADA")
        elif exit_cond_choice == 1:
            params_to_update['tipo_cond_salida'] = 'PRICE_ABOVE'
            val = get_input("Salir si precio SUPERA", float, default=default_exit_val)
            params_to_update['valor_cond_salida'] = val
            print(f"  -> Condición de Salida por Precio: > {val}")
        elif exit_cond_choice == 2:
            params_to_update['tipo_cond_salida'] = 'PRICE_BELOW'
            val = get_input("Salir si precio BAJA DE", float, default=default_exit_val)
            params_to_update['valor_cond_salida'] = val
            print(f"  -> Condición de Salida por Precio: < {val}")
            
    except UserInputCancelled:
        print("\n\nAsistente de configuración cancelado.")
        time.sleep(1.5)
        return
    
    if not params_to_update:
        print("\nNo se realizaron cambios."); time.sleep(1.5)
        return

    if TerminalMenu(["[1] Confirmar y Guardar", "[2] Cancelar"], title="\n¿Guardar estos cambios?", **MENU_STYLE).show() == 0:
        success, msg = pm_api.create_or_update_operation(params_to_update)
        print(f"\n{msg}"); time.sleep(2)
        
def _force_stop_wizard(pm_api: Any):
    title = "¿Cómo deseas finalizar la operación actual?"
    end_menu_items = ["[1] Mantener posiciones y finalizar", "[2] Cerrar todas las posiciones y finalizar", None, "[c] Cancelar"]
    choice = TerminalMenu(end_menu_items, title=title).show()
    if choice in [0, 1]:
        success, msg = pm_api.force_stop_operation(close_positions=(choice == 1))
        print(f"\n{msg}"); time.sleep(2)

def _force_close_all_wizard(pm_api: Any):
    title = "Esta acción cerrará posiciones permanentemente.\n¿Qué posiciones deseas cerrar?"
    close_menu_items = ["[1] Cerrar solo LONGS", "[2] Cerrar solo SHORTS", "[3] Cerrar AMBAS", None, "[c] Cancelar"]
    choice = TerminalMenu(close_menu_items, title=title).show()
    if choice == 0: pm_api.close_all_logical_positions('long', reason="PANIC_CLOSE_ALL"); print("\nÓrdenes de cierre para LONGS enviadas."); time.sleep(2)
    elif choice == 1: pm_api.close_all_logical_positions('short', reason="PANIC_CLOSE_ALL"); print("\nÓrdenes de cierre para SHORTS enviadas."); time.sleep(2)
    elif choice == 2:
        pm_api.close_all_logical_positions('long', reason="PANIC_CLOSE_ALL")
        pm_api.close_all_logical_positions('short', reason="PANIC_CLOSE_ALL")
        print("\nÓrdenes de cierre para TODAS las posiciones enviadas."); time.sleep(2)

def _display_capital_stats(summary: Dict[str, Any]):
    print("\n--- Capital y Rendimiento " + "-"*58)
    op_state = summary.get('operation_status', {})
    op_pnl, op_roi = summary.get('operation_pnl', 0.0), summary.get('operation_roi', 0.0)
    pnl_color, reset = ("\033[92m" if op_pnl >= 0 else "\033[91m"), "\033[0m"
    capital_inicial = op_state.get('capital_inicial_usdt', 0.0)
    pnl_realizado = op_state.get('pnl_realizado_usdt', 0.0)
    capital_actual = capital_inicial + pnl_realizado
    col1 = {"Capital Inicial": f"{capital_inicial:.2f}$", "Capital Actual": f"{capital_actual:.2f}$", "Tiempo Ejecución": op_state.get('tiempo_ejecucion_str', 'N/A')}
    col2 = {"PNL": f"{pnl_color}{op_pnl:+.4f}${reset}", "ROI": f"{pnl_color}{op_roi:+.2f}%{reset}", "Comercios Cerrados": op_state.get('comercios_cerrados_contador', 0)}
    max_key_len = max(len(k) for k in col1.keys())
    for (k1, v1), (k2, v2) in zip(col1.items(), col2.items()):
        print(f"  {k1:<{max_key_len}}: {v1:<20} |  {k2:<18}: {v2}")

def _display_positions_tables(summary: Dict[str, Any], current_price: float):
    print("\n--- Posiciones " + "-"*69)
    def print_table(side: str):
        positions = summary.get(f'open_{side}_positions', [])
        print(f"  Tabla {side.upper()} ({len(positions)})")
        if not positions: print("    (No hay posiciones abiertas)"); return
        header = f"    {'Entrada':>10} {'SL':>10} {'TSL':>15} {'PNL (U)':>15} {'ROI (%)':>10}"
        print(header); print("    " + "-" * (len(header)-4))
        for pos in positions:
            entry, sl, margin, size = pos.get('entry_price', 0.0), pos.get('stop_loss_price'), pos.get('margin_usdt', 0.0), pos.get('size_contracts', 0.0)
            pnl = (current_price - entry) * size if side == 'long' else (entry - current_price) * size
            roi = (pnl / margin) * 100 if margin > 0 else 0.0
            pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
            print(f"    {entry:10.4f} {sl:10.4f if sl else 'N/A':>10} {'Inactivo':>15} {pnl_color}{pnl:14.4f}$\033[0m {pnl_color}{roi:9.2f}%\033[0m")
        print()
    print_table('long'); print_table('short')