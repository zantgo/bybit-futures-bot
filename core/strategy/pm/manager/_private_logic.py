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
    """Clase base que contiene la lógica interna y privada del PositionManager."""

    def _can_open_new_position(self, side: str) -> bool:
        """Verifica si se puede abrir una nueva posición para un lado específico."""
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion or operacion.estado != 'ACTIVA':
            return False
            
        open_positions = operacion.posiciones_activas.get(side, [])
        open_positions_count = len(open_positions)
        
        if open_positions_count >= operacion.max_posiciones_logicas:
            return False

        if operacion.balances.available_margin < 1.0:
            self._memory_logger.log(f"Apertura omitida ({side.upper()}): Margen lógico insuficiente ({operacion.balances.available_margin:.4f} USDT).", level="DEBUG")
            return False

        if open_positions_count > 0:
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
        """Abre una nueva posición lógica para el lado especificado."""
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion or operacion.estado != 'ACTIVA':
            return

        open_positions_count = len(operacion.posiciones_activas.get(side, []))
        available_slots = operacion.max_posiciones_logicas - open_positions_count
        if available_slots <= 0:
            return

        available_margin = operacion.balances.available_margin
        margin_per_slot = self._utils.safe_division(available_margin, available_slots)
        margin_to_use = min(operacion.tamaño_posicion_base_usdt, margin_per_slot)
        
        if margin_to_use < 1.0:
            self._memory_logger.log(f"Apertura omitida ({side.upper()}): Margen a usar ({margin_to_use:.4f} USDT) es menor al umbral mínimo.", level="WARN")
            return
            
        result = self._executor.execute_open(
            side=side, entry_price=entry_price, timestamp=timestamp, 
            margin_to_use=margin_to_use, 
            sl_pct=operacion.sl_posicion_individual_pct,
            tsl_activation_pct=operacion.tsl_activacion_pct,
            tsl_distance_pct=operacion.tsl_distancia_pct
        )

        if result and result.get('success'):
            new_pos_obj = result.get('logical_position_object')
            if new_pos_obj:
                current_op = self._om_api.get_operation_by_side(side)
                if current_op:
                    current_op.balances.decrease_available_margin(margin_to_use)
                    # Es seguro modificar la copia local antes de enviarla
                    current_op.posiciones_activas[side].append(new_pos_obj)
                    
                    self._om_api.create_or_update_operation(side, {
                        'posiciones_activas': current_op.posiciones_activas,
                        'balances': current_op.balances
                    })
                    self._position_state.add_logical_position_obj(side, new_pos_obj)

    def _update_trailing_stop(self, side, position_obj: LogicalPosition, index: int, current_price: float):
        """Actualiza el Trailing Stop para una posición específica."""
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion or operacion.estado != 'ACTIVA':
            return

        activation_pct = position_obj.tsl_activation_pct_at_open
        distance_pct = position_obj.tsl_distance_pct_at_open
        is_ts_active = position_obj.ts_is_active
        entry_price = position_obj.entry_price
        
        pos_mutated_obj = operacion.posiciones_activas[side][index]

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

        self._om_api.create_or_update_operation(side, {'posiciones_activas': operacion.posiciones_activas})

    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> dict:
        """Cierra una posición lógica específica y actualiza el estado de la operación correspondiente."""
        op_before = self._om_api.get_operation_by_side(side)
        if not self._executor or not op_before or index >= len(op_before.posiciones_activas.get(side, [])):
            return {'success': False, 'message': 'Índice o executor no válido'}

        pos_to_close = op_before.posiciones_activas[side][index]
        result = self._executor.execute_close(pos_to_close, side, exit_price, timestamp, reason)

        if result and result.get('success', False):
            margin_original = pos_to_close.margin_usdt
            pnl = result.get('pnl_net_usdt', 0.0)
            reinvest_amount = result.get('amount_reinvested_in_operational_margin', 0.0)
            transfer_amount = result.get('amount_transferable_to_profit', 0.0)
            
            # --- INICIO DE LA MODIFICACIÓN (Lógica Definitiva) ---
            # En lugar de agrupar todo en un gran `create_or_update`, usamos las nuevas funciones atómicas.
            
            # 1. Actualizar contadores centrales de forma atómica.
            self._om_api.actualizar_pnl_realizado(side, pnl)
            self._om_api.actualizar_margen_operativo(side, reinvest_amount) # Suma la ganancia al "dinero para jugar".
            self._om_api.actualizar_total_reinvertido(side, reinvest_amount) # Suma al contador visual de reinversión.
            
            # 2. Obtener el estado actualizado después de las operaciones atómicas.
            op_after = self._om_api.get_operation_by_side(side)
            
            # 3. Realizar las actualizaciones restantes en la copia local.
            if transfer_amount > 0:
                op_after.balances.record_profit_transfer(transfer_amount)
            
            # Libera el margen original que estaba en uso.
            op_after.balances.increase_available_margin(margin_original)
            
            # Elimina la posición de la lista.
            if index < len(op_after.posiciones_activas.get(side, [])):
                op_after.posiciones_activas[side].pop(index)
            
            # 4. Actualizar el estado de la operación en lote con los cambios restantes.
            params = {
                'posiciones_activas': op_after.posiciones_activas,
                'comercios_cerrados_contador': op_after.comercios_cerrados_contador + 1,
                'balances': op_after.balances
            }
            self._om_api.create_or_update_operation(side, params)
            # --- FIN DE LA MODIFICACIÓN ---

            # --- Lógica Post-Cierre (sin cambios) ---
            self._position_state.remove_logical_position(side, index)
            if side == 'long':
                self._total_realized_pnl_long += pnl
            else:
                self._total_realized_pnl_short += pnl
                
            # La condición de monto mínimo se gestiona mejor aquí, antes de la llamada.
            min_transfer = self._config.SESSION_CONFIG["PROFIT"]["MIN_TRANSFER_AMOUNT_USDT"]
            if _transfer_executor and transfer_amount > 0 and transfer_amount >= min_transfer:
                _transfer_executor.execute_transfer(amount=transfer_amount, from_account_side=side, exchange_adapter=self._exchange, config=self._config)
            
            self._om_api.revisar_y_transicionar_a_detenida(side)
        
        return result