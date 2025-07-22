# core/menu/screens/_config_editor.py

"""
Módulo para la Pantalla de Edición de Configuración.

Permite al usuario modificar en tiempo real los parámetros del módulo `config`
para la sesión actual. Los cambios se aplican directamente al objeto `config`
en memoria.
"""
from typing import Any
import time

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Menú ---
from .._helpers import get_input, MENU_STYLE, press_enter_to_continue

# --- Lógica de la Pantalla ---

def show_config_editor_screen(config_module: Any):
    """
    Muestra el menú principal de edición de configuración.

    Args:
        config_module: El módulo `config` importado, para modificar sus atributos.
    """
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado.")
        time.sleep(2)
        return

    while True:
        menu_items = [
            "[1] Configuración del Ticker",
            "[2] Parámetros de la Estrategia (TA y Señal)",
            "[3] Gestión de Posiciones (Capital)",
            "[4] Gestión de Riesgo (SL y TS)",
            "[5] Límites de la Sesión (Disyuntores)",
            None,
            "[b] Guardar y Volver a la Pantalla Principal"
        ]
        main_menu = TerminalMenu(
            menu_items,
            title="Editor de Configuración de la Sesión",
            **MENU_STYLE
        )
        choice_index = main_menu.show()

        if choice_index == 0:
            _show_ticker_config_menu(config_module)
        elif choice_index == 1:
            _show_strategy_config_menu(config_module)
        elif choice_index == 2:
            _show_pm_capital_config_menu(config_module)
        elif choice_index == 3:
            _show_pm_risk_config_menu(config_module)
        elif choice_index == 4:
            _show_session_limits_menu(config_module)
        elif choice_index == 6 or choice_index is None:
            break

# --- Submenús de Configuración (Privados) ---

def _show_ticker_config_menu(cfg: Any):
    """Muestra el submenú para la configuración del Ticker."""
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

def _show_strategy_config_menu(cfg: Any):
    """Muestra el submenú para la configuración de la Estrategia."""
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

def _show_pm_capital_config_menu(cfg: Any):
    """Muestra el submenú para la configuración de Capital."""
    while True:
        menu_items = [
            f"[1] Tamaño Base por Posición (USDT) (Actual: {getattr(cfg, 'POSITION_BASE_SIZE_USDT', 0.0):.2f})",
            f"[2] Máximo de Posiciones por Lado (Actual: {getattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', 0)})",
            f"[3] Apalancamiento (Actual: {getattr(cfg, 'POSITION_LEVERAGE', 0.0):.1f}x)",
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
        else:
            break

def _show_pm_risk_config_menu(cfg: Any):
    """Muestra el submenú para la configuración de Riesgo."""
    while True:
        menu_items = [
            f"[1] Stop Loss Individual (%) (Actual: {getattr(cfg, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', 0.0):.2f})",
            f"[2] Activación de Trailing Stop (%) (Actual: {getattr(cfg, 'TRAILING_STOP_ACTIVATION_PCT', 0.0):.2f})",
            f"[3] Distancia de Trailing Stop (%) (Actual: {getattr(cfg, 'TRAILING_STOP_DISTANCE_PCT', 0.0):.2f})",
            None,
            "[b] Volver"
        ]
        submenu = TerminalMenu(menu_items, title="Gestión de Riesgo (SL y TS)", **MENU_STYLE)
        choice = submenu.show()
        
        if choice == 0:
            new_val = get_input("\nNuevo % de Stop Loss (0 para desactivar)", float, getattr(cfg, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', 0.0), min_val=0.0)
            setattr(cfg, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', new_val)
        elif choice == 1:
            new_val = get_input("\nNuevo % de Activación de TS (0 para desactivar)", float, getattr(cfg, 'TRAILING_STOP_ACTIVATION_PCT', 0.0), min_val=0.0)
            setattr(cfg, 'TRAILING_STOP_ACTIVATION_PCT', new_val)
        elif choice == 2:
            new_val = get_input("\nNuevo % de Distancia de TS", float, getattr(cfg, 'TRAILING_STOP_DISTANCE_PCT', 0.0), min_val=0.0)
            setattr(cfg, 'TRAILING_STOP_DISTANCE_PCT', new_val)
        else:
            break

def _show_session_limits_menu(cfg: Any):
    """Muestra el submenú para los límites de la Sesión."""
    while True:
        action = getattr(cfg, 'SESSION_TIME_LIMIT_ACTION', 'NEUTRAL')
        duration = getattr(cfg, 'SESSION_MAX_DURATION_MINUTES', 0)
        duration_str = f"{duration} min (Acción: {action})" if duration > 0 else "Desactivado"

        menu_items = [
            f"[1] Límite de Duración (minutos) (Actual: {duration_str})",
            f"[2] Límite de Trades Totales (Actual: {'Ilimitados' if getattr(cfg, 'SESSION_MAX_TRADES', 0) == 0 else getattr(cfg, 'SESSION_MAX_TRADES', 0)})",
            f"[3] Stop Loss de Sesión por ROI (%) (Actual: -{getattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', 0.0):.2f})",
            f"[4] Take Profit de Sesión por ROI (%) (Actual: +{getattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0):.2f})",
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
                new_action = "STOP" if action_idx == 1 else "NEUTRAL"
                setattr(cfg, 'SESSION_TIME_LIMIT_ACTION', new_action)
        elif choice == 1:
            new_val = get_input("\nNuevo límite de trades (0 para ilimitados)", int, getattr(cfg, 'SESSION_MAX_TRADES', 0), min_val=0)
            setattr(cfg, 'SESSION_MAX_TRADES', new_val)
        elif choice == 2:
            new_val = get_input("\nNuevo % de SL de Sesión (ej. 10 para -10%)", float, getattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', 0.0), min_val=0.0)
            setattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', new_val)
        elif choice == 3:
            new_val = get_input("\nNuevo % de TP de Sesión (ej. 5 para +5%)", float, getattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0), min_val=0.0)
            setattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', new_val)
        else:
            break