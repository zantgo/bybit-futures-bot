# =============== INICIO ARCHIVO: core/strategy/balance_manager.py (ACTUALIZADO) ===============
"""
Módulo dedicado a gestionar los balances LÓGICOS de las cuentas
(Long Margin, Short Margin, Profit Balance) durante el backtesting y live.
También gestiona una caché de los balances REALES para evitar sobrecargar la API.
"""
import sys
import os
import traceback
import time
from typing import Optional, Dict, Any

# --- Dependencias del Ecosistema PM ---
try:
    from . import pm_state
    from core import utils, live_operations
    import config
    from live.connection import manager as connection_manager
except ImportError:
    pm_state = None
    utils = None
    config = None
    live_operations = None
    connection_manager = None

# --- Constantes ---
REAL_BALANCES_CACHE_EXPIRY_SECONDS = 30 # Actualizar balances reales cada 30 segundos

# --- Estado del Módulo ---
_initialized: bool = False
_default_base_position_size_usdt_config: float = 0.0
_default_initial_max_logical_positions_config: int = 1
_trading_mode_config: str = "N/A"
_operation_mode: str = "unknown"

_operational_long_margin: float = 0.0
_operational_short_margin: float = 0.0
_used_long_margin: float = 0.0
_used_short_margin: float = 0.0
_profit_balance: float = 0.0

_initial_operational_long_margin: float = 0.0
_initial_operational_short_margin: float = 0.0
_initial_profit_balance: float = 0.0
_initial_base_position_size_usdt_session: float = 0.0

# --- Caché de Balances Reales ---
_real_balances_cache: Dict[str, Any] = {}
_real_balances_last_update: float = 0.0


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
    global _real_balances_cache, _real_balances_last_update

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
    _real_balances_cache = {}
    _real_balances_last_update = 0.0

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
    
    _initialized = True 
    recalculate_dynamic_base_sizes()

# ... (resto de funciones sin cambios hasta get_initial_total_capital) ...
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
        _operational_long_margin = _used_long_margin 

    if _trading_mode_config != "LONG_ONLY":
        new_total_op_short = _initial_base_position_size_usdt_session * new_max_slots
        _operational_short_margin = max(new_total_op_short, _used_short_margin)
    else:
        _operational_short_margin = _used_short_margin
    
    recalculate_dynamic_base_sizes()

def simulate_profit_transfer(from_side: str, amount: float) -> bool:
    global _profit_balance
    if not _initialized: return False

    if _operation_mode.startswith("live"):
         return True 

    if not isinstance(amount, (int, float)) or amount < 0:
        return False
    if amount <= 1e-9:
        return True

    _profit_balance += abs(amount)
        
    return True

def record_real_profit_transfer_logically(from_side: str, amount_transferred: float):
    global _profit_balance
    if not _initialized: print("ERROR [BM Record Transfer]: BM no inicializado."); return
    if not _operation_mode.startswith("live"): print("WARN [BM Record Transfer]: Esta función es para modo Live."); return
    if not isinstance(amount_transferred, (int, float)) or amount_transferred < 0: return
    if amount_transferred <= 1e-9: return

    _profit_balance += amount_transferred

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

def recalculate_dynamic_base_sizes():
    if not _initialized or not pm_state or not utils:
        return

    try:
        max_pos = pm_state.get_max_logical_positions()
        base_size_ref = pm_state.get_initial_base_position_size()

        long_size = max(base_size_ref, utils.safe_division(get_available_margin('long'), max_pos))
        short_size = max(base_size_ref, utils.safe_division(get_available_margin('short'), max_pos))
        
        pm_state.set_dynamic_base_size(long_size, short_size)
    except Exception:
        pass

# <<< INICIO DE NUEVAS FUNCIONES PARA LA CACHÉ DE BALANCES REALES >>>
def update_real_balances_cache_from_api():
    """
    Actualiza la caché de balances reales si ha expirado.
    Esta función es llamada periódicamente por el event_processor.
    """
    global _real_balances_cache, _real_balances_last_update
    if not _initialized or not _operation_mode.startswith("live"): return
    if not live_operations or not connection_manager: return

    now = time.time()
    if (now - _real_balances_last_update) < REAL_BALANCES_CACHE_EXPIRY_SECONDS:
        return # La caché todavía es válida

    new_cache = {}
    accounts_to_check = [
        config.ACCOUNT_MAIN, config.ACCOUNT_LONGS,
        config.ACCOUNT_SHORTS, config.ACCOUNT_PROFIT
    ]
    for acc_name in sorted(list(set(accounts_to_check))):
        if acc_name in connection_manager.get_initialized_accounts():
            balance_info = live_operations.get_unified_account_balance_info(acc_name)
            new_cache[acc_name] = balance_info if balance_info else "Error al obtener balance"
    
    _real_balances_cache = new_cache
    _real_balances_last_update = now

def get_real_balances_cache() -> Dict[str, Any]:
    """
    Devuelve una copia de la caché de balances reales.
    Esta función es segura para ser llamada por la TUI.
    """
    return _real_balances_cache.copy()

# <<< FIN DE NUEVAS FUNCIONES PARA LA CACHÉ DE BALANCES REALES >>>

# =============== FIN ARCHIVO: core/strategy/balance_manager.py (ACTUALIZADO) ===============