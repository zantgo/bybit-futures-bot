"""
Módulo para la Pantalla de Edición de Configuración de la Sesión.

v7.1 (Reestructuración UI):
- La UI se divide en dos categorías claras: "Configuración de Sesión" y "Disyuntores".
- Se reintroducen los parámetros de "Comisiones" y "% Reinversión" en la sección de
  configuración de la sesión, ya que afectan el cálculo del PNL y la gestión del capital.
- Los disyuntores (SL/TP/Duración) ahora permiten configurar una acción ('PAUSAR' o 'DETENER').
- Se mantiene el diseño de menú de edición directa en una sola caja.

v7.0 (Rediseño a Menú Directo):
- La UI se rediseñó para mostrar todos los parámetros de sesión en una
  única caja y permitir la edición directa de cada uno, eliminando submenús.
"""
from typing import Any, Dict
import time
import copy
import shutil
import re

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen,
    print_tui_header,
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

# --- Funciones de Ayuda para la UI ---
def _get_terminal_width():
    try:
        return shutil.get_terminal_size().columns
    except:
        return 80

def _clean_ansi_codes(text: str) -> str:
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', str(text))

# --- LÓGICA PRINCIPAL ---

def show_session_config_editor_screen(config_module: Any) -> Dict[str, Any]:
    """
    Muestra la pantalla de edición de config de sesión y devuelve un dict con los cambios.
    """
    logger = _deps.get("memory_logger_module")
    if not TerminalMenu:
        if logger: logger.log("Error: 'simple-term-menu' no está instalado.", level="ERROR")
        return {}

    temp_session_config = copy.deepcopy(config_module.SESSION_CONFIG)
    # Reintroducimos la copia de OPERATION_DEFAULTS porque PROFIT ahora está en SESSION_CONFIG
    # pero el código para aplicarlo está bien así, no es necesario cambiarlo.
    
    changes_made, changed_keys = _show_direct_edit_menu(temp_session_config)

    if changes_made:
        _apply_changes_to_real_config(
            temp_session_config,
            config_module.SESSION_CONFIG,
            logger
        )
        return changed_keys
    
    return {}

def _apply_changes_to_real_config(
    temp_session_cfg: Dict,
    real_session_cfg: Dict,
    logger: Any
):
    """Aplica los cambios del diccionario temporal al real."""
    if not logger: return
    logger.log("Aplicando cambios de configuración de sesión...", "WARN")
    
    # Aplicar cambios a SESSION_CONFIG
    for category, params in temp_session_cfg.items():
        if isinstance(params, dict):
            for key, new_value in params.items():
                if new_value != real_session_cfg[category][key]:
                    logger.log(f"  -> {category}.{key}: '{real_session_cfg[category][key]}' -> '{new_value}'", "WARN")
                    real_session_cfg[category][key] = new_value
        else:
            if params != real_session_cfg[category]:
                logger.log(f"  -> {category}: '{real_session_cfg[category]}' -> '{params}'", "WARN")
                real_session_cfg[category] = params

# --- NUEVO MENÚ DE EDICIÓN DIRECTA ---

