# =============== INICIO ARCHIVO: core/menu/_screens.py (CORREGIDO Y COMPLETO) ===============
"""
Módulo de Pantallas de la TUI (Terminal User Interface).

Contiene las funciones que renderizan cada una de las pantallas específicas
del menú principal. Cada función es una "vista" que interactúa con el
Position Manager para obtener datos y presentarlos al usuario.
"""
import time
from typing import Dict, Any, Optional
import os
import datetime # Importado para el cálculo del ROI por hora

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Proyecto ---
try:
    from core.strategy import pm_facade as position_manager
    from ._helpers import (
        clear_screen,
        print_tui_header,
        get_input,
        MENU_STYLE,
        press_enter_to_continue,
        print_section
    )
    from core.logging import memory_logger
except ImportError as e:
    print(f"ERROR [TUI Screens]: Falló importación de dependencias: {e}")
    position_manager = None
    memory_logger = None
    def clear_screen(): pass
    def print_tui_header(title): print(f"--- {title} ---")
    def get_input(prompt, type_func, default): return default
    def press_enter_to_continue(): input("Press Enter...")
    def print_section(title, data, is_account_balance=False): print(f"--- {title} --- \n {data}")
    MENU_STYLE = {}


# --- Pantallas del Menú Principal ---

def show_status_screen():
    """Muestra una pantalla con el estado detallado de la sesión."""
    clear_screen()
    print_tui_header("Estado Detallado de la Sesión")
    
    summary = position_manager.get_position_summary()
    if not summary or summary.get('error'):
        print(f"\nError al obtener el estado del bot: {summary.get('error', 'Desconocido')}")
        press_enter_to_continue()
        return

    real_account_balances = summary.get('real_account_balances', {})
    if real_account_balances:
        print_section("Balances Reales de Cuentas (UTA)", real_account_balances, is_account_balance=True)

    manual_state = summary.get('manual_mode_status', {})
    limit_str = manual_state.get('limit') or 'Ilimitados'
    
    current_price = position_manager.get_current_price_for_exit() or 0.0
    unrealized_pnl = position_manager.get_unrealized_pnl(current_price)
    total_pnl = summary.get('total_realized_pnl_session', 0.0) + unrealized_pnl
    initial_capital = summary.get('initial_total_capital', 0.0)
    current_roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
    
    session_start_time = position_manager.pm_state.get_session_start_time()
    roi_per_hour = 0.0
    if session_start_time:
        duration_hours = (datetime.datetime.now() - session_start_time).total_seconds() / 3600
        if duration_hours > 0:
            roi_per_hour = current_roi / duration_hours

    print_section("Estado Lógico de la Sesión (Bot)", {
        "Modo Manual Actual": f"{manual_state.get('mode', 'N/A')} (Trades: {manual_state.get('executed', 0)}/{limit_str})",
        "Precio Actual de Mercado": f"{current_price:.4f} USDT",
        "Capital Lógico Inicial": f"{initial_capital:.2f} USDT",
        "PNL Realizado (Sesión)": f"{summary.get('total_realized_pnl_session', 0.0):+.4f} USDT",
        "PNL No Realizado (Actual)": f"{unrealized_pnl:+.4f} USDT",
        "PNL Total (Estimado)": f"{total_pnl:+.4f} USDT",
        "ROI Actual (Estimado)": f"{current_roi:+.2f}%",
        "ROI Promedio por Hora": f"{roi_per_hour:+.2f}%/h",
    })

    rrr_potential = position_manager.get_rrr_potential()
    rrr_str = f"{rrr_potential:.2f}:1" if rrr_potential is not None else "N/A (SL o TS desactivado)"
    
    risk_params = {
        "Apalancamiento Actual": f"{summary.get('leverage', 0.0):.1f}x (para nuevas posiciones)",
        "RRR Potencial (a Activación TS)": rrr_str,
        "Stop Loss Individual": f"{position_manager.pm_state.get_individual_stop_loss_pct() or 0.0:.2f}%",
        "Trailing Stop": f"Activación: {position_manager.pm_state.get_trailing_stop_params()['activation']:.2f}% / Distancia: {position_manager.pm_state.get_trailing_stop_params()['distance']:.2f}%",
    }
    print_section("Parámetros de Riesgo y Capital", risk_params)
    
    session_limits = summary.get('session_limits', {})
    time_limit = session_limits.get('time_limit', {})
    duration_str = f"{time_limit.get('duration', 0)} min (Acción: {time_limit.get('action', 'N/A')})" if time_limit.get('duration', 0) > 0 else "Desactivado"
    
    limits_data = {
        "Límite de Duración": duration_str,
        "Límite de Trades": limit_str,
        "SL Global por ROI": f"-{position_manager.get_global_sl_pct():.2f}%" if position_manager.get_global_sl_pct() else "Desactivado",
        "TP Global por ROI": f"+{position_manager.pm_state.get_global_tp_pct():.2f}%" if position_manager.pm_state.get_global_tp_pct() else "Desactivado",
    }
    print_section("Límites de Sesión y Disyuntores", limits_data)
    
    active_triggers = summary.get('active_triggers', [])
    if active_triggers:
        triggers_data = {}
        for i, trigger in enumerate(active_triggers):
            cond = trigger.get('condition', {})
            act = trigger.get('action', {})
            key = f"Trigger #{i+1} ({trigger.get('id', 'N/A')[-6:]})"
            value = f"Si Precio {cond.get('type', '').replace('_', ' ')} {cond.get('value')}, entonces {act.get('type', '').replace('_', ' ')} {act.get('params', {})}"
            triggers_data[key] = value
        print_section("Triggers Condicionales Activos", triggers_data)

    print("\n--- Posiciones Lógicas Abiertas ---")
    position_manager.display_logical_positions()
    
    press_enter_to_continue()

