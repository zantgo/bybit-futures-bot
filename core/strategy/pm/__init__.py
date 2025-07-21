"""
Fachada Principal y Orquestador del Position Manager (PM).

Este archivo __init__.py es el punto de entrada para el flujo de trabajo principal
del bot. Expone las funciones de alto nivel necesarias para la inicialización y
el procesamiento de ticks, y delega la lógica a los módulos internos.

La API pública para control externo (TUI) se expone a través del módulo `api`.
"""
import sys
import os
import datetime
from typing import Optional, Dict, Any

# --- Guardián de sys.path para importaciones robustas ---
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# --- Exposición de la API Pública para consumidores externos (TUI) ---
from . import _api as api

# --- Dependencias Externas al Paquete ---
try:
    import config
    from core import utils
    # --- SOLUCIÓN: Corregir la importación de 'api' ---
    from core import api as live_operations
    # --- FIN DE LA SOLUCIÓN ---
    from core.logging import memory_logger, closed_position_logger
    from connection import manager as live_manager
except ImportError as e:
    print(f"ERROR CRÍTICO [PM __init__]: Falló importación de dependencias externas: {e}")
    # Definir dummies para evitar fallos catastróficos
    config=None; utils=None; live_operations=None; memory_logger=None;
    closed_position_logger=None; live_manager=None

# --- Módulos Internos del Paquete ---
try:
    from . import _state
    from . import _rules
    from . import _actions
    from . import _balance
    from . import _position_state
    from ._executor import PositionExecutor
    from . import _helpers
    from . import _calculations
except ImportError as e:
    print(f"ERROR CRÍTICO [PM __init__]: Falló importación de módulos internos del PM: {e}")
    _state=None; _rules=None; _actions=None; _balance=None;
    _position_state=None; PositionExecutor=None; _helpers=None;
    _calculations=None


# --- Funciones del Orquestador Principal ---

def initialize(
    operation_mode: str,
    initial_real_state: Optional[Dict[str, Dict[str, Any]]] = None,
    base_position_size_usdt_param: Optional[float] = None,
    initial_max_logical_positions_param: Optional[int] = None,
    stop_loss_event: Optional[Any] = None
):
    """
    Inicializa todos los componentes del Position Manager.
    Esta función es llamada una vez al inicio de la sesión del bot.
    """
    if not all([config, memory_logger, _state, PositionExecutor, _balance, _position_state]):
        print("ERROR CRÍTICO [PM initialize]: Faltan dependencias esenciales. No se puede continuar.")
        return

    if not getattr(config, 'POSITION_MANAGEMENT_ENABLED', False):
        print("[PM Facade] Inicialización omitida (Gestión de Posiciones Desactivada en config).")
        return

    memory_logger.log("PM Orquestador: Inicializando todos los componentes...", level="INFO")

    _state.reset_all_states()
    is_live = operation_mode == "live_interactive"

    base_size = base_position_size_usdt_param or getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0)
    max_pos = initial_max_logical_positions_param or getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1)

    # Inyección de dependencias al crear el Executor
    executor = PositionExecutor(
        is_live_mode=is_live,
        config=config,
        utils=utils,
        balance_manager=_balance,
        position_state=_position_state,
        position_calculations=_calculations,
        live_operations=live_operations,
        closed_position_logger=closed_position_logger,
        position_helpers=_helpers,
        live_manager=live_manager
    )

    # Configuración inicial del estado global del PM
    _state.set_initial_config(
        op_mode=operation_mode,
        live_mode=is_live,
        exec_instance=executor,
        lev=getattr(config, 'POSITION_LEVERAGE', 1.0),
        max_pos=max_pos,
        base_size=base_size,
        stop_event=stop_loss_event
    )

    # Inicialización de los gestores de balance y estado de posiciones
    real_balances_for_init = initial_real_state
    if is_live and not real_balances_for_init and live_manager:
        memory_logger.log("PM Orquestador: Obteniendo balances reales para inicialización...", level="DEBUG")
        real_balances_for_init = {}
        initialized_accounts = live_manager.get_initialized_accounts()
        if initialized_accounts:
            for acc_name in initialized_accounts:
                real_balances_for_init[acc_name] = {
                    'unified_balance': live_operations.get_unified_account_balance_info(acc_name)
                }

    _balance.initialize(operation_mode, real_balances_for_init, base_size, max_pos)
    _position_state.initialize_state(
        is_live_mode=is_live,
        config_dependency=config,
        utils_dependency=utils,
        live_ops_dependency=live_operations
    )

    _state.set_initialized(True)
    memory_logger.log("PM Orquestador: Todos los componentes han sido inicializados.", level="INFO")


