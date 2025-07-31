"""
Módulo de Asistentes del Panel de Control de Operación.

v8.4 (Corrección de Desempaquetado):
- Se corrige el `TypeError` en `_force_stop_wizard` y `_force_close_all_wizard`.
- La llamada a `pm_api.close_all_logical_positions`, que devuelve un único
  booleano, ahora se asigna a una sola variable, evitando el error de
  desempaquetado.
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
    from core.strategy.om._entities import Operacion
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

def _operation_setup_wizard(om_api: Any, side: str, is_modification: bool = False):
    """Asistente único para configurar o modificar una operación estratégica para un lado específico."""
    title = f"Modificar Operación {side.upper()}" if is_modification else f"Configurar Nueva Operación {side.upper()}"
    clear_screen()
    print_tui_header(title)
    
    current_op = om_api.get_operation_by_side(side)
    if not current_op:
        print(f"\nError: No se encontró la operación para el lado {side.upper()}.")
        time.sleep(2)
        return
        
    print("\n(Deja un campo en blanco para mantener el valor actual o presiona Enter para usar el default)")
    params_to_update = {}
    
    try:
        # --- SECCIÓN 1: CONDICIÓN DE ENTRADA (SOLO PARA NUEVAS OPERACIONES) ---
        if not is_modification:
            print("\n--- 1. Condición de Entrada ---")
            cond_menu_items = ["[1] Activación Inmediata (Market)", "[2] Precio SUPERIOR a", "[3] Precio INFERIOR a", None, "[c] Cancelar y Volver"]
            cond_choice = TerminalMenu(cond_menu_items, title="Elige la condición para que la operación se active:").show()
            if cond_choice == 0: 
                new_cond_type, new_cond_value = 'MARKET', 0.0
                print("  -> Condición seleccionada: Activación Inmediata")
            elif cond_choice == 1:
                new_cond_type = 'PRICE_ABOVE'
                new_cond_value = get_input("Activar si precio SUPERA", float, default=current_op.valor_cond_entrada, is_optional=False)
                print(f"  -> Condición seleccionada: Precio > {new_cond_value}")
            elif cond_choice == 2:
                new_cond_type = 'PRICE_BELOW'
                new_cond_value = get_input("Activar si precio BAJA DE", float, default=current_op.valor_cond_entrada, is_optional=False)
                print(f"  -> Condición seleccionada: Precio < {new_cond_value}")
            else: return # Cancelado
            params_to_update['tipo_cond_entrada'] = new_cond_type
            params_to_update['valor_cond_entrada'] = new_cond_value

            tendencia = "LONG_ONLY" if side == 'long' else "SHORT_ONLY"
            params_to_update['tendencia'] = tendencia
            print(f"  -> Tendencia establecida automáticamente a: {tendencia}")
        else:
            # Al modificar, también se puede cambiar la condición de entrada
            print("\n--- 1. Condición de Entrada ---")
            cond_menu_items = ["[1] Activación Inmediata (Market)", "[2] Precio SUPERIOR a", "[3] Precio INFERIOR a", None, "[c] Cancelar y Volver"]
            cond_choice = TerminalMenu(cond_menu_items, title="Elige la condición para que la operación se active:").show()
            if cond_choice == 0: 
                params_to_update['tipo_cond_entrada'] = 'MARKET'
                params_to_update['valor_cond_entrada'] = 0.0
            elif cond_choice == 1:
                params_to_update['tipo_cond_entrada'] = 'PRICE_ABOVE'
                params_to_update['valor_cond_entrada'] = get_input("Activar si precio SUPERA", float, default=current_op.valor_cond_entrada, is_optional=False)
            elif cond_choice == 2:
                params_to_update['tipo_cond_entrada'] = 'PRICE_BELOW'
                params_to_update['valor_cond_entrada'] = get_input("Activar si precio BAJA DE", float, default=current_op.valor_cond_entrada, is_optional=False)

        # --- SECCIÓN 2: PARÁMETROS DE TRADING ---
        use_config_defaults = not is_modification
        default_base_size = getattr(config_module, 'POSITION_BASE_SIZE_USDT', 1.0) if use_config_defaults else current_op.tamaño_posicion_base_usdt
        default_max_pos = getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS', 5) if use_config_defaults else current_op.max_posiciones_logicas
        default_leverage = getattr(config_module, 'POSITION_LEVERAGE', 10.0) if use_config_defaults else current_op.apalancamiento
        
        print(f"\n--- 2. Parámetros de Trading (Obligatorios) ---")
        params_to_update['tamaño_posicion_base_usdt'] = get_input("Tamaño base (USDT)", float, default=default_base_size, min_val=0.01)
        params_to_update['max_posiciones_logicas'] = get_input("Máx. posiciones", int, default=default_max_pos, min_val=1)
        params_to_update['apalancamiento'] = get_input("Apalancamiento", float, default=default_leverage, min_val=1.0)

        print(f"\n--- 3. Riesgo por Posición (Opcional, Enter para desactivar) ---")
        params_to_update['sl_posicion_individual_pct'] = get_input("SL individual (%)", float, default=current_op.sl_posicion_individual_pct, min_val=0.0, is_optional=True) or 0.0
        params_to_update['tsl_activacion_pct'] = get_input("Activación TSL (%)", float, default=current_op.tsl_activacion_pct, min_val=0.0, is_optional=True) or 0.0
        params_to_update['tsl_distancia_pct'] = get_input("Distancia TSL (%)", float, default=current_op.tsl_distancia_pct, min_val=0.0, is_optional=True) or 0.0

        # --- SECCIÓN 3: CONDICIONES DE SALIDA ---
        print(f"\n--- 4. Condiciones de Salida de la Operación (Opcional) ---")
        
        # --- INICIO DE LA MODIFICACIÓN: Configuración del TSL por ROI ---
        # Reemplazamos el TP por ROI estático por el TSL por ROI dinámico.
        tsl_roi_act = get_input(
            "Activación TSL por ROI (%)", 
            float, 
            default=current_op.tsl_roi_activacion_pct, 
            min_val=0.0, 
            is_optional=True
        )
        params_to_update['tsl_roi_activacion_pct'] = tsl_roi_act

        # Solo preguntamos por la distancia si se ha definido una activación.
        if tsl_roi_act is not None and tsl_roi_act > 0:
            tsl_roi_dist = get_input(
                "Distancia TSL por ROI (%)", 
                float, 
                default=current_op.tsl_roi_distancia_pct, 
                min_val=0.1, # La distancia debe ser mayor que cero
                is_optional=False # Es obligatoria si hay activación
            )
            params_to_update['tsl_roi_distancia_pct'] = tsl_roi_dist
        else:
            # Si el usuario desactiva la activación, la distancia también se desactiva.
            params_to_update['tsl_roi_distancia_pct'] = None
        # --- FIN DE LA MODIFICACIÓN ---
            
        sl_roi_val = abs(current_op.sl_roi_pct) if current_op.sl_roi_pct else None
        sl_roi = get_input("SL por ROI (%) (valor positivo)", float, default=sl_roi_val, min_val=0.0, is_optional=True)
        params_to_update['sl_roi_pct'] = -abs(sl_roi) if sl_roi is not None else None
        max_trades = get_input("Máx. trades", int, default=current_op.max_comercios, min_val=1, is_optional=True)
        params_to_update['max_comercios'] = max_trades
        max_duracion = get_input("Duración máx. (min)", int, default=current_op.tiempo_maximo_min, min_val=1, is_optional=True)
        params_to_update['tiempo_maximo_min'] = max_duracion

        print("\n--- Acción al Finalizar (Cuando se cumple un límite de la operación) ---")
        accion_final_menu = TerminalMenu(
            ["[1] Pausar operación (permite reanudar)", "[2] Detener y resetear operación"],
            title="Selecciona la acción a tomar:",
            **MENU_STYLE
        )
        accion_choice = accion_final_menu.show()
        
        if accion_choice == 0:
            params_to_update['accion_al_finalizar'] = 'PAUSAR'
        elif accion_choice == 1:
            params_to_update['accion_al_finalizar'] = 'DETENER'
            
    except UserInputCancelled:
        print("\n\nAsistente de configuración cancelado.")
        time.sleep(1.5)
        return
    
    # --- CONFIRMACIÓN Y GUARDADO ---
    if not params_to_update:
        print("\nNo se realizaron cambios."); time.sleep(1.5)
        return

    confirm_menu_style = MENU_STYLE.copy()
    confirm_menu_style['clear_screen'] = False
    if TerminalMenu(["[1] Confirmar y Guardar", "[2] Cancelar"], title="\n¿Guardar estos cambios?", **confirm_menu_style).show() == 0:
        success, msg = om_api.create_or_update_operation(side, params_to_update)
        print(f"\n{msg}"); time.sleep(2)


def _force_stop_wizard(om_api: Any, pm_api: Any, side: str):
    """
    Asistente para forzar la finalización de la operación para un lado específico.
    """
    title = f"¿Cómo deseas finalizar la operación {side.upper()}?"
    end_menu_items = [
        "[1] Mantener posiciones abiertas y finalizar operación", 
        f"[2] Cerrar todas las posiciones {side.upper()} y finalizar operación", 
        None, 
        "[c] Cancelar"
    ]
    choice = TerminalMenu(end_menu_items, title=title, **MENU_STYLE).show()

    if choice in [0, 1]:
        success, msg = om_api.detener_operacion(side, forzar_cierre_posiciones=(choice == 1))
        print(f"\n{msg}")
        time.sleep(2.5)


def _force_close_all_wizard(pm_api: Any, side: str):
    """
    Asistente simplificado para el cierre de pánico de posiciones para un lado específico.
    """
    summary = pm_api.get_position_summary()
    position_count = summary.get(f'open_{side}_positions_count', 0)

    if position_count == 0:
        print(f"\nNo hay posiciones {side.upper()} para cerrar.")
        time.sleep(2)
        return

    title = f"Esta acción cerrará permanentemente las {position_count} posiciones {side.upper()}.\n¿Estás seguro?"
    confirm_menu_items = [f"[s] Sí, cerrar todas las posiciones {side.upper()}", "[n] No, cancelar"]
    
    confirm_menu = TerminalMenu(confirm_menu_items, title=title, **MENU_STYLE)
    if confirm_menu.show() == 0:
        print(f"\nEnviando órdenes de cierre para posiciones {side.upper()}, por favor espera...")
        closed_successfully = pm_api.close_all_logical_positions(side, reason="PANIC_CLOSE_ALL")
        
        if closed_successfully:
            print(f"\nÉXITO: Todas las posiciones {side.upper()} han sido enviadas a cerrar.")
        else:
            print(f"\nFALLO: No se pudieron enviar las órdenes de cierre para {side.upper()}. Revisa los logs.")
        
        time.sleep(3)