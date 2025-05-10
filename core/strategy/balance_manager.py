# =============== INICIO ARCHIVO: core/strategy/balance_manager.py (v8.7.x - Corregida Lógica Transferencia PNL) ===============
"""
Módulo dedicado a gestionar los balances LÓGICOS de las cuentas
(Long Margin, Short Margin, Profit Balance) durante el backtesting y live.

v8.7.x - Corregida Lógica Transferencia PNL: Las transferencias de PNL a la cuenta de profit
                                           ya no reducen el capital operativo total del lado (_operational_margin).
                                           El margen operativo total solo cambia con la inicialización o ajuste de slots.
v8.7.x - Corregido: Asegura que en modo Live, los márgenes operativos lógicos iniciales
                 se basen en el balance real disponible (UTA Wallet o Available) de las
                 cuentas correspondientes, si no se especifica un capital operativo menor
                 mediante base_position_size_usdt * initial_max_logical_positions.
v8.7.x - Final: Corregida simulate_profit_transfer para deducir del margen operativo
                 y añadida record_real_profit_transfer_logically para modo Live.
v8.7.x: Modificada la inicialización para usar tamaño base por posición y número inicial de slots.
v8.5.8: Guarda correctamente los márgenes lógicos iniciales para get_initial_total_capital.
"""
import sys
import os
import traceback
from typing import Optional, Dict, Any

# Importar config y utils de forma segura
try:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path: sys.path.insert(0, project_root)
    import config
    from core import utils
except ImportError as e:
    print(f"ERROR CRÍTICO [Balance Manager Import]: No se pudo importar core.config o core.utils: {e}")
    config_attrs = {
        'POSITION_MANAGEMENT_ENABLED': False, 'POSITION_TRADING_MODE': 'N/A',
        'POSITION_BASE_SIZE_USDT': 10.0,
        'POSITION_MAX_LOGICAL_POSITIONS': 1,
        'ACCOUNT_LONGS': 'longs', 'ACCOUNT_SHORTS': 'shorts',
        'ACCOUNT_PROFIT': 'profit', 'ACCOUNT_MAIN': 'main',
        'POSITION_PRINT_POSITION_UPDATES': False
    }
    config = type('obj', (object,), config_attrs)()
    utils = type('obj', (object,), {
        'safe_float_convert': lambda v, default=0.0: float(v) if v is not None and str(v).strip() != '' else default,
    })()
except Exception as e_imp:
     print(f"ERROR CRÍTICO inesperado durante importación en balance_manager: {e_imp}")
     traceback.print_exc()
     config = type('obj', (object,), {'POSITION_MANAGEMENT_ENABLED': False})()
     utils = None

# --- Estado del Módulo ---
_initialized: bool = False
_default_base_position_size_usdt_config: float = 0.0
_default_initial_max_logical_positions_config: int = 1
_trading_mode_config: str = "N/A"
_operation_mode: str = "unknown"

_operational_long_margin: float = 0.0  # Capital TOTAL asignado a LONG
_operational_short_margin: float = 0.0 # Capital TOTAL asignado a SHORT
_used_long_margin: float = 0.0         # Capital de _operational_long_margin actualmente USADO en posiciones
_used_short_margin: float = 0.0        # Capital de _operational_short_margin actualmente USADO en posiciones
_profit_balance: float = 0.0           # Balance de la cuenta de Profit

_initial_operational_long_margin: float = 0.0  # Para cálculo de ROI y referencia
_initial_operational_short_margin: float = 0.0 # Para cálculo de ROI y referencia
_initial_profit_balance: float = 0.0           # Para referencia
_initial_base_position_size_usdt_session: float = 0.0 # Para recalcular Op. Margins al cambiar slots

