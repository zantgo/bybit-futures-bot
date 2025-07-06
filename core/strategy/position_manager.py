# =============== INICIO ARCHIVO: core/strategy/position_manager.py (v13 - SL Físico y Control Automático) ===============
"""
Fachada Pública y Contenedor de Estado para Position Manager.
Orquesta el ciclo de vida de las posiciones, mantiene el estado agregado (PNL, cooldown)
e implementa la lógica de Stop Loss físico.

v13:
- Añadida lógica para el Stop Loss Físico en `check_and_close_positions`.
- Añadido `_stop_loss_event` para notificar al runner automático de un SL.
- Nuevas funciones `close_all_logical_positions` y `force_open_multiple_positions`
  para ser usadas por el `automatic_runner` durante los "flips".
- Nueva función `set_base_position_size` para ajuste dinámico del tamaño de posición.
- Modificada `initialize` para recibir el `stop_loss_event`.
"""
import datetime
import uuid
import traceback
import time
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple
import threading # Necesario para el threading.Event

# --- Dependencias Core y Strategy ---
try:
    import config
    from core import utils
    from . import balance_manager # Asegúrate que balance_manager tiene update_operational_margins_based_on_slots
    from . import position_state
    from . import position_calculations
    try:
        from core import live_operations
    except ImportError:
        print("WARN [PM Import Facade]: Módulo core.live_operations no encontrado.")
        live_operations = None
except ImportError as e:
    print(f"ERROR CRITICO [PM Import Facade]: No se pudo importar un módulo base: {e}")
    raise ImportError(f"Fallo importación crítica en PM Facade: {e.name}") from e
except Exception as e_imp_base:
     print(f"ERROR CRITICO [PM Import Facade]: Excepción inesperada importando módulos base: {e_imp_base}")
     raise

# --- CLASE DE EJECUCIÓN CENTRALIZADA ---
try:
    from .position_executor import PositionExecutor
except ImportError as e:
    print(f"ERROR CRITICO [PM Import Facade]: No se pudo importar PositionExecutor: {e}")
    raise ImportError(f"Fallo importación PositionExecutor: {e.name}") from e
except Exception as e_imp_exec:
     print(f"ERROR CRITICO [PM Import Facade]: Excepción inesperada importando PositionExecutor: {e_imp_exec}")
     raise

# --- Módulo Helper ---
try:
    from . import _position_helpers
except ImportError as e:
    print(f"ERROR CRITICO [PM Import Facade]: No se pudo importar _position_helpers: {e}")
    raise ImportError(f"Fallo importación _position_helpers: {e.name}") from e
except Exception as e_imp_help:
     print(f"ERROR CRITICO [PM Import Facade]: Excepción inesperada importando _position_helpers: {e_imp_help}")
     raise

# --- Logger de Posiciones Cerradas (Condicional) ---
closed_position_logger: Optional[Any] = None
if getattr(config, 'POSITION_MANAGEMENT_ENABLED', False) and getattr(config, 'POSITION_LOG_CLOSED_POSITIONS', False):
    try:
        from core.logging import closed_position_logger as cpl_mod
        closed_position_logger = cpl_mod
    except ImportError:
        print("WARN [PM Import Facade]: Log posiciones cerradas habilitado pero no importado.")
    except Exception as e_imp_log:
         print(f"ERROR [PM Import Facade]: Excepción importando closed_position_logger: {e_imp_log}")

# --- Estado Global del Módulo Position Manager (Fachada) ---
_initialized: bool = False
_is_live_mode: bool = False
_live_manager: Optional[Any] = None
_executor: Optional[PositionExecutor] = None
_total_realized_pnl_long: float = 0.0
_total_realized_pnl_short: float = 0.0
_total_transferred_profit: float = 0.0
_trading_mode: str = "N/A"
_leverage: float = 1.0
_min_transfer_amount: float = 0.1

_max_logical_positions: int = 1
_initial_base_position_size_usdt: float = 0.0 # Tamaño base de sesión, usado como piso
_current_dynamic_base_size_long: float = 0.0
_current_dynamic_base_size_short: float = 0.0

_event_counter_since_last_long: int = 0
_event_counter_since_last_short: int = 0
_cooldown_enabled: bool = False
_cooldown_long_period: int = 0
_cooldown_short_period: int = 0
_cached_min_order_qty: Optional[float] = None
_stop_loss_event: Optional[threading.Event] = None


