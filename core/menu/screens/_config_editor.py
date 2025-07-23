"""
Módulo para la Pantalla de Edición de Configuración.

v3.3: Implementado un sistema de estado temporal. Los cambios solo se
guardan si el usuario selecciona explícitamente "Volver (Cambios guardados)",
solucionando el bug de guardado no intencionado al cancelar.
"""
from typing import Any, Dict
import time
# --- INICIO DE LA CORRECCIÓN ---
# Necesitamos `copy` para crear una copia temporal de la configuración.
import copy
# --- FIN DE LA CORRECCIÓN ---

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    get_input,
    MENU_STYLE,
    press_enter_to_continue,
    show_help_popup,
    CancelInput
)

_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    global _deps
    _deps = dependencies

# --- LÓGICA DE LA PANTALLA PRINCIPAL ---

def show_config_editor_screen(config_module: Any):
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado."); time.sleep(2); return

    # --- INICIO DE LA CORRECCIÓN ---
    # 1. Crear un objeto temporal que es una copia de la configuración actual.
    # Usamos un objeto simple para facilitar la copia y modificación.
    class TempConfig:
        pass
    
    temp_config = TempConfig()
    for attr in dir(config_module):
        if not attr.startswith('__'):
            setattr(temp_config, attr, getattr(config_module, attr))
    # --- FIN DE LA CORRECCIÓN ---

    while True:
        menu_items = [
            "[1] Configuración del Ticker",
            "[2] Parámetros de la Estrategia (TA y Señal)",
            "[3] Gestión de Posiciones (Capital)",
            "[4] Límites de la Sesión (Disyuntores)",
            None,
            "[h] Ayuda sobre el Editor de Configuración",
            None,
            "[b] Guardar y Volver",
            "[c] Cancelar (Descartar Cambios)"
        ]
        
        main_menu = TerminalMenu(menu_items, title="Editor de Configuración de la Sesión", **MENU_STYLE)
        choice_index = main_menu.show()
        
        action_map = {
            0: 'ticker', 1: 'strategy', 2: 'capital', 3: 'limits',
            5: 'help', 7: 'save_back', 8: 'cancel_back'
        }
        action = action_map.get(choice_index)

        # Todos los submenús ahora modificarán `temp_config`
        if action == 'ticker':
            _show_ticker_config_menu(temp_config)
        elif action == 'strategy':
            _show_strategy_config_menu(temp_config)
        elif action == 'capital':
            _show_pm_capital_config_menu(temp_config)
        elif action == 'limits':
            pm_api = _deps.get("position_manager_api_module")
            if pm_api:
                _show_session_limits_menu(temp_config, pm_api)
            else:
                print("\nERROR: No se pudo acceder a la API del Position Manager."); time.sleep(2)
        elif action == 'help':
            show_help_popup("config_editor")
        
        # --- INICIO DE LA CORRECCIÓN ---
        elif action == 'save_back':
            # 2. Si el usuario guarda, aplicamos los cambios al módulo original.
            for attr in dir(temp_config):
                if not attr.startswith('__'):
                    setattr(config_module, attr, getattr(temp_config, attr))
            print("\nCambios guardados en la configuración de la sesión.")
            time.sleep(1.5)
            break
        elif action == 'cancel_back' or choice_index is None:
            # 3. Si cancela o usa ESC, simplemente salimos. La copia se descarta.
            print("\nCambios descartados.")
            time.sleep(1.5)
            break
        # --- FIN DE LA CORRECCIÓN ---

# --- SUBMENÚS DE CONFIGURACIÓN ---
# Todas estas funciones ahora reciben `cfg` que es el objeto `temp_config`.
# El resto de la lógica interna no necesita cambios.

def _show_ticker_config_menu(cfg: Any):
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
            if not isinstance(new_val, CancelInput): setattr(cfg, 'TICKER_SYMBOL', new_val.upper())
        elif choice == 1:
            new_val = get_input("\nNuevo Intervalo (segundos, ej. 1, 5)", float, getattr(cfg, 'TICKER_INTERVAL_SECONDS', 1), min_val=0.1)
            if not isinstance(new_val, CancelInput): setattr(cfg, 'TICKER_INTERVAL_SECONDS', new_val)
        else:
            break

