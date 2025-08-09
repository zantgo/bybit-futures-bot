# Contenido completo y unificado para: core/menu/screens/_session_config_editor.py

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
    
    # --- INICIO DE LA MODIFICACIÓN: Copiamos también los valores de promediación ---
    # Los tratamos como parte de la configuración de sesión para poder editarlos en caliente.
    # --- COMENTADO SEGÚN SOLICITUD: La lógica del "código nuevo" no incluye esta sección ---
    # if "RISK" not in temp_session_config:
    #     temp_session_config["RISK"] = {}
    
    # # Si los valores existen en OPERATION_DEFAULTS, los usamos como base
    # op_defaults = getattr(config_module, 'OPERATION_DEFAULTS', {})
    # risk_defaults = op_defaults.get('RISK', {})
    # temp_session_config["RISK"]["AVERAGING_DISTANCE_PCT_LONG"] = risk_defaults.get("AVERAGING_DISTANCE_PCT_LONG", 0.5)
    # temp_session_config["RISK"]["AVERAGING_DISTANCE_PCT_SHORT"] = risk_defaults.get("AVERAGING_DISTANCE_PCT_SHORT", 0.5)
    # --- FIN DE LA MODIFICACIÓN ---

    changes_made, changed_keys = _show_main_config_menu(temp_session_config)

    if changes_made:
        # Aplicamos los cambios tanto a SESSION_CONFIG como a OPERATION_DEFAULTS para mantener la consistencia
        _apply_changes_to_real_config(temp_session_config, config_module.SESSION_CONFIG, logger)
        
        # --- COMENTADO SEGÚN SOLICITUD: El "código nuevo" no aplica cambios a RISK/OPERATION_DEFAULTS ---
        # if "RISK" in temp_session_config:
        #      _apply_changes_to_real_config({"RISK": temp_session_config["RISK"]}, op_defaults, logger)

        return changed_keys
    
    return {}

def _apply_changes_to_real_config(temp_cfg: Dict, real_cfg: Dict, logger: Any):
    if not logger: return
    # Se mantiene la lógica de logging del código original, que es más completa.
    logger.log("Aplicando cambios de configuración...", "WARN")
    
    for category, params in temp_cfg.items():
        if category not in real_cfg:
            real_cfg[category] = {} # Asegurarse de que la categoría exista
        if isinstance(params, dict):
            for key, new_value in params.items():
                if key in real_cfg.get(category, {}) and new_value != real_cfg[category][key]:
                    logger.log(f"  -> {category}.{key}: '{real_cfg[category][key]}' -> '{new_value}'", "WARN")
                    real_cfg[category][key] = new_value
        else:
            new_value = params 
            if new_value != real_cfg.get(category): # Usamos .get() para más seguridad como en el código nuevo
                logger.log(f"  -> {category}: '{real_cfg.get(category)}' -> '{new_value}'", "WARN")
                real_cfg[category] = new_value

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
            "Margen Compra (%)": temp_cfg['SIGNAL']['PRICE_CHANGE_BUY_PERCENTAGE'],
            "Margen Venta (%)": temp_cfg['SIGNAL']['PRICE_CHANGE_SELL_PERCENTAGE'],
            "Umbral Decremento": temp_cfg['SIGNAL']['WEIGHTED_DECREMENT_THRESHOLD'],
            "Umbral Incremento": temp_cfg['SIGNAL']['WEIGHTED_INCREMENT_THRESHOLD'],
        },
        # --- COMENTADO SEGÚN SOLICITUD: La sección "Riesgo y Promediación" no se muestra en el "código nuevo" ---
        # "Riesgo y Promediación": {
        #     "Distancia Prom. LONG (%)": temp_cfg.get('RISK', {}).get('AVERAGING_DISTANCE_PCT_LONG', 'N/A'),
        #     "Distancia Prom. SHORT (%)": temp_cfg.get('RISK', {}).get('AVERAGING_DISTANCE_PCT_SHORT', 'N/A'),
        # },
        "Gestión de Profit": {
            "Tarifa Comisión (%)": f"{temp_cfg['PROFIT']['COMMISSION_RATE'] * 100:.3f}",
            "Porcentaje Reinversión Ganancias": temp_cfg['PROFIT']['REINVEST_PROFIT_PCT'],
            "Monto Mín. Transferencia": f"${temp_cfg['PROFIT']['MIN_TRANSFER_AMOUNT_USDT']:.4f}",
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
        
        for label, value in params.items():
            content = f"{label:<{max_key_len}} : {value}"
            print(_create_config_box_line(content, box_width))
        
        first_section = False

    print("└" + "─" * (box_width - 2) + "┘")


def _show_main_config_menu(temp_cfg: Dict) -> tuple[bool, Dict]:
    """Muestra el menú principal agrupado y gestiona la navegación a submenús."""
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
            # --- COMENTADO SEGÚN SOLICITUD: El "código nuevo" elimina esta opción del menú ---
            # "[4] Editar Parámetros de Riesgo y Promediación",
            "[4] Editar Parámetros de Profit", # <-- Re-numerado de 5 a 4
            None,
            "[s] Guardar Cambios y Volver",
            "[c] Cancelar (Descartar Cambios)"
        ]
        
        menu_options = MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu = TerminalMenu(menu_items, title="\nSelecciona una categoría para editar:", **menu_options)
        
        choice = menu.show()

        try:
            # --- LÓGICA DE MENÚ AJUSTADA a la numeración del "código nuevo" ---
            if choice == 0:
                original = temp_cfg['TICKER_INTERVAL_SECONDS']
                new_val = get_input("\nNuevo Intervalo (s)", float, original, min_val=0.1)
                if new_val != original: changed_keys['TICKER_INTERVAL_SECONDS'] = temp_cfg['TICKER_INTERVAL_SECONDS'] = new_val
            
            elif choice == 1:
                _edit_ta_submenu(temp_cfg['TA'], changed_keys)
            
            elif choice == 2:
                _edit_signal_submenu(temp_cfg['SIGNAL'], changed_keys)

            # --- COMENTADO SEGÚN SOLICITUD: El "código nuevo" no tiene lógica para esta opción ---
            # elif choice == 3:
            #     _edit_risk_submenu(temp_cfg['RISK'], changed_keys)
            
            elif choice == 3: # <-- Re-numerado de 4 a 3
                _edit_profit_submenu(temp_cfg['PROFIT'], changed_keys)
            
            elif choice == 5: # <-- Re-numerado de 6 a 5
                if changed_keys:
                    print("\nCambios guardados."); time.sleep(2)
                    return True, changed_keys
                else:
                    print("\nNo se realizaron cambios."); time.sleep(1.5)
                    return False, {}
            
            elif choice == 6 or choice is None: # <-- Re-numerado de 7 a 6
                if changed_keys:
                    if TerminalMenu(["[1] Sí, descartar cambios", "[2] No, seguir editando"], title="\nDescartar cambios no guardados?").show() == 0:
                        print("\nCambios descartados."); time.sleep(1.5)
                        return False, {}
                else:
                    print("\nAsistente cancelado."); time.sleep(1.5)
                    return False, {}

        except UserInputCancelled:
            print("\n\nEdición cancelada."); time.sleep(1)