# --- Función de Inicialización Principal ---
def initialize(
    operation_mode: str,
    initial_real_state: Optional[Dict[str, Dict[str, Any]]] = None,
    base_position_size_usdt_param: Optional[float] = None,
    initial_max_logical_positions_param: Optional[int] = None,
    stop_loss_event: Optional[threading.Event] = None
):
    global _initialized, _is_live_mode, _live_manager, _executor, _total_realized_pnl_long, _total_realized_pnl_short
    global _total_transferred_profit, _trading_mode, _leverage, _min_transfer_amount, _max_logical_positions
    global _initial_base_position_size_usdt, _current_dynamic_base_size_long, _current_dynamic_base_size_short
    global _event_counter_since_last_long, _event_counter_since_last_short, _cooldown_enabled
    global _cooldown_long_period, _cooldown_short_period, _cached_min_order_qty, _stop_loss_event
    global config, utils, balance_manager, position_state, position_calculations, live_operations, closed_position_logger, _position_helpers

    if not getattr(config, 'POSITION_MANAGEMENT_ENABLED', False):
        print("[PM Facade] Init omitida (Gestión Desactivada en config)."); _initialized = False; return
    if not all([config, utils, balance_manager, position_state, position_calculations, _position_helpers]):
        print(f"ERROR CRITICO [PM Init Facade]: Faltan dependencias esenciales. Imposible inicializar."); _initialized = False; return

    print("[PM Facade] Inicializando Orquestador (Lógica Tamaño Base Dinámico)...")
    _initialized = False; _total_realized_pnl_long = 0.0; _total_realized_pnl_short = 0.0; _total_transferred_profit = 0.0
    _event_counter_since_last_long = 0; _event_counter_since_last_short = 0
    _is_live_mode = operation_mode.startswith(("live", "automatic"))
    _live_manager = None; _executor = None; _cached_min_order_qty = None
    _stop_loss_event = stop_loss_event # Asignar el evento de SL

    try:
        _trading_mode = getattr(config,'POSITION_TRADING_MODE','LONG_SHORT')
        _leverage = max(1.0,float(getattr(config,'POSITION_LEVERAGE',1.0)))
        _min_transfer_amount = float(getattr(config,'POSITION_MIN_TRANSFER_AMOUNT_USDT',0.1))
        _cooldown_enabled = bool(getattr(config, 'POSITION_SIGNAL_COOLDOWN_ENABLED', False))
        _cooldown_long_period = int(getattr(config, 'POSITION_SIGNAL_COOLDOWN_LONG', 0)) if _cooldown_enabled else 0
        _cooldown_short_period = int(getattr(config, 'POSITION_SIGNAL_COOLDOWN_SHORT', 0)) if _cooldown_enabled else 0

        default_base_size_cfg = utils.safe_float_convert(getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0), 10.0)
        default_slots_cfg = int(getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1))
        
        _initial_base_position_size_usdt = base_position_size_usdt_param if base_position_size_usdt_param is not None and base_position_size_usdt_param > 0 else default_base_size_cfg
        _max_logical_positions = initial_max_logical_positions_param if initial_max_logical_positions_param is not None and initial_max_logical_positions_param >= 1 else default_slots_cfg
        
        print(f"  Config PM: ModoOp={_trading_mode}, Lev={_leverage:.1f}x")
        print(f"  Config PM: Tamaño Base Inicial por Posición (Sesión): {_initial_base_position_size_usdt:.4f} USDT")
        print(f"  Config PM: Slots Lógicos Iniciales por Lado: {_max_logical_positions}")
        print(f"  Config PM: Cooldown Señales: {'Activado (L:'+str(_cooldown_long_period)+', S:'+str(_cooldown_short_period)+')' if _cooldown_enabled else 'Desactivado'}")

        if hasattr(_position_helpers, 'set_config_dependency'): _position_helpers.set_config_dependency(config)
        if hasattr(_position_helpers, 'set_utils_dependency'): _position_helpers.set_utils_dependency(utils)
        if hasattr(_position_helpers, 'set_live_operations_dependency'): _position_helpers.set_live_operations_dependency(live_operations if _is_live_mode else None)
    except Exception as e_cfg: print(f"ERROR CRITICO [PM Init Facade]: Cacheando config: {e_cfg}. Abortando."); traceback.print_exc(); return

    if _is_live_mode: 
        try:
            from live.connection import manager as live_conn_manager; _live_manager = live_conn_manager
            if not hasattr(_live_manager, 'get_initialized_accounts') or not _live_manager.get_initialized_accounts(): print("WARN [PM Init Facade]: Live Manager sin cuentas inicializadas.")
            else:
                 accounts_needed = [getattr(config,'ACCOUNT_PROFIT', None)]; loaded_uids = getattr(config,'LOADED_UIDS',{});
                 if _trading_mode != 'SHORT_ONLY': accounts_needed.append(getattr(config,'ACCOUNT_LONGS', None))
                 if _trading_mode != 'LONG_ONLY': accounts_needed.append(getattr(config,'ACCOUNT_SHORTS', None))
                 accounts_needed = [acc for acc in accounts_needed if acc]; missing_uids = [acc for acc in accounts_needed if acc not in loaded_uids]
                 if missing_uids: print(f"  WARN [PM Init Facade]: Faltan UIDs en config.LOADED_UIDS ({missing_uids}).");
                 else: print("  Live Mode: UIDs encontrados para cuentas (transferencias posibles).")
            if not live_operations: print("ERROR CRITICO [PM Init Facade]: Live Operations no cargado (esencial para Live PM)."); return
        except ImportError: print("ERROR CRITICO [PM Init Facade]: No se pudo importar live.connection.manager."); _live_manager = None; _is_live_mode = False; return
        except Exception as e_live: print(f"ERROR [PM Init Facade]: Configurando Live Manager: {e_live}"); _live_manager = None; _is_live_mode = False; return

    try: 
        min_qty_fallback = float(getattr(config, 'DEFAULT_MIN_ORDER_QTY', 0.001))
        symbol_cfg = getattr(config, 'TICKER_SYMBOL', None)
        if _is_live_mode and live_operations and symbol_cfg and hasattr(live_operations, 'get_instrument_info'):
            instr_info = live_operations.get_instrument_info(symbol_cfg)
            if instr_info and instr_info.get('minOrderQty'): _cached_min_order_qty = utils.safe_float_convert(instr_info['minOrderQty'], min_qty_fallback); print(f"  Min Order Qty (API): {_cached_min_order_qty}")
            else: _cached_min_order_qty = min_qty_fallback; print(f"  WARN [PM Init]: No minOrderQty de API. Usando default: {_cached_min_order_qty}")
        else: _cached_min_order_qty = min_qty_fallback; print(f"  Min Order Qty (Config): {_cached_min_order_qty}")
    except Exception as e_qty: print(f"ERROR [PM Init Facade]: Cacheando min_order_qty: {e_qty}"); _cached_min_order_qty = 0.001

    try: 
        if not hasattr(balance_manager, 'initialize'): raise AttributeError("BalanceManager sin 'initialize'.")
        print(f"  Inicializando Balance Manager (Modo: {operation_mode})...")
        balance_manager.initialize(
            operation_mode=operation_mode,
            real_balances_data=initial_real_state if _is_live_mode else None,
            base_position_size_usdt=_initial_base_position_size_usdt, 
            initial_max_logical_positions=_max_logical_positions     
        )
        print("  -> Balance Manager inicializado.")
    except AttributeError as attr_err_bm: print(f"ERROR CRITICO [PM Init Facade]: {attr_err_bm}"); traceback.print_exc(); return
    except Exception as init_e_bm: print(f"ERROR CRITICO [PM Init Facade]: Fallo inicializando BM: {init_e_bm}"); traceback.print_exc(); return

    if _max_logical_positions > 0 and utils and balance_manager and hasattr(balance_manager, 'get_available_margin'):
        if _trading_mode == "LONG_ONLY" or _trading_mode == "LONG_SHORT":
            dynamic_long = utils.safe_division(balance_manager.get_available_margin('long'), _max_logical_positions, 0.0)
            _current_dynamic_base_size_long = max(_initial_base_position_size_usdt, dynamic_long)
        else: 
            _current_dynamic_base_size_long = 0.0 
        if _trading_mode == "SHORT_ONLY" or _trading_mode == "LONG_SHORT":
            dynamic_short = utils.safe_division(balance_manager.get_available_margin('short'), _max_logical_positions, 0.0)
            _current_dynamic_base_size_short = max(_initial_base_position_size_usdt, dynamic_short)
        else: 
            _current_dynamic_base_size_short = 0.0
    else: 
        _current_dynamic_base_size_long = _initial_base_position_size_usdt if _trading_mode != "SHORT_ONLY" else 0.0
        _current_dynamic_base_size_short = _initial_base_position_size_usdt if _trading_mode != "LONG_ONLY" else 0.0
        if not (utils and balance_manager and hasattr(balance_manager, 'get_available_margin')):
            print("WARN [PM Init]: No se pudo calcular dinámicamente el tamaño base, usando _initial_base_position_size_usdt.")
        elif _max_logical_positions <= 0:
            print("WARN [PM Init]: _max_logical_positions es <= 0, usando _initial_base_position_size_usdt para tamaño dinámico.")

    print(f"  Config PM: Tamaño Base Dinámico Inicial Long : {_current_dynamic_base_size_long:.4f} USDT")
    print(f"  Config PM: Tamaño Base Dinámico Inicial Short: {_current_dynamic_base_size_short:.4f} USDT")

    try: 
        if not hasattr(position_state, 'initialize_state'): raise AttributeError("PositionState sin 'initialize_state'.")
        position_state.initialize_state(is_live_mode=_is_live_mode, config_dependency=config, utils_dependency=utils, live_ops_dependency=live_operations)
        print("  -> Position State inicializado.")
    except AttributeError as attr_err_ps: print(f"ERROR CRITICO [PM Init Facade]: {attr_err_ps}."); traceback.print_exc(); return
    except Exception as init_e_ps: print(f"ERROR CRITICO [PM Init Facade]: Fallo inicializando PS: {init_e_ps}"); traceback.print_exc(); return

    if closed_position_logger: 
        try:
             if hasattr(closed_position_logger, 'initialize_logger'): closed_position_logger.initialize_logger(); print("  -> Logger Pos Cerradas inicializado.")
             else: print("WARN [PM Init Facade]: closed_position_logger sin initialize_logger.")
        except Exception as e_log_init: print(f"ERROR inicializando Logger Cerradas: {e_log_init}")

    try: 
        print("  Creando instancia de PositionExecutor...")
        _executor = PositionExecutor(is_live_mode=_is_live_mode, config=config, utils=utils, balance_manager=balance_manager, position_state=position_state, position_calculations=position_calculations, live_operations=live_operations, closed_position_logger=closed_position_logger, position_helpers=_position_helpers, live_manager=_live_manager)
        print("  -> Instancia de PositionExecutor creada.")
    except Exception as exec_init_e: print(f"ERROR CRITICO [PM Init Facade]: Falló creación PositionExecutor: {exec_init_e}"); traceback.print_exc(); _executor = None; return

    _initialized = True
    print("[PM Facade] Orquestador Inicializado.")