# --- Funciones Públicas ---
def initialize(
    operation_mode: str,
    real_balances_data: Optional[Dict[str, Dict[str, Any]]] = None,
    base_position_size_usdt: Optional[float] = None,
    initial_max_logical_positions: Optional[int] = None
):
    global _initialized, _default_base_position_size_usdt_config, _default_initial_max_logical_positions_config
    global _trading_mode_config, _operation_mode
    global _operational_long_margin, _operational_short_margin, _profit_balance
    global _initial_operational_long_margin, _initial_operational_short_margin, _initial_profit_balance
    global _used_long_margin, _used_short_margin
    global _initial_base_position_size_usdt_session

    if not config or not utils or not hasattr(utils, 'safe_float_convert'):
        print("ERROR CRITICO [BM Init]: Faltan dependencias core (config/utils)."); _initialized = False; return
    if not getattr(config, 'POSITION_MANAGEMENT_ENABLED', False):
        print("[Balance Manager] Inicialización omitida (Gestión Desactivada globalmente)."); _initialized = False; return

    print("[Balance Manager] Inicializando balances lógicos (Lógica Tamaño Base y Slots)...")
    _initialized = False
    _operation_mode = operation_mode
    _operational_long_margin, _operational_short_margin, _profit_balance = 0.0, 0.0, 0.0
    _initial_operational_long_margin, _initial_operational_short_margin, _initial_profit_balance = 0.0, 0.0, 0.0
    _used_long_margin, _used_short_margin = 0.0, 0.0

    try:
        _default_base_position_size_usdt_config = max(0.0, utils.safe_float_convert(getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0)))
        _default_initial_max_logical_positions_config = max(1, int(getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1)))
        _trading_mode_config = getattr(config, 'POSITION_TRADING_MODE', 'LONG_SHORT')
    except Exception as e_cfg_read:
        print(f"ERROR CRITICO [BM Init]: Leyendo config: {e_cfg_read}"); traceback.print_exc(); return

    current_base_size = base_position_size_usdt if base_position_size_usdt is not None and base_position_size_usdt > 0 else _default_base_position_size_usdt_config
    current_slots = initial_max_logical_positions if initial_max_logical_positions is not None and initial_max_logical_positions >= 1 else _default_initial_max_logical_positions_config

    _initial_base_position_size_usdt_session = current_base_size

    print(f"  Usando Tamaño Base por Posición para la sesión: {current_base_size:.4f} USDT")
    print(f"  Usando Número Inicial de Slots por Lado para la sesión: {current_slots}")

    is_live = _operation_mode.startswith("live")

    if is_live:
        if not real_balances_data:
            print("ERROR CRITICO [BM Init]: Modo Live pero no se proporcionaron datos de balances reales."); return

        print("  Modo Live: Estableciendo márgenes lógicos iniciales...")
        profit_acc_name = getattr(config, 'ACCOUNT_PROFIT', None)
        long_acc_name_cfg = getattr(config, 'ACCOUNT_LONGS', None)
        short_acc_name_cfg = getattr(config, 'ACCOUNT_SHORTS', None)
        main_acc_name_cfg = getattr(config, 'ACCOUNT_MAIN', 'main')

        real_profit_balance_api = 0.0
        real_operational_long_margin_api = 0.0
        real_operational_short_margin_api = 0.0

        try:
            if profit_acc_name and profit_acc_name in real_balances_data:
                unified_prof = real_balances_data[profit_acc_name].get('unified_balance')
                funding_prof = real_balances_data[profit_acc_name].get('funding_balance')
                uta_profit_avail = utils.safe_float_convert(unified_prof.get('totalAvailableBalance'), 0.0) if unified_prof else 0.0
                fund_profit_wallet = utils.safe_float_convert(funding_prof.get('USDT', {}).get('walletBalance'), 0.0) if funding_prof else 0.0
                real_profit_balance_api = uta_profit_avail + fund_profit_wallet
            elif profit_acc_name: print(f"    WARN: No hay datos API para cuenta profit '{profit_acc_name}' al inicializar balance de profit.")
        except Exception as e_read_profit_api:
            print(f"ERROR [BM Init]: Leyendo balance de profit real: {e_read_profit_api}");

        target_long_acc_name = long_acc_name_cfg if long_acc_name_cfg else main_acc_name_cfg
        if target_long_acc_name in real_balances_data:
            unified_long_data = real_balances_data[target_long_acc_name].get('unified_balance')
            if unified_long_data:
                usdt_coin_data = next((c for c in unified_long_data.get('coin', []) if c.get('coin') == 'USDT'), None)
                if usdt_coin_data:
                    real_operational_long_margin_api = utils.safe_float_convert(usdt_coin_data.get('walletBalance'), 0.0)
                else: 
                    real_operational_long_margin_api = utils.safe_float_convert(unified_long_data.get('totalWalletBalance'), 0.0)
                print(f"    INFO: Balance Real API para Longs ('{target_long_acc_name}' USDT Wallet): {real_operational_long_margin_api:.4f} USDT")
            else:
                print(f"    WARN: No hay datos de balance unificado para la cuenta Long/Main '{target_long_acc_name}'. Margen Long API será 0.")
        else:
             print(f"    WARN: No hay datos de API para la cuenta Long/Main '{target_long_acc_name}'. Margen Long API será 0.")

        target_short_acc_name = short_acc_name_cfg if short_acc_name_cfg else main_acc_name_cfg
        if target_short_acc_name in real_balances_data:
            unified_short_data = real_balances_data[target_short_acc_name].get('unified_balance')
            if unified_short_data:
                usdt_coin_data_short = next((c for c in unified_short_data.get('coin', []) if c.get('coin') == 'USDT'), None)
                if usdt_coin_data_short:
                    real_operational_short_margin_api = utils.safe_float_convert(usdt_coin_data_short.get('walletBalance'), 0.0)
                else:
                    real_operational_short_margin_api = utils.safe_float_convert(unified_short_data.get('totalWalletBalance'), 0.0)
                print(f"    INFO: Balance Real API para Shorts ('{target_short_acc_name}' USDT Wallet): {real_operational_short_margin_api:.4f} USDT")
            else:
                print(f"    WARN: No hay datos de balance unificado para la cuenta Short/Main '{target_short_acc_name}'. Margen Short API será 0.")
        else:
            print(f"    WARN: No hay datos de API para la cuenta Short/Main '{target_short_acc_name}'. Margen Short API será 0.")

        _profit_balance = real_profit_balance_api
        _initial_profit_balance = real_profit_balance_api
        print(f"    Balance Profit Lógico Inicial (API Real): {_profit_balance:.4f} USDT")

        logical_capital_per_side_config = current_base_size * current_slots

        if _trading_mode_config == "LONG_ONLY" or _trading_mode_config == "LONG_SHORT":
            _operational_long_margin = min(logical_capital_per_side_config, real_operational_long_margin_api)
            if logical_capital_per_side_config > real_operational_long_margin_api:
                print(f"    ADVERTENCIA (Long): Capital lógico configurado ({logical_capital_per_side_config:.2f}) > real API ({real_operational_long_margin_api:.2f}). Usando real API.")
        else: 
            _operational_long_margin = 0.0

        if _trading_mode_config == "SHORT_ONLY" or _trading_mode_config == "LONG_SHORT":
            _operational_short_margin = min(logical_capital_per_side_config, real_operational_short_margin_api)
            if logical_capital_per_side_config > real_operational_short_margin_api:
                print(f"    ADVERTENCIA (Short): Capital lógico configurado ({logical_capital_per_side_config:.2f}) > real API ({real_operational_short_margin_api:.2f}). Usando real API.")
        else: 
            _operational_short_margin = 0.0

        _initial_operational_long_margin = _operational_long_margin
        _initial_operational_short_margin = _operational_short_margin

        print(f"    Margen Operativo Lógico Inicial Long (Final): {_operational_long_margin:.4f} USDT")
        print(f"    Margen Operativo Lógico Inicial Short (Final): {_operational_short_margin:.4f} USDT")

    else: # Backtest
        print(f"  Modo: {_operation_mode}. Inicializando balances LÓGICOS para backtest...")
        total_capital_per_side_logical = current_base_size * current_slots
        if _trading_mode_config == "LONG_ONLY":
             _operational_long_margin = total_capital_per_side_logical; _operational_short_margin = 0.0
        elif _trading_mode_config == "SHORT_ONLY":
             _operational_long_margin = 0.0; _operational_short_margin = total_capital_per_side_logical
        elif _trading_mode_config == "LONG_SHORT":
             _operational_long_margin = total_capital_per_side_logical; _operational_short_margin = total_capital_per_side_logical
        else:
             print(f"    WARN: Modo trading '{_trading_mode_config}' no reconocido. Aplicando a ambos lados.");
             _operational_long_margin = total_capital_per_side_logical; _operational_short_margin = total_capital_per_side_logical
        _profit_balance = 0.0
        _initial_operational_long_margin = _operational_long_margin; _initial_operational_short_margin = _operational_short_margin
        _initial_profit_balance = _profit_balance
        print(f"    Margen Operativo Lógico Inicial Long (Backtest): {_operational_long_margin:.4f} USDT")
        print(f"    Margen Operativo Lógico Inicial Short (Backtest): {_operational_short_margin:.4f} USDT")
        print(f"    Balance Profit Lógico Inicial (Backtest): {_profit_balance:.4f} USDT")

    print(f"[Balance Manager] Balances LÓGICOS inicializados -> OpLong: {_operational_long_margin:.4f}, OpShort: {_operational_short_margin:.4f}, Profit: {_profit_balance:.4f} USDT")
    print(f"  (DEBUG Iniciales Guardados: OpLong={_initial_operational_long_margin:.4f}, OpShort={_initial_operational_short_margin:.4f}, Profit={_initial_profit_balance:.4f})")
    print(f"DEBUG BM INIT FINAL: _opL={_operational_long_margin:.4f}, _usedL={_used_long_margin:.4f}, availL={get_available_margin('long'):.4f}")
    print(f"DEBUG BM INIT FINAL: _opS={_operational_short_margin:.4f}, _usedS={_used_short_margin:.4f}, availS={get_available_margin('short'):.4f}")
    _initialized = True


