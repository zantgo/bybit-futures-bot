"""
Módulo para la Pantalla de Edición de Configuración de la Sesión.

v6.0 (Refactor de Configuración):
- Completamente reescrito para leer y modificar valores dentro de los
  diccionarios `config.SESSION_CONFIG` y `config.OPERATION_DEFAULTS`.
- Ahora devuelve un diccionario con las claves planas que cambiaron para que
  SessionManager pueda reaccionar a ellas.

v5.0 (Refactor Ticker Symbol):
- Se elimina la opción para editar el `TICKER_SYMBOL` de esta pantalla.
  Ahora se gestiona en la Configuración General.
"""
from typing import Any, Dict
import time
import copy

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    get_input,
    MENU_STYLE,
    show_help_popup,
    UserInputCancelled
)

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- LÓGICA PRINCIPAL ---

def show_session_config_editor_screen(config_module: Any) -> Dict[str, Any]:
    """
    Muestra la pantalla de edición de config de sesión y devuelve un dict con los cambios.
    """
    logger = _deps.get("memory_logger_module")
    if not TerminalMenu:
        if logger: logger.log("Error: 'simple-term-menu' no está instalado.", level="ERROR")
        return {}

    # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
    # --- (COMENTADO) ---
    # # Crear una copia temporal de la configuración para editarla sin afectar la real
    # # hasta que se guarde explícitamente.
    # class TempConfig: pass
    # temp_config = TempConfig()
    # for attr in dir(config_module):
    #     if attr.isupper() and not attr.startswith('_'):
    #         setattr(temp_config, attr, copy.deepcopy(getattr(config_module, attr)))
    # --- (CORREGIDO) ---
    # Usar deepcopy para crear una copia temporal de los diccionarios relevantes
    temp_session_config = copy.deepcopy(config_module.SESSION_CONFIG)
    temp_op_defaults = copy.deepcopy(config_module.OPERATION_DEFAULTS)

    changes_made, changed_keys = _show_session_config_menu(temp_session_config, temp_op_defaults)

    if changes_made:
        # Si hay cambios, se aplican al config real y se retorna el dict de claves cambiadas
        _apply_changes_to_real_config(
            temp_session_config, temp_op_defaults, 
            config_module.SESSION_CONFIG, config_module.OPERATION_DEFAULTS, 
            logger
        )
        return changed_keys
    
    return {}
    # --- FIN DE LA MODIFICACIÓN ---

def _apply_changes_to_real_config(
    temp_session_cfg: Dict, temp_op_defaults: Dict,
    real_session_cfg: Dict, real_op_defaults: Dict,
    logger: Any
):
    """Aplica los cambios de los diccionarios temporales a los reales."""
    if not logger: return
    logger.log("Aplicando cambios de configuración de sesión...", "WARN")
    
    # Compara y aplica para SESSION_CONFIG
    for category, params in temp_session_cfg.items():
        if isinstance(params, dict):
            for key, new_value in params.items():
                if new_value != real_session_cfg[category][key]:
                    logger.log(f"  -> {category}.{key}: '{real_session_cfg[category][key]}' -> '{new_value}'", "WARN")
                    real_session_cfg[category][key] = new_value
        else: # Para claves de primer nivel como TICKER_INTERVAL_SECONDS
            if params != real_session_cfg[category]:
                logger.log(f"  -> {category}: '{real_session_cfg[category]}' -> '{params}'", "WARN")
                real_session_cfg[category] = params

    # Compara y aplica para OPERATION_DEFAULTS
    for category, params in temp_op_defaults.items():
        if isinstance(params, dict):
            for key, new_value in params.items():
                if new_value != real_op_defaults[category][key]:
                    logger.log(f"  -> {category}.{key}: '{real_op_defaults[category][key]}' -> '{new_value}'", "WARN")
                    real_op_defaults[category][key] = new_value

# --- MENÚ DE EDICIÓN ---

