"""
Módulo para la Pantalla de Edición de Configuración.

v3.6 (Manejo de Cancelación por Excepción):
- Se actualiza el manejo de la entrada del usuario para usar el nuevo
  sistema de `UserInputCancelled` en lugar de la clase `CancelInput`.
- Todos los submenús de edición ahora capturan la excepción para permitir
  una cancelación limpia del proceso de entrada.
"""
# (COMENTARIO) Docstring de la versión anterior (v3.5) para referencia:
# """
# Módulo para la Pantalla de Edición de Configuración.
# 
# v3.5 (Refactor de Contexto):
# - La función principal ahora acepta un 'context' ('general' o 'session').
# - Muestra dinámicamente solo las opciones de configuración relevantes
#   para el contexto proporcionado.
# """
from typing import Any, Dict
import time
import copy

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- INICIO DE LA CORRECCIÓN: Importación actualizada ---
from .._helpers import (
    get_input,
    MENU_STYLE,
    press_enter_to_continue,
    show_help_popup,
    UserInputCancelled # Se importa la nueva excepción
)
# (COMENTARIO) Importación anterior para referencia histórica.
# from .._helpers import CancelInput
# --- FIN DE LA CORRECCIÓN ---

_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

# --- LÓGICA DE LA PANTALLA PRINCIPAL ---

def show_config_editor_screen(config_module: Any, context: str = 'session') -> bool:
    """
    Muestra la pantalla de edición y devuelve True si se guardaron cambios.
    Acepta un 'context' para mostrar diferentes menús.
    """
    logger = _deps.get("memory_logger_module")
    if not TerminalMenu:
        if logger:
            logger.log("Error: 'simple-term-menu' no está instalado. No se puede mostrar el editor.", level="ERROR")
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return False

    class TempConfig:
        pass
    
    temp_config = TempConfig()
    for attr in dir(config_module):
        if attr.isupper() and not attr.startswith('_'):
            value = getattr(config_module, attr)
            if not callable(value):
                setattr(temp_config, attr, copy.deepcopy(value))

    while True:
        if context == 'general':
            title = "Editor de Configuración General del Bot"
            menu_items = [
                "[1] Configuración del Ticker",
                "[2] Parámetros de la Estrategia (TA y Señal)",
                None,
                "[h] Ayuda sobre el Editor de Configuración",
                None,
                "[b] Guardar y Volver",
                "[c] Cancelar (Descartar Cambios)"
            ]
            action_map = {
                0: 'ticker', 1: 'strategy',
                3: 'help', 5: 'save_back', 6: 'cancel_back'
            }
        elif context == 'session':
            title = "Editor de Configuración de la Sesión"
            menu_items = [
                "[1] Gestión de Posiciones (Capital)",
                "[2] Límites de la Sesión (Disyuntores)",
                None,
                "[h] Ayuda sobre el Editor de Configuración",
                None,
                "[b] Guardar y Volver",
                "[c] Cancelar (Descartar Cambios)"
            ]
            action_map = {
                0: 'capital', 1: 'limits',
                3: 'help', 5: 'save_back', 6: 'cancel_back'
            }
        else:
            print(f"Error: Contexto de editor de configuración desconocido: '{context}'"); time.sleep(2); return False

        main_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = main_menu.show()
        
        action = action_map.get(choice_index)

        if action == 'ticker':
            _show_ticker_config_menu(temp_config)
        elif action == 'strategy':
            _show_strategy_config_menu(temp_config)
        elif action == 'capital':
            _show_pm_capital_config_menu(temp_config)
        elif action == 'limits':
            _show_session_limits_menu(temp_config)
        elif action == 'help':
            show_help_popup("config_editor")
        
        elif action == 'save_back':
            pm_api = _deps.get("position_manager_api_module")
            _apply_and_log_changes(temp_config, config_module, pm_api, logger)
            if logger:
                logger.log("Cambios guardados y aplicados en la sesión.", level="INFO")
            print("\nCambios guardados y aplicados en la sesión.")
            time.sleep(1.5)
            return True
            
        elif action == 'cancel_back' or choice_index is None:
            if logger:
                logger.log("Cambios en la configuración descartados.", level="INFO")
            print("\nCambios descartados.")
            time.sleep(1.5)
            return False