def get_available_margin(side: str) -> float:
    if not _initialized: return 0.0
    if side == 'long':
        return max(0.0, _operational_long_margin - _used_long_margin)
    elif side == 'short':
        return max(0.0, _operational_short_margin - _used_short_margin)
    else:
        print(f"ERROR [Balance Manager]: Lado inválido '{side}' en get_available_margin."); return 0.0

def decrease_operational_margin(side: str, amount: float):
    global _used_long_margin, _used_short_margin
    if not _initialized: return
    if not isinstance(amount, (int, float)): print(f"ERROR [BM Decrease Use]: Amount no es número ({amount})."); return
    amount_abs = abs(amount)

    if side == 'long':
        _used_long_margin += amount_abs
    elif side == 'short':
        _used_short_margin += amount_abs
    else:
        print(f"ERROR [Balance Manager]: Lado inválido '{side}' en decrease_operational_margin (uso).")
        return

    if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
        current_used = _used_long_margin if side == 'long' else _used_short_margin
        current_available = get_available_margin(side)
        print(f"DEBUG [BM Use Margin]: Margen {side.upper()} usado incrementado en {amount_abs:.4f}. Total Usado: {current_used:.4f}. Disponible ahora: {current_available:.4f}")

def increase_operational_margin(side: str, amount: float):
    global _used_long_margin, _used_short_margin
    if not _initialized: return
    if not isinstance(amount, (int, float)): print(f"ERROR [BM Increase Release]: Amount no es número ({amount})."); return
    amount_to_release = abs(amount)

    if side == 'long':
        _used_long_margin -= amount_to_release
        if _used_long_margin < 0:
            _used_long_margin = 0.0
    elif side == 'short':
        _used_short_margin -= amount_to_release
        if _used_short_margin < 0:
            _used_short_margin = 0.0
    else:
        print(f"ERROR [Balance Manager]: Lado inválido '{side}' en increase_operational_margin (liberación).")
        return

    if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False):
        current_used = _used_long_margin if side == 'long' else _used_short_margin
        current_available = get_available_margin(side)
        print(f"DEBUG [BM Release Margin]: Margen {side.upper()} usado disminuido en {amount_to_release:.4f}. Total Usado: {current_used:.4f}. Disponible ahora: {current_available:.4f}")

