# core/menu/screens/_automation.py

"""
Módulo para la pantalla de "Automatización y Estrategia Avanzada" de la TUI.

Esta pantalla es el centro de control para configurar reglas automáticas,
límites y disyuntores que operan durante una sesión de trading manual.
"""
import sys
import os
import time
from typing import Dict, Any, Optional

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias
try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

try:
    from core.strategy import pm as position_manager
    from .._helpers import (
        get_input,
        MENU_STYLE
    )
except ImportError as e:
    print(f"ERROR [TUI Automation Screen]: Falló importación de dependencias: {e}")
    position_manager = None
    MENU_STYLE = {}
    def get_input(prompt, type_func, default, min_val=None, max_val=None): return default

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Submenús de Automatización ---

def _show_triggers_submenu():
    """Submenú para gestionar los triggers condicionales."""
    while True:
        triggers = position_manager.get_active_triggers()
        title = "Gestión de Triggers Condicionales por Precio"
        
        menu_items = ["[Añadir] Nuevo Trigger Condicional", None]
        if triggers:
            for t in triggers:
                cond = t.get('condition', {})
                act = t.get('action', {})
                trigger_str = f"ID: ...{t.get('id', 'N/A')[-12:]} | SI Precio {cond.get('type', '').replace('_', ' ')} {cond.get('value')} -> {act.get('type', '').replace('_', ' ')}"
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
            
            elif action_type_idx == 1: # Iniciar Nueva Tendencia
                print("\n--- Configurando la Nueva Tendencia para el Trigger ---")
                mode_idx = TerminalMenu(["[1] LONG_ONLY", "[2] SHORT_ONLY"], title="Elige el modo de la tendencia:").show()
                if mode_idx is None: continue
                trend_mode = "LONG_ONLY" if mode_idx == 0 else "SHORT_ONLY"
                
                trade_limit = get_input("Límite de trades (0 para ilimitado)", int, default=0, min_val=0)
                duration = get_input("Duración máxima (min, 0 para ilimitado)", int, default=0, min_val=0)
                tp_roi = get_input("Objetivo de TP por ROI (%, ej: 2.5, 0 para desactivar)", float, default=0.0, min_val=0.0)
                sl_roi = get_input("Objetivo de SL por ROI (%, ej: -1.5, 0 para desactivar)", float, default=0.0, max_val=0.0)

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
        
        elif choice_index is not None and choice_index > 1 and menu_items[choice_index] is not None and triggers:
            trigger_to_remove_idx = choice_index - 2 # Ajustar por el [Añadir] y el `None`
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
        tp_global = position_manager.get_global_tp_pct() or 0.0
        
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
    """Submenú para gestionar los límites de la PRÓXIMA tendencia manual."""
    while True:
        limits = position_manager.get_trend_limits()
        duration = limits.get("duration_minutes")
        tp_roi = limits.get("tp_roi_pct")
        sl_roi = limits.get("sl_roi_pct")
        
        manual_state = position_manager.get_manual_state()
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
    if not TerminalMenu or not position_manager:
        print("\nError: Dependencias de menú no disponibles (TerminalMenu o PositionManager).")
        time.sleep(2)
        return
        
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
        else: # Si el usuario presiona 'b', ESC o elige una opción nula
            break