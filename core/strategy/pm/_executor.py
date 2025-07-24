"""
Clase PositionExecutor: Encapsula y centraliza la lógica de ejecución de
operaciones de mercado (apertura/cierre) y sincronización de estado.

v22.0 (Refactor de Hitos):
- `execute_open` ahora acepta `sl_pct` como argumento para permitir que el
  PositionManager delegue los parámetros de riesgo de la tendencia activa.
"""
import datetime
import uuid
import time
import traceback
import json
from typing import Optional, Dict, Any

try:
    from core.logging import memory_logger
    from core.exchange import AbstractExchange, StandardOrder
except ImportError:
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    class AbstractExchange: pass
    class StandardOrder: pass

class PositionExecutor:
    """
    Clase responsable de la ejecución mecánica de apertura y cierre de posiciones
    y de la sincronización del estado físico a través de una interfaz de exchange.
    """
    def __init__(self,
                 config: Any,
                 utils: Any,
                 balance_manager: Any,
                 position_state: Any,
                 state_manager: Any,
                 exchange_adapter: AbstractExchange,
                 calculations: Any,
                 helpers: Any,
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
        self._exchange = exchange_adapter
        self._calculations = calculations
        self._helpers = helpers
        self._closed_position_logger = closed_position_logger
        
        # --- Cacheo de configuraciones para acceso rápido ---
        self._symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
        self._price_prec = int(getattr(config, 'PRICE_PRECISION', 4))
        self._pnl_prec = int(getattr(config, 'PNL_PRECISION', 2))
        
        memory_logger.log("[PositionExecutor] Inicializado.", level="INFO")

    def execute_open(self, side: str, entry_price: float, timestamp: datetime.datetime, margin_to_use: float, sl_pct: float) -> Dict[str, Any]:
        """Orquesta la apertura de una posición a través de la interfaz de exchange."""
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
                is_live=True,
                exchange_adapter=self._exchange
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
        
        # El `sl_pct` ahora viene como argumento, delegado desde la tendencia activa.
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
            order_to_place = StandardOrder(
                symbol=self._symbol,
                side="buy" if side == 'long' else "sell",
                order_type="market",
                quantity_contracts=float(size_contracts_str),
                reduce_only=False
            )
            
            account_purpose = 'longs' if side == 'long' else 'shorts'
            success, order_id_or_error = self._exchange.place_order(order_to_place, account_purpose=account_purpose)
            
            if success:
                execution_success = True
                api_order_id = order_id_or_error
                memory_logger.log(f"  -> ÉXITO EXCHANGE: Orden Market aceptada. OrderID: {api_order_id}")
                self._balance_manager.decrease_used_margin(side, margin_to_use)
            else:
                result['message'] = f"Fallo en Exchange al colocar orden Market: {order_id_or_error}"
                memory_logger.log(f"  -> ERROR EXCHANGE: {result['message']}", level="ERROR")
        except Exception as exec_err:
            result['message'] = f"Excepción durante ejecución de orden: {exec_err}"
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
        
        result['api_order_id'] = api_order_id
        return result

    def execute_close(self, side: str, position_index: int, exit_price: float, timestamp: datetime.datetime, exit_reason: str = "UNKNOWN") -> Dict[str, Any]:
        """Orquesta el cierre de una posición a través de la interfaz de exchange."""
        result = {'success': False, 'pnl_net_usdt': 0.0, 'message': 'Error no especificado'}
        memory_logger.log(f"CLOSE [{side.upper()} Idx:{position_index}] -> Solicitud para cerrar @ {exit_price:.{self._price_prec}f} (Razón: {exit_reason})", level="INFO")

        open_positions = self._position_state.get_open_logical_positions(side)
        if not (0 <= position_index < len(open_positions)):
            result['message'] = f"Índice {position_index} fuera de rango."
            return result
        
        pos_to_close = open_positions[position_index]
        size_to_close_float = self._utils.safe_float_convert(pos_to_close.get('size_contracts'), 0.0)
        
        format_qty_result = self._helpers.format_quantity_for_api(size_to_close_float, self._symbol, is_live=True, exchange_adapter=self._exchange)
        if not format_qty_result['success']:
            result['message'] = f"Error formateando cantidad para API: {format_qty_result['error']}"
            return result
        size_to_close_str = format_qty_result['qty_str']
        
        execution_success = False
        try:
            order_to_close = StandardOrder(
                symbol=self._symbol,
                side="sell" if side == 'long' else "buy",
                order_type="market",
                quantity_contracts=float(size_to_close_str),
                reduce_only=True
            )
            
            account_purpose = 'longs' if side == 'long' else 'shorts'
            success, response_msg = self._exchange.place_order(order_to_close, account_purpose=account_purpose)
            
            if success:
                execution_success = True
            else:
                # Comprobar si el error es porque la posición ya no existe
                if "position does not exist" in response_msg.lower() or "110001" in response_msg:
                    execution_success = True # Consideramos éxito si la posición ya está cerrada.
                    memory_logger.log(f"WARN [Exec Close]: Posición no encontrada en el exchange ({response_msg}). Asumiendo ya cerrada.", level="WARN")
                else:
                    result['message'] = f"Fallo en Exchange al colocar orden de cierre: {response_msg}"
        except Exception as e:
            result['message'] = f"Excepción durante ejecución de cierre: {e}"

        if execution_success:
            removed_pos = self._position_state.remove_logical_position(side, position_index)
            if not removed_pos:
                result['message'] = "Ejecución en Exchange OK pero falló al remover posición lógica."
                memory_logger.log(f"ERROR SEVERE [Exec Close]: {result['message']}", level="ERROR")
                return result

            calc_res = self._calculations.calculate_pnl_commission_reinvestment(
                side, removed_pos['entry_price'], exit_price, removed_pos['size_contracts']
            )
            result.update(calc_res)
            
            margin_to_return = removed_pos['margin_usdt'] + calc_res.get('amount_reinvested_in_operational_margin', 0.0)
            self._balance_manager.increase_available_margin(side, margin_to_return)

            open_positions_now = self._position_state.get_open_logical_positions(side)
            if open_positions_now:
                aggs = self._calculations.calculate_physical_aggregates(open_positions_now)
                leverage = self._state_manager.get_leverage()
                liq = self._calculations.calculate_liquidation_price(side, aggs['avg_entry_price'], leverage)
                self._position_state.update_physical_position_state(side, **aggs, liq_price=liq, timestamp=timestamp)
            else:
                self._position_state.reset_physical_position_state(side)
            
            if self._closed_position_logger and removed_pos:
                log_data = {**removed_pos, **calc_res, "exit_price": exit_price, "exit_timestamp": timestamp, "exit_reason": exit_reason}
                self._closed_position_logger.log_closed_position(log_data)
            
            result['success'] = True
            result['message'] = f"Cierre {side.upper()} idx {position_index} exitoso."
        
        return result

    def sync_physical_state(self, side: str):
        """Sincroniza el estado físico interno con el real del exchange."""
        try:
            account_purpose = 'longs' if side == 'long' else 'shorts'
            standard_positions = self._exchange.get_positions(self._symbol, account_purpose=account_purpose)
            if standard_positions is None: return

            positions_for_side = [p for p in standard_positions if p.side == side]
            
            state_data = self._helpers.extract_physical_state_from_standard_positions(positions_for_side, self._utils)
            
            if state_data:
                self._position_state.update_physical_position_state(side=side, **state_data)
            else:
                self._position_state.reset_physical_position_state(side)
        except Exception as e:
            memory_logger.log(f"ERROR [Sync State]: Excepción sincronizando {side.upper()}: {e}", level="ERROR")