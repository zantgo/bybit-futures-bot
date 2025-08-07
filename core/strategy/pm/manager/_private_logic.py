# ./core/strategy/pm/manager/_private_logic.py
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

        # <<-- CAMBIO: La condición principal ya no es max_posiciones o available_margin.
        # Es simplemente si hay alguna posición esperando a ser abierta.
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
        
        # <<-- CAMBIO: Encontrar la primera posición pendiente para abrirla.
        pending_position = next((pos for pos in operacion.posiciones if pos.estado == 'PENDIENTE'), None)
        if not pending_position:
            self._memory_logger.log(f"Apertura fallida ({side.upper()}): No se encontró ninguna posición pendiente en el momento de la ejecución.", level="WARN")
            return

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
                # <<-- CAMBIO: Actualizar la posición existente en lugar de añadir una nueva.
                current_op = self._om_api.get_operation_by_side(side) # Obtener una copia fresca
                
                # Encontrar la posición que acabamos de abrir por su ID para actualizarla.
                pos_to_update = next((p for p in current_op.posiciones if p.id == pending_position.id), None)
                if pos_to_update:
                    pos_to_update.estado = 'ABIERTA'
                    # Poblar la posición con los datos de la ejecución real.
                    pos_to_update.entry_timestamp = new_pos_data.entry_timestamp
                    pos_to_update.entry_price = new_pos_data.entry_price
                    pos_to_update.margin_usdt = new_pos_data.margin_usdt
                    pos_to_update.size_contracts = new_pos_data.size_contracts
                    pos_to_update.stop_loss_price = new_pos_data.stop_loss_price
                    pos_to_update.est_liq_price = new_pos_data.est_liq_price
                    pos_to_update.api_order_id = new_pos_data.api_order_id
                    pos_to_update.api_avg_fill_price = new_pos_data.api_avg_fill_price
                    pos_to_update.api_filled_qty = new_pos_data.api_filled_qty
                
                # Enviar toda la lista de posiciones actualizada al OM.
                self._om_api.create_or_update_operation(side, {'posiciones': [asdict(p) for p in current_op.posiciones]})
                # Actualizar el estado local (si es necesario)
                self._position_state.sync_positions_from_operation(current_op)
                

    def _update_trailing_stop(self, side, position_obj: LogicalPosition, index: int, current_price: float):
        """Actualiza el Trailing Stop para una posición específica."""
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion or operacion.estado != 'ACTIVA':
            return
        
        if index >= len(operacion.posiciones):
            return # Guardia de seguridad
        
        pos_mutated_obj = operacion.posiciones[index]
        activation_pct = position_obj.tsl_activation_pct_at_open
        distance_pct = position_obj.tsl_distance_pct_at_open
        is_ts_active = position_obj.ts_is_active
        entry_price = position_obj.entry_price

        if not is_ts_active and activation_pct > 0 and entry_price:
            activation_price = entry_price * (1 + activation_pct / 100) if side == 'long' else entry_price * (1 - activation_pct / 100)
            if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                pos_mutated_obj.ts_is_active = True
                pos_mutated_obj.ts_peak_price = current_price
        
        if pos_mutated_obj.ts_is_active:
            peak_price = pos_mutated_obj.ts_peak_price or current_price
            if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                pos_mutated_obj.ts_peak_price = current_price
            
            new_peak_price = pos_mutated_obj.ts_peak_price
            new_stop_price = new_peak_price * (1 - distance_pct / 100) if side == 'long' else new_peak_price * (1 + distance_pct / 100)
            pos_mutated_obj.ts_stop_price = new_stop_price
        
        # <<-- CAMBIO: Se envía la lista completa de posiciones actualizada.
        self._om_api.create_or_update_operation(side, {'posiciones': [asdict(p) for p in operacion.posiciones]})
        # <<-- ANTERIOR: self._om_api.create_or_update_operation(side, {'posiciones_activas': operacion.posiciones_activas})

    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> dict:
        """
        Cierra una posición lógica. En lugar de eliminarla, cambia su estado
        a 'PENDIENTE' y resetea sus datos de ejecución.
        """
        op_before = self._om_api.get_operation_by_side(side)
        
        # <<-- CAMBIO: La validación ahora se hace sobre la lista principal 'posiciones'.
        if not self._executor or not op_before or index >= len(op_before.posiciones):
            return {'success': False, 'message': 'Índice o executor no válido'}

        pos_to_close = op_before.posiciones[index]
        # <<-- ANTERIOR: pos_to_close = op_before.posiciones_activas[side][index]

        result = self._executor.execute_close(pos_to_close, side, exit_price, timestamp, reason)

        if result and result.get('success', False):
            pnl = result.get('pnl_net_usdt', 0.0)
            reinvest_amount = result.get('amount_reinvested_in_operational_margin', 0.0)
            transfer_amount = result.get('amount_transferable_to_profit', 0.0)
            
            # 1. Actualizar contadores centrales de forma atómica.
            self._om_api.actualizar_pnl_realizado(side, pnl)
            # <<-- CAMBIO: La reinversión ya no se maneja así, el capital se "libera" al volver a PENDIENTE.
            # self._om_api.actualizar_margen_operativo(side, reinvest_amount)
            self._om_api.actualizar_total_reinvertido(side, reinvest_amount)
            self._om_api.actualizar_comisiones_totales(side, result.get('fee_usdt', 0.0))
            
            # 2. Obtener el estado actualizado y modificar la posición.
            op_after = self._om_api.get_operation_by_side(side)
            
            # <<-- CAMBIO: En lugar de eliminar la posición, la reseteamos a su estado 'PENDIENTE'.
            pos_to_reset = next((p for p in op_after.posiciones if p.id == pos_to_close.id), None)
            if pos_to_reset:
                pos_to_reset.estado = 'PENDIENTE'
                # Limpiar los campos de ejecución para que esté lista para un nuevo trade.
                pos_to_reset.entry_timestamp = None
                pos_to_reset.entry_price = None
                # No reseteamos margin_usdt, puede ser útil para logs, pero la lógica usará capital_asignado.
                pos_to_reset.size_contracts = None
                pos_to_reset.stop_loss_price = None
                pos_to_reset.est_liq_price = None
                pos_to_reset.ts_is_active = False
                pos_to_reset.ts_peak_price = None
                pos_to_reset.ts_stop_price = None
                pos_to_reset.api_order_id = None
                pos_to_reset.api_avg_fill_price = None
                pos_to_reset.api_filled_qty = None

            # 3. Actualizar el estado de la operación en lote.
            params = {
                'posiciones': [asdict(p) for p in op_after.posiciones],
                'comercios_cerrados_contador': op_after.comercios_cerrados_contador + 1,
            }
            self._om_api.create_or_update_operation(side, params)
            # <<-- ANTERIOR:
            # op_after.balances.record_profit_transfer(transfer_amount)
            # op_after.balances.increase_available_margin(margin_original)
            # op_after.posiciones_activas[side].pop(index)
            # ...

            # --- Lógica Post-Cierre (sin cambios) ---
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