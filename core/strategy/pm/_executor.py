"""
Clase PositionExecutor: Encapsula y centraliza la lógica de ejecución de
operaciones de mercado (apertura/cierre) y sincronización de estado.

v20.0 (Clean Architecture Refactor):
- Adaptado para recibir instancias de BalanceManager y PositionState.
- Eliminada la lógica de backtesting para enfocarse en el modo 'live'.
"""
import datetime
import uuid
import time
import traceback
import json
from typing import Optional, Dict, Any

try:
    from core.logging import memory_logger
except ImportError:
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

class PositionExecutor:
    """
    Clase responsable de la ejecución mecánica de apertura y cierre de posiciones
    y de la sincronización del estado físico con la API.
    """
    def __init__(self,
                 config: Any,
                 utils: Any,
                 balance_manager: Any,      # Ahora es una instancia de BalanceManager
                 position_state: Any,       # Ahora es una instancia de PositionState
                 state_manager: Any,        # La nueva clase que contendrá el estado general
                 calculations: Any,
                 helpers: Any,
                 live_operations: Any,
                 connection_manager: Any,
                 closed_position_logger: Optional[Any] = None
                 ):
        """
        Inicializa el ejecutor con todas sus dependencias inyectadas.
        """
        # --- Inyección de Dependencias ---
        self._config = config
        self._utils = utils
        self._balance_manager = balance_manager
        self._position_state = position_state
        self._state_manager = state_manager
        self._calculations = calculations
        self._helpers = helpers
        self._live_operations = live_operations
        self._connection_manager = connection_manager
        self._closed_position_logger = closed_position_logger
        
        # --- Cacheo de configuraciones para acceso rápido ---
        self._symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
        self._price_prec = int(getattr(config, 'PRICE_PRECISION', 4))
        self._pnl_prec = int(getattr(config, 'PNL_PRECISION', 2))
        
        memory_logger.log("[PositionExecutor] Inicializado.", level="INFO")

    def execute_open(self, side: str, entry_price: float, timestamp: datetime.datetime, margin_to_use: float) -> Dict[str, Any]:
        """Orquesta la apertura de una posición en modo live."""
        result = {'success': False, 'api_order_id': None, 'logical_position_id': None, 'message': 'Error no especificado'}
        leverage = self._state_manager.get_leverage()

        memory_logger.log(f"OPEN [{side.upper()}] -> Solicitud para abrir @ {entry_price:.{self._price_prec}f}", level="INFO")

        # --- 1. Calcular Tamaño y Validar ---
        try:
            calc_qty_result = self._helpers.calculate_and_round_quantity(
                margin_usdt=margin_to_use, 
                entry_price=entry_price, 
                leverage=leverage, 
                symbol=self._symbol, 
                is_live=True
            )
            if not calc_qty_result['success']:
                result['message'] = calc_qty_result['error']
                memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR")
                return result
                
            size_contracts_float = calc_qty_result['qty_float']
            size_contracts_str = calc_qty_result['qty_str']
            qty_precision = calc_qty_result['precision']
            memory_logger.log(f"  Tamaño Calculado: {size_contracts_float:.{qty_precision}f} ({size_contracts_str} API), Margen: {margin_to_use:.4f} USDT", level="DEBUG")

        except Exception as e:
            result['message'] = f"Excepción calculando tamaño/margen: {e}"
            memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR")
            traceback.print_exc()
            return result
        
        # --- 2. Crear Datos de la Posición Lógica ---
        logical_position_id = str(uuid.uuid4())
        sl_pct = self._state_manager.get_individual_stop_loss_pct()
        stop_loss_price = self._calculations.calculate_stop_loss(side, entry_price, sl_pct)
        est_liq_price = self._calculations.calculate_liquidation_price(side, entry_price, leverage)
        
        new_position_data = {
            'id': logical_position_id, 'entry_timestamp': timestamp, 'entry_price': entry_price,
            'margin_usdt': margin_to_use, 'size_contracts': size_contracts_float,
            'leverage': leverage, 'stop_loss_price': stop_loss_price,
            'est_liq_price': est_liq_price, 'ts_is_active': False,
            'ts_peak_price': None, 'ts_stop_price': None, 'api_order_id': None
        }
        result['logical_position_id'] = logical_position_id

        # --- 3. Ejecutar Orden en el Exchange ---
        execution_success = False
        api_order_id = None
        try:
            account_to_use, _ = self._connection_manager.get_session_for_operation('trading', side=side)
            order_side_api = "Buy" if side == 'long' else "Sell"
            pos_idx = 1 if side == 'long' else 2

            api_response = self._live_operations.place_market_order(
                symbol=self._symbol, side=order_side_api, quantity=size_contracts_str,
                reduce_only=False, position_idx=pos_idx, account_name=account_to_use
            )
            
            if api_response and api_response.get('retCode') == 0:
                execution_success = True
                api_order_id = api_response.get('result', {}).get('orderId', 'N/A')
                memory_logger.log(f"  -> ÉXITO API: Orden Market aceptada. OrderID: {api_order_id}")
                self._balance_manager.decrease_used_margin(side, margin_to_use)
            else:
                ret_msg = api_response.get('retMsg', 'N/A') if api_response else 'No Response'
                result['message'] = f"Fallo API en orden Market: {ret_msg}"
                memory_logger.log(f"  -> ERROR API: {result['message']}", level="ERROR")
        except Exception as exec_err:
            result['message'] = f"Excepción durante ejecución: {exec_err}"
            memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR")

        # --- 4. Actualizar Estado Interno ---
        if execution_success:
            new_position_data['api_order_id'] = api_order_id
            add_ok = self._position_state.add_logical_position(side, new_position_data)
            if add_ok:
                open_positions = self._position_state.get_open_logical_positions(side)
                aggregates = self._calculations.calculate_physical_aggregates(open_positions)
                liq_agg = self._calculations.calculate_liquidation_price(side, aggregates['avg_entry_price'], leverage)
                self._position_state.update_physical_position_state(
                    side, aggregates.get('avg_entry_price', 0.0), aggregates.get('total_size_contracts', 0.0),
                    aggregates.get('total_margin_usdt', 0.0), liq_agg, timestamp
                )
                result['success'] = True
                result['message'] = f"Apertura {side.upper()} exitosa."
            else:
                result['message'] = "Ejecución OK pero falló al añadir posición lógicamente."
                memory_logger.log(f"ERROR SEVERE [Exec Open]: {result['message']}", level="ERROR")
                # Aquí se debería implementar lógica de compensación (cerrar la posición real)
        
        result['api_order_id'] = api_order_id
        return result

    def execute_close(self, side: str, position_index: int, exit_price: float, timestamp: datetime.datetime, exit_reason: str = "UNKNOWN") -> Dict[str, Any]:
        """Orquesta el cierre de una posición en modo live."""
        result = {'success': False, 'pnl_net_usdt': 0.0, 'message': 'Error no especificado'}
        memory_logger.log(f"CLOSE [{side.upper()} Idx:{position_index}] -> Solicitud para cerrar @ {exit_price:.{self._price_prec}f} (Razón: {exit_reason})", level="INFO")

        # --- 1. Obtener Datos de la Posición a Cerrar ---
        open_positions = self._position_state.get_open_logical_positions(side)
        if not (0 <= position_index < len(open_positions)):
            result['message'] = f"Índice {position_index} fuera de rango."
            return result
        
        pos_to_close = open_positions[position_index]
        size_to_close = self._utils.safe_float_convert(pos_to_close.get('size_contracts'), 0.0)
        
        format_qty_result = self._helpers.format_quantity_for_api(size_to_close, self._symbol, is_live=True)
        if not format_qty_result['success']:
            result['message'] = f"Error formateando cantidad para API: {format_qty_result['error']}"
            return result
        size_contracts_str = format_qty_result['qty_str']
        
        # --- 2. Ejecutar Orden en el Exchange ---
        execution_success = False
        api_ret_code = None
        try:
            account_to_use, _ = self._connection_manager.get_session_for_operation('trading', side=side)
            close_side_api = "Sell" if side == 'long' else "Buy"
            pos_idx = 1 if side == 'long' else 2

            api_response = self._live_operations.place_market_order(
                symbol=self._symbol, side=close_side_api, quantity=size_contracts_str,
                reduce_only=True, position_idx=pos_idx, account_name=account_to_use
            )
            
            if api_response: api_ret_code = api_response.get('retCode')
            if api_ret_code == 0:
                execution_success = True
            elif api_ret_code == 110001: # Posición no encontrada
                execution_success = True # Consideramos éxito para poder limpiar el estado lógico
                memory_logger.log("WARN [Exec Close]: Posición no encontrada en API (110001).", level="WARN")
            else:
                result['message'] = f"Fallo API en orden de cierre: {api_response.get('retMsg', 'N/A')}"
        except Exception as e:
            result['message'] = f"Excepción durante ejecución de cierre: {e}"

        # --- 3. Actualizar Estado Interno y Loguear ---
        if execution_success:
            removed_pos = self._position_state.remove_logical_position(side, position_index)
            if not removed_pos and api_ret_code != 110001:
                result['message'] = "Ejecución OK pero falló al remover posición lógica."
                memory_logger.log(f"ERROR SEVERE [Exec Close]: {result['message']}", level="ERROR")
                return result

            # Calcular PNL y reinversión
            calc_res = self._calculations.calculate_pnl_commission_reinvestment(
                side, removed_pos['entry_price'], exit_price, removed_pos['size_contracts']
            )
            result.update(calc_res) # Añade PNL, reinversión, etc.
            
            # Devolver margen al balance manager
            margin_to_return = removed_pos['margin_usdt'] + calc_res.get('amount_reinvested_in_operational_margin', 0.0)
            self._balance_manager.increase_available_margin(side, margin_to_return)

            # Recalcular estado físico
            open_positions_now = self._position_state.get_open_logical_positions(side)
            if open_positions_now:
                aggs = self._calculations.calculate_physical_aggregates(open_positions_now)
                leverage = self._state_manager.get_leverage()
                liq = self._calculations.calculate_liquidation_price(side, aggs['avg_entry_price'], leverage)
                self._position_state.update_physical_position_state(side, **aggs, liq_price=liq, timestamp=timestamp)
            else:
                self._position_state.reset_physical_position_state(side)
            
            # Loguear posición cerrada
            if self._closed_position_logger and removed_pos:
                log_data = {**removed_pos, **calc_res, "exit_price": exit_price, "exit_timestamp": timestamp, "exit_reason": exit_reason}
                self._closed_position_logger.log_closed_position(log_data)
            
            result['success'] = True
            result['message'] = f"Cierre {side.upper()} idx {position_index} exitoso."
        
        return result

    def sync_physical_state(self, side: str):
        """Sincroniza el estado físico interno con el real de la API."""
        try:
            account_to_use, _ = self._connection_manager.get_session_for_operation('trading', side=side)
            raw_positions = self._live_operations.get_active_position_details_api(self._symbol, account_to_use)
            if raw_positions is None: return

            state_data = self._helpers.extract_physical_state_from_api(raw_positions, self._symbol, side, self._utils)
            if state_data:
                self._position_state.update_physical_position_state(side=side, **state_data)
            else:
                self._position_state.reset_physical_position_state(side)
        except Exception as e:
            memory_logger.log(f"ERROR [Sync State]: Excepción sincronizando {side.upper()}: {e}", level="ERROR")