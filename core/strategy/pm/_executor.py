"""
Clase PositionExecutor: Encapsula y centraliza la lógica de ejecución de
operaciones de mercado (apertura/cierre) y sincronización de estado.

v23.0 (Capital Lógico por Operación):
- Se elimina la dependencia del `balance_manager`. El `executor` ahora se centra
  únicamente en la interacción con el exchange y el cálculo de PNL.
- `execute_open` y `execute_close` ya no interactúan con el balance lógico;
  esa responsabilidad se ha trasladado al `_private_logic.py`.
"""
import datetime
import uuid
import traceback
# import json # Comentado, no usado en esta versión.
from typing import Optional, Dict, Any

try:
    from core.logging import memory_logger
    from core.exchange import AbstractExchange, StandardOrder
    # --- INICIO DE LA MODIFICACIÓN ---
    from .._entities import LogicalPosition # Se importa la clase LogicalPosition
    from dataclasses import asdict # Para convertir LogicalPosition a dict si es necesario
    # --- FIN DE LA MODIFICACIÓN ---
except ImportError:
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    class AbstractExchange: pass
    class StandardOrder: pass
    # --- INICIO DE LA MODIFICACIÓN ---
    class LogicalPosition: pass # Fallback para LogicalPosition
    def asdict(obj): return obj.__dict__ # Fallback básico para asdict
    # --- FIN DE LA MODIFICACIÓN ---

