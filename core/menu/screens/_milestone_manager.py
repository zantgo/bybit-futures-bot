"""
Módulo para la Pantalla de Gestión de la Operación Estratégica.

v6.4 (UI Mejorada y Salida por Precio):
- El encabezado ahora muestra el ticker y el precio actual.
- Se añade una sección detallada que muestra todos los parámetros de trading
  de la operación activa.
- El asistente de configuración ahora permite definir una condición de salida
  basada en un nivel de precio específico.
- Se ha reordenado el menú de condición de entrada para mayor claridad.
- Se corrige un bug en la lógica de valores por defecto del asistente.
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
    show_help_popup,
    CancelInput 
)

try:
    from core.strategy.pm._entities import Operacion
    # Importar el módulo config para acceder a los valores por defecto y al ticker
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
            summary = pm_api.get_position_summary()
            operacion = pm_api.get_operation()
            current_price = pm_api.get_current_market_price() or 0.0
            
            # --- INICIO DE LA MODIFICACIÓN: Encabezado dinámico ---
            ticker_symbol = getattr(config_module, 'TICKER_SYMBOL', 'N/A') if config_module else 'N/A'
            header_title = f"Panel de Control: {ticker_symbol} @ {current_price:.4f} USDT"
            clear_screen()
            print_tui_header(header_title)
            # --- FIN DE LA MODIFICACIÓN ---

            if not summary or summary.get('error') or not operacion:
                error_msg = summary.get('error', 'No se pudo obtener el estado de la operación.')
                print(f"\n\033[91mADVERTENCIA: {error_msg}\033[0m")
                print("Esto puede deberse a un problema de conexión con el exchange.")
                
                menu_items = ["[r] Reintentar", "[b] Volver al Dashboard"]
                menu_options = MENU_STYLE.copy()
                menu_options['clear_screen'] = False
                choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()
                if choice == 0: continue
                else: break
            
            _display_operation_details(summary)
            _display_capital_stats(summary)
            _display_positions_tables(summary, current_price)
            _display_operation_conditions(operacion)

            menu_items = []
            action_map = {}
            is_trading_active = operacion.tendencia != 'NEUTRAL'

            if is_trading_active:
                menu_items.append("[1] Modificar Operación en Curso")
                menu_items.append("[2] Forzar Fin de Operación")
                action_map = {0: "modify", 1: "stop"}
            else:
                menu_items.append("[1] Iniciar Nueva Operación")
                menu_items.append("[2] Forzar Cierre de Posiciones")
                action_map = {0: "start_new", 1: "panic_close"}

            next_action_index = len(menu_items)
            menu_items.extend([None, "[r] Refrescar", "[h] Ayuda", "[b] Volver al Dashboard"])
            
            action_map[next_action_index + 1] = "refresh"
            action_map[next_action_index + 2] = "help"
            action_map[next_action_index + 3] = "back"

            menu_options = MENU_STYLE.copy()
            menu_options['clear_screen'] = False
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
            clear_screen()
            print_tui_header("Panel de Control de Operación")
            print(f"\n\033[91mERROR CRÍTICO: {e}\033[0m")
            print("Ocurrió un error inesperado al renderizar la pantalla.")
            
            menu_items = ["[r] Reintentar", "[b] Volver al Dashboard"]
            menu_options = MENU_STYLE.copy()
            menu_options['clear_screen'] = False
            choice = TerminalMenu(menu_items, title="\nAcciones:", **menu_options).show()
            if choice == 0: continue
            else: break

# --- FUNCIONES DE VISUALIZACIÓN Y ASISTENTES ---

def _display_operation_conditions(operacion: Operacion):
    print("\n--- Condiciones de la Operación " + "-"*54)
    estado = 'ACTIVA' if operacion.tendencia != 'NEUTRAL' else 'EN_ESPERA'
    
    cond_in_str = "N/A"
    if operacion.tipo_cond_entrada == 'MARKET':
        cond_in_str = "Inmediata (Precio de Mercado)"
    elif operacion.tipo_cond_entrada and operacion.valor_cond_entrada is not None:
        op = ">" if operacion.tipo_cond_entrada == 'PRICE_ABOVE' else "<"
        cond_in_str = f"Precio {op} {operacion.valor_cond_entrada:.4f}"
    
    status_color_map = {'EN_ESPERA': "\033[93m", 'ACTIVA': "\033[92m"}
    color, reset = status_color_map.get(estado, ""), "\033[0m"
    
    print(f"  Estado: {color}{estado}{reset}")
    print(f"  Condición de Entrada: {cond_in_str}")
    
    print(f"  Condiciones de Salida:")
    exit_conditions = []
    # --- INICIO DE LA MODIFICACIÓN: Mostrar condición de salida por precio ---
    if operacion.tipo_cond_salida and operacion.valor_cond_salida is not None:
        op = ">" if operacion.tipo_cond_salida == 'PRICE_ABOVE' else "<"
        exit_conditions.append(f"Precio {op} {operacion.valor_cond_salida:.4f}")
    # --- FIN DE LA MODIFICACIÓN ---
    if operacion.tp_roi_pct is not None: exit_conditions.append(f"TP-ROI >= {operacion.tp_roi_pct}%")
    if operacion.sl_roi_pct is not None: exit_conditions.append(f"SL-ROI <= {operacion.sl_roi_pct}%")
    if operacion.tiempo_maximo_min is not None: exit_conditions.append(f"Tiempo >= {operacion.tiempo_maximo_min} min")
    if operacion.max_comercios is not None: exit_conditions.append(f"Trades >= {operacion.max_comercios}")

    if not exit_conditions: print("    - Ninguna (finalización manual)")
    else: print(f"    - {', '.join(exit_conditions)}")

def _operation_setup_wizard(pm_api: Any, current_op: Operacion, is_modification: bool = False):
    title = "Modificar Operación Activa" if is_modification else "Configurar Nueva Operación"
    clear_screen(); print_tui_header(title)
    print("\n(Deja un campo en blanco para mantener su valor actual)")
    params_to_update = {}

    if not is_modification:
        print("\n--- 1. Condición de Entrada ---")
        # --- INICIO DE LA MODIFICACIÓN: Reordenar menú ---
        cond_menu_items = ["[1] Activación Inmediata", "[2] Precio SUPERIOR a", "[3] Precio INFERIOR a", None, "[c] Cancelar y Volver"]
        cond_choice = TerminalMenu(cond_menu_items, title="Elige la condición de activación:").show()
        
        new_cond_type, new_cond_value = current_op.tipo_cond_entrada, current_op.valor_cond_entrada
        if cond_choice == 0:
            new_cond_type, new_cond_value = 'MARKET', 0.0
        elif cond_choice == 1:
            new_cond_type = 'PRICE_ABOVE'
            val = get_input("Activar si precio SUPERA", float, default=current_op.valor_cond_entrada)
            if not isinstance(val, CancelInput): new_cond_value = val
        elif cond_choice == 2:
            new_cond_type = 'PRICE_BELOW'
            val = get_input("Activar si precio BAJA DE", float, default=current_op.valor_cond_entrada)
            if not isinstance(val, CancelInput): new_cond_value = val
        else:
            return
        # --- FIN DE LA MODIFICACIÓN ---
        params_to_update['tipo_cond_entrada'] = new_cond_type
        params_to_update['valor_cond_entrada'] = new_cond_value

        print("\n--- 2. Parámetros de Trading ---")
        tendencia_idx = TerminalMenu(["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT"], title=f"Tendencia [Actual: {current_op.tendencia}]").show()
        if tendencia_idx is None: return
        params_to_update['tendencia'] = ["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT"][tendencia_idx]
    else:
        print(f"\nModificando Operación ACTIVA (Tendencia: {current_op.tendencia}).")
    
    # --- INICIO DE LA CORRECCIÓN: Usar valores por defecto correctos ---
    use_config_defaults = not is_modification
    default_base_size = getattr(config_module, 'POSITION_BASE_SIZE_USDT', 1.0) if use_config_defaults else current_op.tamaño_posicion_base_usdt
    default_max_pos = getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS', 5) if use_config_defaults else current_op.max_posiciones_logicas
    default_leverage = getattr(config_module, 'POSITION_LEVERAGE', 10.0) if use_config_defaults else current_op.apalancamiento
    default_sl_ind = getattr(config_module, 'DEFAULT_TREND_INDIVIDUAL_SL_PCT', 10.0) if use_config_defaults else current_op.sl_posicion_individual_pct
    default_tsl_act = getattr(config_module, 'DEFAULT_TREND_TS_ACTIVATION_PCT', 0.4) if use_config_defaults else current_op.tsl_activacion_pct
    default_tsl_dist = getattr(config_module, 'DEFAULT_TREND_TS_DISTANCE_PCT', 0.1) if use_config_defaults else current_op.tsl_distancia_pct
    default_tp_roi = getattr(config_module, 'DEFAULT_TREND_LIMIT_TP_ROI_PCT', 2.5) if use_config_defaults else (current_op.tp_roi_pct or 0.0)
    default_sl_roi = getattr(config_module, 'DEFAULT_TREND_LIMIT_SL_ROI_PCT', -1.5) if use_config_defaults else (current_op.sl_roi_pct or 0.0)
    default_max_trades = getattr(config_module, 'DEFAULT_TREND_LIMIT_TRADE_COUNT', 0) if use_config_defaults else (current_op.max_comercios or 0)
    default_max_duracion = getattr(config_module, 'DEFAULT_TREND_LIMIT_DURATION_MINUTES', 0) if use_config_defaults else (current_op.tiempo_maximo_min or 0)
    
    # Parámetros de Trading
    base_size = get_input("Tamaño base (USDT)", float, default=default_base_size)
    if not isinstance(base_size, CancelInput): params_to_update['tamaño_posicion_base_usdt'] = base_size
    max_pos = get_input("Máx. posiciones", int, default=default_max_pos)
    if not isinstance(max_pos, CancelInput): params_to_update['max_posiciones_logicas'] = max_pos
    leverage = get_input("Apalancamiento", float, default=default_leverage)
    if not isinstance(leverage, CancelInput): params_to_update['apalancamiento'] = leverage
    sl_ind = get_input("SL individual (%)", float, default=default_sl_ind)
    if not isinstance(sl_ind, CancelInput): params_to_update['sl_posicion_individual_pct'] = sl_ind
    tsl_act = get_input("Activación TSL (%)", float, default=default_tsl_act)
    if not isinstance(tsl_act, CancelInput): params_to_update['tsl_activacion_pct'] = tsl_act
    tsl_dist = get_input("Distancia TSL (%)", float, default=default_tsl_dist)
    if not isinstance(tsl_dist, CancelInput): params_to_update['tsl_distancia_pct'] = tsl_dist

    # Condiciones de Salida por Límites
    print("\n--- 3. Condiciones de Salida por Límites (0 o vacío para desactivar) ---")
    tp_roi = get_input("TP por ROI (%)", float, default=default_tp_roi)
    if not isinstance(tp_roi, CancelInput): params_to_update['tp_roi_pct'] = tp_roi if tp_roi > 0 else None
    sl_roi = get_input("SL por ROI (%)", float, default=default_sl_roi)
    if not isinstance(sl_roi, CancelInput): params_to_update['sl_roi_pct'] = sl_roi if sl_roi != 0 else None
    max_trades = get_input("Máx. trades", int, default=default_max_trades)
    if not isinstance(max_trades, CancelInput): params_to_update['max_comercios'] = max_trades if max_trades > 0 else None
    max_duracion = get_input("Duración máx. (min)", int, default=default_max_duracion)
    if not isinstance(max_duracion, CancelInput): params_to_update['tiempo_maximo_min'] = max_duracion if max_duracion > 0 else None

    # --- INICIO DE LA MODIFICACIÓN: Añadir condición de salida por precio ---
    print("\n--- 4. Condición de Salida por Precio (Opcional) ---")
    exit_cond_choice = TerminalMenu(["[1] Salir si Precio SUPERIOR a", "[2] Salir si Precio INFERIOR a", "[3] Sin condición de precio"], title="Añadir condición de salida por precio:", **MENU_STYLE).show()
    
    new_exit_cond_type, new_exit_cond_value = current_op.tipo_cond_salida, current_op.valor_cond_salida
    if exit_cond_choice == 0:
        new_exit_cond_type = 'PRICE_ABOVE'
        val = get_input("Salir si precio SUPERA", float, default=current_op.valor_cond_salida)
        if not isinstance(val, CancelInput): new_exit_cond_value = val
    elif exit_cond_choice == 1:
        new_exit_cond_type = 'PRICE_BELOW'
        val = get_input("Salir si precio BAJA DE", float, default=current_op.valor_cond_salida)
        if not isinstance(val, CancelInput): new_exit_cond_value = val
    elif exit_cond_choice == 2:
        new_exit_cond_type, new_exit_cond_value = None, None
    
    params_to_update['tipo_cond_salida'] = new_exit_cond_type
    params_to_update['valor_cond_salida'] = new_exit_cond_value
    # --- FIN DE LA MODIFICACIÓN ---

    if TerminalMenu(["[1] Confirmar y Guardar", "[2] Cancelar"]).show() == 0:
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
    if choice == 0:
        pm_api.close_all_logical_positions('long', reason="PANIC_CLOSE_ALL")
        print("\nÓrdenes de cierre para posiciones LONG enviadas."); time.sleep(2)
    elif choice == 1:
        pm_api.close_all_logical_positions('short', reason="PANIC_CLOSE_ALL")
        print("\nÓrdenes de cierre para posiciones SHORT enviadas."); time.sleep(2)
    elif choice == 2:
        pm_api.close_all_logical_positions('long', reason="PANIC_CLOSE_ALL")
        pm_api.close_all_logical_positions('short', reason="PANIC_CLOSE_ALL")
        print("\nÓrdenes de cierre para TODAS las posiciones enviadas."); time.sleep(2)

def _display_operation_details(summary: Dict[str, Any]):
    print("\n--- Parámetros de la Operación " + "-"*54)
    op_state = summary.get('operation_status', {})
    tendencia = op_state.get('tendencia', 'NEUTRAL')
    
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m", 'LONG_SHORT': "\033[96m", 'NEUTRAL': "\033[90m"}
    color = color_map.get(tendencia, "")
    reset = "\033[0m"

    pos_abiertas = len(summary.get('open_long_positions', [])) + len(summary.get('open_short_positions', []))
    pos_total = op_state.get('max_posiciones_logicas', 0)

    # --- INICIO DE LA MODIFICACIÓN: Mostrar todos los parámetros ---
    col1 = {
        "Tendencia": f"{color}{tendencia}{reset}",
        "Tamaño Base": f"{op_state.get('tamaño_posicion_base_usdt', 0):.2f}$",
        "Apalancamiento": f"{op_state.get('apalancamiento', 0.0):.1f}x",
        "Posiciones": f"{pos_abiertas} / {pos_total}"
    }
    col2 = {
        "SL Individual": f"{op_state.get('sl_posicion_individual_pct', 0.0)}%",
        "TSL Activación": f"{op_state.get('tsl_activacion_pct', 0.0)}%",
        "TSL Distancia": f"{op_state.get('tsl_distancia_pct', 0.0)}%",
        " ": " " # Espaciador para alinear
    }

    max_key_len1 = max(len(k) for k in col1.keys())
    max_key_len2 = max(len(k) for k in col2.keys())
    keys1, keys2 = list(col1.keys()), list(col2.keys())
    
    for i in range(len(keys1)):
        k1, v1 = keys1[i], col1[keys1[i]]
        k2, v2 = keys2[i], col2[keys2[i]]
        print(f"  {k1:<{max_key_len1}}: {v1:<22} |  {k2:<{max_key_len2}}: {v2}")
    # --- FIN DE LA MODIFICACIÓN ---

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
        if not positions:
            print("    (No hay posiciones abiertas)")
            return
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