def show_mode_menu():
    """Muestra el menú para cambiar el modo de trading con opciones de cierre explícitas."""
    current_mode = position_manager.pm_state.get_manual_state().get('mode', 'N/A')
    
    menu_items = [
        "[1] LONG_SHORT (Operar en ambos lados)",
        "[2] LONG_ONLY (Solo compras)",
        "[3] SHORT_ONLY (Solo ventas)",
        "[4] NEUTRAL (Detener nuevas entradas)",
        None,
        "[b] Volver al menú principal"
    ]
    
    title = f"Selecciona el nuevo modo de trading\nModo actual: {current_mode}"
    
    terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
    choice_index = terminal_menu.show()

    if choice_index is not None and choice_index < 4:
        modes = ["LONG_SHORT", "LONG_ONLY", "SHORT_ONLY", "NEUTRAL"]
        new_mode = modes[choice_index]
        
        close_open = False
        incompatible_side_to_close = None
        
        if current_mode in ["LONG_SHORT", "LONG_ONLY"] and new_mode not in ["LONG_SHORT", "LONG_ONLY"]:
            incompatible_side_to_close = "LONG"
        elif current_mode in ["LONG_SHORT", "SHORT_ONLY"] and new_mode not in ["LONG_SHORT", "SHORT_ONLY"]:
            incompatible_side_to_close = "SHORT"

        if incompatible_side_to_close:
            confirm_title = (
                f"Al cambiar a '{new_mode}', ¿qué hacer con las posiciones {incompatible_side_to_close} abiertas?\n"
                f"----------------------------------------"
            )
            confirm_menu_items = [
                f"[1] Cerrar Inmediatamente Todas las Posiciones {incompatible_side_to_close}",
                f"[2] No Cerrar Nada (dejar que se gestionen hasta su cierre natural)",
                None,
                "[3] Cancelar Cambio de Modo"
            ]
            confirm_menu = TerminalMenu(confirm_menu_items, title=confirm_title, **MENU_STYLE)
            close_choice = confirm_menu.show()
            
            if close_choice == 0:
                close_open = True
            elif close_choice in [None, 2]: # Si cancela o elige no cerrar, no hacemos nada
                return 

        success, message = position_manager.set_manual_trading_mode(new_mode, close_open=close_open)
        print(f"\n{message}")
        time.sleep(2)