class PositionExecutor:
    """
    Clase responsable de la ejecución mecánica de apertura y cierre de posiciones
    y de la sincronización del estado físico a través de una interfaz de exchange.
    """
    def __init__(self,
                 config: Any,
                 utils: Any,
                 # --- INICIO DE LA MODIFICACIÓN ---
                 # balance_manager: Any, # Comentado/Eliminado: la dependencia del balance_manager
                 # --- FIN DE LA MODIFICACIÓN ---
                 position_state: Any,
                 state_manager: Any, # Es la instancia de PositionManager
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
        # --- INICIO DE LA MODIFICACIÓN ---
        # self._balance_manager = balance_manager # Comentado/Eliminado
        # --- FIN DE LA MODIFICACIÓN ---
        self._position_state = position_state
        self._state_manager = state_manager # PositionManager, que ahora gestiona el balance lógico a través de Operacion
        self._exchange = exchange_adapter
        self._calculations = calculations
        self._helpers = helpers
        self._closed_position_logger = closed_position_logger
        
        # --- Cacheo de configuraciones para acceso rápido ---
        self._symbol = getattr(config, 'TICKER_SYMBOL', 'N/A')
        self._price_prec = int(getattr(config, 'PRICE_PRECISION', 4))
        self._pnl_prec = int(getattr(config, 'PNL_PRECISION', 2))
        
        memory_logger.log("[PositionExecutor] Inicializado.", level="INFO")

    # --- INICIO DE LA MODIFICACIÓN ---
    # Se añaden tsl_activation_pct y tsl_distance_pct a la firma para crear el objeto LogicalPosition.
    def execute_open(self, side: str, entry_price: float, timestamp: datetime.datetime, margin_to_use: float, sl_pct: float, tsl_activation_pct: float, tsl_distance_pct: float) -> Dict[str, Any]:
    # --- FIN DE LA MODIFICACIÓN ---
        """Orquesta la apertura de una posición a través de la interfaz de exchange."""
        # --- INICIO DE LA MODIFICACIÓN ---
        # `logical_position_id` se usará para el objeto, `logical_position_object` para el retorno.
        result = {'success': False, 'api_order_id': None, 'logical_position_object': None, 'message': 'Error no especificado'}
        # Obtenemos el apalancamiento desde la operación activa a través del PositionManager
        operacion = self._state_manager._om_api.get_operation_by_side(side)
        if not operacion:
            result['message'] = f"Error: No se pudo obtener la operación para el lado '{side}'."
            return result
        leverage = operacion.apalancamiento
        # --- FIN DE LA MODIFICACIÓN ---

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
            memory_logger.log(traceback.format_exc(), level="ERROR")
            return result
        
        # --- 2. Crear Objeto de la Posición Lógica ---
        logical_position_id = str(uuid.uuid4())
        
        stop_loss_price = self._calculations.calculate_stop_loss(side, entry_price, sl_pct)
        est_liq_price = self._calculations.calculate_liquidation_price(side, entry_price, leverage)
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Crear un objeto `LogicalPosition` con todos los parámetros.
        new_position_obj = LogicalPosition(
            id=logical_position_id, 
            entry_timestamp=timestamp, 
            entry_price=entry_price,
            margin_usdt=margin_to_use, 
            size_contracts=size_contracts_float,
            leverage=leverage, 
            stop_loss_price=stop_loss_price,
            est_liq_price=est_liq_price, 
            ts_is_active=False,
            ts_peak_price=None, 
            ts_stop_price=None, 
            api_order_id=None,
            tsl_activation_pct_at_open=tsl_activation_pct, # Añadido
            tsl_distance_pct_at_open=tsl_distance_pct # Añadido
        )
        result['logical_position_object'] = new_position_obj # Se devuelve el objeto completo
        # --- FIN DE LA MODIFICACIÓN ---

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
                # --- INICIO DE LA MODIFICACIÓN ---
                # Eliminada la llamada a self._balance_manager.decrease_used_margin()
                # self._balance_manager.decrease_used_margin(side, margin_to_use)
                # --- FIN DE LA MODIFICACIÓN ---
            else:
                result['message'] = f"Fallo en Exchange al colocar orden Market: {order_id_or_error}"
                memory_logger.log(f"  -> ERROR EXCHANGE: {result['message']}", level="ERROR")
        except Exception as exec_err:
            result['message'] = f"Excepción durante ejecución de orden: {exec_err}"
            # memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR") # Comentada, ya logueada en `result['message']`
            # memory_logger.log(traceback.format_exc(), level="ERROR") # Comentada, ya logueada en `result['message']`

        # --- 4. Actualizar Estado Interno ---
        if execution_success:
            new_position_obj.api_order_id = api_order_id # Actualizar el objeto con el ID de la API
            # El estado lógico (tabla de posiciones) y físico se actualizan AHORA en _private_logic.py
            result['success'] = True
            result['message'] = f"Apertura {side.upper()} exitosa."
        
        result['api_order_id'] = api_order_id
        return result

    # --- INICIO DE LA MODIFICACIÓN ---
    # La firma del método `execute_close` cambia para recibir un objeto `LogicalPosition`
    def execute_close(self, position_to_close: LogicalPosition, side: str, exit_price: float, timestamp: datetime.datetime, exit_reason: str = "UNKNOWN") -> Dict[str, Any]:
    # --- FIN DE LA MODIFICACIÓN ---
        """Orquesta el cierre de una posición a través de la interfaz de exchange."""
        result = {'success': False, 'pnl_net_usdt': 0.0, 'message': 'Error no especificado'}
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se obtiene el ID acortado directamente del objeto.
        pos_id_short = str(position_to_close.id)[-6:]
        memory_logger.log(f"CLOSE [{side.upper()} ID:{pos_id_short}] -> Solicitud para cerrar @ {exit_price:.{self._price_prec}f} (Razón: {exit_reason})", level="INFO")
        # --- FIN DE LA MODIFICACIÓN ---

        # --- INICIO DE LA MODIFICACIÓN ---
        # `size_to_close_float` se obtiene directamente del objeto `position_to_close`.
        size_to_close_float = self._utils.safe_float_convert(position_to_close.size_contracts, 0.0)
        # --- FIN DE LA MODIFICACIÓN ---
        
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
            # --- INICIO DE LA MODIFICACIÓN ---
            # Se usa el objeto `position_to_close` directamente.
            # Convertimos el objeto `LogicalPosition` a un diccionario para compatibilidad con `calc_res`.
            removed_pos_dict = asdict(position_to_close)

            # Ya no removemos la posición lógica ni actualizamos el balance desde aquí.
            # Eso lo hace _private_logic.py
            # removed_pos = self._position_state.remove_logical_position(side, position_index)
            # if not removed_pos:
            #     result['message'] = "Ejecución en Exchange OK pero falló al remover posición lógica."
            #     memory_logger.log(f"ERROR SEVERE [Exec Close]: {result['message']}", level="ERROR")
            #     return result

            calc_res = self._calculations.calculate_pnl_commission_reinvestment(
                side, removed_pos_dict['entry_price'], exit_price, removed_pos_dict['size_contracts']
            )
            result.update(calc_res)
            
            # Eliminada la llamada a self._balance_manager.increase_available_margin()
            # margin_to_return = removed_pos_dict['margin_usdt'] + calc_res.get('amount_reinvested_in_operational_margin', 0.0)
            # self._balance_manager.increase_available_margin(side, margin_to_return)

            # La actualización del estado físico y el logging de la posición cerrada se manejan en _private_logic.py
            # open_positions_now = self._position_state.get_open_logical_positions(side)
            # if open_positions_now:
            #     aggs = self._calculations.calculate_physical_aggregates(open_positions_now)
            #     leverage = self._state_manager.get_leverage()
            #     liq = self._calculations.calculate_liquidation_price(side, aggs['avg_entry_price'], leverage)
            #     self._position_state.update_physical_position_state(side, **aggs, liq_price=liq, timestamp=timestamp)
            # else:
            #     self._position_state.reset_physical_position_state(side)
            
            if self._closed_position_logger and removed_pos_dict: # Usamos el dict local
                log_data = {**removed_pos_dict, **calc_res, "exit_price": exit_price, "exit_timestamp": timestamp, "exit_reason": exit_reason}
                self._closed_position_logger.log_closed_position(log_data)
            
            result['success'] = True
            result['message'] = f"Cierre {side.upper()} ID {pos_id_short} exitoso."
            # --- FIN DE LA MODIFICACIÓN ---
        
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