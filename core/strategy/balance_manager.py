# =============== INICIO ARCHIVO: core/strategy/balance_manager.py (Corregido UnboundLocalError) ===============
"""
Módulo dedicado a gestionar los balances LÓGICOS de las cuentas
(Long Margin, Short Margin, Profit Balance) durante el backtesting y live.

v8.7.x - Final: Corregida simulate_profit_transfer para deducir del margen operativo
                 y añadida record_real_profit_transfer_logically para modo Live.
v8.7.x: Modificada la inicialización para usar tamaño base por posición y número inicial de slots.
v8.5.8: Guarda correctamente los márgenes lógicos iniciales para get_initial_total_capital.
Modificado: Añadida función para actualizar márgenes operativos basada en cambio de slots.
            Corregido UnboundLocalError en simulate_profit_transfer.
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

_operational_long_margin: float = 0.0
_operational_short_margin: float = 0.0
_used_long_margin: float = 0.0
_used_short_margin: float = 0.0
_profit_balance: float = 0.0

_initial_operational_long_margin: float = 0.0
_initial_operational_short_margin: float = 0.0
_initial_profit_balance: float = 0.0
_initial_base_position_size_usdt_session: float = 0.0

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
        
        real_profit_balance_api = 0.0
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
        
        _profit_balance = real_profit_balance_api
        _initial_profit_balance = real_profit_balance_api
        print(f"    Balance Profit Lógico Inicial (API Real): {_profit_balance:.4f} USDT")

        total_capital_per_side_logical = current_base_size * current_slots

        if _trading_mode_config == "LONG_ONLY":
            _operational_long_margin = total_capital_per_side_logical
            _operational_short_margin = 0.0
        elif _trading_mode_config == "SHORT_ONLY":
            _operational_long_margin = 0.0
            _operational_short_margin = total_capital_per_side_logical
        elif _trading_mode_config == "LONG_SHORT":
            _operational_long_margin = total_capital_per_side_logical
            _operational_short_margin = total_capital_per_side_logical
        else: 
            print(f"    WARN: Modo trading '{_trading_mode_config}' desconocido. Aplicando capital a ambos lados.")
            _operational_long_margin = total_capital_per_side_logical
            _operational_short_margin = total_capital_per_side_logical
        
        _initial_operational_long_margin = _operational_long_margin
        _initial_operational_short_margin = _operational_short_margin

        print(f"    Margen Operativo Lógico Inicial Long (Calculado): {_operational_long_margin:.4f} USDT")
        print(f"    Margen Operativo Lógico Inicial Short (Calculado): {_operational_short_margin:.4f} USDT")

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

    _initialized = True
    print(f"[Balance Manager] Balances LÓGICOS inicializados -> OpLong: {_operational_long_margin:.4f}, OpShort: {_operational_short_margin:.4f}, Profit: {_profit_balance:.4f} USDT")
    print(f"  (DEBUG Iniciales Guardados: OpLong={_initial_operational_long_margin:.4f}, OpShort={_initial_operational_short_margin:.4f}, Profit={_initial_profit_balance:.4f})")

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
    if not isinstance(amount, (int, float)): print(f"ERROR [BM Decrease]: Amount no es número ({amount})."); return
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
    if not isinstance(amount, (int, float)): print(f"ERROR [BM Increase]: Amount no es número ({amount})."); return
    amount_to_release = abs(amount) 
    
    if side == 'long': 
        _used_long_margin -= amount_to_release
        if _used_long_margin < 0:
            print(f"WARN [BM Release Margin]: _used_long_margin < 0 ({_used_long_margin:.4f}) después de liberar. Ajustando a 0.")
            _used_long_margin = 0.0
    elif side == 'short': 
        _used_short_margin -= amount_to_release
        if _used_short_margin < 0:
            print(f"WARN [BM Release Margin]: _used_short_margin < 0 ({_used_short_margin:.4f}) después de liberar. Ajustando a 0.")
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
        _operational_long_margin = 0.0

    if _trading_mode_config != "LONG_ONLY":
        new_total_op_short = _initial_base_position_size_usdt_session * new_max_slots
        _operational_short_margin = max(new_total_op_short, _used_short_margin)
    else:
        _operational_short_margin = 0.0

    print(f"  INFO [BM Update Op Margins]: Márgenes operativos TOTALES actualizados para {new_max_slots} slots.")
    print(f"    Long : Antes {previous_op_long_margin:.4f} -> Op.Total Ahora {_operational_long_margin:.4f} (Usado: {_used_long_margin:.4f}, Disp: {get_available_margin('long'):.4f})")
    print(f"    Short: Antes {previous_op_short_margin:.4f} -> Op.Total Ahora {_operational_short_margin:.4f} (Usado: {_used_short_margin:.4f}, Disp: {get_available_margin('short'):.4f})")

def simulate_profit_transfer(from_side: str, amount: float) -> bool:
    # <<<<<<< CORRECCIÓN AQUÍ >>>>>>>
    global _profit_balance, _operational_long_margin, _operational_short_margin
    # <<<<<<< FIN CORRECCIÓN >>>>>>>
    if not _initialized: return False
    
    if _operation_mode.startswith("live"): 
         print("DEBUG [BM Sim Transfer]: Llamado en modo Live. Esta función es para simulación de Backtest. La lógica de ajuste de balances para Live es manejada por PositionManager/Executor y record_real_profit_transfer_logically.")
         return True

    if not isinstance(amount, (int, float)) or amount < 0: 
        print(f"WARN [BM Sim Transfer]: Amount inválido ({amount}). No se transfiere."); return False
    if amount <= 1e-9: 
        return True 

    print_updates = getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False) if config else False
    amount_to_transfer = abs(amount) 
    
    margin_available_on_side = get_available_margin(from_side)
    
    print(f"DEBUG [BM SimTransfer]: Lado: {from_side}, Intentando transferir (de disponible): {amount_to_transfer:.4f}, Margen DISPONIBLE Lado: {margin_available_on_side:.4f}")

    if margin_available_on_side >= (amount_to_transfer - 1e-9):
        if from_side == 'long':
            _operational_long_margin -= amount_to_transfer
        elif from_side == 'short':
            _operational_short_margin -= amount_to_transfer
        
        _profit_balance += amount_to_transfer
        if print_updates: 
            current_op_margin_after = _operational_long_margin if from_side == 'long' else _operational_short_margin
            print(f"  SIMULATED [BM Transfer]: {amount_to_transfer:.4f} USDT movido de Op. Margin '{from_side.upper()}' "
                  f"a Profit Balance. Nuevo Profit: {_profit_balance:.4f}. Nuevo Op.Margin {from_side.upper()}: {current_op_margin_after:.4f}")
        return True
    else:
        print(f"WARN [BM Sim Transfer]: Insuficiente margen DISPONIBLE en '{from_side.upper()}' ({margin_available_on_side:.4f}) "
              f"para simular transferencia de PNL Neto de {amount_to_transfer:.4f} a Profit. Transferencia no realizada.")
        return False

def record_real_profit_transfer_logically(from_side: str, amount_transferred: float):
    global _profit_balance, _operational_long_margin, _operational_short_margin # Asegurar que estas también sean globales aquí
    if not _initialized: print("ERROR [BM Record Transfer]: BM no inicializado."); return
    if not _operation_mode.startswith("live"): print("WARN [BM Record Transfer]: Esta función es para modo Live."); return
    if not isinstance(amount_transferred, (int, float)) or amount_transferred < 0: print(f"WARN [BM Record Transfer]: Monto transferido inválido ({amount_transferred})."); return
    if amount_transferred <= 1e-9: return

    print_updates = getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False) if config else False
    
    print(f"DEBUG [BM Record Real Transfer]: Registrando transferencia lógica de {amount_transferred:.4f} desde Op.Margin {from_side} a profit.")
    
    if from_side == 'long':
        _operational_long_margin -= amount_transferred
        if _operational_long_margin < _used_long_margin: 
            print(f"WARN [BM Record Transfer]: Op. Long Margin ({_operational_long_margin:.4f}) < Usado Long ({_used_long_margin:.4f}) después de transfer. Ajustando Op. Long.")
            _operational_long_margin = _used_long_margin 
    elif from_side == 'short':
        _operational_short_margin -= amount_transferred
        if _operational_short_margin < _used_short_margin: 
            print(f"WARN [BM Record Transfer]: Op. Short Margin ({_operational_short_margin:.4f}) < Usado Short ({_used_short_margin:.4f}) después de transfer. Ajustando Op. Short.")
            _operational_short_margin = _used_short_margin
            
    _profit_balance += amount_transferred

    if print_updates:
        op_margin_after = _operational_long_margin if from_side == 'long' else _operational_short_margin
        avail_margin_after = get_available_margin(from_side)
        print(f"  LOGICAL BALANCES UPDATED [BM Record Transfer]: {amount_transferred:.4f} USDT deducido de Op.Margin '{from_side.upper()}' "
              f"y añadido a Profit Balance. Nuevo Profit Lógico: {_profit_balance:.4f}. Nuevo Op.Margin {from_side.upper()}: {op_margin_after:.4f}. Disp: {avail_margin_after:.4f}")

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

# =============== FIN ARCHIVO: core/strategy/balance_manager.py (Corregido UnboundLocalError) ===============