def show_risk_menu():
    """Muestra el menú para ajustar parámetros de riesgo en un bucle."""
    while True:
        summary = position_manager.get_position_summary()
        leverage = summary.get('leverage', 0.0)
        sl_ind = position_manager.pm_state.get_individual_stop_loss_pct()
        ts_params = position_manager.pm_state.get_trailing_stop_params()
        
        menu_items = [
            f"[1] Ajustar Apalancamiento (Actual: {leverage:.1f}x)",
            f"[2] Ajustar Stop Loss Individual (Actual: {sl_ind:.2f}%)",
            f"[3] Ajustar Trailing Stop (Actual: Act {ts_params['activation']:.2f}% / Dist {ts_params['distance']:.2f}%)",
            None,
            "[b] Volver al menú principal"
        ]
        
        title = "Ajustar Parámetros de Riesgo"
        
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            new_lev = get_input("\nNuevo Apalancamiento (afecta a nuevas posiciones)", float, leverage, min_val=1.0, max_val=100.0)
            success, msg = position_manager.set_leverage(new_lev)
            print(f"\n{msg}"); time.sleep(2.0)
        elif choice_index == 1:
            new_sl = get_input("\nNuevo % de Stop Loss Individual (0 para desactivar)", float, sl_ind, min_val=0.0)
            success, msg = position_manager.set_individual_stop_loss_pct(new_sl)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 2:
            print("\n--- Ajustar Trailing Stop (para todas las posiciones) ---")
            new_act = get_input("Nuevo % de Activación (0 para desactivar)", float, ts_params['activation'], min_val=0.0)
            new_dist = get_input("Nuevo % de Distancia", float, ts_params['distance'], min_val=0.0)
            success, msg = position_manager.set_trailing_stop_params(new_act, new_dist)
            print(f"\n{msg}"); time.sleep(1.5)
        else:
            break

def show_capital_menu():
    """Muestra el menú para ajustar parámetros de capital en un bucle."""
    while True:
        summary = position_manager.get_position_summary()
        slots = summary.get('max_logical_positions', 0)
        base_size = summary.get('initial_base_position_size_usdt', 0.0)

        menu_items = [
            f"[1] Ajustar Slots por Lado (Actual: {slots})",
            f"[2] Ajustar Tamaño Base de Posición (Actual: {base_size:.2f} USDT)",
            None,
            "[b] Volver al menú principal"
        ]
        
        title = "Ajustar Parámetros de Capital"
        
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()

        if choice_index == 0:
            new_slots = get_input("\nNuevo número de slots por lado", int, slots, min_val=1)
            msg = ""
            if new_slots > slots:
                for _ in range(new_slots - slots):
                    success, msg = position_manager.add_max_logical_position_slot()
            elif new_slots < slots:
                for _ in range(slots - new_slots):
                    success, msg = position_manager.remove_max_logical_position_slot()
                    if not success:
                        break
            else:
                msg = "El número de slots no ha cambiado."
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 1:
            new_size = get_input("\nNuevo tamaño base por posición (USDT)", float, base_size, min_val=1.0)
            success, msg = position_manager.set_base_position_size(new_size)
            print(f"\n{msg}"); time.sleep(1.5)
        else:
            break

# --- INICIO DE LA MODIFICACIÓN: Reestructuración y Mejora de los Menús de Automatización ---