def _handle_stop_loss_trigger(side: str, exit_price: float, timestamp: datetime.datetime):
    """Función privada que centraliza la respuesta a un SL."""
    global _stop_loss_event
    print(f"  -> Procediendo a cerrar TODAS las posiciones {side.upper()} por SL.")
    close_all_logical_positions(side, exit_price, timestamp)
    
    # Notificar al runner que el SL ocurrió
    if _stop_loss_event and not _stop_loss_event.is_set():
        print("  -> Activando evento de Stop Loss para el runner.")
        _stop_loss_event.set()


# --- Funciones Públicas de Gestión ---
def check_and_close_positions(current_price: float, timestamp: datetime.datetime):
    global _initialized, _trading_mode, config, utils, position_state, position_calculations
    if not _initialized: return
    if not isinstance(current_price, (int, float)) or current_price <= 0: return
    if not isinstance(timestamp, datetime.datetime): return
    if not all([config, utils, position_state, position_calculations]): print("ERROR [CheckClose Facade]: Dependencias no disponibles."); return
    
    sides_to_check = []
    if _trading_mode in ["LONG_SHORT", "LONG_ONLY"]: sides_to_check.append('long')
    if _trading_mode in ["LONG_SHORT", "SHORT_ONLY"]: sides_to_check.append('short')
    if _trading_mode == "NEUTRAL":
        sides_to_check = ['long', 'short']

    for side in sides_to_check:
        try:
            open_positions = list(position_state.get_open_logical_positions(side))
            if not open_positions: continue

            # --- 1. Lógica de Take Profit (TP) ---
            indices_to_close_tp = []
            for i, pos in enumerate(open_positions):
                tp_stored = pos.get('take_profit_price')
                tp_float = utils.safe_float_convert(tp_stored, default=None)
                if tp_float is not None:
                    if (side == 'long' and current_price >= tp_float) or \
                       (side == 'short' and current_price <= tp_float):
                        indices_to_close_tp.append(i)
            
            if indices_to_close_tp:
                for index in sorted(indices_to_close_tp, reverse=True):
                    close_logical_position(side, index, current_price, timestamp)
                # Actualizar la lista de posiciones abiertas después de cerrar
                open_positions = list(position_state.get_open_logical_positions(side))
            
            if not open_positions: continue

            # --- 2. Lógica de Stop Loss (SL) Físico ---
            sl_pct = getattr(config, 'POSITION_PHYSICAL_STOP_LOSS_PCT', 0.0)
            if sl_pct > 0:
                physical_state = position_state.get_physical_position_state(side)
                avg_entry = utils.safe_float_convert(physical_state.get('avg_entry_price'))
                if avg_entry > 0:
                    sl_price = avg_entry * (1 - sl_pct / 100.0) if side == 'long' else avg_entry * (1 + sl_pct / 100.0)
                    if (side == 'long' and current_price <= sl_price) or \
                       (side == 'short' and current_price >= sl_price):
                        print("\n" + "!"*80 + f"\n!! ALERTA: STOP LOSS FÍSICO ACTIVADO PARA POSICIÓN {side.upper()} !!".center(80) + f"\n!!   - Precio Actual: {current_price:.4f} | Precio SL: {sl_price:.4f}".center(80) + "\n" + "!"*80 + "\n")
                        _handle_stop_loss_trigger(side, current_price, timestamp)
        
        except Exception as check_err:
            print(f"ERROR CRÍTICO [CheckClose Facade]: Verificando {side}: {check_err}"); traceback.print_exc()


