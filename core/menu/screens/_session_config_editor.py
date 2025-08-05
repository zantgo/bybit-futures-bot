"""
Módulo para la Pantalla de Edición de Configuración de la Sesión.

v8.0 (Rediseño UI Completo y Funcional):
- La UI se ha rediseñado para mostrar todos los parámetros de la sesión en una
  única caja, con un estilo visual consistente con el resto de la TUI.
- El menú de edición es ahora directo, permitiendo modificar cada parámetro
  individualmente sin submenús.
- La visualización de parámetros se ha desglosado para mayor claridad (ej. EMA en su propia línea).
- Se ha incluido la edición de todos los parámetros relevantes de SESSION_CONFIG.
- Mantiene la adaptabilidad al tamaño del terminal y la lógica de actualización en caliente.
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

def _create_config_box_line(content: str, width: int) -> str:
    """Crea una línea de caja de configuración con el contenido alineado."""
    clean_content = _clean_ansi_codes(content)
    padding = ' ' * max(0, width - len(clean_content) - 4)
    return f"│ {content}{padding} │"

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
    
    changes_made, changed_keys = _show_direct_edit_menu(temp_session_config)

    if changes_made:
        _apply_changes_to_real_config(temp_session_config, config_module.SESSION_CONFIG, logger)
        return changed_keys
    
    return {}

# ./core/menu/screens/_session_config_editor.py

def _apply_changes_to_real_config(temp_cfg: Dict, real_cfg: Dict, logger: Any):
    """Aplica los cambios del diccionario temporal al real."""
    if not logger: return
    logger.log("Aplicando cambios de configuración de sesión...", "WARN")
    
    for category, params in temp_cfg.items():
        if isinstance(params, dict):
            for key, new_value in params.items():
                # Comprobar si el valor realmente cambió
                if key in real_cfg.get(category, {}) and new_value != real_cfg[category][key]:
                    logger.log(f"  -> {category}.{key}: '{real_cfg[category][key]}' -> '{new_value}'", "WARN")
                    real_cfg[category][key] = new_value
        else:
            # --- INICIO DE LA CORRECCIÓN ---
            # El nuevo valor es la variable 'params' directamente.
            new_value = params 
            if new_value != real_cfg[category]:
                logger.log(f"  -> {category}: '{real_cfg[category]}' -> '{new_value}'", "WARN")
                real_cfg[category] = new_value
            # --- FIN DE LA CORRECCIÓN ---

def _show_direct_edit_menu(temp_cfg: Dict) -> tuple[bool, Dict]:
    """Muestra un menú único para editar todos los parámetros de la sesión directamente."""
    changed_keys = {}
    
    while True:
        clear_screen()
        print_tui_header("Editor de Configuración de Sesión")

        terminal_width = _get_terminal_width()
        box_width = min(terminal_width, 110)

        # --- PANEL DE VALORES ACTUALES ---
        print("\nValores Actuales:")
        print("┌" + "─" * (box_width - 2) + "┐")

        # Recolectar parámetros para mostrar
        signal_cfg = temp_cfg['SIGNAL']
        profit_cfg = temp_cfg['PROFIT']
        ta_cfg = temp_cfg['TA']
        limits_cfg = temp_cfg['SESSION_LIMITS']
        
        params_to_display = {
            "Ticker Intervalo (s)": temp_cfg['TICKER_INTERVAL_SECONDS'],
            "TA Activado": "Sí" if ta_cfg['ENABLED'] else "No",
            "  └─ Período EMA": ta_cfg['EMA_WINDOW'],
            "  └─ Período W.Inc": ta_cfg['WEIGHTED_INC_WINDOW'],
            "  └─ Período W.Dec": ta_cfg['WEIGHTED_DEC_WINDOW'],
            "Señal Activada": "Sí" if signal_cfg['ENABLED'] else "No",
            "  └─ Margen Compra (%)": signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE'],
            "  └─ Margen Venta (%)": signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE'],
            "  └─ Umbral Decremento": signal_cfg['WEIGHTED_DECREMENT_THRESHOLD'],
            "  └─ Umbral Incremento": signal_cfg['WEIGHTED_INCREMENT_THRESHOLD'],
            "Tarifa Comisión (%)": f"{profit_cfg['COMMISSION_RATE'] * 100:.3f}",
            "% Reinversión Ganancias": profit_cfg['REINVEST_PROFIT_PCT'],
            "Monto Mín. Transferencia": f"${profit_cfg['MIN_TRANSFER_AMOUNT_USDT']:.4f}",
            "Disyuntor Duración": f"{limits_cfg['MAX_DURATION']['MINUTES']} min" if limits_cfg['MAX_DURATION']['ENABLED'] else "Desactivado",
            "Disyuntor SL por ROI": f"-{limits_cfg['ROI_SL']['PERCENTAGE']:.2f}%" if limits_cfg['ROI_SL']['ENABLED'] else "Desactivado",
            "Disyuntor TP por ROI": f"+{limits_cfg['ROI_TP']['PERCENTAGE']:.2f}%" if limits_cfg['ROI_TP']['ENABLED'] else "Desactivado",
        }
        
        max_key_len = max(len(k) for k in params_to_display.keys())
        for key, value in params_to_display.items():
            content = f"{key:<{max_key_len}} : {value}"
            print(_create_config_box_line(content, box_width))

        print("└" + "─" * (box_width - 2) + "┘")

        # --- MENÚ DE ACCIONES ---
        menu_items = [
            f"[ 1] Ticker Intervalo",
            f"[ 2] Períodos de TA (EMA, WMA)",
            f"[ 3] Parámetros de Señal (Márgenes, Umbrales)",
            f"[ 4] Parámetros de Profit (Comisión, Reinversión)",
            f"[ 5] Disyuntores de Sesión (SL, TP, Duración)",
            None,
            "[s] Guardar y Volver",
            "[c] Cancelar (Descartar Cambios)"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nSelecciona una categoría para editar:", **menu_options)
        
        choice = menu.show()

        try:
            if choice == 0: # Ticker
                original = temp_cfg['TICKER_INTERVAL_SECONDS']
                new_val = get_input("\nNuevo Intervalo (s)", float, original, min_val=0.1)
                if new_val != original: changed_keys['TICKER_INTERVAL_SECONDS'] = temp_cfg['TICKER_INTERVAL_SECONDS'] = new_val

            elif choice == 1: # Períodos TA
                ta_cfg = temp_cfg['TA']
                original = ta_cfg['EMA_WINDOW']
                new_val = get_input("\nNuevo Período EMA", int, original, min_val=1)
                if new_val != original: changed_keys['EMA_WINDOW'] = ta_cfg['EMA_WINDOW'] = new_val
                
                original = ta_cfg['WEIGHTED_INC_WINDOW']
                new_val = get_input("Nuevo Período W.Inc", int, original, min_val=1)
                if new_val != original: changed_keys['WEIGHTED_INC_WINDOW'] = ta_cfg['WEIGHTED_INC_WINDOW'] = new_val

                original = ta_cfg['WEIGHTED_DEC_WINDOW']
                new_val = get_input("Nuevo Período W.Dec", int, original, min_val=1)
                if new_val != original: changed_keys['WEIGHTED_DEC_WINDOW'] = ta_cfg['WEIGHTED_DEC_WINDOW'] = new_val

            elif choice == 2: # Parámetros de Señal
                signal_cfg = temp_cfg['SIGNAL']
                original = signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE']
                new_val = get_input("\nNuevo Margen Compra (%)", float, original)
                if new_val != original: changed_keys['PRICE_CHANGE_BUY_PERCENTAGE'] = signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE'] = new_val
                
                original = signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE']
                new_val = get_input("Nuevo Margen Venta (%)", float, original)
                if new_val != original: changed_keys['PRICE_CHANGE_SELL_PERCENTAGE'] = signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE'] = new_val

                original = signal_cfg['WEIGHTED_DECREMENT_THRESHOLD']
                new_val = get_input("Nuevo Umbral Decremento (0-1)", float, original)
                if new_val != original: changed_keys['WEIGHTED_DECREMENT_THRESHOLD'] = signal_cfg['WEIGHTED_DECREMENT_THRESHOLD'] = new_val
                
                original = signal_cfg['WEIGHTED_INCREMENT_THRESHOLD']
                new_val = get_input("Nuevo Umbral Incremento (0-1)", float, original)
                if new_val != original: changed_keys['WEIGHTED_INCREMENT_THRESHOLD'] = signal_cfg['WEIGHTED_INCREMENT_THRESHOLD'] = new_val
            
            elif choice == 3: # Profit
                profit_cfg = temp_cfg['PROFIT']
                original = profit_cfg['COMMISSION_RATE']
                new_val = get_input("\nNueva Tarifa Comisión (%)", float, original * 100, min_val=0.0)
                if new_val / 100 != original: changed_keys['COMMISSION_RATE'] = profit_cfg['COMMISSION_RATE'] = new_val / 100
                
                original = profit_cfg['REINVEST_PROFIT_PCT']
                new_val = get_input("% Reinversión de Ganancias", float, original, min_val=0.0, max_val=100.0)
                if new_val != original: changed_keys['REINVEST_PROFIT_PCT'] = profit_cfg['REINVEST_PROFIT_PCT'] = new_val

                original = profit_cfg['MIN_TRANSFER_AMOUNT_USDT']
                new_val = get_input("Monto Mín. de Transferencia (USDT)", float, original, min_val=0.0)
                if new_val != original: changed_keys['MIN_TRANSFER_AMOUNT_USDT'] = profit_cfg['MIN_TRANSFER_AMOUNT_USDT'] = new_val

            elif choice == 4: # Disyuntores
                limits_cfg = temp_cfg['SESSION_LIMITS']
                # Duración
                enabled = get_input("\nActivar Límite de Duración? (s/n)", str, "s" if limits_cfg['MAX_DURATION']['ENABLED'] else "n").lower() == 's'
                if enabled != limits_cfg['MAX_DURATION']['ENABLED']: changed_keys['MAX_DURATION_ENABLED'] = limits_cfg['MAX_DURATION']['ENABLED'] = enabled
                if enabled:
                    original = limits_cfg['MAX_DURATION']['MINUTES']
                    new_val = get_input("Duración Máx. (min)", int, original, min_val=1)
                    if new_val != original: changed_keys['MAX_DURATION_MINUTES'] = limits_cfg['MAX_DURATION']['MINUTES'] = new_val
                # SL
                enabled = get_input("\nActivar SL por ROI? (s/n)", str, "s" if limits_cfg['ROI_SL']['ENABLED'] else "n").lower() == 's'
                if enabled != limits_cfg['ROI_SL']['ENABLED']: changed_keys['ROI_SL_ENABLED'] = limits_cfg['ROI_SL']['ENABLED'] = enabled
                if enabled:
                    original = limits_cfg['ROI_SL']['PERCENTAGE']
                    new_val = get_input("Umbral SL (%) (positivo)", float, original, min_val=0.1)
                    if new_val != original: changed_keys['ROI_SL_PERCENTAGE'] = limits_cfg['ROI_SL']['PERCENTAGE'] = new_val
                # TP
                enabled = get_input("\nActivar TP por ROI? (s/n)", str, "s" if limits_cfg['ROI_TP']['ENABLED'] else "n").lower() == 's'
                if enabled != limits_cfg['ROI_TP']['ENABLED']: changed_keys['ROI_TP_ENABLED'] = limits_cfg['ROI_TP']['ENABLED'] = enabled
                if enabled:
                    original = limits_cfg['ROI_TP']['PERCENTAGE']
                    new_val = get_input("Umbral TP (%) (positivo)", float, original, min_val=0.1)
                    if new_val != original: changed_keys['ROI_TP_PERCENTAGE'] = limits_cfg['ROI_TP']['PERCENTAGE'] = new_val
            
            elif choice == 6: # Guardar
                if changed_keys:
                    print("\nCambios guardados."); time.sleep(2)
                    return True, changed_keys
                else:
                    print("\nNo se realizaron cambios."); time.sleep(1.5)
                    return False, {}
            
            elif choice == 7 or choice is None: # Cancelar
                print("\nCambios descartados."); time.sleep(1.5); return False, {}

        except UserInputCancelled:
            print("\n\nEdición cancelada."); time.sleep(1)