# --- Lógica de Aplicación de Cambios (sin cambios) ---

def _apply_and_log_changes(temp_cfg: Any, real_cfg: Any, pm_api: Any, logger: Any):
    """Compara la config temporal con la real, aplica los cambios y los loguea."""
    if not logger: return

    logger.log("Aplicando cambios de configuración desde la TUI...", "WARN")
    changes_found = False

    for attr in dir(temp_cfg):
        if not attr.startswith('__') and not callable(getattr(temp_cfg, attr)):
            new_value = getattr(temp_cfg, attr)
            old_value = getattr(real_cfg, attr, None)
            
            if new_value != old_value:
                changes_found = True
                logger.log(f"  -> {attr}: '{old_value}' -> '{new_value}'", "WARN")
                setattr(real_cfg, attr, new_value)
                
                if pm_api:
                    if attr == 'SESSION_STOP_LOSS_ROI_PCT':
                        if getattr(real_cfg, 'SESSION_ROI_SL_ENABLED', False):
                            pm_api.set_global_stop_loss_pct(new_value)
                    elif attr == 'SESSION_TAKE_PROFIT_ROI_PCT':
                         if getattr(real_cfg, 'SESSION_ROI_TP_ENABLED', False):
                            pm_api.set_global_take_profit_pct(new_value)

                    elif attr == 'SESSION_ROI_SL_ENABLED':
                        pm_api.set_global_stop_loss_pct(getattr(temp_cfg, 'SESSION_STOP_LOSS_ROI_PCT') if new_value else 0)
                    elif attr == 'SESSION_ROI_TP_ENABLED':
                        pm_api.set_global_take_profit_pct(getattr(temp_cfg, 'SESSION_TAKE_PROFIT_ROI_PCT') if new_value else 0)

    if not changes_found:
        logger.log("No se detectaron cambios en la configuración.", "INFO")

# --- SUBMENÚS DE CONFIGURACIÓN ---
def _show_ticker_config_menu(cfg: Any):
    # --- INICIO DE LA MODIFICACIÓN: Envolver en try-except ---
    try:
        while True:
            menu_items = [
                f"[1] Símbolo del Ticker (Actual: {getattr(cfg, 'TICKER_SYMBOL', 'N/A')})",
                f"[2] Intervalo de Estrategia (segundos) (Actual: {getattr(cfg, 'TICKER_INTERVAL_SECONDS', 1)})",
                None,
                "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Configuración del Ticker", **MENU_STYLE)
            choice = submenu.show()
            if choice == 0:
                new_val = get_input("\nNuevo Símbolo (ej. ETHUSDT)", str, getattr(cfg, 'TICKER_SYMBOL', 'N/A'))
                setattr(cfg, 'TICKER_SYMBOL', new_val.upper())
            elif choice == 1:
                new_val = get_input("\nNuevo Intervalo (segundos, ej. 1, 5)", float, getattr(cfg, 'TICKER_INTERVAL_SECONDS', 1), min_val=0.1)
                setattr(cfg, 'TICKER_INTERVAL_SECONDS', new_val)
            else:
                break
    except UserInputCancelled:
        print("\n\nEdición cancelada por el usuario.")
        time.sleep(1)
    # --- FIN DE LA MODIFICACIÓN ---