# --- Submenús de edición ---
def _edit_ta_submenu(ta_cfg: Dict, changed_keys: Dict):
    while True:
        menu_items = [
            f"[1] Período EMA ({ta_cfg['EMA_WINDOW']})",
            f"[2] Período W.Inc ({ta_cfg['WEIGHTED_INC_WINDOW']})",
            f"[3] Período W.Dec ({ta_cfg['WEIGHTED_DEC_WINDOW']})",
            None,
            "[b] Volver"
        ]
        submenu = TerminalMenu(menu_items, title="\nEditando Parámetros de TA:", **MENU_STYLE).show()
        if submenu == 0:
            original = ta_cfg['EMA_WINDOW']
            new_val = get_input("Nuevo Período EMA", int, original, min_val=1)
            if new_val != original: changed_keys['EMA_WINDOW'] = ta_cfg['EMA_WINDOW'] = new_val
        elif submenu == 1:
            original = ta_cfg['WEIGHTED_INC_WINDOW']
            new_val = get_input("Nuevo Período W.Inc", int, original, min_val=1)
            if new_val != original: changed_keys['WEIGHTED_INC_WINDOW'] = ta_cfg['WEIGHTED_INC_WINDOW'] = new_val
        elif submenu == 2:
            original = ta_cfg['WEIGHTED_DEC_WINDOW']
            new_val = get_input("Nuevo Período W.Dec", int, original, min_val=1)
            if new_val != original: changed_keys['WEIGHTED_DEC_WINDOW'] = ta_cfg['WEIGHTED_DEC_WINDOW'] = new_val
        else:
            break

