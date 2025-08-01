"""
Módulo para la Pantalla de Edición de Configuración de la Sesión.

v9.0 (Recarga en Caliente):
- Se modifica el submenú de Ticker para impedir la modificación de `TICKER_SYMBOL`
  y `TICKER_INTERVAL_SECONDS` mientras una sesión está activa, ya que estos
  parámetros no pueden cambiarse dinámicamente sin reiniciar el Ticker.
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

def show_session_config_editor_screen(config_module: Any) -> bool:
    """
    Muestra la pantalla de edición de configuración de sesión y devuelve True si se guardaron cambios.
    """
    logger = _deps.get("memory_logger_module")
    if not TerminalMenu:
        if logger: logger.log("Error: 'simple-term-menu' no está instalado.", level="ERROR")
        return False

    # Crear una copia temporal de la configuración para editarla sin afectar la real
    # hasta que se guarde explícitamente.
    class TempConfig: pass
    temp_config = TempConfig()
    for attr in dir(config_module):
        if attr.isupper() and not attr.startswith('_'):
            setattr(temp_config, attr, copy.deepcopy(getattr(config_module, attr)))

    changes_made = _show_session_config_menu(temp_config)

    if changes_made:
        _apply_changes_to_real_config(temp_config, config_module, logger)
        return True
    
    return False

# --- Lógica de Aplicación de Cambios ---

def _apply_changes_to_real_config(temp_cfg: Any, real_cfg: Any, logger: Any):
    """Compara la config temporal con la real, aplica los cambios y los loguea."""
    if not logger: return
    logger.log("Aplicando cambios de configuración de sesión...", "WARN")
    for attr in dir(temp_cfg):
        if attr.isupper() and not attr.startswith('_'):
            new_value = getattr(temp_cfg, attr)
            # Aplicar solo si el atributo existe en la config real y el valor ha cambiado
            if hasattr(real_cfg, attr) and new_value != getattr(real_cfg, attr):
                logger.log(f"  -> {attr}: '{getattr(real_cfg, attr)}' -> '{new_value}'", "WARN")
                setattr(real_cfg, attr, new_value)

# --- MENÚ DE EDICIÓN ---

def _show_session_config_menu(temp_cfg: Any) -> bool:
    """Muestra el menú principal para editar la configuración de una sesión."""
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

        if action == 'ticker': _show_ticker_config_menu(temp_cfg)
        elif action == 'strategy': _show_strategy_config_menu(temp_cfg)
        elif action == 'capital': _show_pm_capital_config_menu(temp_cfg)
        elif action == 'limits': _show_session_limits_menu(temp_cfg)
        elif action == 'help': show_help_popup("config_editor")
        elif action == 'save':
            print("\nCambios guardados. Se aplicarán dinámicamente a la sesión."); time.sleep(2); return True
        elif action == 'cancel' or action is None:
            print("\nCambios descartados."); time.sleep(1.5); return False

# --- SUBMENÚS DE EDICIÓN ---
def _show_ticker_config_menu(cfg: Any):
    """Muestra el menú para editar los parámetros del Ticker."""
    # --- INICIO DE LA MODIFICACIÓN ---
    # Verificar si la sesión ya está corriendo para deshabilitar opciones.
    from core.strategy.sm import api as sm_api
    is_session_running = sm_api.is_running() if sm_api else False
    # --- FIN DE LA MODIFICACIÓN ---
    
    try:
        while True:
            menu_items = [
                f"[1] Símbolo del Ticker (Actual: {getattr(cfg, 'TICKER_SYMBOL', 'N/A')})",
                f"[2] Intervalo (segundos) (Actual: {getattr(cfg, 'TICKER_INTERVAL_SECONDS', 1)})",
                None, "[b] Volver"
            ]
            
            # --- INICIO DE LA MODIFICACIÓN ---
            # Añadir mensaje informativo si la sesión está activa
            title = "Configuración del Ticker"
            if is_session_running:
                title += "\n(Símbolo e Intervalo no se pueden cambiar durante una sesión activa)"
            # --- FIN DE LA MODIFICACIÓN ---

            submenu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
            choice = submenu.show()

            # --- INICIO DE LA MODIFICACIÓN ---
            # Bloquear la edición si la sesión está activa
            if is_session_running and choice in [0, 1]:
                print("\nEste parámetro no puede ser modificado mientras la sesión está en ejecución.")
                time.sleep(2)
                continue
            # --- FIN DE LA MODIFICACIÓN ---

            if choice == 0:
                new_val = get_input("\nNuevo Símbolo (ej. ETHUSDT)", str, getattr(cfg, 'TICKER_SYMBOL', 'N/A'))
                setattr(cfg, 'TICKER_SYMBOL', new_val.upper())
            elif choice == 1:
                new_val = get_input("\nNuevo Intervalo (segundos)", float, getattr(cfg, 'TICKER_INTERVAL_SECONDS', 1), min_val=0.1)
                setattr(cfg, 'TICKER_INTERVAL_SECONDS', new_val)
            else: break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)


def _show_strategy_config_menu(cfg: Any):
    """Muestra el menú para editar los parámetros de la estrategia."""
    try:
        while True:
            menu_items = [
                f"[1] Margen de Compra (%) (Actual: {getattr(cfg, 'STRATEGY_MARGIN_BUY', 0.0)})",
                f"[2] Margen de Venta (%) (Actual: {getattr(cfg, 'STRATEGY_MARGIN_SELL', 0.0)})",
                f"[3] Umbral de Decremento Ponderado (Actual: {getattr(cfg, 'STRATEGY_DECREMENT_THRESHOLD', 0.0)})",
                f"[4] Umbral de Incremento Ponderado (Actual: {getattr(cfg, 'STRATEGY_INCREMENT_THRESHOLD', 0.0)})",
                f"[5] Período EMA (TA_EMA_WINDOW) (Actual: {getattr(cfg, 'TA_EMA_WINDOW', 0)})",
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
    """Muestra el menú para editar los parámetros de capital por defecto."""
    try:
        while True:
            menu_items = [
                f"[1] Tamaño Base por Posición (USDT) (Actual: {getattr(cfg, 'POSITION_BASE_SIZE_USDT', 0.0):.2f})",
                f"[2] Máximo de Posiciones por Lado (Actual: {getattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', 0)})",
                f"[3] Apalancamiento (Actual: {getattr(cfg, 'POSITION_LEVERAGE', 0.0):.1f}x)",
                f"[4] % de Reinversión de Ganancias (Actual: {getattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', 0.0):.1f}%)",
                None, "[b] Volver"
            ]
            submenu = TerminalMenu(menu_items, title="Gestión de Posiciones (Defaults para Operaciones)", **MENU_STYLE)
            choice = submenu.show()
            if choice == 0: setattr(cfg, 'POSITION_BASE_SIZE_USDT', get_input("\nNuevo Tamaño Base (USDT)", float, getattr(cfg, 'POSITION_BASE_SIZE_USDT', 0.0), min_val=0.1))
            elif choice == 1: setattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', get_input("\nNuevo Máximo de Posiciones por Lado", int, getattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', 0), min_val=1))
            elif choice == 2: setattr(cfg, 'POSITION_LEVERAGE', get_input("\nNuevo Apalancamiento (ej. 10.0)", float, getattr(cfg, 'POSITION_LEVERAGE', 0.0), min_val=1.0, max_val=100.0))
            elif choice == 3: setattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', get_input("\nNuevo % de Reinversión (0-100)", float, getattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', 0.0), min_val=0.0, max_val=100.0))
            else: break
    except UserInputCancelled: print("\n\nEdición cancelada."); time.sleep(1)

def _show_session_limits_menu(cfg: Any):
    """Muestra el menú para editar los disyuntores de la sesión."""
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