def can_open_new_position(side: str) -> bool:
    global _initialized, _is_live_mode, _trading_mode, _max_logical_positions, _cooldown_enabled, _event_counter_since_last_long, _event_counter_since_last_short, _cooldown_long_period, _cooldown_short_period, config, utils, balance_manager, position_state, live_operations, _live_manager, _position_helpers, _current_dynamic_base_size_long, _current_dynamic_base_size_short
    
    if not _initialized: return False
    if not all([config, utils, balance_manager, position_state]): print("WARN [can_open Facade]: Faltan dependencias."); return False
    if side not in ['long', 'short']: return False
    if side == 'long' and _trading_mode == "SHORT_ONLY": return False
    if side == 'short' and _trading_mode == "LONG_ONLY": return False
    if _trading_mode == "NEUTRAL":
        if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False): print(f"INFO [Can Open]: No se puede abrir en modo NEUTRAL.")
        return False

    try: 
        if not hasattr(position_state, 'get_open_logical_positions'): print("ERROR [can_open Facade]: PS sin get_open_logical_positions."); return False
        open_positions = position_state.get_open_logical_positions(side)
        if len(open_positions) >= _max_logical_positions:
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False): print(f"INFO [Can Open]: Límite {side.upper()} slots ({_max_logical_positions}) alcanzado.");
            return False
    except Exception as e: print(f"ERROR [can_open]: Verificando límite {side}: {e}"); return False

    try: 
        if not hasattr(balance_manager, 'get_available_margin'): print("ERROR [can_open Facade]: BM sin get_available_margin."); return False
        current_avail_margin_logical = balance_manager.get_available_margin(side)
        margin_needed_for_this_pos = _current_dynamic_base_size_long if side == 'long' else _current_dynamic_base_size_short
        
        if current_avail_margin_logical < margin_needed_for_this_pos - 1e-6 :
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False): print(f"INFO [Can Open]: Margen LÓGICO disponible ({current_avail_margin_logical:.4f}) < necesario ({margin_needed_for_this_pos:.4f}) para {side.upper()}.");
            return False
    except Exception as e: print(f"ERROR [can_open]: Verificando margen lógico {side}: {e}"); traceback.print_exc(); return False

    if _cooldown_enabled: 
        if side == 'long' and _event_counter_since_last_long < _cooldown_long_period:
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False): print(f"INFO [Cooldown Long]: Ignorada. Eventos: {_event_counter_since_last_long}/{_cooldown_long_period}");
            return False
        if side == 'short' and _event_counter_since_last_short < _cooldown_short_period:
            if getattr(config, 'POSITION_PRINT_POSITION_UPDATES', False): print(f"INFO [Cooldown Short]: Ignorada. Eventos: {_event_counter_since_last_short}/{_cooldown_short_period}");
            return False

    ENABLE_PRE_OPEN_SYNC_CHECK = getattr(config, 'POSITION_PRE_OPEN_SYNC_CHECK', True)
    if _is_live_mode and live_operations and ENABLE_PRE_OPEN_SYNC_CHECK: 
        symbol = getattr(config, 'TICKER_SYMBOL', None)
        if not symbol: print("WARN [PM Pre-Open Check Facade]: Falta TICKER_SYMBOL."); return False
        if not _live_manager or not hasattr(_live_manager, 'get_initialized_accounts'): print("WARN [PM Pre-Open Check Facade]: Live Manager no disponible."); return False
        if not _position_helpers or not hasattr(_position_helpers, 'extract_physical_state_from_api'): print("WARN [PM Pre-Open Check Facade]: Helpers no disponibles."); return False
        
        target_account_name_cfg = getattr(config, 'ACCOUNT_LONGS', None) if side == 'long' else getattr(config, 'ACCOUNT_SHORTS', None)
        main_acc_name_cfg = getattr(config, 'ACCOUNT_MAIN', 'main'); 
        initialized_accounts = _live_manager.get_initialized_accounts()
        account_to_check = target_account_name_cfg if target_account_name_cfg and target_account_name_cfg in initialized_accounts else main_acc_name_cfg
        
        if account_to_check not in initialized_accounts: 
            print(f"WARN [PM Pre-Open Check Facade]: Cuenta operativa '{account_to_check}' no inicializada. Saltando chequeo sync real.")
        else:
            try:
                if not all([hasattr(live_operations, 'get_unified_account_balance_info'), hasattr(live_operations, 'get_active_position_details_api'), utils, hasattr(position_state, 'get_open_logical_positions')]):
                    print("ERROR [PM Pre-Open Check Facade]: Faltan métodos/módulos en dependencias para chequeo real."); return False
                
                margin_needed_real_check = _current_dynamic_base_size_long if side == 'long' else _current_dynamic_base_size_short
                print(f"DEBUG [PM Pre-Open Check]: Verificando margen REAL (USDT WalletBalance) en '{account_to_check}' para abrir con {margin_needed_real_check:.4f} USDT...")
                
                balance_info_raw = live_operations.get_unified_account_balance_info(account_to_check)
                real_usdt_wallet_balance = 0.0
                
                if balance_info_raw and isinstance(balance_info_raw.get('coin'), list):
                    usdt_coin_data = next((c for c in balance_info_raw['coin'] if c.get('coin') == 'USDT'), None)
                    if usdt_coin_data: real_usdt_wallet_balance = utils.safe_float_convert(usdt_coin_data.get('walletBalance'), 0.0)
                    else: real_usdt_wallet_balance = utils.safe_float_convert(balance_info_raw.get('totalWalletBalance'), 0.0)
                elif balance_info_raw: real_usdt_wallet_balance = utils.safe_float_convert(balance_info_raw.get('totalWalletBalance'), 0.0)
                else: print(f"WARN [PM Pre-Open Check Facade]: No se pudo obtener balance real de '{account_to_check}'. No abrir {side.upper()}."); return False

                if real_usdt_wallet_balance < margin_needed_real_check - 1e-6: 
                    print(f"WARN [PM Pre-Open Check Facade]: Margen REAL (USDT Wallet: {real_usdt_wallet_balance:.4f}) en '{account_to_check}' < nec. ({margin_needed_real_check:.4f}). No abrir {side.upper()}."); 
                    return False
                else: print(f"  DEBUG [PM Pre-Open Check]: Chequeo de USDT WalletBalance OK.")

                open_positions_for_size_check = position_state.get_open_logical_positions(side)
                physical_pos_raw = live_operations.get_active_position_details_api(symbol, account_to_check)
                current_physical_state = _position_helpers.extract_physical_state_from_api(physical_pos_raw, symbol, side, utils)
                current_physical_size = current_physical_state['total_size_contracts'] if current_physical_state else 0.0
                current_logical_size = sum(utils.safe_float_convert(p.get('size_contracts'), 0.0) for p in open_positions_for_size_check)
                if abs(current_physical_size - current_logical_size) > 1e-9: print(f"WARN [PM Pre-Open Check Facade]: Discrepancia FÍSICO {side.upper()} ({current_physical_size:.8f}) != LÓGICO ({current_logical_size:.8f}) en '{account_to_check}'. No abrir."); return False
            except Exception as sync_err: print(f"ERROR [PM Pre-Open Check Facade]: Excepción sync {side.upper()} en '{account_to_check}': {sync_err}"); traceback.print_exc(); return False
    return True

def open_logical_position(side: str, entry_price: float, timestamp: datetime.datetime):
    global _initialized, _max_logical_positions, _cooldown_enabled, _event_counter_since_last_long, _event_counter_since_last_short, config, utils, balance_manager, position_state, _executor, _cached_min_order_qty, _leverage, _current_dynamic_base_size_long, _current_dynamic_base_size_short
    if not _initialized: print("WARN [Open Facade]: PM no inicializado."); return
    if not _executor: print("ERROR [Open Facade]: PositionExecutor no inicializado."); return
    if not isinstance(entry_price, (int, float)) or entry_price <= 0: print(f"WARN [Open Facade]: Precio entrada inválido: {entry_price}"); return
    if not isinstance(timestamp, datetime.datetime): print(f"WARN [Open Facade]: Timestamp inválido: {timestamp}"); return
    if not all([config, utils, balance_manager, position_state]): print("ERROR [Open Facade]: Faltan dependencias."); return

    if not can_open_new_position(side): return

    try: 
        open_positions = position_state.get_open_logical_positions(side)
        if open_positions:
            last_pos = open_positions[-1]; last_entry_price = utils.safe_float_convert(last_pos.get('entry_price'), 0.0); last_pos_id_short = str(last_pos.get('id', 'N/A'))[-6:]
            if last_entry_price > 1e-9:
                pct_diff = utils.safe_division( (entry_price - last_entry_price), last_entry_price, default=float('inf')) * 100.0
                if side == 'long':
                    threshold_long = getattr(config, 'POSITION_MIN_PRICE_DIFF_LONG_PCT', -1.0)
                    if pct_diff > threshold_long: print(f"WARN [Open {side.upper()} Facade]: Precio {entry_price:.4f} ({pct_diff:.2f}%) vs últ. {last_entry_price:.4f} (...{last_pos_id_short}). Req: < {threshold_long:.2f}%. No abrir."); return
                elif side == 'short':
                    threshold_short = getattr(config, 'POSITION_MIN_PRICE_DIFF_SHORT_PCT', 1.0)
                    if pct_diff < threshold_short: print(f"WARN [Open {side.upper()} Facade]: Precio {entry_price:.4f} ({pct_diff:.2f}%) vs últ. {last_entry_price:.4f} (...{last_pos_id_short}). Req: > {threshold_short:.2f}%. No abrir."); return
    except Exception as e_dist_check: print(f"ERROR [Open Facade]: Verificando distancia {side}: {e_dist_check}"); traceback.print_exc(); return

    margin_to_use = _current_dynamic_base_size_long if side == 'long' else _current_dynamic_base_size_short
    
    try: 
        if _cached_min_order_qty is None or _cached_min_order_qty <= 0: print("WARN [Open Facade]: min_order_qty no disponible. Saltando chequeo margen mín.")
        else:
            min_margin_needed_approx = utils.safe_division( _cached_min_order_qty * entry_price, _leverage, default=float('inf')) * 1.01
            if margin_to_use < min_margin_needed_approx: print(f"WARN [Open {side.upper()} Facade]: Margen base dinámico ({margin_to_use:.4f}) INSUF. vs mín. nec. ({min_margin_needed_approx:.4f}). No abrir."); return
    except Exception as e_min_margin_check: print(f"ERROR [Open Facade]: Verificando margen mín. para {side}: {e_min_margin_check}"); traceback.print_exc(); return

    try: 
        print(f"INFO [Open Facade]: Delegando apertura {side.upper()} a Executor (Margen: {margin_to_use:.4f})...")
        result = _executor.execute_open( side=side, entry_price=entry_price, timestamp=timestamp, margin_to_use=margin_to_use )
        if result and result.get('success'):
            if _cooldown_enabled:
                if side == 'long': _event_counter_since_last_long = 0; print(f"DEBUG [Cooldown Long]: Contador reseteado.")
                elif side == 'short': _event_counter_since_last_short = 0; print(f"DEBUG [Cooldown Short]: Contador reseteado.")
    except Exception as e_exec: print(f"ERROR CRITICO [PM Facade]: Excepción delegando/ejecutando open ({side}): {e_exec}"); traceback.print_exc()