def _edit_signal_submenu(signal_cfg: Dict, changed_keys: Dict):
    while True:
        menu_items = [
            f"[1] Margen Compra (%) ({signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE']})",
            f"[2] Margen Venta (%) ({signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE']})",
            f"[3] Umbral Decremento ({signal_cfg['WEIGHTED_DECREMENT_THRESHOLD']})",
            f"[4] Umbral Incremento ({signal_cfg['WEIGHTED_INCREMENT_THRESHOLD']})",
            None,
            "[b] Volver"
        ]
        submenu = TerminalMenu(menu_items, title="\nEditando Parámetros de Señal:", **MENU_STYLE).show()
        if submenu == 0:
            original = signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE']
            new_val = get_input("Nuevo Margen Compra (%)", float, original)
            if new_val != original: changed_keys['PRICE_CHANGE_BUY_PERCENTAGE'] = signal_cfg['PRICE_CHANGE_BUY_PERCENTAGE'] = new_val
        elif submenu == 1:
            original = signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE']
            new_val = get_input("Nuevo Margen Venta (%)", float, original)
            if new_val != original: changed_keys['PRICE_CHANGE_SELL_PERCENTAGE'] = signal_cfg['PRICE_CHANGE_SELL_PERCENTAGE'] = new_val
        elif submenu == 2:
            original = signal_cfg['WEIGHTED_DECREMENT_THRESHOLD']
            new_val = get_input("Nuevo Umbral Decremento (0-1)", float, original)
            if new_val != original: changed_keys['WEIGHTED_DECREMENT_THRESHOLD'] = signal_cfg['WEIGHTED_DECREMENT_THRESHOLD'] = new_val
        elif submenu == 3:
            original = signal_cfg['WEIGHTED_INCREMENT_THRESHOLD']
            new_val = get_input("Nuevo Umbral Incremento (0-1)", float, original)
            if new_val != original: changed_keys['WEIGHTED_INCREMENT_THRESHOLD'] = signal_cfg['WEIGHTED_INCREMENT_THRESHOLD'] = new_val
        else:
            break

# --- COMENTADO SEGÚN SOLICITUD: La función _edit_risk_submenu no existe en el "código nuevo" ---
# # --- INICIO DE LA MODIFICACIÓN: Nuevo submenú para Riesgo y Promediación ---
# def _edit_risk_submenu(risk_cfg: Dict, changed_keys: Dict):
#     """Submenú para editar los parámetros de riesgo y promediación."""
#     while True:
#         menu_items = [
#             f"[1] Distancia Prom. LONG (%) ({risk_cfg['AVERAGING_DISTANCE_PCT_LONG']})",
#             f"[2] Distancia Prom. SHORT (%) ({risk_cfg['AVERAGING_DISTANCE_PCT_SHORT']})",
#             None,
#             "[b] Volver"
#         ]
#         submenu = TerminalMenu(menu_items, title="\nEditando Parámetros de Riesgo:", **MENU_STYLE).show()
        
#         if submenu == 0:
#             original = risk_cfg['AVERAGING_DISTANCE_PCT_LONG']
#             new_val = get_input("Nueva Distancia de Promediación para LONG (%)", float, original, min_val=0.0)
#             if new_val != original:
#                 changed_keys['AVERAGING_DISTANCE_PCT_LONG'] = risk_cfg['AVERAGING_DISTANCE_PCT_LONG'] = new_val
#         elif submenu == 1:
#             original = risk_cfg['AVERAGING_DISTANCE_PCT_SHORT']
#             new_val = get_input("Nueva Distancia de Promediación para SHORT (%)", float, original, min_val=0.0)
#             if new_val != original:
#                 changed_keys['AVERAGING_DISTANCE_PCT_SHORT'] = risk_cfg['AVERAGING_DISTANCE_PCT_SHORT'] = new_val
#         else:
#             break
# # --- FIN DE LA MODIFICACIÓN ---

def _edit_profit_submenu(profit_cfg: Dict, changed_keys: Dict):
    while True:
        menu_items = [
            f"[1] Tarifa Comisión (%) ({profit_cfg['COMMISSION_RATE'] * 100:.3f})",
            f"[2] Porcentaje Reinversión Ganancias ({profit_cfg['REINVEST_PROFIT_PCT']})",
            f"[3] Monto Mín. Transferencia (${profit_cfg['MIN_TRANSFER_AMOUNT_USDT']:.4f})",
            None,
            "[b] Volver"
        ]
        submenu = TerminalMenu(menu_items, title="\nEditando Parámetros de Profit:", **MENU_STYLE).show()
        if submenu == 0:
            original = profit_cfg['COMMISSION_RATE']
            new_val = get_input("Nueva Tarifa Comisión (%)", float, original * 100, min_val=0.0)
            if new_val / 100 != original: changed_keys['COMMISSION_RATE'] = profit_cfg['COMMISSION_RATE'] = new_val / 100
        elif submenu == 1:
            original = profit_cfg['REINVEST_PROFIT_PCT']
            new_val = get_input("Porcentaje Reinversión de Ganancias", float, original, min_val=0.0, max_val=100.0)
            if new_val != original: changed_keys['REINVEST_PROFIT_PCT'] = profit_cfg['REINVEST_PROFIT_PCT'] = new_val
        elif submenu == 2:
            original = profit_cfg['MIN_TRANSFER_AMOUNT_USDT']
            new_val = get_input("Monto Mín. de Transferencia (USDT)", float, original, min_val=0.0)
            if new_val != original: changed_keys['MIN_TRANSFER_AMOUNT_USDT'] = profit_cfg['MIN_TRANSFER_AMOUNT_USDT'] = new_val
        else:
            break