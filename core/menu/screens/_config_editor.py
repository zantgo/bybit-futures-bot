"""
Módulo para la Pantalla de Edición de Configuración.

v2.2: Añadida la inyección de dependencias para poder acceder a la pm_api
y propagar los cambios de configuración al Position Manager.
"""
from typing import Any, Dict
import time

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    get_input,
    MENU_STYLE,
    press_enter_to_continue,
    show_help_popup
)

# --- INYECCIÓN DE DEPENDENCIAS A NIVEL DE MÓDULO ---
# Esta variable global almacenará las dependencias inyectadas una sola vez.
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """
    Recibe las dependencias inyectadas desde el paquete de pantallas (__init__.py).
    Esto permite que los submenús accedan a la API del Position Manager.
    """
    global _deps
    _deps = dependencies


# --- LÓGICA DE LA PANTALLA PRINCIPAL ---

def show_config_editor_screen(config_module: Any):
    """
    Muestra el menú principal de edición de configuración.
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
            "[h] Ayuda sobre el Editor de Configuración",
            None,
            "[b] Guardar y Volver a la Pantalla Anterior"
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
            # Obtenemos la pm_api desde el diccionario de dependencias del módulo.
            pm_api = _deps.get("position_manager_api_module")
            if pm_api:
                _show_session_limits_menu(config_module, pm_api)
            else:
                print("\nERROR: No se pudo acceder a la API del Position Manager.")
                time.sleep(2)
        elif choice_index == 6:
            show_help_popup("config_editor")
        elif choice_index == 8 or choice_index is None:
            break

# --- SUBMENÚS DE CONFIGURACIÓN (SIN CAMBIOS) ---

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

def _show_session_limits_menu(cfg: Any, pm_api: Any):
    """Muestra el submenú para los límites de la Sesión, usando flags y propagando los cambios."""
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
                new_action = "STOP" if action_idx == 1 else "NEUTRAL"
                setattr(cfg, 'SESSION_TIME_LIMIT_ACTION', new_action)
        
        elif choice == 1:
            new_val = get_input("\nNuevo límite de trades (0 para ilimitados)", int, getattr(cfg, 'SESSION_MAX_TRADES', 0), min_val=0)
            setattr(cfg, 'SESSION_MAX_TRADES', new_val)
        
        elif choice == 3:
            current_status = getattr(cfg, 'SESSION_ROI_SL_ENABLED', False)
            menu_choice = TerminalMenu(["[1] Activado", "[2] Desactivado"], title=f"\nEstado actual del SL de Sesión: { 'Activado' if current_status else 'Desactivado' }").show()
            if menu_choice is not None:
                new_status = (menu_choice == 0)
                setattr(cfg, 'SESSION_ROI_SL_ENABLED', new_status)
                if not new_status:
                    pm_api.set_global_stop_loss_pct(0)
                    print("\nSL de Sesión DESACTIVADO en el Position Manager.")
                else:
                    current_val = getattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
                    pm_api.set_global_stop_loss_pct(current_val)
                    print(f"\nSL de Sesión ACTIVADO en el PM con valor -{current_val}%.")
                time.sleep(1.5)

        elif choice == 4:
            new_val = get_input("\nNuevo % de SL de Sesión (ej. 10 para -10%)", float, sl_roi_val, min_val=0.1)
            setattr(cfg, 'SESSION_STOP_LOSS_ROI_PCT', new_val)
            if getattr(cfg, 'SESSION_ROI_SL_ENABLED', False):
                pm_api.set_global_stop_loss_pct(new_val)
                print(f"\nUmbral de SL en el PM actualizado a -{new_val}%.")
                time.sleep(1.5)
        
        elif choice == 6:
            current_status = getattr(cfg, 'SESSION_ROI_TP_ENABLED', False)
            menu_choice = TerminalMenu(["[1] Activado", "[2] Desactivado"], title=f"\nEstado actual del TP de Sesión: { 'Activado' if current_status else 'Desactivado' }").show()
            if menu_choice is not None:
                new_status = (menu_choice == 0)
                setattr(cfg, 'SESSION_ROI_TP_ENABLED', new_status)
                if not new_status:
                    pm_api.set_global_take_profit_pct(0)
                    print("\nTP de Sesión DESACTIVADO en el Position Manager.")
                else:
                    current_val = getattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)
                    pm_api.set_global_take_profit_pct(current_val)
                    print(f"\nTP de Sesión ACTIVADO en el PM con valor +{current_val}%.")
                time.sleep(1.5)

        elif choice == 7:
            new_val = get_input("\nNuevo % de TP de Sesión (ej. 5 para +5%)", float, tp_roi_val, min_val=0.1)
            setattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', new_val)
            if getattr(cfg, 'SESSION_ROI_TP_ENABLED', False):
                pm_api.set_global_take_profit_pct(new_val)
                print(f"\nUmbral de TP en el PM actualizado a +{new_val}%.")
                time.sleep(1.5)
        
        else:
            break