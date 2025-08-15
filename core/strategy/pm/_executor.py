import datetime, uuid, traceback
from typing import Optional, Dict, Any
from dataclasses import asdict

try:
    from core.logging import memory_logger
    from core.exchange import AbstractExchange, StandardOrder
    from core.strategy.entities import LogicalPosition, Operacion # Añadido Operacion para el type hint
except ImportError as e:
    print(f"ERROR FATAL [Executor Import]: {e}")
    def LogicalPosition(*args, **kwargs):
        raise ImportError("Fallo crítico importando LogicalPosition. Verifica la estructura de archivos.")
    class AbstractExchange: pass
    class StandardOrder: pass
    class Operacion: pass # Fallback
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

class PositionExecutor:
    """
    Clase responsable de la ejecución mecánica de apertura y cierre de posiciones
    y de la sincronización del estado físico a través de una interfaz de exchange.
    """
    def __init__(self,
                 config: Any,
                 utils: Any,
                 position_state: Any,
                 state_manager: Any,
                 exchange_adapter: AbstractExchange,
                 calculations: Any,
                 helpers: Any,
                 closed_position_logger: Optional[Any] = None
                 ):
        self._config = config
        self._utils = utils
        self._position_state = position_state
        self._state_manager = state_manager
        self._exchange = exchange_adapter
        self._calculations = calculations
        self._helpers = helpers
        self._closed_position_logger = closed_position_logger
        
        self._symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
        self._price_prec = self._config.PRECISION_FALLBACKS["PRICE_PRECISION"]
        self._pnl_prec = self._config.PRECISION_FALLBACKS["PNL_PRECISION"]
        
        memory_logger.log("[PositionExecutor] Inicializado.", level="INFO")

    def execute_open(self, side: str, entry_price: float, timestamp: datetime.datetime, margin_to_use: float, sl_pct: float, tsl_activation_pct: float, tsl_distance_pct: float) -> Dict[str, Any]:
        """Orquesta la apertura de una posición a través de la interfaz de exchange."""
        result = {'success': False, 'api_order_id': None, 'logical_position_object': None, 'message': 'Error no especificado'}
        
        operacion = self._state_manager._om_api.get_operation_by_side(side)
        if not operacion:
            result['message'] = f"Error: No se pudo obtener la operación para el lado '{side}'."
            return result
        
        leverage = operacion.apalancamiento

        memory_logger.log(f"OPEN [{side.upper()}] -> Solicitud para abrir @ {entry_price:.{self._price_prec}f}", level="INFO")

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
            memory_logger.log(traceback.format_exc(), level="ERROR")
            return result
        
        logical_position_id = str(uuid.uuid4())
        
        stop_loss_price = self._calculations.calculate_stop_loss(side, entry_price, sl_pct)
        est_liq_price = self._calculations.calculate_liquidation_price(side, entry_price, leverage)
        
        new_position_obj = LogicalPosition(
            id=logical_position_id,
            capital_asignado=margin_to_use,
            entry_timestamp=timestamp, 
            entry_price=entry_price,
            margin_usdt=margin_to_use,
            size_contracts=size_contracts_float,
            stop_loss_price=stop_loss_price,
            est_liq_price=est_liq_price, 
            tsl_activation_pct_at_open=tsl_activation_pct,
            tsl_distance_pct_at_open=tsl_distance_pct
        )
        result['logical_position_object'] = new_position_obj

        execution_success = False
        api_order_id = None
        
        if self._config.BOT_CONFIG["PAPER_TRADING_MODE"]:
            memory_logger.log(f"  -> MODO PAPEL: Simulación de orden Market aceptada.", "WARN")
            execution_success = True
            api_order_id = f"paper-open-{uuid.uuid4()}"
        else:
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
                else:
                    result['message'] = f"Fallo en Exchange al colocar orden Market: {order_id_or_error}"
                    memory_logger.log(f"  -> ERROR EXCHANGE: {result['message']}", level="ERROR")
            except Exception as exec_err:
                result['message'] = f"Excepción durante ejecución de orden: {exec_err}"

        if execution_success:
            new_position_obj.api_order_id = api_order_id
            result['success'] = True
            result['message'] = f"Apertura {side.upper()} exitosa."
        
        result['api_order_id'] = api_order_id
        return result

    def execute_close(self, position_to_close: LogicalPosition, side: str, exit_price: float, timestamp: datetime.datetime, exit_reason: str = "UNKNOWN") -> Dict[str, Any]:
        """Orquesta el cierre de una posición a través de la interfaz de exchange."""
        result = {'success': False, 'pnl_net_usdt': 0.0, 'message': 'Error no especificado'}
        
        pos_id_short = str(position_to_close.id)[-6:]
        memory_logger.log(f"CLOSE [{side.upper()} ID:{pos_id_short}] -> Solicitud para cerrar @ {exit_price:.{self._price_prec}f} (Razón: {exit_reason})", level="INFO")

        size_to_close_float = self._utils.safe_float_convert(position_to_close.size_contracts, 0.0)
        
        format_qty_result = self._helpers.format_quantity_for_api(size_to_close_float, self._symbol, is_live=True, exchange_adapter=self._exchange)
        if not format_qty_result['success']:
            result['message'] = f"Error formateando cantidad para API: {format_qty_result['error']}"
            return result
        size_to_close_str = format_qty_result['qty_str']
        
        execution_success = False
        
        if self._config.BOT_CONFIG["PAPER_TRADING_MODE"]:
            memory_logger.log(f"  -> MODO PAPEL: Simulación de orden de cierre aceptada para ID {pos_id_short}.", "WARN")
            execution_success = True
        else:
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
                    if "position does not exist" in response_msg.lower() or "110001" in response_msg:
                        execution_success = True
                        memory_logger.log(f"WARN [Exec Close]: Posición no encontrada en el exchange ({response_msg}). Asumiendo ya cerrada.", level="WARN")
                    else:
                        result['message'] = f"Fallo en Exchange al colocar orden de cierre: {response_msg}"
            except Exception as e:
                result['message'] = f"Excepción durante ejecución de cierre: {e}"

        if execution_success:
            removed_pos_dict = asdict(position_to_close)

            # --- INICIO DE LA MODIFICACIÓN ---
            # La función de cálculo ahora solo calcula las porciones. La decisión se toma aquí.
            calc_res = self._calculations.calculate_pnl_commission_reinvestment(
                side, removed_pos_dict['entry_price'], exit_price, removed_pos_dict['size_contracts']
            )

            # Obtenemos el objeto de operación para verificar si la reinversión está activada
            operacion = self._state_manager._om_api.get_operation_by_side(side)
            
            # Si la reinversión NO está activada, movemos todo al monto transferible
            if operacion and not operacion.auto_reinvest_enabled:
                if calc_res.get('pnl_net_usdt', 0.0) > 0:
                    # Sumamos la porción de reinversión a la de transferencia
                    calc_res['amount_transferable_to_profit'] += calc_res['amount_reinvested_in_operational_margin']
                    # Y ponemos a cero la de reinversión
                    calc_res['amount_reinvested_in_operational_margin'] = 0.0

            result.update(calc_res)
            # --- FIN DE LA MODIFICACIÓN ---
            
            if self._closed_position_logger and removed_pos_dict:
                log_data = {**removed_pos_dict, **calc_res, "exit_price": exit_price, "exit_timestamp": timestamp, "exit_reason": exit_reason}
                self._closed_position_logger.log_closed_position(log_data)
            
            result['success'] = True
            result['message'] = f"Cierre {side.upper()} ID {pos_id_short} exitoso."
        
        return result

    def sync_physical_state(self, side: str):
        """Sincroniza el estado físico interno con el real del exchange."""
        if self._config.BOT_CONFIG["PAPER_TRADING_MODE"]:
            return
        
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