def _show_triggers_submenu():
    """Submenú mejorado para gestionar los triggers condicionales con acciones potentes."""
    while True:
        triggers = position_manager.get_active_triggers()
        title = "Gestión de Triggers Condicionales"
        
        menu_items = ["[Añadir] Nuevo Trigger Condicional", None]
        if triggers:
            for t in triggers:
                cond = t.get('condition', {})
                act = t.get('action', {})
                # Usar un ID más largo para evitar colisiones visuales
                trigger_str = f"ID: ...{t.get('id', 'N/A')[-12:]} | SI Precio {cond.get('type', '').split('_')[-1]} {cond.get('value')} -> {act.get('type', '').replace('_', ' ')}"
                menu_items.append(f"[Eliminar] {trigger_str}")
        else:
            menu_items.append("(No hay triggers activos)")
            
        menu_items.extend([None, "[b] Volver"])

        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()
        
        if choice_index == 0: # Añadir
            cond_type_idx = TerminalMenu(["[1] Precio SUBE POR ENCIMA DE", "[2] Precio BAJA POR DEBAJO DE"], title="Elige la condición:").show()
            if cond_type_idx is None: continue
            cond_type = "PRICE_ABOVE" if cond_type_idx == 0 else "PRICE_BELOW"
            cond_value = get_input("Introduce el precio objetivo (USDT)", float, min_val=0.0)

            action_menu_items = [
                "[1] Cambiar Modo de Trading (Simple)", 
                "[2] Iniciar Nueva Tendencia Manual (Avanzado)",
                "[3] Cerrar Todas las Posiciones LONG", 
                "[4] Cerrar Todas las Posiciones SHORT"
            ]
            action_type_idx = TerminalMenu(action_menu_items, title="Elige la acción a ejecutar:").show()
            if action_type_idx is None: continue
            
            action = {}
            if action_type_idx == 0: # Cambiar Modo
                mode_idx = TerminalMenu(["[1] LONG_SHORT", "[2] LONG_ONLY", "[3] SHORT_ONLY", "[4] NEUTRAL"], title="Elige el nuevo modo:").show()
                if mode_idx is None: continue
                action = {"type": "SET_MODE", "params": {"mode": ["LONG_SHORT", "LONG_ONLY", "SHORT_ONLY", "NEUTRAL"][mode_idx]}}
            
            elif action_type_idx == 1: # Iniciar Nueva Tendencia (la nueva opción potente)
                print("\n--- Configurando la Nueva Tendencia para el Trigger ---")
                mode_idx = TerminalMenu(["[1] LONG_ONLY", "[2] SHORT_ONLY"], title="Elige el modo de la tendencia:").show()
                if mode_idx is None: continue
                trend_mode = "LONG_ONLY" if mode_idx == 0 else "SHORT_ONLY"
                
                trade_limit = get_input("Límite de trades para esta tendencia (0 para ilimitado)", int, default=0, min_val=0)
                duration = get_input("Duración máxima de la tendencia (min, 0 para ilimitado)", int, default=0, min_val=0)
                # --- NUEVA LÓGICA PARA ROI DUAL ---
                tp_roi = get_input("Objetivo de TP por ROI (%, 0 para desactivar)", float, default=0.0, min_val=0.0)
                sl_roi = get_input("Objetivo de SL por ROI (%, ej: -5, 0 para desactivar)", float, default=0.0, max_val=0.0)

                action = {
                    "type": "START_MANUAL_TREND", 
                    "params": {
                        "mode": trend_mode,
                        "trade_limit": trade_limit if trade_limit > 0 else None,
                        "duration_limit": duration if duration > 0 else None,
                        "tp_roi_limit": tp_roi if tp_roi > 0 else None,
                        "sl_roi_limit": sl_roi if sl_roi < 0 else None
                    }
                }

            elif action_type_idx == 2: # Cerrar Longs
                action = {"type": "CLOSE_ALL_LONGS", "params": {}}
            elif action_type_idx == 3: # Cerrar Shorts
                action = {"type": "CLOSE_ALL_SHORTS", "params": {}}

            if action:
                success, msg = position_manager.add_conditional_trigger(condition={"type": cond_type, "value": cond_value}, action=action)
                print(f"\n{msg}"); time.sleep(2)
        
        elif choice_index is not None and choice_index > 1 and triggers:
            trigger_to_remove_idx = choice_index - 2
            if 0 <= trigger_to_remove_idx < len(triggers):
                trigger_id = triggers[trigger_to_remove_idx]['id']
                success, msg = position_manager.remove_conditional_trigger(trigger_id)
                print(f"\n{msg}"); time.sleep(1.5)
        else:
            break

