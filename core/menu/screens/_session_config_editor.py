# core/menu/screens/_session_config_editor.py

"""
Módulo para la Pantalla de Edición de Configuración de la Sesión.
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

def _create_config_box_line(content: str, width: int, is_header=False) -> str:
    """Crea una línea de caja de configuración con el contenido alineado."""
    clean_content = _clean_ansi_codes(content)
    
    if is_header:
        padding_total = width - len(clean_content) - 4
        left_pad = padding_total // 2
        right_pad = padding_total - left_pad
        return f"│{'─' * left_pad} \033[96m{content}\033[0m {'─' * right_pad}│"

    padding_needed = width - len(clean_content) - 4
    return f"│ {content}{' ' * padding_needed} │"

# --- Lógica Principal del Módulo ---

def show_session_config_editor_screen(config_module: Any) -> Dict[str, Any]:
    logger = _deps.get("memory_logger_module")
    if not TerminalMenu:
        if logger: logger.log("Error: 'simple-term-menu' no está instalado.", level="ERROR")
        return {}

    temp_session_config = copy.deepcopy(config_module.SESSION_CONFIG)
    
    if 'RISK' not in temp_session_config:
        temp_session_config['RISK'] = {
            "MAINTENANCE_MARGIN_RATE": config_module.PRECISION_FALLBACKS.get("MAINTENANCE_MARGIN_RATE", 0.005)
        }

    changes_made, changed_keys = _show_main_config_menu(temp_session_config)

    if changes_made:
        _apply_changes_to_real_config(temp_session_config, config_module.SESSION_CONFIG, logger)
        
        if 'RISK' in temp_session_config and 'MAINTENANCE_MARGIN_RATE' in temp_session_config['RISK']:
             new_mmr = temp_session_config['RISK']['MAINTENANCE_MARGIN_RATE']
             if new_mmr != config_module.PRECISION_FALLBACKS['MAINTENANCE_MARGIN_RATE']:
                 if logger:
                    logger.log(f"  -> Global PRECISION_FALLBACKS.MAINTENANCE_MARGIN_RATE: '{config_module.PRECISION_FALLBACKS['MAINTENANCE_MARGIN_RATE']}' -> '{new_mmr}'", "WARN")
                 config_module.PRECISION_FALLBACKS['MAINTENANCE_MARGIN_RATE'] = new_mmr

        return changed_keys
    
    return {}

def _apply_changes_to_real_config(temp_cfg: Dict, real_cfg: Dict, logger: Any):
    if not logger: return
    logger.log("Aplicando cambios de configuración...", "WARN")
    
    for category, params in temp_cfg.items():
        if category not in real_cfg:
            real_cfg[category] = {} 
        if isinstance(params, dict):
            if not isinstance(real_cfg.get(category), dict):
                real_cfg[category] = {}

            for key, new_value in params.items():
                if new_value != real_cfg[category].get(key):
                    logger.log(f"  -> {category}.{key}: '{real_cfg[category].get(key)}' -> '{new_value}'", "WARN")
                    real_cfg[category][key] = new_value
        else:
            new_value = params 
            if new_value != real_cfg.get(category):
                logger.log(f"  -> {category}: '{real_cfg.get(category)}' -> '{new_value}'", "WARN")
                real_cfg[category] = new_value

def _show_main_config_menu(temp_cfg: Dict) -> tuple[bool, Dict]:
    """Muestra el menú principal agrupado y gestiona la navegación a submenús."""
    from .._helpers import show_help_popup
    changed_keys = {}

    while True:
        clear_screen()
        
        print_tui_header("Editor de Configuración de Sesión")
        
        box_width = min(_get_terminal_width() - 2, 90)
        _display_config_box(temp_cfg, box_width)

        menu_items = [
            "[1] Editar Parámetros de Ticker",
            "[2] Editar Parámetros de Análisis Técnico (TA)",
            "[3] Editar Parámetros de Señal",
            "[4] Editar Parámetros de Profit",
            "[5] Editar Parámetros de Riesgo",
            None,
            "[h] Ayuda",
            "[s] Guardar Cambios y Volver",
            "[c] Cancelar (Descartar Cambios)"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nSelecciona una categoría para editar:", **menu_options)
        
        choice = menu.show()

        try:
            if choice == 0:
                original = temp_cfg['TICKER_INTERVAL_SECONDS']
                new_val = get_input("\nNuevo Intervalo (s)", float, original, min_val=0.1)
                if new_val != original: changed_keys['TICKER_INTERVAL_SECONDS'] = temp_cfg['TICKER_INTERVAL_SECONDS'] = new_val
            
            elif choice == 1:
                if _edit_ta_submenu(temp_cfg['TA'], changed_keys):
                    changed_keys['TA'] = True # Marcar que la categoría cambió
            
            elif choice == 2:
                if _edit_signal_submenu(temp_cfg['SIGNAL'], changed_keys):
                    changed_keys['SIGNAL'] = True

            elif choice == 3: 
                if _edit_profit_submenu(temp_cfg['PROFIT'], changed_keys):
                    changed_keys['PROFIT'] = True
            
            elif choice == 4:
                if 'RISK' not in temp_cfg: temp_cfg['RISK'] = {}
                if _edit_risk_submenu(temp_cfg['RISK'], changed_keys):
                    changed_keys['RISK'] = True
            
            elif choice == 6: # Índice de Ayuda
                show_help_popup('session_config_editor')

            elif choice == 7: # Índice de Guardar
                if changed_keys:
                    print("\nCambios guardados."); time.sleep(2)
                    return True, changed_keys
                else:
                    print("\nNo se realizaron cambios."); time.sleep(1.5)
                    return False, {}
            
            elif choice == 8 or choice is None: # Índice de Cancelar
                if changed_keys:
                    confirm_options = MENU_STYLE.copy()
                    confirm_options['clear_screen'] = True
                    if TerminalMenu(["[1] Sí, descartar cambios", "[2] No, seguir editando"], title="\nDescartar cambios no guardados?", **confirm_options).show() == 0:
                        print("\nCambios descartados."); time.sleep(1.5)
                        return False, {}
                else:
                    print("\nAsistente cancelado."); time.sleep(1.5)
                    return False, {}

        except UserInputCancelled:
            print("\n\nEdición cancelada."); time.sleep(1)
            
# --- Submenús de edición ---
def _edit_ta_submenu(ta_cfg: Dict, changed_keys: Dict) -> bool:
    changes_in_submenu = False
    while True:
        menu_items = [
            f"[1] Período EMA ({ta_cfg['EMA_WINDOW']})",
            f"[2] Período W.Inc ({ta_cfg['WEIGHTED_INC_WINDOW']})",
            f"[3] Período W.Dec ({ta_cfg['WEIGHTED_DEC_WINDOW']})",
            None,
            "[b] Volver"
        ]
        # Los submenús no deben limpiar la pantalla, ya que el bucle principal lo hace
        submenu_options = MENU_STYLE.copy()
        submenu_options['clear_screen'] = False
        submenu = TerminalMenu(menu_items, title="\nEditando Parámetros de TA:", **submenu_options).show()
        if submenu == 0:
            original = ta_cfg['EMA_WINDOW']
            new_val = get_input("Nuevo Período EMA", int, original, min_val=1)
            if new_val != original: 
                changed_keys['EMA_WINDOW'] = ta_cfg['EMA_WINDOW'] = new_val
                changes_in_submenu = True
        elif submenu == 1:
            original = ta_cfg['WEIGHTED_INC_WINDOW']
            new_val = get_input("Nuevo Período W.Inc", int, original, min_val=1)
            if new_val != original: 
                changed_keys['WEIGHTED_INC_WINDOW'] = ta_cfg['WEIGHTED_INC_WINDOW'] = new_val
                changes_in_submenu = True
        elif submenu == 2:
            original = ta_cfg['WEIGHTED_DEC_WINDOW']
            new_val = get_input("Nuevo Período W.Dec", int, original, min_val=1)
            if new_val != original: 
                changed_keys['WEIGHTED_DEC_WINDOW'] = ta_cfg['WEIGHTED_DEC_WINDOW'] = new_val
                changes_in_submenu = True
        else:
            break
    return changes_in_submenu

def _edit_profit_submenu(profit_cfg: Dict, changed_keys: Dict) -> bool:
    changes_in_submenu = False
    while True:
        menu_items = [
            f"[1] Tarifa Comisión (%) ({profit_cfg['COMMISSION_RATE'] * 100:.3f})",
            f"[2] Porcentaje Reinversión Ganancias ({profit_cfg['REINVEST_PROFIT_PCT']})",
            f"[3] Monto Mín. Transferencia (${profit_cfg['MIN_TRANSFER_AMOUNT_USDT']:.4f})",
            f"[4] Slippage Estimado (%) ({profit_cfg.get('SLIPPAGE_PCT', 0.0) * 100:.3f})",
            None,
            "[b] Volver"
        ]
        submenu_options = MENU_STYLE.copy()
        submenu_options['clear_screen'] = False
        submenu = TerminalMenu(menu_items, title="\nEditando Parámetros de Profit:", **submenu_options).show()
        if submenu == 0:
            original = profit_cfg['COMMISSION_RATE']
            new_val = get_input("Nueva Tarifa Comisión (%)", float, original * 100, min_val=0.0)
            if new_val / 100 != original: 
                changed_keys['COMMISSION_RATE'] = profit_cfg['COMMISSION_RATE'] = new_val / 100
                changes_in_submenu = True
        elif submenu == 1:
            original = profit_cfg['REINVEST_PROFIT_PCT']
            new_val = get_input("Porcentaje Reinversión de Ganancias", float, original, min_val=0.0, max_val=100.0)
            if new_val != original: 
                changed_keys['REINVEST_PROFIT_PCT'] = profit_cfg['REINVEST_PROFIT_PCT'] = new_val
                changes_in_submenu = True
        elif submenu == 2:
            original = profit_cfg['MIN_TRANSFER_AMOUNT_USDT']
            new_val = get_input("Monto Mín. de Transferencia (USDT)", float, original, min_val=0.0)
            if new_val != original: 
                changed_keys['MIN_TRANSFER_AMOUNT_USDT'] = profit_cfg['MIN_TRANSFER_AMOUNT_USDT'] = new_val
                changes_in_submenu = True
        elif submenu == 3:
            original = profit_cfg.get('SLIPPAGE_PCT', 0.0)
            new_val = get_input("Nuevo Slippage Estimado (%)", float, original * 100, min_val=0.0)
            if new_val / 100 != original: 
                changed_keys['SLIPPAGE_PCT'] = profit_cfg['SLIPPAGE_PCT'] = new_val / 100
                changes_in_submenu = True
        else:
            break
    return changes_in_submenu

def _edit_risk_submenu(risk_cfg: Dict, changed_keys: Dict) -> bool:
    """Submenú específico para editar los parámetros de riesgo de la sesión."""
    changes_in_submenu = False
    while True:
        current_mmr_pct = risk_cfg.get('MAINTENANCE_MARGIN_RATE', 0.0) * 100
        current_max_failures = risk_cfg.get('MAX_SYNC_FAILURES', 100)
        
        menu_items = [
            f"[1] Tasa Margen Mantenimiento (%) ({current_mmr_pct:.3f})",
            f"[2] Máx. Reintentos Sincronización ({current_max_failures})",
            None,
            "[b] Volver"
        ]
        
        submenu_options = MENU_STYLE.copy()
        submenu_options['clear_screen'] = False
        submenu = TerminalMenu(menu_items, title="\nEditando Parámetros de Riesgo:", **submenu_options).show()
        
        if submenu == 0:
            original_pct = current_mmr_pct
            new_val_pct = get_input("Nueva Tasa de Margen de Mantenimiento (%)", float, original_pct, min_val=0.1)
            
            new_val_decimal = new_val_pct / 100.0
            
            if new_val_decimal != risk_cfg.get('MAINTENANCE_MARGIN_RATE'):
                changed_keys['MAINTENANCE_MARGIN_RATE'] = risk_cfg['MAINTENANCE_MARGIN_RATE'] = new_val_decimal
                changes_in_submenu = True
                
        elif submenu == 1:
            original_val = current_max_failures
            new_val = get_input("Nuevo número de reintentos de sincronización", int, original_val, min_val=1)
            if new_val != original_val:
                changed_keys['MAX_SYNC_FAILURES'] = risk_cfg['MAX_SYNC_FAILURES'] = new_val
                changes_in_submenu = True

        else:
            break
    return changes_in_submenu

def _display_config_box(temp_cfg: Dict, box_width: int):
    """Muestra la caja de configuración con formato y alineación adaptativos."""
    print("\nValores Actuales:")
    print("┌" + "─" * (box_width - 2) + "┐")

    sections = {
        "Ticker": {
            "Ticker Intervalo (s)": temp_cfg['TICKER_INTERVAL_SECONDS'],
        },
        "Análisis Técnico": {
            "Período EMA": temp_cfg['TA']['EMA_WINDOW'],
            "Período W.Inc": temp_cfg['TA']['WEIGHTED_INC_WINDOW'],
            "Período W.Dec": temp_cfg['TA']['WEIGHTED_DEC_WINDOW'],
        },
        "Generación de Señal": {
            "Umbral Caída para Comprar (%)": temp_cfg['SIGNAL']['PRICE_CHANGE_BUY_PERCENTAGE'],
            "Umbral Subida para Vender (%)": temp_cfg['SIGNAL']['PRICE_CHANGE_SELL_PERCENTAGE'],
            "Umbral Decremento": temp_cfg['SIGNAL']['WEIGHTED_DECREMENT_THRESHOLD'],
            "Umbral Incremento": temp_cfg['SIGNAL']['WEIGHTED_INCREMENT_THRESHOLD'],
        },
        "Gestión de Profit": {
            "Tarifa Comisión (%)": f"{temp_cfg['PROFIT']['COMMISSION_RATE'] * 100:.3f}",
            "Porcentaje Reinversión Ganancias": temp_cfg['PROFIT']['REINVEST_PROFIT_PCT'],
            "Monto Mín. Transferencia": f"${temp_cfg['PROFIT']['MIN_TRANSFER_AMOUNT_USDT']:.4f}",
            "Slippage Estimado (%)": f"{temp_cfg['PROFIT'].get('SLIPPAGE_PCT', 0.0) * 100:.2f}",
        },
        "Gestión de Riesgo": {
            "Tasa Margen Mantenimiento (%)": f"{temp_cfg.get('RISK', {}).get('MAINTENANCE_MARGIN_RATE', 0.0) * 100:.3f}",
            "Máx. Reintentos Sincronización": temp_cfg.get('RISK', {}).get('MAX_SYNC_FAILURES', 100),
        }
    }
    
    all_labels = []
    for section_params in sections.values():
        all_labels.extend(section_params.keys())
    max_key_len = max(len(label) for label in all_labels) if all_labels else 0

    first_section = True
    for title, params in sections.items():
        if not first_section:
            print("├" + "─" * (box_width - 2) + "┤")
        
        print(_create_config_box_line(title, box_width, is_header=True))
        
        for label, value in params.items():
            content = f"{label:<{max_key_len}} : {value}"
            print(_create_config_box_line(content, box_width))
        
        first_section = False

    print("└" + "─" * (box_width - 2) + "┘")

def _edit_signal_submenu(signal_cfg: Dict, changed_keys: Dict) -> bool:
    changes_in_submenu = False
    while True:
        menu_items = [
            f"[1] Umbral Caída para Comprar (%) ({signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE']})",
            f"[2] Umbral Subida para Vender (%) ({signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE']})",
            f"[3] Umbral Decremento ({signal_cfg['WEIGHTED_DECREMENT_THRESHOLD']})",
            f"[4] Umbral Incremento ({signal_cfg['WEIGHTED_INCREMENT_THRESHOLD']})",
            None,
            "[b] Volver"
        ]
        submenu_options = MENU_STYLE.copy()
        submenu_options['clear_screen'] = False
        submenu = TerminalMenu(menu_items, title="\nEditando Parámetros de Señal:", **submenu_options).show()
        if submenu == 0:
            original = signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE']
            new_val = get_input("Nuevo Umbral Caída para Comprar (%)", float, original)
            if new_val != original: 
                changed_keys['PRICE_CHANGE_BUY_PERCENTAGE'] = signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE'] = new_val
                changes_in_submenu = True
        elif submenu == 1:
            original = signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE']
            new_val = get_input("Nuevo Umbral Subida para Vender (%)", float, original)
            if new_val != original: 
                changed_keys['PRICE_CHANGE_SELL_PERCENTAGE'] = signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE'] = new_val
                changes_in_submenu = True
        elif submenu == 2:
            original = signal_cfg['WEIGHTED_DECREMENT_THRESHOLD']
            new_val = get_input("Nuevo Umbral Decremento (0-1)", float, original)
            if new_val != original: 
                changed_keys['WEIGHTED_DECREMENT_THRESHOLD'] = signal_cfg['WEIGHTED_DECREMENT_THRESHOLD'] = new_val
                changes_in_submenu = True
        elif submenu == 3:
            original = signal_cfg['WEIGHTED_INCREMENT_THRESHOLD']
            new_val = get_input("Nuevo Umbral Incremento (0-1)", float, original)
            if new_val != original: 
                changed_keys['WEIGHTED_INCREMENT_THRESHOLD'] = signal_cfg['WEIGHTED_INCREMENT_THRESHOLD'] = new_val
                changes_in_submenu = True
        else:
            break
    return changes_in_submenu