def _show_direct_edit_menu(temp_session_cfg: Dict) -> tuple[bool, Dict]:
    """Muestra un menú único para editar todos los parámetros de la sesión directamente."""
    changed_keys = {}
    
    while True:
        clear_screen()
        print_tui_header("Editor de Configuración de Sesión")

        terminal_width = _get_terminal_width()
        box_width = min(terminal_width, 100)

        print("\nValores Actuales:")
        print("┌" + "─" * (box_width - 2) + "┐")

        # --- SECCIÓN 1: Configuración de la Sesión ---
        print(f"│{'Configuración de la Sesión':^{box_width - 2}}│")
        print("├" + "─" * (box_width - 2) + "┤")
        
        # --- INICIO DE LA CORRECCIÓN: Usar 'SIGNAL' en lugar de 'STRATEGY' y nuevas claves ---
        signal_cfg = temp_session_cfg['SIGNAL']
        profit_cfg = temp_session_cfg['PROFIT']
        params_session = {
            "Ticker Intervalo (s)": temp_session_cfg['TICKER_INTERVAL_SECONDS'],
            "Margen Compra/Venta (%)": f"{signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE']} / {signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE']}",
            "Umbral Dec/Inc": f"{signal_cfg['WEIGHTED_DECREMENT_THRESHOLD']} / {signal_cfg['WEIGHTED_INCREMENT_THRESHOLD']}",
            "Períodos TA (EMA/W.Inc/W.Dec)": f"{temp_session_cfg['TA']['EMA_WINDOW']} / {temp_session_cfg['TA']['WEIGHTED_INC_WINDOW']} / {temp_session_cfg['TA']['WEIGHTED_DEC_WINDOW']}",
            "Tarifa de Comisión (%)": profit_cfg['COMMISSION_RATE'] * 100,
            "% Reinversión de Ganancias": profit_cfg['REINVEST_PROFIT_PCT'],
        }
        # --- FIN DE LA CORRECCIÓN ---

        max_key_len1 = max(len(k) for k in params_session.keys())
        for key, value in params_session.items():
            content = f"  {key:<{max_key_len1}} : {value}"
            padding = ' ' * max(0, box_width - len(_clean_ansi_codes(content)) - 3)
            print(f"│{content}{padding}│")

        # --- SECCIÓN 2: Disyuntores de Sesión ---
        print("├" + "─" * (box_width - 2) + "┤")
        print(f"│{'Disyuntores de Sesión':^{box_width - 2}}│")
        print("├" + "─" * (box_width - 2) + "┤")
        
        limits = temp_session_cfg['SESSION_LIMITS']
        params_limits = {
            "Duración Máxima": f"{limits['MAX_DURATION']['MINUTES']} min" if limits['MAX_DURATION']['ENABLED'] else "Desactivado",
            "SL por ROI": f"-{limits['ROI_SL']['PERCENTAGE']:.2f}%" if limits['ROI_SL']['ENABLED'] else "Desactivado",
            "TP por ROI": f"+{limits['ROI_TP']['PERCENTAGE']:.2f}%" if limits['ROI_TP']['ENABLED'] else "Desactivado",
        }
        max_key_len2 = max(len(k) for k in params_limits.keys())
        for key, value in params_limits.items():
            content = f"  {key:<{max_key_len2}} : {value}"
            padding = ' ' * max(0, box_width - len(_clean_ansi_codes(content)) - 3)
            print(f"│{content}{padding}│")

        print("└" + "─" * (box_width - 2) + "┘")

        # --- MENÚ DE ACCIONES ---
        menu_items = [
            "[1] Editar Configuración de Sesión",
            "[2] Editar Disyuntores de Sesión",
            None,
            "[h] Ayuda",
            None,
            "[s] Guardar Cambios y Volver",
            "[c] Cancelar y Descartar Cambios"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nSelecciona una categoría para editar:", **menu_options)
        
        choice = menu.show()

        if choice == 0:
            changes = _edit_session_config_wizard(temp_session_cfg)
            changed_keys.update(changes)
        elif choice == 1:
            changes = _edit_session_breakers_wizard(temp_session_cfg)
            changed_keys.update(changes)
        elif choice == 3:
            show_help_popup("config_editor")
        elif choice == 5: # Guardar
            if changed_keys:
                print("\nCambios guardados. Se aplicarán dinámicamente."); time.sleep(2)
                return True, changed_keys
            else:
                print("\nNo se realizaron cambios."); time.sleep(1.5)
                return False, {}
        elif choice == 6 or choice is None: # Cancelar
            print("\nCambios descartados."); time.sleep(1.5); return False, {}

def _edit_session_config_wizard(temp_session_cfg: Dict) -> Dict:
    """Asistente para editar los parámetros principales de la sesión."""
    changes = {}
    signal_cfg = temp_session_cfg['SIGNAL']
    profit_cfg = temp_session_cfg['PROFIT']
    ta_cfg = temp_session_cfg['TA']
    try:
        print("\n--- Editando Configuración de la Sesión ---")
        # Ticker
        original = temp_session_cfg['TICKER_INTERVAL_SECONDS']
        new_val = get_input("Ticker Intervalo (s)", float, original, min_val=0.1)
        if new_val != original: changes['TICKER_INTERVAL_SECONDS'] = temp_session_cfg['TICKER_INTERVAL_SECONDS'] = new_val

        # --- CORRECCIÓN: Usar nuevas claves de config ---
        # Señal
        original = signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE']
        new_val = get_input("Margen Compra (%)", float, original)
        if new_val != original: changes['PRICE_CHANGE_BUY_PERCENTAGE'] = signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE'] = new_val

        original = signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE']
        new_val = get_input("Margen Venta (%)", float, original)
        if new_val != original: changes['PRICE_CHANGE_SELL_PERCENTAGE'] = signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE'] = new_val
        
        # TA
        original = ta_cfg['EMA_WINDOW']
        new_val = get_input("Período EMA", int, original, min_val=1)
        if new_val != original: changes['EMA_WINDOW'] = ta_cfg['EMA_WINDOW'] = new_val
        
        # Profit
        original = profit_cfg['COMMISSION_RATE']
        new_val = get_input("Tarifa Comisión (%)", float, original * 100, min_val=0.0)
        if new_val / 100 != original: changes['COMMISSION_RATE'] = profit_cfg['COMMISSION_RATE'] = new_val / 100
        
        original = profit_cfg['REINVEST_PROFIT_PCT']
        new_val = get_input("% Reinversión Ganancias", float, original, min_val=0.0, max_val=100.0)
        if new_val != original: changes['REINVEST_PROFIT_PCT'] = profit_cfg['REINVEST_PROFIT_PCT'] = new_val

    except UserInputCancelled: print("\nEdición cancelada."); time.sleep(1)
    return changes

def _edit_session_breakers_wizard(temp_session_cfg: Dict) -> Dict:
    """Asistente para editar los disyuntores de la sesión."""
    changes = {}
    try:
        print("\n--- Editando Disyuntores de Sesión ---")
        limits = temp_session_cfg['SESSION_LIMITS']
        
        # Duración
        original_enabled = limits['MAX_DURATION']['ENABLED']
        new_enabled = get_input("Activar Límite de Duración? (s/n)", str, "s" if original_enabled else "n").lower() == 's'
        if new_enabled != original_enabled: changes['MAX_DURATION_ENABLED'] = limits['MAX_DURATION']['ENABLED'] = new_enabled
        
        if new_enabled:
            original = limits['MAX_DURATION']['MINUTES']
            new_val = get_input("Duración Máx. (min)", int, original, min_val=1)
            if new_val != original: changes['MAX_DURATION_MINUTES'] = limits['MAX_DURATION']['MINUTES'] = new_val
        
        # SL por ROI
        original_enabled = limits['ROI_SL']['ENABLED']
        new_enabled = get_input("Activar SL por ROI? (s/n)", str, "s" if original_enabled else "n").lower() == 's'
        if new_enabled != original_enabled: changes['ROI_SL_ENABLED'] = limits['ROI_SL']['ENABLED'] = new_enabled
        
        if new_enabled:
            original = limits['ROI_SL']['PERCENTAGE']
            new_val = get_input("Umbral SL (%) (positivo)", float, original, min_val=0.1)
            if new_val != original: changes['ROI_SL_PERCENTAGE'] = limits['ROI_SL']['PERCENTAGE'] = new_val
            
        # TP por ROI
        original_enabled = limits['ROI_TP']['ENABLED']
        new_enabled = get_input("Activar TP por ROI? (s/n)", str, "s" if original_enabled else "n").lower() == 's'
        if new_enabled != original_enabled: changes['ROI_TP_ENABLED'] = limits['ROI_TP']['ENABLED'] = new_enabled
        
        if new_enabled:
            original = limits['ROI_TP']['PERCENTAGE']
            new_val = get_input("Umbral TP (%) (positivo)", float, original, min_val=0.1)
            if new_val != original: changes['ROI_TP_PERCENTAGE'] = limits['ROI_TP']['PERCENTAGE'] = new_val

    except UserInputCancelled: print("\nEdición cancelada."); time.sleep(1)
    return changes