def _show_strategy_config_menu(cfg: Any):
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
            if not isinstance(new_val, CancelInput): setattr(cfg, 'STRATEGY_MARGIN_BUY', new_val)
        elif choice == 1:
            new_val = get_input("\nNuevo Margen de Venta (ej. 0.1)", float, getattr(cfg, 'STRATEGY_MARGIN_SELL', 0.0))
            if not isinstance(new_val, CancelInput): setattr(cfg, 'STRATEGY_MARGIN_SELL', new_val)
        elif choice == 2:
            new_val = get_input("\nNuevo Umbral de Decremento (0-1)", float, getattr(cfg, 'STRATEGY_DECREMENT_THRESHOLD', 0.0), min_val=0.0, max_val=1.0)
            if not isinstance(new_val, CancelInput): setattr(cfg, 'STRATEGY_DECREMENT_THRESHOLD', new_val)
        elif choice == 3:
            new_val = get_input("\nNuevo Umbral de Incremento (0-1)", float, getattr(cfg, 'STRATEGY_INCREMENT_THRESHOLD', 0.0), min_val=0.0, max_val=1.0)
            if not isinstance(new_val, CancelInput): setattr(cfg, 'STRATEGY_INCREMENT_THRESHOLD', new_val)
        elif choice == 5:
            new_val = get_input("\nNuevo Período para la EMA", int, getattr(cfg, 'TA_EMA_WINDOW', 0), min_val=1)
            if not isinstance(new_val, CancelInput): setattr(cfg, 'TA_EMA_WINDOW', new_val)
        else:
            break

def _show_pm_capital_config_menu(cfg: Any):
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
            if not isinstance(new_val, CancelInput): setattr(cfg, 'POSITION_BASE_SIZE_USDT', new_val)
        elif choice == 1:
            new_val = get_input("\nNuevo Máximo de Posiciones por Lado", int, getattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', 0), min_val=1)
            if not isinstance(new_val, CancelInput): setattr(cfg, 'POSITION_MAX_LOGICAL_POSITIONS', new_val)
        elif choice == 2:
            new_val = get_input("\nNuevo Apalancamiento (ej. 10.0)", float, getattr(cfg, 'POSITION_LEVERAGE', 0.0), min_val=1.0, max_val=100.0)
            if not isinstance(new_val, CancelInput): setattr(cfg, 'POSITION_LEVERAGE', new_val)
        elif choice == 4:
            new_val = get_input("\nNueva Dif. Mín. LONG (% , ej: -0.25)", float, getattr(cfg, 'POSITION_MIN_PRICE_DIFF_LONG_PCT', 0.0))
            if not isinstance(new_val, CancelInput): setattr(cfg, 'POSITION_MIN_PRICE_DIFF_LONG_PCT', new_val)
        elif choice == 5:
            new_val = get_input("\nNueva Dif. Mín. SHORT (% , ej: 0.25)", float, getattr(cfg, 'POSITION_MIN_PRICE_DIFF_SHORT_PCT', 0.0))
            if not isinstance(new_val, CancelInput): setattr(cfg, 'POSITION_MIN_PRICE_DIFF_SHORT_PCT', new_val)
        elif choice == 6:
            new_val = get_input("\nNuevo % de Reinversión (0-100)", float, getattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', 0.0), min_val=0.0, max_val=100.0)
            if not isinstance(new_val, CancelInput): setattr(cfg, 'POSITION_REINVEST_PROFIT_PCT', new_val)
        else:
            break

def _show_session_limits_menu(cfg: Any, pm_api: Any):
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
            if not isinstance(new_duration, CancelInput):
                setattr(cfg, 'SESSION_MAX_DURATION_MINUTES', new_duration)
                if new_duration > 0:
                    action_idx = TerminalMenu(["[1] Pasar a modo NEUTRAL", "[2] Parada de Emergencia (STOP)"], title="Acción al alcanzar el límite:").show()
                    if action_idx is not None:
                        new_action = "STOP" if action_idx == 1 else "NEUTRAL"
                        setattr(cfg, 'SESSION_TIME_LIMIT_ACTION', new_action)
        elif choice == 1:
            new_val = get_input("\nNuevo límite de trades (0 para ilimitados)", int, getattr(cfg, 'SESSION_MAX_TRADES', 0), min_val=0)
            if not isinstance(new_val, CancelInput): setattr(cfg, 'SESSION_MAX_TRADES', new_val)
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
            if not isinstance(new_val, CancelInput):
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
            if not isinstance(new_val, CancelInput):
                setattr(cfg, 'SESSION_TAKE_PROFIT_ROI_PCT', new_val)
                if getattr(cfg, 'SESSION_ROI_TP_ENABLED', False):
                    pm_api.set_global_take_profit_pct(new_val)
                    print(f"\nUmbral de TP en el PM actualizado a +{new_val}%.")
                    time.sleep(1.5)
        else:
            break