def _show_session_config_menu(temp_session_cfg: Dict, temp_op_cfg: Dict) -> tuple[bool, Dict]:
    """Muestra el menú principal para editar la configuración de una sesión."""
    changed_keys = {}
    
    while True:
        menu_items = [
            "[1] Parámetros del Ticker",
            "[2] Parámetros de Estrategia (TA y Señal)",
            "[3] Parámetros de Capital (Defaults de Operación)",
            "[4] Parámetros de Límites (Disyuntores de Sesión)",
            None,
            "[h] Ayuda",
            None,
            "[s] Guardar y Volver",
            "[c] Cancelar (Descartar Cambios)"
        ]
        action_map = {0: 'ticker', 1: 'strategy', 2: 'capital', 3: 'limits', 5: 'help', 7: 'save', 8: 'cancel'}

        menu = TerminalMenu(menu_items, title="Editor de Configuración de Sesión", **MENU_STYLE)
        
        action = action_map.get(menu.show())

        if action == 'ticker':
            changes = _show_ticker_config_menu(temp_session_cfg)
            changed_keys.update(changes)
        elif action == 'strategy':
            changes = _show_strategy_config_menu(temp_session_cfg)
            changed_keys.update(changes)
        elif action == 'capital':
            changes = _show_pm_capital_config_menu(temp_op_cfg)
            changed_keys.update(changes)
        elif action == 'limits':
            changes = _show_session_limits_menu(temp_session_cfg)
            changed_keys.update(changes)
        elif action == 'help':
            show_help_popup("config_editor")
        elif action == 'save':
            if changed_keys:
                print("\nCambios guardados. Se aplicarán dinámicamente a la sesión."); time.sleep(2)
                return True, changed_keys
            else:
                print("\nNo se realizaron cambios."); time.sleep(1.5)
                return False, {}
        elif action == 'cancel' or action is None:
            print("\nCambios descartados."); time.sleep(1.5); return False, {}

# --- SUBMENÚS DE EDICIÓN ---
def _show_ticker_config_menu(cfg: Dict) -> Dict:
    """Muestra el menú para editar los parámetros del Ticker."""
    changes = {}
    try:
        while True:
            menu_items = [
                f"[1] Intervalo (segundos) (Actual: {cfg['TICKER_INTERVAL_SECONDS']})",
                None, "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Configuración del Ticker", **MENU_STYLE)
            choice = submenu.show()

            if choice == 0:
                original_value = cfg['TICKER_INTERVAL_SECONDS']
                new_val = get_input("\nNuevo Intervalo (segundos)", float, original_value, min_val=0.1)
                if new_val != original_value:
                    cfg['TICKER_INTERVAL_SECONDS'] = new_val
                    changes['TICKER_INTERVAL_SECONDS'] = new_val
            else: 
                break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)
    return changes