def update_operational_margins_based_on_slots(new_max_slots: int):
    global _operational_long_margin, _operational_short_margin, _initial_base_position_size_usdt_session, _trading_mode_config, _initialized, _used_long_margin, _used_short_margin

    if not _initialized:
        print("WARN [BM Update Op Margins]: Balance Manager no inicializado.")
        return

    if new_max_slots < 0:
        print(f"WARN [BM Update Op Margins]: new_max_slots inválido: {new_max_slots}. No se actualiza.")
        return

    previous_op_long_margin = _operational_long_margin
    previous_op_short_margin = _operational_short_margin

    if _trading_mode_config != "SHORT_ONLY":
        new_total_op_long = _initial_base_position_size_usdt_session * new_max_slots
        _operational_long_margin = max(new_total_op_long, _used_long_margin)
    else:
        _operational_long_margin = _used_long_margin # Si es SHORT_ONLY, OpLong es solo lo que esté usado (idealmente 0)

    if _trading_mode_config != "LONG_ONLY":
        new_total_op_short = _initial_base_position_size_usdt_session * new_max_slots
        _operational_short_margin = max(new_total_op_short, _used_short_margin)
    else:
        _operational_short_margin = _used_short_margin # Si es LONG_ONLY, OpShort es solo lo que esté usado (idealmente 0)


    print(f"  INFO [BM Update Op Margins]: Márgenes operativos TOTALES actualizados para {new_max_slots} slots.")
    print(f"    Long : Antes {previous_op_long_margin:.4f} -> Op.Total Ahora {_operational_long_margin:.4f} (Usado: {_used_long_margin:.4f}, Disp: {get_available_margin('long'):.4f})")
    print(f"    Short: Antes {previous_op_short_margin:.4f} -> Op.Total Ahora {_operational_short_margin:.4f} (Usado: {_used_short_margin:.4f}, Disp: {get_available_margin('short'):.4f})")