def _show_strategy_config_menu(cfg: Any):
    # --- INICIO DE LA MODIFICACIÓN: Envolver en try-except ---
    try:
        while True:
            menu_items = [
                f"[1] Margen de Compra (%) (Actual: {getattr(cfg, 'STRATEGY_MARGIN_BUY', 0.0)})",
                f"[2] Margen de Venta (%) (Actual: {getattr(cfg, 'STRATEGY_MARGIN_SELL', 0.0)})",
                f"[3] Umbral de Decremento Ponderado (Actual: {getattr(cfg, 'STRATEGY_DECREMENT_THRESHOLD', 0.0)})",
                f"[4] Umbral de Incremento Ponderado (Actual: {getattr(cfg, 'STRATEGY_INCREMENT_THRESHOLD', 0.0)})",
                None,
                f"[5] Período EMA (Actual: {getattr(cfg, 'TA_EMA_WINDOW', 0)})",
                None,
                "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Parámetros de la Estrategia (TA y Señal)", **MENU_STYLE)
            choice = submenu.show()
            if choice == 0:
                new_val = get_input("\nNuevo Margen de Compra (ej. -0.1)", float, getattr(cfg, 'STRATEGY_MARGIN_BUY', 0.0))
                setattr(cfg, 'STRATEGY_MARGIN_BUY', new_val)
            elif choice == 1:
                new_val = get_input("\nNuevo Margen de Venta (ej. 0.1)", float, getattr(cfg, 'STRATEGY_MARGIN_SELL', 0.0))
                setattr(cfg, 'STRATEGY_MARGIN_SELL', new_val)
            elif choice == 2:
                new_val = get_input("\nNuevo Umbral de Decremento (0-1)", float, getattr(cfg, 'STRATEGY_DECREMENT_THRESHOLD', 0.0), min_val=0.0, max_val=1.0)
                setattr(cfg, 'STRATEGY_DECREMENT_THRESHOLD', new_val)
            elif choice == 3:
                new_val = get_input("\nNuevo Umbral de Incremento (0-1)", float, getattr(cfg, 'STRATEGY_INCREMENT_THRESHOLD', 0.0), min_val=0.0, max_val=1.0)
                setattr(cfg, 'STRATEGY_INCREMENT_THRESHOLD', new_val)
            elif choice == 5:
                new_val = get_input("\nNuevo Período para la EMA", int, getattr(cfg, 'TA_EMA_WINDOW', 0), min_val=1)
                setattr(cfg, 'TA_EMA_WINDOW', new_val)
            else:
                break
    except UserInputCancelled:
        print("\n\nEdición cancelada por el usuario.")
        time.sleep(1)
    # --- FIN DE LA MODIFICACIÓN ---