def _show_strategy_config_menu(cfg: Dict) -> Dict:
    """Muestra el menú para editar los parámetros de la estrategia."""
    changes = {}
    try:
        while True:
            strategy_cfg = cfg['STRATEGY']
            ta_cfg = cfg['TA']
            menu_items = [
                f"[1] Margen de Compra (%) (Actual: {strategy_cfg['MARGIN_BUY']})",
                f"[2] Margen de Venta (%) (Actual: {strategy_cfg['MARGIN_SELL']})",
                f"[3] Umbral de Decremento Ponderado (Actual: {strategy_cfg['DECREMENT_THRESHOLD']})",
                f"[4] Umbral de Incremento Ponderado (Actual: {strategy_cfg['INCREMENT_THRESHOLD']})",
                None,
                f"[5] Período EMA (Actual: {ta_cfg['EMA_WINDOW']})",
                f"[6] Período WMA Incremento (Actual: {ta_cfg['WEIGHTED_INC_WINDOW']})",
                f"[7] Período WMA Decremento (Actual: {ta_cfg['WEIGHTED_DEC_WINDOW']})",
                None, 
                "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Parámetros de la Estrategia (TA y Señal)", **MENU_STYLE)
            choice = submenu.show()
            
            if choice == 0:
                original = strategy_cfg['MARGIN_BUY']
                strategy_cfg['MARGIN_BUY'] = get_input("\nNuevo Margen de Compra (ej. -0.1)", float, original)
                if strategy_cfg['MARGIN_BUY'] != original: changes['STRATEGY_MARGIN_BUY'] = strategy_cfg['MARGIN_BUY']
            elif choice == 1:
                original = strategy_cfg['MARGIN_SELL']
                strategy_cfg['MARGIN_SELL'] = get_input("\nNuevo Margen de Venta (ej. 0.1)", float, original)
                if strategy_cfg['MARGIN_SELL'] != original: changes['STRATEGY_MARGIN_SELL'] = strategy_cfg['MARGIN_SELL']
            elif choice == 2:
                original = strategy_cfg['DECREMENT_THRESHOLD']
                strategy_cfg['DECREMENT_THRESHOLD'] = get_input("\nNuevo Umbral de Decremento (0-1)", float, original, min_val=0.0, max_val=1.0)
                if strategy_cfg['DECREMENT_THRESHOLD'] != original: changes['STRATEGY_DECREMENT_THRESHOLD'] = strategy_cfg['DECREMENT_THRESHOLD']
            elif choice == 3:
                original = strategy_cfg['INCREMENT_THRESHOLD']
                strategy_cfg['INCREMENT_THRESHOLD'] = get_input("\nNuevo Umbral de Incremento (0-1)", float, original, min_val=0.0, max_val=1.0)
                if strategy_cfg['INCREMENT_THRESHOLD'] != original: changes['STRATEGY_INCREMENT_THRESHOLD'] = strategy_cfg['INCREMENT_THRESHOLD']
            elif choice == 4:
                original = ta_cfg['EMA_WINDOW']
                ta_cfg['EMA_WINDOW'] = get_input("\nNuevo Período para la EMA", int, original, min_val=1)
                if ta_cfg['EMA_WINDOW'] != original: changes['TA_EMA_WINDOW'] = ta_cfg['EMA_WINDOW']
            elif choice == 5:
                original = ta_cfg['WEIGHTED_INC_WINDOW']
                ta_cfg['WEIGHTED_INC_WINDOW'] = get_input("\nNuevo Período para WMA de Incremento", int, original, min_val=1)
                if ta_cfg['WEIGHTED_INC_WINDOW'] != original: changes['TA_WEIGHTED_INC_WINDOW'] = ta_cfg['WEIGHTED_INC_WINDOW']
            elif choice == 6:
                original = ta_cfg['WEIGHTED_DEC_WINDOW']
                ta_cfg['WEIGHTED_DEC_WINDOW'] = get_input("\nNuevo Período para WMA de Decremento", int, original, min_val=1)
                if ta_cfg['WEIGHTED_DEC_WINDOW'] != original: changes['TA_WEIGHTED_DEC_WINDOW'] = ta_cfg['WEIGHTED_DEC_WINDOW']
            else: 
                break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)
    return changes
        
def _show_pm_capital_config_menu(cfg: Dict) -> Dict:
    """Muestra el menú para editar los parámetros de capital por defecto."""
    changes = {}
    try:
        while True:
            capital = cfg['CAPITAL']
            profit = cfg['PROFIT']
            menu_items = [
                f"[1] Tamaño Base por Posición (USDT) (Actual: {capital['BASE_SIZE_USDT']:.2f})",
                f"[2] Máximo de Posiciones por Lado (Actual: {capital['MAX_POSITIONS']})",
                f"[3] Apalancamiento (Actual: {capital['LEVERAGE']:.1f}x)",
                f"[4] % de Reinversión de Ganancias (Actual: {profit['REINVEST_PROFIT_PCT']:.1f}%)",
                None, "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Gestión de Posiciones (Defaults para Operaciones)", **MENU_STYLE)
            choice = submenu.show()

            if choice == 0:
                original = capital['BASE_SIZE_USDT']
                capital['BASE_SIZE_USDT'] = get_input("\nNuevo Tamaño Base (USDT)", float, original, min_val=0.1)
                if capital['BASE_SIZE_USDT'] != original: changes['POSITION_BASE_SIZE_USDT'] = capital['BASE_SIZE_USDT']
            elif choice == 1:
                original = capital['MAX_POSITIONS']
                capital['MAX_POSITIONS'] = get_input("\nNuevo Máximo de Posiciones por Lado", int, original, min_val=1)
                if capital['MAX_POSITIONS'] != original: changes['POSITION_MAX_LOGICAL_POSITIONS'] = capital['MAX_POSITIONS']
            elif choice == 2:
                original = capital['LEVERAGE']
                capital['LEVERAGE'] = get_input("\nNuevo Apalancamiento (ej. 10.0)", float, original, min_val=1.0, max_val=100.0)
                if capital['LEVERAGE'] != original: changes['POSITION_LEVERAGE'] = capital['LEVERAGE']
            elif choice == 3:
                original = profit['REINVEST_PROFIT_PCT']
                profit['REINVEST_PROFIT_PCT'] = get_input("\nNuevo % de Reinversión (0-100)", float, original, min_val=0.0, max_val=100.0)
                if profit['REINVEST_PROFIT_PCT'] != original: changes['POSITION_REINVEST_PROFIT_PCT'] = profit['REINVEST_PROFIT_PCT']
            else: break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)
    return changes