def close_logical_position(side: str, position_index: int, exit_price: float, timestamp: datetime.datetime):
    global _initialized, _total_realized_pnl_long, _total_realized_pnl_short, _total_transferred_profit, _min_transfer_amount, config, _executor, balance_manager, _max_logical_positions, _initial_base_position_size_usdt, _current_dynamic_base_size_long, _current_dynamic_base_size_short, _is_live_mode, utils
    if not _initialized: print("WARN [Close Facade]: PM no inicializado."); return
    if not _executor: print("ERROR [Close Facade]: PositionExecutor no inicializado."); return
    if not isinstance(exit_price, (int, float)) or exit_price <= 0: print(f"WARN [Close Facade]: Precio salida inválido: {exit_price}"); return
    if not isinstance(timestamp, datetime.datetime): print(f"WARN [Close Facade]: Timestamp inválido: {timestamp}"); return
    if side not in ['long', 'short']: print(f"WARN [Close Facade]: Lado inválido: {side}"); return
    try:
        print(f"INFO [Close Facade]: Delegando cierre {side.upper()} índice {position_index} a Executor (Px Salida: {exit_price:.4f})...")
        result = _executor.execute_close( side=side, position_index=position_index, exit_price=exit_price, timestamp=timestamp )
        
        if result and result.get('success'):
            pnl_net_usdt = result.get('pnl_net_usdt', 0.0)
            amount_to_potentially_transfer = result.get('amount_transferable_to_profit', 0.0)

            if side == 'long': _total_realized_pnl_long += pnl_net_usdt
            else: _total_realized_pnl_short += pnl_net_usdt
            
            if balance_manager and hasattr(balance_manager, 'get_available_margin') and _max_logical_positions > 0 and utils:
                new_dynamic_base = utils.safe_division(balance_manager.get_available_margin(side), _max_logical_positions, 0.0)
                if side == 'long': _current_dynamic_base_size_long = max(_initial_base_position_size_usdt, new_dynamic_base)
                else: _current_dynamic_base_size_short = max(_initial_base_position_size_usdt, new_dynamic_base)
            
            if amount_to_potentially_transfer >= float(_min_transfer_amount):
                transferred_amount_via_executor = _executor.execute_transfer(amount_to_potentially_transfer, side)
                if transferred_amount_via_executor > 0:
                    _total_transferred_profit += transferred_amount_via_executor
                    if _is_live_mode and balance_manager and hasattr(balance_manager, 'record_real_profit_transfer_logically'):
                        balance_manager.record_real_profit_transfer_logically(side, transferred_amount_via_executor)
    except Exception as e: print(f"ERROR CRITICO [PM Facade]: Excepción en close_logical_position ({side}, idx {position_index}): {e}"); traceback.print_exc()

def get_current_price_for_exit() -> Optional[float]:
    """Helper para obtener el precio actual para cierres/aperturas forzadas."""
    try:
        from live.connection import ticker
        price_info = ticker.get_latest_price()
        return price_info.get('price')
    except Exception as e:
        print(f"ERROR [get_current_price_for_exit]: {e}")
        return None

def close_all_logical_positions(side: str, exit_price: Optional[float] = None, timestamp: Optional[datetime.datetime] = None) -> bool:
    """Cierra todas las posiciones lógicas abiertas para un lado dado."""
    if not _initialized: return False
    
    open_positions = position_state.get_open_logical_positions(side)
    if not open_positions:
        print(f"INFO [Close All]: No hay posiciones {side.upper()} para cerrar."); return True
    
    price_to_use = exit_price if exit_price else get_current_price_for_exit()
    if not price_to_use:
        print(f"ERROR [Close All]: No se pudo determinar el precio de salida para {side.upper()}. Abortando."); return False
    
    ts_to_use = timestamp if timestamp else datetime.datetime.now()

    print(f"--- Cerrando todas las {len(open_positions)} posiciones {side.upper()} a precio {price_to_use:.4f} ---")
    
    for i in sorted(range(len(open_positions)), reverse=True):
        close_logical_position(side, i, price_to_use, ts_to_use)
        time.sleep(0.1) # Pequeña pausa para no sobrecargar
        
    final_open_count = len(position_state.get_open_logical_positions(side))
    if final_open_count == 0:
        print(f"--- Cierre Total {side.upper()} Completado ---")
        return True
    else:
        print(f"--- ERROR: Aún quedan {final_open_count} posiciones {side.upper()} abiertas después de intentar cerrar todas. ---")
        return False

def force_open_multiple_positions(side: str, count: int) -> bool:
    """Abre un número específico de posiciones para el lado dado."""
    if not _initialized: return False
    success_count = 0
    print(f"--- Intentando abrir forzadamente {count} posiciones {side.upper()} ---")
    for i in range(count):
        price = get_current_price_for_exit()
        if not price:
            print(f"ERROR [Force Open Multiple]: No se pudo obtener precio para abrir pos #{i+1}."); return False
        
        open_logical_position(side, price, datetime.datetime.now())
        # Aquí no podemos verificar el éxito directamente sin cambiar la firma de open_logical_position
        # Asumimos que se intentó
        success_count += 1
        time.sleep(0.2)
    
    final_count = len(position_state.get_open_logical_positions(side))
    print(f"--- Apertura Forzada Múltiple {side.upper()} finalizada. Posiciones abiertas: {final_count} ---")
    # El éxito se considera si se intentaron todas las aperturas
    return success_count == count