def _show_pm_capital_config_menu(cfg: Any):
    # --- INICIO DE LA MODIFICACIÓN: Envolver en try-except ---
    try:
        while True:
            menu_items = [
                f"[1] Tamaño Base por Posición (USDT) (Actual: {getattr(cfg, 'POSITION_BASE_SIZE_USDT', 0.0):.2f})",
                f"[2] Máximo de Posiciones por Lado (Actual: {getattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', 0)})",
                f"[3] Apalancamiento (Actual: {getattr(cfg, 'POSITION_LEVERAGE', 0.0):.1f}x)",
                None,
                f"[4] Dif. Mín. Precio LONG (%) (Actual: {getattr(cfg, 'POSITION_MIN_PRICE_DIFF_LONG_PCT', 0.0):.2f}%)",
                f"[5] Dif. Mín. Precio SHORT (%) (Actual: {getattr(cfg, 'POSITION_MIN_PRICE_DIFF_SHORT_PCT', 0.0):.2f}%)",
                f"[6] % de Reinversión de Ganancias (Actual: {getattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', 0.0):.1f}%)",
                None,
                "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Gestión de Posiciones (Capital)", **MENU_STYLE)
            choice = submenu.show()
            if choice == 0:
                new_val = get_input("\nNuevo Tamaño Base (USDT)", float, getattr(cfg, 'POSITION_BASE_SIZE_USDT', 0.0), min_val=0.1)
                setattr(cfg, 'POSITION_BASE_SIZE_USDT', new_val)
            elif choice == 1:
                new_val = get_input("\nNuevo Máximo de Posiciones por Lado", int, getattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', 0), min_val=1)
                setattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', new_val)
            elif choice == 2:
                new_val = get_input("\nNuevo Apalancamiento (ej. 10.0)", float, getattr(cfg, 'POSITION_LEVERAGE', 0.0), min_val=1.0, max_val=100.0)
                setattr(cfg, 'POSITION_LEVERAGE', new_val)
            elif choice == 4:
                new_val = get_input("\nNueva Dif. Mín. LONG (% , ej: -0.25)", float, getattr(cfg, 'POSITION_MIN_PRICE_DIFF_LONG_PCT', 0.0))
                setattr(cfg, 'POSITION_MIN_PRICE_DIFF_LONG_PCT', new_val)
            elif choice == 5:
                new_val = get_input("\nNueva Dif. Mín. SHORT (% , ej: 0.25)", float, getattr(cfg, 'POSITION_MIN_PRICE_DIFF_SHORT_PCT', 0.0))
                setattr(cfg, 'POSITION_MIN_PRICE_DIFF_SHORT_PCT', new_val)
            elif choice == 6:
                new_val = get_input("\nNuevo % de Reinversión (0-100)", float, getattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', 0.0), min_val=0.0, max_val=100.0)
                setattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', new_val)
            else:
                break
    except UserInputCancelled:
        print("\n\nEdición cancelada por el usuario.")
        time.sleep(1)
    # --- FIN DE LA MODIFICACIÓN ---

def _show_session_limits_menu(cfg: Any):
    # --- INICIO DE LA MODIFICACIÓN: Envolver en try-except ---
    try:
        while True:
            action = getattr(cfg, 'SESSION_TIME_LIMIT_ACTION', 'NEUTRAL')
            duration = getattr(cfg, 'SESSION_MAX_DURATION_MINUTES', 0)
            duration_str = f"{duration} min (Acción: {action})" if duration > 0 else "Desactivado"
            sl_roi_enabled = getattr(cfg, 'SESSION_ROI_SL_ENABLED', False)
            tp_roi_enabled = getattr(cfg, 'SESSION_ROI_TP_ENABLED', False)
            sl_roi_status = "Activado" if sl_roi_enabled else "Desactivado"
            tp_roi_status = "Activado" if tp_roi_enabled else "Desactivado"
            sl_roi_val = getattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
            tp_roi_val = getattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)
            
            menu_items = [
                f"[1] Límite de Duración (minutos) (Actual: {duration_str})",
                f"[2] Límite de Trades Totales (Actual: {'Ilimitados' if getattr(cfg, 'SESSION_MAX_TRADES', 0) == 0 else getattr(cfg, 'SESSION_MAX_TRADES', 0)})",
                None,
                f"[3] Stop Loss de Sesión por ROI (Estado: {sl_roi_status})",
                f"[4]    └─ Umbral de SL (%): (Actual: -{sl_roi_val:.2f})",
                None,
                f"[5] Take Profit de Sesión por ROI (Estado: {tp_roi_status})",
                f"[6]    └─ Umbral de TP (%): (Actual: +{tp_roi_val:.2f})",
                None,
                "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Límites de Sesión (Disyuntores)", **MENU_STYLE)
            choice = submenu.show()
            if choice == 0:
                new_duration = get_input("\nNueva duración máxima (minutos, 0 para desactivar)", int, duration, min_val=0)
                setattr(cfg, 'SESSION_MAX_DURATION_MINUTES', new_duration)
                if new_duration > 0:
                    action_idx = TerminalMenu(["[1] Pasar a modo NEUTRAL", "[2] Parada de Emergencia (STOP)"], title="Acción al alcanzar el límite:").show()
                    if action_idx is not None:
                        new_action = "STOP" if action_idx == 1 else "NEUTRAL"
                        setattr(cfg, 'SESSION_TIME_LIMIT_ACTION', new_action)
            elif choice == 1:
                new_val = get_input("\nNuevo límite de trades (0 para ilimitados)", int, getattr(cfg, 'SESSION_MAX_TRADES', 0), min_val=0)
                setattr(cfg, 'SESSION_MAX_TRADES', new_val)
            elif choice == 3:
                setattr(cfg, 'SESSION_ROI_SL_ENABLED', not getattr(cfg, 'SESSION_ROI_SL_ENABLED', False))
            elif choice == 4:
                new_val = get_input("\nNuevo % de SL de Sesión (ej. 10 para -10%)", float, sl_roi_val, min_val=0.1)
                setattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', new_val)
            
            elif choice == 6:
                setattr(cfg, 'SESSION_ROI_TP_ENABLED', not getattr(cfg, 'SESSION_ROI_TP_ENABLED', False))
            elif choice == 7:
                new_val = get_input("\nNuevo % de TP de Sesión (ej. 5 para +5%)", float, tp_roi_val, min_val=0.1)
                setattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', new_val)
                
            else:
                break
    except UserInputCancelled:
        print("\n\nEdición cancelada por el usuario.")
        time.sleep(1)
    # --- FIN DE LA MODIFICACIÓN ---