def _show_session_limits_submenu():
    """Submenú para gestionar los límites GLOBALES de la sesión (disyuntores)."""
    while True:
        summary = position_manager.get_position_summary()
        limits = summary.get('session_limits', {})
        time_limit = limits.get('time_limit', {})
        sl_global = position_manager.get_global_sl_pct() or 0.0
        tp_global = position_manager.pm_state.get_global_tp_pct() or 0.0
        
        duration_str = f"{time_limit.get('duration', 0)} min" if time_limit.get('duration', 0) > 0 else "Desactivado"
        
        menu_items = [
            f"[1] Límite por Duración Total (Actual: {duration_str})",
            f"[2] Límite por ROI % (Stop Loss Global) (Actual: -{sl_global:.2f}%)",
            f"[3] Límite por ROI % (Take Profit Global) (Actual: +{tp_global:.2f}%)",
            None,
            "[b] Volver"
        ]
        
        title = "Gestión de Límites Globales de Sesión (Disyuntores)"
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()

        if choice_index == 0:
            new_duration = get_input("\nNueva duración máxima (minutos, 0 para desactivar)", int, time_limit.get('duration', 0), min_val=0)
            action = "NEUTRAL"
            if new_duration > 0:
                action_idx = TerminalMenu(["[1] Pasar a modo NEUTRAL", "[2] Parada de Emergencia (STOP)"], title="Acción al alcanzar el límite:").show()
                if action_idx == 1: action = "STOP"
            success, msg = position_manager.set_session_time_limit(new_duration, action)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 1:
            new_sl_g = get_input("\nNuevo % de SL Global por ROI (0 para desactivar)", float, sl_global, min_val=0.0)
            success, msg = position_manager.set_global_stop_loss_pct(new_sl_g)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 2:
            new_tp_g = get_input("\nNuevo % de TP Global por ROI (0 para desactivar)", float, tp_global, min_val=0.0)
            success, msg = position_manager.set_global_take_profit_pct(new_tp_g)
            print(f"\n{msg}"); time.sleep(1.5)
        else:
            break

def _show_trend_limits_submenu():
    """Submenú mejorado para gestionar los límites de la PRÓXIMA tendencia manual."""
    while True:
        limits = position_manager.pm_state.get_trend_limits()
        duration = limits.get("duration_minutes")
        tp_roi = limits.get("tp_roi_pct")
        sl_roi = limits.get("sl_roi_pct")
        
        manual_state = position_manager.pm_state.get_manual_state()
        trade_limit = manual_state.get("limit")
        
        duration_str = f"{duration} min" if duration else "Desactivado"
        tp_roi_str = f"+{tp_roi:.2f}%" if tp_roi else "Desactivado"
        sl_roi_str = f"{sl_roi:.2f}%" if sl_roi else "Desactivado"
        trade_limit_str = f"{trade_limit} trades" if trade_limit else "Ilimitados"

        menu_items = [
            f"[1] Límite por Duración de Tendencia (Actual: {duration_str})",
            f"[2] Límite por Nº de Trades (Actual: {trade_limit_str})",
            f"[3] Límite TP por ROI de Tendencia (Actual: {tp_roi_str})",
            f"[4] Límite SL por ROI de Tendencia (Actual: {sl_roi_str})",
            None,
            "[b] Volver"
        ]
        
        title = "Gestión de Límites para la PRÓXIMA Tendencia"
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()

        if choice_index == 0:
            new_duration = get_input("\nNueva duración máxima (min, 0 para desactivar)", int, duration or 0, min_val=0)
            success, msg = position_manager.set_trend_limits(new_duration, tp_roi, sl_roi, trade_limit)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 1:
            new_limit = get_input("\nNuevo límite de trades (0 para ilimitados)", int, trade_limit or 0, min_val=0)
            success, msg = position_manager.set_trend_limits(duration, tp_roi, sl_roi, new_limit)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 2:
            new_tp_roi = get_input("\nNuevo objetivo de TP por ROI (%, 0 para desactivar)", float, tp_roi or 0.0, min_val=0.0)
            success, msg = position_manager.set_trend_limits(duration, new_tp_roi, sl_roi, trade_limit)
            print(f"\n{msg}"); time.sleep(1.5)
        elif choice_index == 3:
            new_sl_roi = get_input("\nNuevo objetivo de SL por ROI (%, ej: -5, 0 para desactivar)", float, sl_roi or 0.0, max_val=0.0)
            success, msg = position_manager.set_trend_limits(duration, tp_roi, new_sl_roi, trade_limit)
            print(f"\n{msg}"); time.sleep(1.5)
        else:
            break

def show_automation_menu():
    """Muestra el menú principal de automatización, ahora reestructurado."""
    while True:
        menu_items = [
            "[1] Límites Globales de Sesión (Disyuntores)",
            "[2] Límites para la Próxima Tendencia Manual",
            "[3] Triggers Condicionales por Precio",
            None,
            "[b] Volver al menú principal"
        ]
        title = "Automatización y Estrategia Avanzada"
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()
        
        if choice_index == 0:
            _show_session_limits_submenu()
        elif choice_index == 1:
            _show_trend_limits_submenu()
        elif choice_index == 2:
            _show_triggers_submenu()
        else:
            break