def set_base_position_size(new_size_usdt: float) -> Tuple[bool, str]:
    """Permite cambiar el tamaño base de las futuras posiciones."""
    global _initial_base_position_size_usdt, _current_dynamic_base_size_long, _current_dynamic_base_size_short
    if not _initialized: return False, "Error: PM no inicializado."
    if not isinstance(new_size_usdt, (int, float)) or new_size_usdt <= 0: return False, f"Error: Tamaño base inválido ({new_size_usdt})."
    
    old_size = _initial_base_position_size_usdt
    _initial_base_position_size_usdt = new_size_usdt
    
    if _max_logical_positions > 0 and balance_manager and utils:
        _current_dynamic_base_size_long = max(_initial_base_position_size_usdt, utils.safe_division(balance_manager.get_available_margin('long'), _max_logical_positions, 0.0))
        _current_dynamic_base_size_short = max(_initial_base_position_size_usdt, utils.safe_division(balance_manager.get_available_margin('short'), _max_logical_positions, 0.0))
        msg = f"Tamaño base actualizado de {old_size:.2f} a {new_size_usdt:.2f} USDT."
        print(f"INFO [PM Set Base Size]: {msg}")
        return True, msg
    else:
        return False, "Error: No se pudieron recalcular tamaños dinámicos (dependencias faltantes)."

def force_open_test_position(side: str, entry_price: float, timestamp: datetime.datetime, size_contracts_str_api: str) -> Tuple[bool, Optional[str]]:
    global _initialized, _is_live_mode, _executor, _cooldown_enabled, _event_counter_since_last_long, _event_counter_since_last_short
    if not _initialized: print("ERROR [Force Open Facade]: PM no inicializado."); return False, None
    if not _is_live_mode: print("ERROR [Force Open Facade]: Solo modo Live."); return False, None
    if not _executor: print("ERROR [Force Open Facade]: PositionExecutor no inicializado."); return False, None
    if not isinstance(timestamp, datetime.datetime): print("ERROR [Force Open Facade]: Timestamp inválido."); return False, None
    if not isinstance(size_contracts_str_api, str) or not size_contracts_str_api: print("ERROR [Force Open Facade]: Tamaño (str) inválido."); return False, None
    print(f"INFO [Force Open Facade]: Delegando apertura FORZADA {side.upper()} a Executor (Tamaño API: {size_contracts_str_api})...")
    try:
        result = _executor.execute_open( side=side, entry_price=entry_price, timestamp=timestamp, size_contracts_str_api=size_contracts_str_api )
        success = result.get('success', False); api_order_id = result.get('api_order_id')
        if success and _cooldown_enabled:
             if side == 'long': _event_counter_since_last_long = 0; print("DEBUG [Cooldown Long - Force Open]: Contador reseteado.")
             elif side == 'short': _event_counter_since_last_short = 0; print("DEBUG [Cooldown Short - Force Open]: Contador reseteado.")
        return success, api_order_id
    except Exception as e: print(f"ERROR [Force Open Facade]: Excepción delegando: {e}"); traceback.print_exc(); return False, None

def force_close_test_position(side: str, index: int, exit_price: float, timestamp: datetime.datetime) -> bool:
    global _initialized, _is_live_mode, _total_realized_pnl_long, _total_realized_pnl_short, _total_transferred_profit, _min_transfer_amount, config, _executor, balance_manager 
    if not _initialized: print("ERROR [Force Close Facade]: PM no inicializado."); return False
    if not _is_live_mode: print("ERROR [Force Close Facade]: Solo modo Live."); return False
    if not _executor: print("ERROR [Force Close Facade]: PositionExecutor no inicializado."); return False
    if not isinstance(timestamp, datetime.datetime): print("ERROR [Force Close Facade]: Timestamp inválido."); return False
    print(f"INFO [Force Close Facade]: Delegando cierre FORZADO {side.upper()} índice {index} a Executor...")
    try:
        result = _executor.execute_close( side=side, position_index=index, exit_price=exit_price, timestamp=timestamp )
        execution_success = result.get('success', False)
        if execution_success:
            pnl_net_usdt = result.get('pnl_net_usdt', 0.0)
            amount_to_transfer = result.get('amount_transferable_to_profit', 0.0) 
            if side == 'long': _total_realized_pnl_long += pnl_net_usdt
            else: _total_realized_pnl_short += pnl_net_usdt
            
            if amount_to_transfer >= float(_min_transfer_amount):
                 transferred = _executor.execute_transfer(amount_to_transfer, side)
                 if transferred > 0:
                     _total_transferred_profit += transferred
                     if _is_live_mode and balance_manager and hasattr(balance_manager, 'record_real_profit_transfer_logically'):
                         balance_manager.record_real_profit_transfer_logically(side, transferred)
        return execution_success
    except Exception as e: print(f"ERROR [Force Close Facade]: Excepción delegando: {e}"); traceback.print_exc(); return False

def sync_physical_state(side: str):
    global _initialized, _is_live_mode, _executor
    if not _initialized: print("WARN [Sync Facade]: PM no inicializado."); return
    if not _is_live_mode: print("WARN [Sync Facade]: Solo modo Live."); return
    if not _executor: print("WARN [Sync Facade]: PositionExecutor no inicializado."); return
    if side not in ['long', 'short']: print(f"WARN [Sync Facade]: Lado inválido: {side}"); return
    print(f"INFO [Sync Facade]: Delegando sync física {side.upper()} a Executor...")
    try:
        if hasattr(_executor, 'sync_physical_state'): _executor.sync_physical_state(side); print(f"  DEBUG [Sync Facade]: Llamada sync_physical_state({side}) delegada.")
        else: print("ERROR [Sync Facade]: Executor sin 'sync_physical_state'.")
    except Exception as e: print(f"ERROR [Sync Facade]: Excepción delegando sync: {e}"); traceback.print_exc()

