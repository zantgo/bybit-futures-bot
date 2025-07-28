"""
Módulo para la Pantalla de Gestión de la Operación Estratégica.

v6.0 (Modelo de Operación Única):
- Completamente refactorizado para eliminar el concepto de Hitos.
- La pantalla ahora es un "Panel de Control de Operación" que permite
  configurar, modificar y controlar una única operación estratégica.
- Se eliminan todas las funciones relacionadas con la gestión de un
  árbol de decisiones.
- Se introduce un nuevo "Asistente de Configuración de Operación".
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
    # (COMENTADO) Ya no se usan las entidades de Hitos.
    # from core.strategy.pm._entities import (
    #     Hito, CondicionHito, AccionHito, ConfiguracionOperacion
    # )
    from core.strategy.pm._entities import Operacion
except ImportError:
    # class Hito: pass
    # class CondicionHito: pass
    # class AccionHito: pass
    # class ConfiguracionOperacion: pass
    class Operacion: pass


_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

# --- LÓGICA DE LA PANTALLA PRINCIPAL (NUEVA VERSIÓN v6.0) ---
def show_milestone_manager_screen():
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return

    pm_api = _deps.get("position_manager_api_module")
    if not pm_api:
        print("ERROR CRÍTICO: PM API no inyectada."); time.sleep(3); return

    while True:
        clear_screen()
        print_tui_header("Panel de Control de Operación")
        
        summary = pm_api.get_position_summary()
        # (NUEVO) Se obtiene el objeto de operación única en lugar de una lista de hitos.
        operacion = pm_api.get_operation()
        # (COMENTADO) La llamada a get_all_milestones() se elimina.
        # all_milestones = pm_api.get_all_milestones()
        current_price = pm_api.get_current_market_price() or 0.0

        if not summary or 'error' in summary or not operacion:
            print(f"Error obteniendo datos del PM: {summary.get('error', 'Desconocido')}")
            time.sleep(2)
            continue

        _display_operation_details(summary)
        _display_capital_stats(summary)
        _display_positions_tables(summary, current_price)
        # (MODIFICADO) Se llama a la nueva función que muestra las condiciones de la operación.
        _display_operation_conditions(operacion, current_price)
        # (COMENTADO) La llamada a _display_decision_tree() se elimina.
        # _display_decision_tree(all_milestones, summary.get('operation_status', {}))

        # (NUEVO) El menú ahora es dinámico y se adapta al estado de la operación.
        menu_items = [
            "[1] Configurar/Modificar Operación",
        ]
        if operacion.estado == 'EN_ESPERA':
            menu_items.append("[2] Forzar Inicio de Operación")
        elif operacion.estado == 'ACTIVA':
            menu_items.append("[2] Forzar Fin de Operación")
        
        menu_items.extend([
            None,
            "[r] Refrescar",
            "[h] Ayuda",
            "[b] Volver al Dashboard"
        ])
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        main_menu = TerminalMenu(menu_items, title="\nAcciones:", **menu_options)
        choice = main_menu.show()
        
        # (NUEVO) Lógica de menú refactorizada para la operación única.
        if choice == 0:
            _operation_setup_wizard(pm_api, operacion)
        elif choice == 1:
            if operacion.estado == 'EN_ESPERA':
                # (NUEVO) Se llama a la nueva función de la API.
                success, msg = pm_api.force_start_operation()
                print(f"\n{msg}"); time.sleep(2)
            elif operacion.estado == 'ACTIVA':
                _end_operation_wizard(pm_api)
        elif choice == 3: # Corresponde a 'Refrescar'
            continue
        elif choice == 4: # Corresponde a 'Ayuda'
            show_help_popup("auto_mode")
        else:
            break

# --- FUNCIONES DE VISUALIZACIÓN Y ASISTENTES (REFACTORIZADAS) ---

# (NUEVO) Función para mostrar las condiciones de la operación única. Reemplaza a _display_decision_tree.
def _display_operation_conditions(operacion: Operacion, current_price: float):
    print("\n--- Estrategia de la Operación " + "-"*53)
    
    # Condición de Entrada
    cond_in_str = "N/A"
    if operacion.tipo_cond_entrada == 'MARKET':
        cond_in_str = "Inmediata (Precio de Mercado)"
    elif operacion.tipo_cond_entrada and operacion.valor_cond_entrada is not None:
        op = ">" if operacion.tipo_cond_entrada == 'PRICE_ABOVE' else "<"
        cond_in_str = f"Precio {op} {operacion.valor_cond_entrada:.4f}"
    
    status_color_map = {'EN_ESPERA': "\033[93m", 'ACTIVA': "\033[92m", 'FINALIZADA': "\033[90m"}
    color = status_color_map.get(operacion.estado, "")
    reset = "\033[0m"
    
    print(f"  Estado: {color}{operacion.estado}{reset}")
    print(f"  Condición de Entrada: {cond_in_str}")
    
    # Condiciones de Salida
    print(f"  Condiciones de Salida:")
    exit_conditions = []
    if operacion.tp_roi_pct is not None:
        exit_conditions.append(f"TP si ROI >= {operacion.tp_roi_pct}%")
    if operacion.sl_roi_pct is not None:
        exit_conditions.append(f"SL si ROI <= {operacion.sl_roi_pct}%")
    if operacion.tiempo_maximo_min is not None:
        exit_conditions.append(f"Tiempo >= {operacion.tiempo_maximo_min} min")
    if operacion.max_comercios is not None:
        exit_conditions.append(f"Trades >= {operacion.max_comercios}")
    
    if not exit_conditions:
        print("    - Ninguna (finalización manual)")
    else:
        print(f"    - {', '.join(exit_conditions)}")


# (NUEVO) Asistente único para configurar la operación. Reemplaza a _create_milestone_wizard.
def _operation_setup_wizard(pm_api: Any, current_op: Operacion):
    """Asistente único para crear o modificar la operación estratégica."""
    title = "Asistente de Configuración de Operación"
    clear_screen(); print_tui_header(title)
    
    print("\nDefine los parámetros para la próxima operación o modifica la actual.")
    print("(Deja un campo en blanco para mantener su valor actual)")
    
    # --- Paso 1: Condición de Entrada ---
    print("\n--- 1. Condición de Entrada ---")
    cond_choice = TerminalMenu(["Precio SUPERIOR a", "Precio INFERIOR a", "Activación Inmediata (Mercado)"]).show()
    
    new_cond_type, new_cond_value = current_op.tipo_cond_entrada, current_op.valor_cond_entrada
    if cond_choice == 0:
        new_cond_type = 'PRICE_ABOVE'
        val = get_input(f"Activar si precio SUPERA", float, default=current_op.valor_cond_entrada)
        if not isinstance(val, CancelInput): new_cond_value = val
    elif cond_choice == 1:
        new_cond_type = 'PRICE_BELOW'
        val = get_input(f"Activar si precio BAJA DE", float, default=current_op.valor_cond_entrada)
        if not isinstance(val, CancelInput): new_cond_value = val
    elif cond_choice == 2:
        new_cond_type, new_cond_value = 'MARKET', 0.0
    
    # --- Paso 2: Parámetros de Trading ---
    print("\n--- 2. Parámetros de Trading ---")
    tendencia_idx = TerminalMenu(["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT", "NEUTRAL"], title=f"Tendencia [Actual: {current_op.tendencia}]").show()
    new_tendencia = ["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT", "NEUTRAL"][tendencia_idx] if tendencia_idx is not None else current_op.tendencia

    new_base_size = get_input("Tamaño base (USDT)", float, default=current_op.tamaño_posicion_base_usdt)
    new_max_pos = get_input("Máx. posiciones", int, default=current_op.max_posiciones_logicas)
    new_leverage = get_input("Apalancamiento", float, default=current_op.apalancamiento)
    new_sl_ind = get_input("SL individual (%)", float, default=current_op.sl_posicion_individual_pct)
    new_tsl_act = get_input("Activación TSL (%)", float, default=current_op.tsl_activacion_pct)
    new_tsl_dist = get_input("Distancia TSL (%)", float, default=current_op.tsl_distancia_pct)

    # --- Paso 3: Condiciones de Salida ---
    print("\n--- 3. Condiciones de Salida (0 o vacío para desactivar) ---")
    new_tp_roi = get_input("TP por ROI (%)", float, default=current_op.tp_roi_pct or 0)
    new_sl_roi = get_input("SL por ROI (%)", float, default=current_op.sl_roi_pct or 0)
    new_max_trades = get_input("Máx. trades", int, default=current_op.max_comercios or 0)
    new_max_duracion = get_input("Duración máx. (min)", int, default=current_op.tiempo_maximo_min or 0)

    # Recopilar todos los parámetros en un diccionario
    params_to_update = {
        'tipo_cond_entrada': new_cond_type,
        'valor_cond_entrada': new_cond_value,
        'tendencia': new_tendencia,
        'tamaño_posicion_base_usdt': new_base_size if not isinstance(new_base_size, CancelInput) else current_op.tamaño_posicion_base_usdt,
        'max_posiciones_logicas': new_max_pos if not isinstance(new_max_pos, CancelInput) else current_op.max_posiciones_logicas,
        'apalancamiento': new_leverage if not isinstance(new_leverage, CancelInput) else current_op.apalancamiento,
        'sl_posicion_individual_pct': new_sl_ind if not isinstance(new_sl_ind, CancelInput) else current_op.sl_posicion_individual_pct,
        'tsl_activacion_pct': new_tsl_act if not isinstance(new_tsl_act, CancelInput) else current_op.tsl_activacion_pct,
        'tsl_distancia_pct': new_tsl_dist if not isinstance(new_tsl_dist, CancelInput) else current_op.tsl_distancia_pct,
        'tp_roi_pct': new_tp_roi if not isinstance(new_tp_roi, CancelInput) and new_tp_roi > 0 else None,
        'sl_roi_pct': new_sl_roi if not isinstance(new_sl_roi, CancelInput) and new_sl_roi != 0 else None,
        'max_comercios': new_max_trades if not isinstance(new_max_trades, CancelInput) and new_max_trades > 0 else None,
        'tiempo_maximo_min': new_max_duracion if not isinstance(new_max_duracion, CancelInput) and new_max_duracion > 0 else None,
    }

    if TerminalMenu(["[1] Confirmar y Guardar", "[2] Cancelar"]).show() == 0:
        # (NUEVO) Se llama a la nueva función de la API para actualizar la operación.
        success, msg = pm_api.create_or_update_operation(params_to_update)
        print(f"\n{msg}"); time.sleep(2)


# (MODIFICADO) Ligeramente adaptada para el nuevo modelo de datos del summary.
def _display_operation_details(summary: Dict[str, Any]):
    print("\n--- Detalles de la Operación " + "-"*55)
    op_state = summary.get('operation_status', {})
    # En el nuevo modelo, operation_status es el dict de la operación, no un sub-diccionario.
    config_op = op_state 
    tendencia = config_op.get('tendencia', 'NEUTRAL')
    
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m", 'LONG_SHORT': "\033[96m", 'NEUTRAL': "\033[90m"}
    color = color_map.get(tendencia, "")
    reset = "\033[0m"

    price_at_start = "N/A"
    
    pos_abiertas = len(summary.get('open_long_positions', [])) + len(summary.get('open_short_positions', []))
    pos_total = config_op.get('max_posiciones_logicas', 0)

    capital_en_uso = sum(p.get('margin_usdt', 0) for p in summary.get('open_long_positions', [])) + \
                     sum(p.get('margin_usdt', 0) for p in summary.get('open_short_positions', []))
    
    capital_total_op = config_op.get('tamaño_posicion_base_usdt', 0) * pos_total

    print(f"  Tendencia: {color}{tendencia:<12}{reset} | Precio Entrada (Op): {price_at_start:<15} | Precio Salida (Op): N/A")
    print(f"  Tamaño Posición Base: {config_op.get('tamaño_posicion_base_usdt', 0):.2f}$")
    print(f"  Posiciones Abiertas / Total: {pos_abiertas} / {pos_total}")
    print(f"  Capital en Uso / Total Op:   {capital_en_uso:.2f}$ / {capital_total_op:.2f}$")

# (MODIFICADO) Ligeramente adaptada para el nuevo modelo de datos del summary.
def _display_capital_stats(summary: Dict[str, Any]):
    print("\n--- Capital y Rendimiento " + "-"*58)
    op_state = summary.get('operation_status', {})
    op_pnl = summary.get('operation_pnl', 0.0)
    op_roi = summary.get('operation_roi', 0.0)
    pnl_color = "\033[92m" if op_pnl >= 0 else "\033[91m"
    reset = "\033[0m"

    # Lógica actualizada para capital actual
    capital_inicial = op_state.get('capital_inicial_usdt', 0.0)
    pnl_realizado = op_state.get('pnl_realizado_usdt', 0.0)
    capital_actual = capital_inicial + pnl_realizado

    col1 = {
        "Capital Inicial": f"{capital_inicial:.2f}$",
        "Capital Actual": f"{capital_actual:.2f}$",
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

# (MODIFICADO) Ligeramente adaptada para ser más robusta.
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
            
            pnl = (current_price - entry) * size if side == 'long' else (entry - current_price) * size
            roi = (pnl / margin) * 100 if margin > 0 else 0.0
            pnl_color = COLOR_GREEN if pnl >= 0 else COLOR_RED

            entry_str = f"{entry:10.4f}"
            sl_str = f"{sl:10.4f}" if sl else f"{'N/A':>10}"
            tsl_str = f"{ts_info:>15}"
            pnl_str = f"{pnl_color}{pnl:14.4f}${COLOR_RESET}"
            roi_str = f"{pnl_color}{roi:9.2f}%{COLOR_RESET}"

            print(f"    {entry_str} {sl_str} {tsl_str} {pnl_str} {roi_str}")
        print()

    print_table('long')
    print_table('short')

# (MODIFICADO) Adaptado a la nueva lógica y nombres de funciones de la API.
def _end_operation_wizard(pm_api: Any):
    title = "¿Cómo deseas finalizar la operación actual?"
    end_menu_items = ["[1] Mantener posiciones y finalizar", "[2] Cerrar todas las posiciones y finalizar", None, "[c] Cancelar"]
    choice = TerminalMenu(end_menu_items, title=title).show()
    if choice in [0, 1]:
        # (NUEVO) Se llama a la función `force_stop_operation`
        success, msg = pm_api.force_stop_operation(close_positions=(choice == 1))
        print(f"\n{msg}"); time.sleep(2)
