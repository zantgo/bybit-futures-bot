import datetime
import uuid
from typing import Any
from dataclasses import asdict

try:
    from core.strategy.entities import Operacion, LogicalPosition
    from .. import _transfer_executor
except ImportError:
    class Operacion: pass
    class LogicalPosition: pass
    _transfer_executor = None

class _PrivateLogic:
    """
    Clase base que contiene la lógica interna y privada del PositionManager.
    Actualizada para operar con un modelo de posiciones individuales con estado.
    """

    def _can_open_new_position(self, side: str) -> bool:
        """
        Verifica si se puede abrir una nueva posición. La condición principal ahora es
        la existencia de una posición en estado 'PENDIENTE'.
        """
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion or operacion.estado != 'ACTIVA':
            return False

        if not operacion.posiciones_pendientes:
            self._memory_logger.log(f"Apertura omitida ({side.upper()}): No hay posiciones pendientes disponibles.", level="DEBUG")
            return False
        
        open_positions = operacion.posiciones_abiertas
        if open_positions:
            last_position_entry_price = open_positions[-1].entry_price
            current_price = self.get_current_market_price()
            
            if not current_price:
                self._memory_logger.log(f"Apertura omitida ({side.upper()}): No se pudo obtener el precio de mercado actual para calcular la distancia.", level="WARN")
                return False

            if side == 'long':
                required_distance_pct = self._config.OPERATION_DEFAULTS["RISK"]["AVERAGING_DISTANCE_PCT_LONG"]
                price_condition_met = current_price <= last_position_entry_price * (1 - required_distance_pct / 100)
            else: # side == 'short'
                required_distance_pct = self._config.OPERATION_DEFAULTS["RISK"]["AVERAGING_DISTANCE_PCT_SHORT"]
                price_condition_met = current_price >= last_position_entry_price * (1 + required_distance_pct / 100)

            if not price_condition_met:
                price_diff_pct = (abs(current_price - last_position_entry_price) / last_position_entry_price) * 100
                self._memory_logger.log(
                    f"Apertura omitida ({side.upper()}): Distancia insuficiente. "
                    f"Última entrada: {last_position_entry_price:.4f}, Actual: {current_price:.4f}. "
                    f"Distancia: {price_diff_pct:.2f}%, Requerida: {required_distance_pct:.2f}%",
                    level="DEBUG"
                )
                return False

        return True

    def _open_logical_position(self, side: str, entry_price: float, timestamp: datetime.datetime):
        """
        Abre una nueva posición lógica, tomando la primera posición 'PENDIENTE'
        disponible y usando su 'capital_asignado'.
        """
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion or operacion.estado != 'ACTIVA':
            return
        
        pending_position = next((pos for pos in operacion.posiciones if pos.estado == 'PENDIENTE'), None)
        if not pending_position:
            self._memory_logger.log(f"Apertura fallida ({side.upper()}): No se encontró ninguna posición pendiente en el momento de la ejecución.", level="WARN")
            return

        margin_to_use = pending_position.capital_asignado
        
        if margin_to_use < 1.0:
            self._memory_logger.log(f"Apertura omitida ({side.upper()}): Capital asignado ({margin_to_use:.4f} USDT) es menor al umbral mínimo.", level="WARN")
            return

        result = self._executor.execute_open(
            side=side, entry_price=entry_price, timestamp=timestamp, 
            margin_to_use=margin_to_use, 
            sl_pct=operacion.sl_posicion_individual_pct,
            tsl_activation_pct=operacion.tsl_activacion_pct,
            tsl_distance_pct=operacion.tsl_distancia_pct
        )

        if result and result.get('success'):
            new_pos_data = result.get('logical_position_object')
            if new_pos_data:
                current_op = self._om_api.get_operation_by_side(side)
                
                pos_to_update = next((p for p in current_op.posiciones if p.id == pending_position.id), None)
                if pos_to_update:
                    pos_to_update.estado = 'ABIERTA'
                    pos_to_update.entry_timestamp = new_pos_data.entry_timestamp
                    pos_to_update.entry_price = new_pos_data.entry_price
                    pos_to_update.margin_usdt = new_pos_data.margin_usdt
                    pos_to_update.size_contracts = new_pos_data.size_contracts
                    pos_to_update.stop_loss_price = new_pos_data.stop_loss_price
                    pos_to_update.est_liq_price = new_pos_data.est_liq_price
                    pos_to_update.api_order_id = new_pos_data.api_order_id
                    pos_to_update.api_avg_fill_price = new_pos_data.api_avg_fill_price
                    pos_to_update.api_filled_qty = new_pos_data.api_filled_qty
                
                self._om_api.create_or_update_operation(side, {'posiciones': [asdict(p) for p in current_op.posiciones]})
                if hasattr(self, '_position_state') and hasattr(self._position_state, 'sync_positions_from_operation'):
                    self._position_state.sync_positions_from_operation(current_op)
    
    # --- INICIO DE LA MODIFICACIÓN (Solución al bug del TSL) ---
    # 1. Se elimina el parámetro 'position_obj'. La función ahora solo necesita saber el 'index'
    #    de la posición a actualizar y obtendrá la versión más reciente por sí misma.
    # def _update_trailing_stop(self, side, position_obj: LogicalPosition, index: int, current_price: float): # <-- LÍNEA ORIGINAL COMENTADA
    def _update_trailing_stop(self, side: str, index: int, current_price: float):
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion or operacion.estado != 'ACTIVA':
            return
        
        if index >= len(operacion.posiciones):
            return
        
        # 2. Obtenemos el objeto de la posición directamente de la copia fresca de 'operacion'.
        #    Este objeto será tanto la fuente de verdad para leer como el destino para escribir.
        position_to_update = operacion.posiciones[index]
        # pos_mutated_obj = operacion.posiciones[index] # <-- LÍNEA ORIGINAL (Referencia eliminada)
        
        # 3. Se reemplazan todas las lecturas de 'position_obj' para que usen 'position_to_update'.
        #    Esto asegura que siempre trabajemos con el estado más reciente.
        activation_pct = position_to_update.tsl_activation_pct_at_open
        distance_pct = position_to_update.tsl_distance_pct_at_open
        is_ts_active = position_to_update.ts_is_active
        entry_price = position_to_update.entry_price
        
        # activation_pct = position_obj.tsl_activation_pct_at_open # <-- LÍNEA ORIGINAL COMENTADA
        # distance_pct = position_obj.tsl_distance_pct_at_open # <-- LÍNEA ORIGINAL COMENTADA
        # is_ts_active = position_obj.ts_is_active # <-- LÍNEA ORIGINAL COMENTADA
        # entry_price = position_obj.entry_price # <-- LÍNEA ORIGINAL COMENTADA

        if not is_ts_active and activation_pct > 0 and entry_price:
            activation_price = entry_price * (1 + activation_pct / 100) if side == 'long' else entry_price * (1 - activation_pct / 100)
            if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                position_to_update.ts_is_active = True
                position_to_update.ts_peak_price = current_price
        
        if position_to_update.ts_is_active:
            peak_price = position_to_update.ts_peak_price or current_price
            if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                position_to_update.ts_peak_price = current_price
            
            new_peak_price = position_to_update.ts_peak_price
            if new_peak_price:
                new_stop_price = new_peak_price * (1 - distance_pct / 100) if side == 'long' else new_peak_price * (1 + distance_pct / 100)
                position_to_update.ts_stop_price = new_stop_price
        # --- FIN DE LA MODIFICACIÓN ---
        
        # Esta línea es correcta y se mantiene, ya que guarda los cambios realizados en 'position_to_update'
        # (que es un objeto dentro de 'operacion.posiciones') de vuelta al gestor de operaciones.
        # El siguiente paso será hacer que 'create_or_update_operation' sea más inteligente para no
        # registrar un cambio si los datos son idénticos.
        self._om_api.create_or_update_operation(side, {'posiciones': [asdict(p) for p in operacion.posiciones]})

    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> dict:
        op_before = self._om_api.get_operation_by_side(side)
        
        if not self._executor or not op_before or index >= len(op_before.posiciones):
            return {'success': False, 'message': 'Índice o executor no válido'}

        pos_to_close = op_before.posiciones[index]
        result = self._executor.execute_close(pos_to_close, side, exit_price, timestamp, reason)

        if result and result.get('success', False):
            pnl = result.get('pnl_net_usdt', 0.0)
            reinvest_amount = result.get('amount_reinvested_in_operational_margin', 0.0)
            transfer_amount = result.get('amount_transferable_to_profit', 0.0)
            
            self._om_api.actualizar_pnl_realizado(side, pnl)
            self._om_api.actualizar_total_reinvertido(side, reinvest_amount)
            self._om_api.actualizar_comisiones_totales(side, result.get('commission_usdt', 0.0))
            
            op_after = self._om_api.get_operation_by_side(side)
            
            pos_to_reset = next((p for p in op_after.posiciones if p.id == pos_to_close.id), None)
            if pos_to_reset:
                pos_to_reset.estado = 'PENDIENTE'
                pos_to_reset.entry_timestamp = None
                pos_to_reset.entry_price = None
                pos_to_reset.size_contracts = None
                pos_to_reset.stop_loss_price = None
                pos_to_reset.est_liq_price = None
                pos_to_reset.ts_is_active = False
                pos_to_reset.ts_peak_price = None
                pos_to_reset.ts_stop_price = None
                pos_to_reset.api_order_id = None
                pos_to_reset.api_avg_fill_price = None
                pos_to_reset.api_filled_qty = None

            params = {
                'posiciones': [asdict(p) for p in op_after.posiciones],
                'comercios_cerrados_contador': op_after.comercios_cerrados_contador + 1,
            }
            if hasattr(op_after, 'profit_balance_acumulado') and transfer_amount > 0:
                params['profit_balance_acumulado'] = op_after.profit_balance_acumulado + transfer_amount
            
            self._om_api.create_or_update_operation(side, params)
            
            if hasattr(self, '_position_state') and hasattr(self._position_state, 'sync_positions_from_operation'):
                self._position_state.sync_positions_from_operation(op_after)
            
            if side == 'long':
                self._total_realized_pnl_long += pnl
            else:
                self._total_realized_pnl_short += pnl
                
            min_transfer = self._config.SESSION_CONFIG["PROFIT"]["MIN_TRANSFER_AMOUNT_USDT"]
            if _transfer_executor and transfer_amount > 0 and transfer_amount >= min_transfer:
                _transfer_executor.execute_transfer(amount=transfer_amount, from_account_side=side, exchange_adapter=self._exchange, config=self._config)
            
            self._om_api.revisar_y_transicionar_a_detenida(side)
        
        return result