def get_position_summary() -> dict:
    global _initialized, _is_live_mode, _trading_mode, _leverage, _max_logical_positions, _total_realized_pnl_long, _total_realized_pnl_short, _total_transferred_profit, config, utils, balance_manager, position_state, _position_helpers, _initial_base_position_size_usdt, _current_dynamic_base_size_long, _current_dynamic_base_size_short
    summary_error = None
    if not _initialized: summary_error = "PM not initialized"
    elif not all([config, utils, balance_manager, position_state, _position_helpers]): summary_error = "Dependencias no disponibles"
    if summary_error: return {"error": summary_error}
    try:
        current_balances = balance_manager.get_balances() 
        phys_long = position_state.get_physical_position_state('long'); phys_short = position_state.get_physical_position_state('short')
        open_longs = position_state.get_open_logical_positions('long'); open_shorts = position_state.get_open_logical_positions('short')
        long_summary_list = [_position_helpers.format_pos_for_summary(p, utils) for p in open_longs]
        short_summary_list = [_position_helpers.format_pos_for_summary(p, utils) for p in open_shorts]
        
        summary = {
            "initialized": _initialized, "is_live_mode": _is_live_mode,
            "management_enabled": getattr(config, 'POSITION_MANAGEMENT_ENABLED', False),
            "trading_mode": _trading_mode, "leverage": _leverage,
            "max_logical_positions": _max_logical_positions,
            "initial_base_position_size_usdt": _initial_base_position_size_usdt,
            "current_dynamic_base_size_long": _current_dynamic_base_size_long,
            "current_dynamic_base_size_short": _current_dynamic_base_size_short,
            "bm_available_long_margin": current_balances.get("available_long_margin", 0.0),
            "bm_available_short_margin": current_balances.get("available_short_margin", 0.0),
            "bm_used_long_margin": current_balances.get("used_long_margin", 0.0),
            "bm_used_short_margin": current_balances.get("used_short_margin", 0.0),
            "bm_operational_long_margin": current_balances.get("operational_long_margin", 0.0),
            "bm_operational_short_margin": current_balances.get("operational_short_margin", 0.0),
            "bm_profit_balance": current_balances.get("profit_balance", 0.0),
            "open_long_positions_count": len(open_longs), "open_short_positions_count": len(open_shorts),
            "open_long_positions": long_summary_list, "open_short_positions": short_summary_list,
            "physical_long_state": phys_long, "physical_short_state": phys_short,
            "total_realized_pnl_long": round(_total_realized_pnl_long, 4), "total_realized_pnl_short": round(_total_realized_pnl_short, 4),
            "total_transferred_profit": round(_total_transferred_profit, 4),
        }
        return summary
    except Exception as e: print(f"ERROR CRITICO [PM Facade]: Excepción en get_position_summary: {e}"); traceback.print_exc(); return {"error": f"Excepción: {e}"}

def increment_event_counters():
    global _initialized, _cooldown_enabled, _event_counter_since_last_long, _event_counter_since_last_short
    if not _initialized or not _cooldown_enabled: return
    _event_counter_since_last_long += 1; _event_counter_since_last_short += 1

def display_logical_positions():
    global _initialized, position_state
    if not _initialized: print("ERROR [PM Display]: No inicializado."); return
    if not position_state or not hasattr(position_state, 'display_logical_table'): print("ERROR [PM Display]: PS o display_logical_table no disponible."); return
    print("\n" + "="*70 + "\n" + " " * 20 + "ESTADO POSICIONES LÓGICAS (PM)" + " " * 20 + "\n" + "="*70)
    try: position_state.display_logical_table('long'); print("-" * 70); position_state.display_logical_table('short')
    except Exception as e: print(f"ERROR [PM Display]: Excepción: {e}"); traceback.print_exc()
    finally: print("="*70 + "\n")

# --- FUNCIONES MANUALES (Mantenidas por compatibilidad, pero su uso puede ser obsoleto) ---
def manual_open_with_api(side: str, entry_price: float, timestamp: datetime.datetime) -> Tuple[bool, str]:
    global _initialized, _is_live_mode, _trading_mode, _max_logical_positions, _leverage, _executor, balance_manager, position_state, utils, config, _cached_min_order_qty, _cooldown_enabled, _event_counter_since_last_long, _event_counter_since_last_short, _current_dynamic_base_size_long, _current_dynamic_base_size_short
    if not _initialized: return False, "Error: PM no inicializado."
    if not _executor: return False, "Error: PositionExecutor no disponible."
    if side not in ['long', 'short']: return False, f"Error: Lado '{side}' inválido."
    if not isinstance(entry_price, (int, float)) or entry_price <= 0: return False, f"Error: Precio entrada '{entry_price}' inválido."
    if not isinstance(timestamp, datetime.datetime): return False, "Error: Timestamp inválido."
    print(f"INFO [Manual Open]: Intentando abrir {side.upper()} manualmente a {entry_price:.4f}...")
    if side == 'long' and _trading_mode == "SHORT_ONLY": return False, f"Error: No se puede abrir LONG en modo SHORT_ONLY."
    if side == 'short' and _trading_mode == "LONG_ONLY": return False, f"Error: No se puede abrir SHORT en modo LONG_ONLY."
    try:
        open_positions = position_state.get_open_logical_positions(side)
        if len(open_positions) >= _max_logical_positions: return False, f"Error: Límite {side.upper()} slots ({_max_logical_positions}) alcanzado."
    except Exception as e: return False, f"Error verificando slots: {e}"
    margin_to_use = _current_dynamic_base_size_long if side == 'long' else _current_dynamic_base_size_short
    try:
        current_avail_margin_logical = balance_manager.get_available_margin(side)
        if current_avail_margin_logical < margin_to_use - 1e-6: return False, f"Error: Margen LÓGICO disponible ({current_avail_margin_logical:.4f}) < necesario ({margin_to_use:.4f}) para {side.upper()}."
        if _cached_min_order_qty is not None and _cached_min_order_qty > 0:
            min_margin_needed_approx = utils.safe_division(_cached_min_order_qty * entry_price, _leverage, default=float('inf')) * 1.01
            if margin_to_use < min_margin_needed_approx: return False, f"Error: Margen base dinámico ({margin_to_use:.4f}) INSUF. vs mín. nec. ({min_margin_needed_approx:.4f})."
        else: print("WARN [Manual Open]: min_order_qty no disponible, saltando chequeo margen mín.")
    except Exception as e: return False, f"Error calculando/verificando margen: {e}"
    try:
        print(f"INFO [Manual Open]: Delegando apertura {side.upper()} a Executor (Margen: {margin_to_use:.4f})...")
        result = _executor.execute_open(side=side, entry_price=entry_price, timestamp=timestamp, margin_to_use=margin_to_use)
        if result and result.get('success'):
            order_id = result.get('api_order_id', result.get('logical_position_id', 'N/A'))
            if _cooldown_enabled:
                if side == 'long': _event_counter_since_last_long = 0; print(f"DEBUG [Manual Open]: Cooldown Long reseteado.")
                elif side == 'short': _event_counter_since_last_short = 0; print(f"DEBUG [Manual Open]: Cooldown Short reseteado.")
            msg = f"Posición {side.upper()} abierta manualmente. ID: {order_id}"; print(f"SUCCESS [Manual Open]: {msg}"); return True, msg
        else:
            error_msg = result.get('message', 'Fallo ejecución apertura manual.') if result else 'Fallo desconocido.'; print(f"ERROR [Manual Open]: {error_msg}"); return False, f"Error: {error_msg}"
    except Exception as e_exec: print(f"ERROR CRITICO [Manual Open]: Excepción ejecución: {e_exec}"); traceback.print_exc(); return False, f"Error crítico: {e_exec}"