def simulate_profit_transfer(from_side: str, amount: float) -> bool:
    # Esta función es SOLO para BACKTEST.
    # Aquí, el 'amount' es el PNL Neto que se va a la cuenta de profit.
    # El capital operativo (_operational_..._margin) NO se reduce por esta transferencia.
    # La reducción/aumento del margen disponible ya ocurrió a través de
    # decrease_operational_margin (al abrir) e increase_operational_margin (al cerrar, que incluye la reinversión).
    global _profit_balance
    if not _initialized: return False

    if _operation_mode.startswith("live"):
         print("DEBUG [BM Sim Transfer]: Llamado en modo Live. Esta función es solo para Backtest. No se realizarán cambios lógicos aquí.")
         return True # Indica que la "operación" (no hacer nada) fue "exitosa" para Live.

    if not isinstance(amount, (int, float)) or amount < 0:
        print(f"WARN [BM Sim Transfer]: Amount inválido ({amount}). No se transfiere."); return False
    if amount <= 1e-9:
        return True

    print_updates = getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False) if config else False
    amount_to_transfer = abs(amount)

    # En Backtest, simplemente se añade al balance de profit.
    # El margen operativo del lado no se reduce aquí porque la simulación de
    # 'cosechar' ganancias no implica reducir el capital base asignado a las operaciones.
    _profit_balance += amount_to_transfer
    if print_updates:
        print(f"  SIMULATED [BM Transfer]: {amount_to_transfer:.4f} USDT añadidos a Profit Balance. Nuevo Profit: {_profit_balance:.4f}.")
        # Mostrar márgenes disponibles para debug, no cambian por esta función en sí.
        print(f"    Margen Disponible Long : {get_available_margin('long'):.4f}")
        print(f"    Margen Disponible Short: {get_available_margin('short'):.4f}")
    return True


def record_real_profit_transfer_logically(from_side: str, amount_transferred: float):
    # Esta función actualiza los balances lógicos DESPUÉS de una transferencia API REAL.
    # El 'amount_transferred' (PNL Neto) se añade al profit_balance.
    # El capital operativo (_operational_..._margin) del lado NO se reduce por esta transferencia.
    # La reducción/aumento del margen disponible ya ocurrió a través de
    # decrease_operational_margin (al abrir) e increase_operational_margin (al cerrar).
    global _profit_balance
    if not _initialized: print("ERROR [BM Record Transfer]: BM no inicializado."); return
    if not _operation_mode.startswith("live"): print("WARN [BM Record Transfer]: Esta función es para modo Live."); return
    if not isinstance(amount_transferred, (int, float)) or amount_transferred < 0: print(f"WARN [BM Record Transfer]: Monto transferido inválido ({amount_transferred})."); return
    if amount_transferred <= 1e-9: return

    print_updates = getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False) if config else False

    print(f"DEBUG [BM Record Real Transfer]: Registrando lógicamente PNL Neto transferido de {amount_transferred:.4f} del lado {from_side} a profit.")

    # Solo se acredita al balance de profit. El margen operativo del lado no se modifica.
    _profit_balance += amount_transferred

    if print_updates:
        op_margin_side = _operational_long_margin if from_side == 'long' else _operational_short_margin
        avail_margin_side = get_available_margin(from_side)
        print(f"  LOGICAL BALANCES UPDATED [BM Record Transfer]: {amount_transferred:.4f} USDT añadidos a Profit Balance. "
              f"Nuevo Profit Lógico: {_profit_balance:.4f}.")
        print(f"    Margen Operativo Total {from_side.upper()}: {op_margin_side:.4f} (Sin cambios por esta transferencia). "
              f"Disponible {from_side.upper()}: {avail_margin_side:.4f}")

def get_balances() -> dict:
    if not _initialized:
        return {
            "available_long_margin": 0.0, "available_short_margin": 0.0,
            "used_long_margin": 0.0, "used_short_margin": 0.0,
            "operational_long_margin": 0.0, "operational_short_margin": 0.0,
            "profit_balance": 0.0, "error": "Balance Manager not initialized"
         }
    return {
        "available_long_margin": round(get_available_margin('long'), 8),
        "available_short_margin": round(get_available_margin('short'), 8),
        "used_long_margin": round(_used_long_margin, 8),
        "used_short_margin": round(_used_short_margin, 8),
        "operational_long_margin": round(_operational_long_margin, 8),
        "operational_short_margin": round(_operational_short_margin, 8),
        "profit_balance": round(_profit_balance, 8)
     }

def get_initial_total_capital() -> float:
    global _initial_operational_long_margin, _initial_operational_short_margin
    if not _initialized: return 0.0
    return _initial_operational_long_margin + _initial_operational_short_margin

# =============== FIN ARCHIVO: core/strategy/balance_manager.py (v8.7.x - Corregida Lógica Transferencia PNL) ===============