# --- FIN DE LA MODIFICACIÓN ---

def _manage_side_positions(side: str):
    """Función interna para gestionar las posiciones de un lado (long o short)."""
    while True:
        summary = position_manager.get_position_summary()
        if not summary or summary.get('error'):
            print("Error obteniendo resumen de posiciones."); time.sleep(1.5); return

        open_positions = summary.get(f'open_{side}_positions', [])
        if not open_positions:
            print(f"\nNo hay posiciones {side.upper()} abiertas."); time.sleep(1.5); return

        current_price = position_manager.get_current_price_for_exit() or 0.0
        
        menu_items = []
        for i, pos in enumerate(open_positions):
            pnl = (current_price - pos['entry_price']) * pos['size_contracts'] if side == 'long' else (pos['entry_price'] - current_price) * pos['size_contracts']
            menu_items.append(f"[Idx {i}] Px: {pos['entry_price']:.2f}, Qty: {pos['size_contracts']:.4f}, PNL: {pnl:+.2f} USDT")

        menu_items.extend([None, f"[TODAS] Cerrar TODAS las {len(open_positions)} posiciones {side.upper()}", "[b] Volver"])
        
        title = f"Gestionar Posiciones {side.upper()}"
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()

        if choice_index is None or choice_index >= len(menu_items) - 1:
            break
        elif choice_index == len(menu_items) - 2:
            confirm_title = f"¿Cerrar TODAS las posiciones {side.upper()}?"
            confirm_menu = TerminalMenu(["[s] Sí, cerrar todas", "[n] No, cancelar"], title=confirm_title, **MENU_STYLE)
            if confirm_menu.show() == 0:
                position_manager.close_all_logical_positions(side, reason="MANUAL_CLOSE_ALL")
                print(f"Enviando órdenes para cerrar todas las posiciones {side.upper()}..."); time.sleep(2)
        else:
            success, msg = position_manager.manual_close_logical_position_by_index(side, choice_index)
            print(f"\n{msg}"); time.sleep(2)

def show_positions_menu():
    """Muestra el menú para elegir qué lado de las posiciones gestionar."""
    while True:
        menu_items = ["[1] Gestionar posiciones LONG", "[2] Gestionar posiciones SHORT", None, "[b] Volver al menú principal"]
        title = "Selecciona qué lado gestionar"
        terminal_menu = TerminalMenu(menu_items, title=title, **MENU_STYLE)
        choice_index = terminal_menu.show()
        
        if choice_index == 0: _manage_side_positions('long')
        elif choice_index == 1: _manage_side_positions('short')
        else: break

def show_log_viewer():
    """
    Muestra una pantalla con los últimos logs capturados en memoria.
    Esta función ahora tiene su propio bucle para permitir refrescar la vista
    sin volver al menú principal.
    """
    log_viewer_style = MENU_STYLE.copy()
    log_viewer_style["clear_screen"] = False

    while True:
        clear_screen()
        print_tui_header("Visor de Logs en Tiempo Real")
        
        try:
            terminal_height = os.get_terminal_size().lines
            lines_for_logs = max(5, terminal_height - 10)
        except OSError:
            lines_for_logs = 20

        logs = memory_logger.get_logs() if memory_logger else []
        
        if not logs:
            print("\n  (No hay logs para mostrar)")
        else:
            logs_to_show = logs[-lines_for_logs:]
            print("\n  --- Últimos Mensajes (más recientes al final) ---")
            for timestamp, level, message in logs_to_show:
                color_code = ""
                if level == "ERROR": color_code = "\x1b[91m"
                elif level == "WARN": color_code = "\x1b[93m"
                elif level == "DEBUG": color_code = "\x1b[90m"
                reset_code = "\x1b[0m"
                print(f"  {timestamp} [{color_code}{level:<5}{reset_code}] {message[:120]}")

        menu_items = ["[r] Refrescar", "[b] Volver al Menú Principal"]
        title = "\n[r] Refrescar | [b] o [ESC] Volver"
        
        terminal_menu = TerminalMenu(menu_items, title=title, **log_viewer_style)
        choice_index = terminal_menu.show()

        if choice_index == 0:
            continue
        else:
            break

# =============== FIN ARCHIVO: core/menu/_screens.py (CORREGIDO Y COMPLETO) ===============