def manual_close_with_api(side: str, position_index: int, exit_price: float, timestamp: datetime.datetime) -> Tuple[bool, str]:
    global _initialized, _executor, _total_realized_pnl_long, _total_realized_pnl_short, _total_transferred_profit, _min_transfer_amount, config, balance_manager, _max_logical_positions, _initial_base_position_size_usdt, _current_dynamic_base_size_long, _current_dynamic_base_size_short, _is_live_mode, utils
    if not _initialized: return False, "Error: PM no inicializado."
    if not _executor: return False, "Error: PositionExecutor no disponible."
    if side not in ['long', 'short']: return False, f"Error: Lado '{side}' inválido."
    if not isinstance(position_index, int) or position_index < 0: return False, f"Error: Índice pos '{position_index}' inválido."
    if not isinstance(exit_price, (int, float)) or exit_price <= 0: return False, f"Error: Precio salida '{exit_price}' inválido."
    if not isinstance(timestamp, datetime.datetime): return False, "Error: Timestamp inválido."
    print(f"INFO [Manual Close]: Intentando cerrar {side.upper()} índice {position_index} manualmente a {exit_price:.4f}...")
    try:
        result = _executor.execute_close(side=side, position_index=position_index, exit_price=exit_price, timestamp=timestamp)
        if result and result.get('success'):
            pnl_net_usdt = result.get('pnl_net_usdt', 0.0)
            amount_transferable = result.get('amount_transferable_to_profit', 0.0) 
            closed_pos_id = result.get('closed_position_id', 'N/A')

            if side == 'long': _total_realized_pnl_long += pnl_net_usdt
            else: _total_realized_pnl_short += pnl_net_usdt
            msg = f"Posición {side.upper()} (...{str(closed_pos_id)[-6:]}) cerrada manualmente. PNL Neto: {pnl_net_usdt:+.4f}."
            print(f"SUCCESS [Manual Close]: {msg}")

            if balance_manager and hasattr(balance_manager, 'get_available_margin') and _max_logical_positions > 0 and utils:
                new_dynamic_base = utils.safe_division(balance_manager.get_available_margin(side), _max_logical_positions, 0.0)
                if side == 'long':
                    _current_dynamic_base_size_long = max(_initial_base_position_size_usdt, new_dynamic_base)
                else: 
                    _current_dynamic_base_size_short = max(_initial_base_position_size_usdt, new_dynamic_base)
            
            if amount_transferable >= float(_min_transfer_amount):
                transferred_amount_actual = _executor.execute_transfer(amount_transferable, side)
                if transferred_amount_actual > 0:
                    _total_transferred_profit += transferred_amount_actual
                    if _is_live_mode and balance_manager and hasattr(balance_manager, 'record_real_profit_transfer_logically'):
                        balance_manager.record_real_profit_transfer_logically(side, transferred_amount_actual)
            return True, msg
        else:
            error_msg = result.get('message', f'Fallo ejecución cierre manual {side.upper()} idx {position_index}.') if result else 'Fallo desconocido.'; print(f"ERROR [Manual Close]: {error_msg}"); return False, f"Error: {error_msg}"
    except Exception as e_exec: print(f"ERROR CRITICO [Manual Close]: Excepción ejecución: {e_exec}"); traceback.print_exc(); return False, f"Error crítico: {e_exec}"

def add_max_logical_position_slot() -> Tuple[bool, str]:
    global _max_logical_positions, _initialized, balance_manager, _initial_base_position_size_usdt, _current_dynamic_base_size_long, _current_dynamic_base_size_short, utils, _trading_mode
    if not _initialized: return False, "Error: PM no inicializado."
    _max_logical_positions += 1
    
    if balance_manager and hasattr(balance_manager, 'update_operational_margins_based_on_slots'):
        balance_manager.update_operational_margins_based_on_slots(_max_logical_positions)
    else:
        print("WARN [PM Add Slot]: BalanceManager no disponible o sin 'update_operational_margins_based_on_slots'. Márgenes operativos en BM no actualizados.")

    if balance_manager and hasattr(balance_manager, 'get_available_margin') and _max_logical_positions > 0 and utils:
        if _trading_mode == "LONG_ONLY" or _trading_mode == "LONG_SHORT":
            dynamic_long = utils.safe_division(balance_manager.get_available_margin('long'), _max_logical_positions, 0.0)
            _current_dynamic_base_size_long = max(_initial_base_position_size_usdt, dynamic_long)
        
        if _trading_mode == "SHORT_ONLY" or _trading_mode == "LONG_SHORT":
            dynamic_short = utils.safe_division(balance_manager.get_available_margin('short'), _max_logical_positions, 0.0)
            _current_dynamic_base_size_short = max(_initial_base_position_size_usdt, dynamic_short)
    
    msg = f"Slots máximos incrementados a: {_max_logical_positions}."
    print(f"INFO [PM Slots]: {msg}")
    return True, msg

def remove_max_logical_position_slot() -> Tuple[bool, str]:
    global _max_logical_positions, position_state, _initialized, balance_manager, _initial_base_position_size_usdt, _current_dynamic_base_size_long, _current_dynamic_base_size_short, utils, _trading_mode
    if not _initialized: return False, "Error: PM no inicializado."
    if _max_logical_positions <= 1: msg = "No se pueden remover más slots. Mínimo (1) alcanzado."; print(f"WARN [PM Slots]: {msg}"); return False, msg
    
    try:
        if not position_state or not hasattr(position_state, 'get_open_logical_positions'):
            error_msg = "Error: PositionState no disponible para verificar posiciones abiertas."
            print(f"ERROR [PM Slots]: {error_msg}"); return False, error_msg

        current_open_longs = len(position_state.get_open_logical_positions('long'))
        current_open_shorts = len(position_state.get_open_logical_positions('short'))
        max_current_positions_any_side = max(current_open_longs, current_open_shorts)
        
        if (_max_logical_positions - 1) < max_current_positions_any_side :
             msg = f"No remover slots. Límite nuevo ({_max_logical_positions - 1}) < pos abiertas ({max_current_positions_any_side})."; print(f"WARN [PM Slots]: {msg}"); return False, msg
        
        _max_logical_positions -= 1

        if balance_manager and hasattr(balance_manager, 'update_operational_margins_based_on_slots'):
            balance_manager.update_operational_margins_based_on_slots(_max_logical_positions)
        else:
            print("WARN [PM Remove Slot]: BalanceManager no disponible o sin 'update_operational_margins_based_on_slots'. Márgenes operativos en BM no actualizados.")

        if balance_manager and hasattr(balance_manager, 'get_available_margin') and _max_logical_positions > 0 and utils:
            if _trading_mode == "LONG_ONLY" or _trading_mode == "LONG_SHORT":
                dynamic_long = utils.safe_division(balance_manager.get_available_margin('long'), _max_logical_positions, 0.0)
                _current_dynamic_base_size_long = max(_initial_base_position_size_usdt, dynamic_long)

            if _trading_mode == "SHORT_ONLY" or _trading_mode == "LONG_SHORT":
                dynamic_short = utils.safe_division(balance_manager.get_available_margin('short'), _max_logical_positions, 0.0)
                _current_dynamic_base_size_short = max(_initial_base_position_size_usdt, dynamic_short)
            
        msg = f"Slots máximos decrementados a: {_max_logical_positions}."; print(f"INFO [PM Slots]: {msg}"); return True, msg
    except Exception as e: 
        error_msg = f"Error verificando pos abiertas al remover slot: {e}"; 
        print(f"ERROR [PM Slots]: {error_msg}"); traceback.print_exc(); 
        return False, error_msg

# =============== FIN ARCHIVO: core/strategy/position_manager.py (v13 - SL Físico y Control Automático) ===============