def handle_low_level_signal(signal: str, entry_price: float, timestamp: datetime.datetime, market_context: str = "UNKNOWN"):
    """
    Punto de entrada para señales desde el `event_processor`.
    Delega la lógica a los módulos de reglas y acciones.
    """
    if not _state or not _state.is_initialized(): return
    
    operation_mode = _state.get_operation_mode()

    if operation_mode == "live_interactive":
        manual_mode = _state.get_manual_state()["mode"]
        side_to_open = 'long' if signal == "BUY" else 'short'
        
        side_allowed = (side_to_open == 'long' and manual_mode in ["LONG_ONLY", "LONG_SHORT"]) or \
                       (side_to_open == 'short' and manual_mode in ["SHORT_ONLY", "LONG_SHORT"])
        
        if side_allowed and _rules.can_open_new_position(side_to_open):
            _actions.open_logical_position(side_to_open, entry_price, timestamp)
    
    # --- [LÓGICA OBSOLETA COMENTADA] ---
    # La siguiente sección corresponde al modo automático/backtest y ha sido comentada
    # según lo solicitado para la simplificación del bot al modo live_interactive.
    # else: 
    #     trend_state = _state.get_trend_state()
    #     if trend_state["tp_hit"]:
    #          return
    #     
    #     # Lógica específica de modo automático...


def check_and_close_positions(current_price: float, timestamp: datetime.datetime):
    """
    Revisa Stop Loss y Trailing Stop para todas las posiciones abiertas.
    Llamado en cada tick por el `event_processor`.
    """
    if not _state or not _state.is_initialized(): return

    for side in ['long', 'short']:
        open_positions = _position_state.get_open_logical_positions(side)
        if not open_positions:
            continue

        indices_to_close = []
        reasons_for_close = {}
        for i, pos in enumerate(open_positions):
            entry_price, pos_id = pos.get('entry_price'), pos.get('id')
            if not pos_id or not entry_price:
                continue

            # 1. Comprobar Stop Loss Fijo
            sl_price = pos.get('stop_loss_price')
            if sl_price and ((side == 'long' and current_price <= sl_price) or \
                             (side == 'short' and current_price >= sl_price)):
                indices_to_close.append(i)
                reasons_for_close[i] = "SL"
                continue

            # 2. Comprobar y actualizar Trailing Stop
            is_ts_active = pos.get('ts_is_active', False)
            ts_params = _state.get_trailing_stop_params()
            activation_pct, distance_pct = ts_params['activation'], ts_params['distance']

            if not is_ts_active:
                if activation_pct > 0:
                    activation_price = entry_price * (1 + activation_pct / 100.0) if side == 'long' \
                                       else entry_price * (1 - activation_pct / 100.0)
                    if (side == 'long' and current_price >= activation_price) or \
                       (side == 'short' and current_price <= activation_price):
                        pos.update({
                            'ts_is_active': True,
                            'ts_peak_price': current_price,
                            'ts_stop_price': current_price * (1 - distance_pct / 100.0) if side == 'long' \
                                               else current_price * (1 + distance_pct / 100.0)
                        })
                        _position_state.update_logical_position_details(side, pos_id, pos)
            else:
                peak_price = pos.get('ts_peak_price')
                stop_price = pos.get('ts_stop_price')
                if peak_price is None or stop_price is None:
                    continue

                if (side == 'long' and current_price > peak_price) or \
                   (side == 'short' and current_price < peak_price):
                    pos.update({
                        'ts_peak_price': current_price,
                        'ts_stop_price': current_price * (1 - distance_pct / 100.0) if side == 'long' \
                                           else current_price * (1 + distance_pct / 100.0)
                    })
                    _position_state.update_logical_position_details(side, pos_id, pos)

                if (side == 'long' and current_price <= stop_price) or \
                   (side == 'short' and current_price >= stop_price):
                    indices_to_close.append(i)
                    reasons_for_close[i] = "TS"

        # Cerrar posiciones marcadas
        for index in sorted(list(set(indices_to_close)), reverse=True):
            _actions.close_logical_position(
                side,
                index,
                current_price,
                timestamp,
                reason=reasons_for_close.get(index, "UNKNOWN")
            )