def _show_session_limits_menu(cfg: Dict) -> Dict:
    """Muestra el menú para editar los disyuntores de la sesión."""
    changes = {}
    try:
        while True:
            limits = cfg['SESSION_LIMITS']
            duration = limits['MAX_DURATION']['MINUTES']
            duration_str = f"{duration} min (Acción: {limits['MAX_DURATION']['ACTION']})" if duration > 0 else "Desactivado"
            sl_roi_status = "Activado" if limits['ROI_SL']['ENABLED'] else "Desactivado"
            tp_roi_status = "Activado" if limits['ROI_TP']['ENABLED'] else "Desactivado"
            
            menu_items = [
                f"[1] Límite de Duración (min) (Actual: {duration_str})",
                f"[2] Stop Loss de Sesión por ROI (Estado: {sl_roi_status})",
                f"[3]    └─ Umbral de SL (%): (Actual: -{limits['ROI_SL']['PERCENTAGE']:.2f})",
                f"[4] Take Profit de Sesión por ROI (Estado: {tp_roi_status})",
                f"[5]    └─ Umbral de TP (%): (Actual: +{limits['ROI_TP']['PERCENTAGE']:.2f})",
                None, "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Límites de Sesión (Disyuntores)", **MENU_STYLE)
            choice = submenu.show()

            if choice == 0:
                original_duration = duration
                new_duration = get_input("\nDuración máx (min, 0=desactivar)", int, original_duration, min_val=0)
                if new_duration != original_duration: changes['SESSION_MAX_DURATION_MINUTES'] = new_duration
                limits['MAX_DURATION']['MINUTES'] = new_duration
                
                if new_duration > 0:
                    original_action = limits['MAX_DURATION']['ACTION']
                    action_idx = TerminalMenu(["[1] NEUTRAL", "[2] STOP"], title="Acción al alcanzar límite:").show()
                    if action_idx is not None:
                        new_action = "STOP" if action_idx == 1 else "NEUTRAL"
                        if new_action != original_action: changes['SESSION_TIME_LIMIT_ACTION'] = new_action
                        limits['MAX_DURATION']['ACTION'] = new_action
            elif choice == 1:
                limits['ROI_SL']['ENABLED'] = not limits['ROI_SL']['ENABLED']
                changes['SESSION_ROI_SL_ENABLED'] = limits['ROI_SL']['ENABLED']
            elif choice == 2:
                original = limits['ROI_SL']['PERCENTAGE']
                limits['ROI_SL']['PERCENTAGE'] = get_input("\nNuevo % de SL (ej. 10 para -10%)", float, original, min_val=0.1)
                if limits['ROI_SL']['PERCENTAGE'] != original: changes['SESSION_STOP_LOSS_ROI_PCT'] = limits['ROI_SL']['PERCENTAGE']
            elif choice == 3:
                limits['ROI_TP']['ENABLED'] = not limits['ROI_TP']['ENABLED']
                changes['SESSION_ROI_TP_ENABLED'] = limits['ROI_TP']['ENABLED']
            elif choice == 4:
                original = limits['ROI_TP']['PERCENTAGE']
                limits['ROI_TP']['PERCENTAGE'] = get_input("\nNuevo % de TP (ej. 5 para +5%)", float, original, min_val=0.1)
                if limits['ROI_TP']['PERCENTAGE'] != original: changes['SESSION_TAKE_PROFIT_ROI_PCT'] = limits['ROI_TP']['PERCENTAGE']
            else: break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)
    return changes