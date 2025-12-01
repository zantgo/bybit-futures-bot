# core/strategy/pm/manager/_private_logic.py

import datetime
import uuid
import traceback
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

            required_distance_pct = operacion.averaging_distance_pct
            
            if required_distance_pct is None or required_distance_pct <= 0:
                return True

            if side == 'long':
                price_condition_met = current_price <= last_position_entry_price * (1 - required_distance_pct / 100)
            else: # side == 'short'
                price_condition_met = current_price >= last_position_entry_price * (1 + required_distance_pct / 100)

            if not price_condition_met:
                price_diff_pct = (abs(current_price - last_position_entry_price) / last_position_entry_price) * 100
                '''
                self._memory_logger.log(
                    f"Apertura omitida ({side.upper()}): Distancia insuficiente. "
                    f"Última entrada: {last_position_entry_price:.4f}, Actual: {current_price:.4f}. "
                    f"Distancia: {price_diff_pct:.2f}%, Requerida: {required_distance_pct:.2f}%",
                    level="DEBUG"
                )
                '''
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
                op_to_update = self._om_api.get_operation_by_side(side)
                
                pos_to_update_in_list = next((p for p in op_to_update.posiciones if p.id == pending_position.id), None)
                
                if pos_to_update_in_list:
                    pos_to_update_in_list.estado = 'ABIERTA'
                    pos_to_update_in_list.entry_timestamp = new_pos_data.entry_timestamp
                    pos_to_update_in_list.entry_price = new_pos_data.entry_price
                    pos_to_update_in_list.margin_usdt = new_pos_data.margin_usdt
                    pos_to_update_in_list.size_contracts = new_pos_data.size_contracts
                    pos_to_update_in_list.stop_loss_price = new_pos_data.stop_loss_price
                    pos_to_update_in_list.est_liq_price = new_pos_data.est_liq_price
                    pos_to_update_in_list.api_order_id = new_pos_data.api_order_id
                    pos_to_update_in_list.api_avg_fill_price = new_pos_data.api_avg_fill_price
                    pos_to_update_in_list.api_filled_qty = new_pos_data.api_filled_qty
                    
                    pos_to_update_in_list.tsl_activation_pct_at_open = new_pos_data.tsl_activation_pct_at_open
                    pos_to_update_in_list.tsl_distance_pct_at_open = new_pos_data.tsl_distance_pct_at_open
                
                    self._om_api.create_or_update_operation(side, {'posiciones': op_to_update.posiciones})

                    if hasattr(self, '_position_state') and hasattr(self._position_state, 'sync_positions_from_operation'):
                        self._position_state.sync_positions_from_operation(op_to_update)

    def _update_trailing_stop(self, side: str, index: int, current_price: float):
        try:
            operacion = self._om_api.get_operation_by_side(side)
            if not operacion or operacion.estado not in ['ACTIVA', 'PAUSADA']:
                return
            
            if index >= len(operacion.posiciones):
                return
            
            position_to_update = operacion.posiciones[index]
            pos_id_short = str(position_to_update.id)[-6:]

            activation_pct = position_to_update.tsl_activation_pct_at_open
            distance_pct = position_to_update.tsl_distance_pct_at_open
            is_ts_active = position_to_update.ts_is_active
            entry_price = position_to_update.entry_price

            if not (activation_pct is not None and activation_pct > 0 and distance_pct is not None and distance_pct > 0 and entry_price is not None):
                return

            if not is_ts_active:
                activation_price = entry_price * (1 + activation_pct / 100) if side == 'long' else entry_price * (1 - activation_pct / 100)
                
                if (side == 'long' and current_price >= activation_price) or \
                   (side == 'short' and current_price <= activation_price):
                    
                    self._memory_logger.log(f"¡TSL ACTIVADO! [ID:{pos_id_short}] Precio cruzó umbral. Pico inicial fijado en {current_price:.4f}", level="INFO")
                    position_to_update.ts_is_active = True
                    position_to_update.ts_peak_price = current_price
            
            if position_to_update.ts_is_active:
                current_peak = position_to_update.ts_peak_price if position_to_update.ts_peak_price is not None else entry_price
                
                if (side == 'long' and current_price > current_peak) or \
                   (side == 'short' and current_price < current_peak):
                    
                    position_to_update.ts_peak_price = current_price
                
                new_peak_price = position_to_update.ts_peak_price
                if new_peak_price:
                    new_stop_price = new_peak_price * (1 - distance_pct / 100) if side == 'long' else new_peak_price * (1 + distance_pct / 100)
                    
                    if new_stop_price != position_to_update.ts_stop_price:
                        self._memory_logger.log(f"TSL Stop Price Update [ID:{pos_id_short}]: Nuevo Stop en {new_stop_price:.4f}", level="DEBUG")
                        position_to_update.ts_stop_price = new_stop_price

            self._om_api.create_or_update_operation(side, {'posiciones': operacion.posiciones})
            
        except AttributeError as ae:
            self._memory_logger.log(f"ERROR [TSL AttrErr] side={side} index={index} current_price={current_price}: {ae}", level="ERROR")
            self._memory_logger.log(traceback.format_exc(), level="ERROR")
        except Exception as e:
            self._memory_logger.log(f"ERROR [TSL] side={side} index={index} current_price={current_price}: {e}", level="ERROR")
            self._memory_logger.log(traceback.format_exc(), level="ERROR")
    
    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> dict:
        self._manual_close_in_progress = True
        self._memory_logger.log(f"Bandera de protección de cierre ACTIVADA para {side.upper()} (Razón: {reason}).", "DEBUG")
        try:
            op_before = self._om_api.get_operation_by_side(side)
            
            if not self._executor or not op_before or index >= len(op_before.posiciones):
                self._memory_logger.log(f"ERROR [Close Attempt] side={side} index={index} executor={self._executor is not None} op_before_exists={op_before is not None}", level="ERROR")
                return {'success': False, 'message': 'Índice o executor no válido'}
        
            pos_to_close = op_before.posiciones[index]
            pos_id_to_reset = pos_to_close.id
        
            result = self._executor.execute_close(pos_to_close, side, exit_price, timestamp, reason)
        
            if result and result.get('success', False):
                pnl = result.get('pnl_net_usdt', 0.0)
                reinvest_amount = result.get('amount_reinvested_in_operational_margin', 0.0)
                transfer_amount = result.get('amount_transferable_to_profit', 0.0)
                
                self._om_api.actualizar_pnl_realizado(side, pnl)
                self._om_api.actualizar_total_reinvertido(side, reinvest_amount)
                self._om_api.actualizar_comisiones_totales(side, result.get('commission_usdt', 0.0))
                
                op_after_updates = self._om_api.get_operation_by_side(side)
                
                if op_after_updates and op_after_updates.auto_reinvest_enabled and reinvest_amount > 0:
                    self._om_api.actualizar_reinvestable_profit(side, reinvest_amount)
                
                pos_to_reset_in_list = None
                if op_after_updates:
                    pos_to_reset_in_list = next((p for p in op_after_updates.posiciones if p.id == pos_id_to_reset), None)
                
                if pos_to_reset_in_list:
                    self._memory_logger.log(f"Reseteando posición ID ...{str(pos_id_to_reset)[-6:]} a estado PENDIENTE.", "INFO")
                    pos_to_reset_in_list.estado = 'PENDIENTE'
                    pos_to_reset_in_list.entry_timestamp = None
                    pos_to_reset_in_list.entry_price = None
                    pos_to_reset_in_list.margin_usdt = None
                    pos_to_reset_in_list.size_contracts = None
                    pos_to_reset_in_list.stop_loss_price = None
                    pos_to_reset_in_list.est_liq_price = None
                    pos_to_reset_in_list.ts_is_active = False
                    pos_to_reset_in_list.ts_peak_price = None
                    pos_to_reset_in_list.ts_stop_price = None
                    pos_to_reset_in_list.api_order_id = None
                    pos_to_reset_in_list.api_avg_fill_price = None
                    pos_to_reset_in_list.api_filled_qty = None
                else:
                    self._memory_logger.log(f"ADVERTENCIA [Close]: No se encontró la posición con ID ...{str(pos_id_to_reset)[-6:]} para resetearla. Esto no debería ocurrir.", "WARN")
        
                if op_after_updates:
                    params = {
                        'posiciones': op_after_updates.posiciones,
                        'comercios_cerrados_contador': op_after_updates.comercios_cerrados_contador + 1,
                    }
                    if hasattr(op_after_updates, 'profit_balance_acumulado') and transfer_amount > 0:
                        params['profit_balance_acumulado'] = op_after_updates.profit_balance_acumulado + transfer_amount
                    
                    self._om_api.create_or_update_operation(side, params)
                
                op_final_for_distribute = self._om_api.get_operation_by_side(side)
                if op_final_for_distribute and op_final_for_distribute.auto_reinvest_enabled and reinvest_amount > 0:
                    self._om_api.distribuir_reinvestable_profits(side)
        
                if hasattr(self, '_position_state') and hasattr(self._position_state, 'sync_positions_from_operation'):
                    op_final_for_sync = self._om_api.get_operation_by_side(side)
                    if op_final_for_sync:
                        self._position_state.sync_positions_from_operation(op_final_for_sync)
                
                if side == 'long':
                    self._total_realized_pnl_long += pnl
                else:
                    self._total_realized_pnl_short += pnl
                    
                min_transfer = self._config.SESSION_CONFIG["PROFIT"]["MIN_TRANSFER_AMOUNT_USDT"]
                if _transfer_executor and transfer_amount > 0 and transfer_amount >= min_transfer:
                    _transfer_executor.execute_transfer(amount=transfer_amount, from_account_side=side, exchange_adapter=self._exchange, config=self._config)
                
                self._om_api.revisar_y_transicionar_a_detenida(side)
            
            return result

        finally:
            self._manual_close_in_progress = False
            self._memory_logger.log(f"Bandera de protección de cierre DESACTIVADA para {side.upper()}.", "DEBUG")
        
    def _manual_open_position(self, side: str, entry_price: float, timestamp: datetime.datetime) -> dict:
        """
        Lógica interna para abrir una posición manualmente. Es casi idéntica a
        _open_logical_position pero sin la validación de `_can_open_new_position`.
        Devuelve el diccionario de resultado del ejecutor.
        """
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion:
            return {'success': False, 'message': f"Operación para el lado {side.upper()} no encontrada."}

        # Encontrar la primera posición pendiente en la lista
        pending_position = next((pos for pos in operacion.posiciones if pos.estado == 'PENDIENTE'), None)
        
        if not pending_position:
            return {'success': False, 'message': "No se encontró ninguna posición pendiente para abrir manualmente."}

        margin_to_use = pending_position.capital_asignado
        
        if margin_to_use < 1.0:
            msg = f"Apertura omitida ({side.upper()}): Capital asignado ({margin_to_use:.4f} USDT) es menor al umbral mínimo."
            self._memory_logger.log(msg, level="WARN")
            return {'success': False, 'message': msg}

        # Llamar al ejecutor con los parámetros de la operación actual
        result = self._executor.execute_open(
            side=side, entry_price=entry_price, timestamp=timestamp, 
            margin_to_use=margin_to_use, 
            sl_pct=operacion.sl_posicion_individual_pct,
            tsl_activation_pct=operacion.tsl_activacion_pct,
            tsl_distance_pct=operacion.tsl_distancia_pct
        )

        # Si la apertura fue exitosa, actualizar el estado de la operación
        if result and result.get('success'):
            new_pos_data = result.get('logical_position_object')
            if new_pos_data:
                op_to_update = self._om_api.get_operation_by_side(side)
                
                pos_to_update_in_list = next((p for p in op_to_update.posiciones if p.id == pending_position.id), None)
                
                if pos_to_update_in_list:
                    # Actualizar todos los campos de la posición lógica que cambió de estado
                    pos_to_update_in_list.estado = 'ABIERTA'
                    pos_to_update_in_list.entry_timestamp = new_pos_data.entry_timestamp
                    pos_to_update_in_list.entry_price = new_pos_data.entry_price
                    pos_to_update_in_list.margin_usdt = new_pos_data.margin_usdt
                    pos_to_update_in_list.size_contracts = new_pos_data.size_contracts
                    pos_to_update_in_list.stop_loss_price = new_pos_data.stop_loss_price
                    pos_to_update_in_list.est_liq_price = new_pos_data.est_liq_price
                    pos_to_update_in_list.api_order_id = new_pos_data.api_order_id
                    pos_to_update_in_list.api_avg_fill_price = new_pos_data.api_avg_fill_price
                    pos_to_update_in_list.api_filled_qty = new_pos_data.api_filled_qty
                    pos_to_update_in_list.tsl_activation_pct_at_open = new_pos_data.tsl_activation_pct_at_open
                    pos_to_update_in_list.tsl_distance_pct_at_open = new_pos_data.tsl_distance_pct_at_open
                
                    # Guardar el estado actualizado de la lista de posiciones
                    self._om_api.create_or_update_operation(side, {'posiciones': op_to_update.posiciones})

                    # Sincronizar el estado interno del PositionState si existe
                    if hasattr(self, '_position_state') and hasattr(self._position_state, 'sync_positions_from_operation'):
                        self._position_state.sync_positions_from_operation(op_to_update)
        
        return result
