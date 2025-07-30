"""
Módulo para la Pantalla de Edición de Configuración.

v4.0 (Arquitectura de Controladores):
- Refactorizado para tener menús distintos y claros para los contextos
  'general' (BotController) y 'session' (SessionManager).
- La lógica de aplicación de cambios se simplifica, ya que los controladores
  serán responsables de propagar las actualizaciones a sus componentes hijos.
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
    press_enter_to_continue,
    show_help_popup,
    UserInputCancelled
)

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies

# --- LÓGICA DE LA PANTALLA PRINCIPAL ---

def show_config_editor_screen(config_module: Any, context: str) -> bool:
    """
    Muestra la pantalla de edición para un contexto específico ('general' o 'session')
    y devuelve True si se guardaron cambios.
    """
    logger = _deps.get("memory_logger_module")
    if not TerminalMenu:
        if logger:
            logger.log("Error: 'simple-term-menu' no está instalado.", level="ERROR")
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return False

    # Crear una copia temporal de la configuración para editar de forma segura
    class TempConfig:
        pass
    temp_config = TempConfig()
    for attr in dir(config_module):
        if attr.isupper() and not attr.startswith('_'):
            value = getattr(config_module, attr)
            if not callable(value):
                setattr(temp_config, attr, copy.deepcopy(value))

    # Lanzar el menú correspondiente al contexto
    if context == 'general':
        changes_made = _show_general_config_menu(temp_config)
    elif context == 'session':
        changes_made = _show_session_config_menu(temp_config)
    else:
        print(f"Error: Contexto de editor desconocido: '{context}'"); time.sleep(2)
        return False

    # Si se guardaron cambios, aplicarlos a la configuración real
    if changes_made:
        _apply_changes_to_real_config(temp_config, config_module, logger)
        return True
    
    return False

# --- Lógica de Aplicación de Cambios ---

def _apply_changes_to_real_config(temp_cfg: Any, real_cfg: Any, logger: Any):
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

    if not changes_found:
        logger.log("No se detectaron cambios en la configuración.", "INFO")

# --- MENÚS PRINCIPALES POR CONTEXTO ---

def _show_general_config_menu(temp_cfg: Any) -> bool:
    """Muestra el menú principal para editar la configuración general del bot."""
    while True:
        menu_items = [
            f"[1] Exchange (Actual: {getattr(temp_cfg, 'EXCHANGE_NAME', 'N/A')})",
            f"[2] Modo Testnet (Actual: {'Activado' if getattr(temp_cfg, 'UNIVERSAL_TESTNET_MODE', False) else 'Desactivado'})",
            None,
            "[h] Ayuda",
            None,
            "[s] Guardar y Volver",
            "[c] Cancelar (Descartar Cambios)"
        ]
        action_map = {0: 'exchange', 1: 'testnet', 3: 'help', 5: 'save', 6: 'cancel'}
        
        menu = TerminalMenu(menu_items, title="Editor de Configuración General", **MENU_STYLE)
        choice = menu.show()
        action = action_map.get(choice)

        try:
            if action == 'exchange':
                # En el futuro, podría ser un menú si se soportan más exchanges.
                new_val = get_input("\nNuevo Exchange (ej. bybit)", str, getattr(temp_cfg, 'EXCHANGE_NAME', 'bybit'))
                setattr(temp_cfg, 'EXCHANGE_NAME', new_val.lower())
            elif action == 'testnet':
                current_val = getattr(temp_cfg, 'UNIVERSAL_TESTNET_MODE', False)
                setattr(temp_cfg, 'UNIVERSAL_TESTNET_MODE', not current_val)
            elif action == 'help':
                show_help_popup("config_editor")
            elif action == 'save':
                print("\nCambios guardados."); time.sleep(1.5)
                return True
            elif action == 'cancel' or choice is None:
                print("\nCambios descartados."); time.sleep(1.5)
                return False
        except UserInputCancelled:
            print("\n\nEdición cancelada por el usuario."); time.sleep(1)

def _show_session_config_menu(temp_cfg: Any) -> bool:
    """Muestra el menú principal para editar la configuración de una sesión."""
    while True:
        menu_items = [
            "[1] Parámetros del Ticker",
            "[2] Parámetros de Estrategia (TA y Señal)",
            "[3] Parámetros de Capital (Posiciones)",
            "[4] Parámetros de Límites (Disyuntores)",
            None,
            "[h] Ayuda",
            None,
            "[s] Guardar y Volver",
            "[c] Cancelar (Descartar Cambios)"
        ]
        action_map = {0: 'ticker', 1: 'strategy', 2: 'capital', 3: 'limits', 5: 'help', 7: 'save', 8: 'cancel'}

        menu = TerminalMenu(menu_items, title="Editor de Configuración de Sesión", **MENU_STYLE)
        choice = menu.show()
        action = action_map.get(choice)

        if action == 'ticker': _show_ticker_config_menu(temp_cfg)
        elif action == 'strategy': _show_strategy_config_menu(temp_cfg)
        elif action == 'capital': _show_pm_capital_config_menu(temp_cfg)
        elif action == 'limits': _show_session_limits_menu(temp_cfg)
        elif action == 'help': show_help_popup("config_editor")
        elif action == 'save':
            print("\nCambios guardados."); time.sleep(1.5)
            return True
        elif action == 'cancel' or choice is None:
            print("\nCambios descartados."); time.sleep(1.5)
            return False

# --- SUBMENÚS DE EDICIÓN (Lógica de bajo nivel, sin cambios) ---

def _show_ticker_config_menu(cfg: Any):
    try:
        while True:
            menu_items = [
                f"[1] Símbolo del Ticker (Actual: {getattr(cfg, 'TICKER_SYMBOL', 'N/A')})",
                f"[2] Intervalo de Estrategia (segundos) (Actual: {getattr(cfg, 'TICKER_INTERVAL_SECONDS', 1)})",
                None, "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Configuración del Ticker", **MENU_STYLE)
            choice = submenu.show()
            if choice == 0:
                new_val = get_input("\nNuevo Símbolo (ej. ETHUSDT)", str, getattr(cfg, 'TICKER_SYMBOL', 'N/A'))
                setattr(cfg, 'TICKER_SYMBOL', new_val.upper())
            elif choice == 1:
                new_val = get_input("\nNuevo Intervalo (segundos, ej. 1, 5)", float, getattr(cfg, 'TICKER_INTERVAL_SECONDS', 1), min_val=0.1)
                setattr(cfg, 'TICKER_INTERVAL_SECONDS', new_val)
            else: break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)

def _show_strategy_config_menu(cfg: Any):
    try:
        while True:
            menu_items = [
                f"[1] Margen de Compra (%) (Actual: {getattr(cfg, 'STRATEGY_MARGIN_BUY', 0.0)})",
                f"[2] Margen de Venta (%) (Actual: {getattr(cfg, 'STRATEGY_MARGIN_SELL', 0.0)})",
                f"[3] Umbral de Decremento Ponderado (Actual: {getattr(cfg, 'STRATEGY_DECREMENT_THRESHOLD', 0.0)})",
                f"[4] Umbral de Incremento Ponderado (Actual: {getattr(cfg, 'STRATEGY_INCREMENT_THRESHOLD', 0.0)})",
                f"[5] Período EMA (Actual: {getattr(cfg, 'TA_EMA_WINDOW', 0)})",
                None, "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Parámetros de la Estrategia (TA y Señal)", **MENU_STYLE)
            choice = submenu.show()
            if choice == 0: setattr(cfg, 'STRATEGY_MARGIN_BUY', get_input("\nNuevo Margen de Compra (ej. -0.1)", float, getattr(cfg, 'STRATEGY_MARGIN_BUY', 0.0)))
            elif choice == 1: setattr(cfg, 'STRATEGY_MARGIN_SELL', get_input("\nNuevo Margen de Venta (ej. 0.1)", float, getattr(cfg, 'STRATEGY_MARGIN_SELL', 0.0)))
            elif choice == 2: setattr(cfg, 'STRATEGY_DECREMENT_THRESHOLD', get_input("\nNuevo Umbral de Decremento (0-1)", float, getattr(cfg, 'STRATEGY_DECREMENT_THRESHOLD', 0.0), min_val=0.0, max_val=1.0))
            elif choice == 3: setattr(cfg, 'STRATEGY_INCREMENT_THRESHOLD', get_input("\nNuevo Umbral de Incremento (0-1)", float, getattr(cfg, 'STRATEGY_INCREMENT_THRESHOLD', 0.0), min_val=0.0, max_val=1.0))
            elif choice == 4: setattr(cfg, 'TA_EMA_WINDOW', get_input("\nNuevo Período para la EMA", int, getattr(cfg, 'TA_EMA_WINDOW', 0), min_val=1))
            else: break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)

def _show_pm_capital_config_menu(cfg: Any):
    try:
        while True:
            menu_items = [
                f"[1] Tamaño Base por Posición (USDT) (Actual: {getattr(cfg, 'POSITION_BASE_SIZE_USDT', 0.0):.2f})",
                f"[2] Máximo de Posiciones por Lado (Actual: {getattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', 0)})",
                f"[3] Apalancamiento (Actual: {getattr(cfg, 'POSITION_LEVERAGE', 0.0):.1f}x)",
                f"[4] % de Reinversión de Ganancias (Actual: {getattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', 0.0):.1f}%)",
                None, "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Gestión de Posiciones (Capital)", **MENU_STYLE)
            choice = submenu.show()
            if choice == 0: setattr(cfg, 'POSITION_BASE_SIZE_USDT', get_input("\nNuevo Tamaño Base (USDT)", float, getattr(cfg, 'POSITION_BASE_SIZE_USDT', 0.0), min_val=0.1))
            elif choice == 1: setattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', get_input("\nNuevo Máximo de Posiciones por Lado", int, getattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', 0), min_val=1))
            elif choice == 2: setattr(cfg, 'POSITION_LEVERAGE', get_input("\nNuevo Apalancamiento (ej. 10.0)", float, getattr(cfg, 'POSITION_LEVERAGE', 0.0), min_val=1.0, max_val=100.0))
            elif choice == 3: setattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', get_input("\nNuevo % de Reinversión (0-100)", float, getattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', 0.0), min_val=0.0, max_val=100.0))
            else: break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)

def _show_session_limits_menu(cfg: Any):
    try:
        while True:
            duration = getattr(cfg, 'SESSION_MAX_DURATION_MINUTES', 0)
            duration_str = f"{duration} min (Acción: {getattr(cfg, 'SESSION_TIME_LIMIT_ACTION', 'NEUTRAL')})" if duration > 0 else "Desactivado"
            sl_roi_status = "Activado" if getattr(cfg, 'SESSION_ROI_SL_ENABLED', False) else "Desactivado"
            tp_roi_status = "Activado" if getattr(cfg, 'SESSION_ROI_TP_ENABLED', False) else "Desactivado"
            
            menu_items = [
                f"[1] Límite de Duración (min) (Actual: {duration_str})",
                f"[2] Stop Loss de Sesión por ROI (Estado: {sl_roi_status})",
                f"[3]    └─ Umbral de SL (%): (Actual: -{getattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', 0.0):.2f})",
                f"[4] Take Profit de Sesión por ROI (Estado: {tp_roi_status})",
                f"[5]    └─ Umbral de TP (%): (Actual: +{getattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0):.2f})",
                None, "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Límites de Sesión (Disyuntores)", **MENU_STYLE)
            choice = submenu.show()
            if choice == 0:
                new_duration = get_input("\nDuración máx (min, 0=desactivar)", int, duration, min_val=0)
                setattr(cfg, 'SESSION_MAX_DURATION_MINUTES', new_duration)
                if new_duration > 0:
                    action_idx = TerminalMenu(["[1] NEUTRAL", "[2] STOP"], title="Acción al alcanzar límite:").show()
                    if action_idx is not None: setattr(cfg, 'SESSION_TIME_LIMIT_ACTION', "STOP" if action_idx == 1 else "NEUTRAL")
            elif choice == 1: setattr(cfg, 'SESSION_ROI_SL_ENABLED', not getattr(cfg, 'SESSION_ROI_SL_ENABLED', False))
            elif choice == 2: setattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', get_input("\nNuevo % de SL (ej. 10 para -10%)", float, getattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', 0.0), min_val=0.1))
            elif choice == 3: setattr(cfg, 'SESSION_ROI_TP_ENABLED', not getattr(cfg, 'SESSION_ROI_TP_ENABLED', False))
            elif choice == 4: setattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', get_input("\nNuevo % de TP (ej. 5 para +5%)", float, getattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0), min_val=0.1))
            else: break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)