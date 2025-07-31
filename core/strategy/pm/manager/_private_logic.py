"""
Módulo del Position Manager: Lógica Privada.

v7.1 (Triggers Automáticos):
- Se elimina la nota de refactorización v7.0. La lógica de inicio/fin
  de operaciones ahora reside completamente en el EventProcessor (automático)
  y la TUI (manual), haciendo que la nota sea obsoleta.
"""
import datetime
import uuid
from typing import Any
from collections import defaultdict
from dataclasses import asdict

try:
    from .._entities import Operacion, LogicalPosition
    from .. import _transfer_executor
except ImportError:
    class Operacion: pass
    class LogicalPosition: pass
    _transfer_executor = None

class _PrivateLogic:
    """Clase base que contiene la lógica interna y privada del PositionManager."""

    def _reset_all_states(self):
        """Resetea todos los atributos de estado del manager a sus valores iniciales."""
        self._initialized = False
        self._total_realized_pnl_long = 0.0
        self._total_realized_pnl_short = 0.0
        self._session_tp_hit = False
        self._session_start_time = None
        self._global_stop_loss_roi_pct = None
        self._global_take_profit_roi_pct = None

    def _can_open_new_position(self, side: str) -> bool:
        """Verifica si se puede abrir una nueva posición para un lado específico."""
        if self._session_tp_hit:
            return False
            
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion or operacion.estado != 'ACTIVA':
            return False
            
        open_positions_count = len(operacion.posiciones_activas.get(side, []))
        if open_positions_count >= operacion.max_posiciones_logicas:
            return False
        if self._balance_manager.get_available_margin(side) < 1.0:
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

        available_margin = self._balance_manager.get_available_margin(side)
        margin_per_slot = self._utils.safe_division(available_margin, available_slots)
        margin_to_use = min(operacion.tamaño_posicion_base_usdt, margin_per_slot)
        
        if margin_to_use < 1.0:
            self._memory_logger.log(f"Apertura omitida ({side.upper()}): Margen a usar ({margin_to_use:.4f} USDT) es menor al umbral mínimo.", level="WARN")
            return
            
        result = self._executor.execute_open(
            side=side, entry_price=entry_price, timestamp=timestamp, 
            margin_to_use=margin_to_use, 
            sl_pct=operacion.sl_posicion_individual_pct,
            leverage=operacion.apalancamiento,
            tsl_activation_pct=operacion.tsl_activacion_pct,
            tsl_distance_pct=operacion.tsl_distancia_pct
        )

        if result and result.get('success'):
            new_pos_obj = result.get('logical_position_object')
            if new_pos_obj:
                # Obtenemos de nuevo la operación para asegurar que tenemos la versión más fresca del estado
                current_op = self._om_api.get_operation_by_side(side)
                if current_op:
                    new_positions = current_op.posiciones_activas
                    new_positions[side].append(new_pos_obj)
                    # Actualizamos la operación del lado correspondiente
                    self._om_api.create_or_update_operation(side, {'posiciones_activas': new_positions})
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
        
        # Obtenemos una referencia al objeto de posición que podemos mutar
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

        # Enviar el estado actualizado de la operación del lado correspondiente
        self._om_api.create_or_update_operation(side, {'posiciones_activas': operacion.posiciones_activas})

    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> bool:
        """Cierra una posición lógica específica y actualiza el estado de la operación correspondiente."""
        operacion = self._om_api.get_operation_by_side(side)
        if not self._executor or not operacion:
            return False
        
        pos_to_close = operacion.posiciones_activas[side][index]
        result = self._executor.execute_close(pos_to_close, side, exit_price, timestamp, reason)
        
        if result and result.get('success', False):
            # Preparamos las modificaciones para la operación del lado correspondiente
            new_positions = operacion.posiciones_activas
            new_positions[side].pop(index)
            
            pnl = result.get('pnl_net_usdt', 0.0)
            new_pnl_realizado = operacion.pnl_realizado_usdt + pnl
            new_trade_count = operacion.comercios_cerrados_contador + 1

            if side == 'long':
                self._total_realized_pnl_long += pnl
            else:
                self._total_realized_pnl_short += pnl
            
            # Enviamos todos los cambios en una sola llamada a la API para el lado correcto
            params_to_update = {
                'posiciones_activas': new_positions,
                'pnl_realizado_usdt': new_pnl_realizado,
                'comercios_cerrados_contador': new_trade_count
            }
            self._om_api.create_or_update_operation(side, params_to_update)
            self._position_state.remove_logical_position(side, index)

            transfer_amount = result.get('amount_transferable_to_profit', 0.0)
            if _transfer_executor and transfer_amount >= getattr(self._config, 'POSITION_MIN_TRANSFER_AMOUNT_USDT', 0.1):
                transferred = _transfer_executor.execute_transfer(amount=transfer_amount, from_account_side=side, exchange_adapter=self._exchange, config=self._config, balance_manager=self._balance_manager)
                if transferred > 0: self._balance_manager.record_real_profit_transfer(transferred)
        
        return result.get('success', False)
