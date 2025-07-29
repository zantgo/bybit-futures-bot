"""
Módulo de Asistentes del Panel de Control de Operación.

Contiene todas las funciones que guían al usuario a través de una serie de
pasos o menús para realizar una acción compleja, como configurar una nueva
operación o forzar el cierre de posiciones.
"""
import time
from typing import Any, Dict, Optional

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# Importar helpers y entidades necesarios
from ..._helpers import (
    clear_screen,
    print_tui_header,
    get_input,
    MENU_STYLE,
    UserInputCancelled
)

try:
    from core.strategy.pm._entities import Operacion
    import config as config_module
except ImportError:
    class Operacion: pass
    config_module = None

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el __init__.py del módulo."""
    global _deps
    _deps = dependencies

# --- Funciones de Asistente ---

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
    """Asistente para forzar la finalización de la operación actual."""
    title = "¿Cómo deseas finalizar la operación actual?"
    end_menu_items = ["[1] Mantener posiciones y finalizar", "[2] Cerrar todas las posiciones y finalizar", None, "[c] Cancelar"]
    choice = TerminalMenu(end_menu_items, title=title).show()
    if choice in [0, 1]:
        success, msg = pm_api.force_stop_operation(close_positions=(choice == 1))
        print(f"\n{msg}"); time.sleep(2)

def _force_close_all_wizard(pm_api: Any):
    """Asistente para el cierre de pánico de todas las posiciones."""
    title = "Esta acción cerrará posiciones permanentemente.\n¿Qué posiciones deseas cerrar?"
    close_menu_items = ["[1] Cerrar solo LONGS", "[2] Cerrar solo SHORTS", "[3] Cerrar AMBAS", None, "[c] Cancelar"]
    choice = TerminalMenu(close_menu_items, title=title).show()
    if choice == 0: 
        pm_api.close_all_logical_positions('long', reason="PANIC_CLOSE_ALL")
        print("\nÓrdenes de cierre para LONGS enviadas."); time.sleep(2)
    elif choice == 1: 
        pm_api.close_all_logical_positions('short', reason="PANIC_CLOSE_ALL")
        print("\nÓrdenes de cierre para SHORTS enviadas."); time.sleep(2)
    elif choice == 2:
        pm_api.close_all_logical_positions('long', reason="PANIC_CLOSE_ALL")
        pm_api.close_all_logical_positions('short', reason="PANIC_CLOSE_ALL")
        print("\nÓrdenes de cierre para TODAS las posiciones enviadas."); time.sleep(2)