"""
Módulo del Position Manager: Lógica Privada.

v6.2 (Inmutabilidad del TSL):
- `_open_logical_position` ahora pasa los parámetros de TSL al `PositionExecutor`
  para que queden almacenados en el objeto `LogicalPosition` al momento de su creación.
- `_update_trailing_stop` ha sido modificado para leer los parámetros de TSL
  desde el propio objeto de la posición, en lugar de la operación activa.
  Esto asegura que los cambios en la configuración solo afecten a nuevas posiciones.
"""
import datetime
import uuid
from typing import Any
from collections import defaultdict

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
        self._initialized = False; self._operation_mode = "unknown"
        self._total_realized_pnl_long = 0.0; self._total_realized_pnl_short = 0.0
        self._session_tp_hit = False; self._session_start_time = None
        self._global_stop_loss_roi_pct = None; self._global_take_profit_roi_pct = None
        self.operacion_activa = None

    def _start_operation(self, reason: str):
        """Activa la operación actual que está EN_ESPERA."""
        if self.operacion_activa and self.operacion_activa.estado == 'EN_ESPERA':
            self.operacion_activa.estado = 'ACTIVA'
            self.operacion_activa.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
            self._memory_logger.log(f"OPERACIÓN INICIADA: Modo '{self.operacion_activa.tendencia}' activado. Razón: {reason}", "INFO")

    def _end_operation(self, reason: str):
        """Finaliza la operación activa y la resetea a un estado NEUTRAL EN_ESPERA."""
        if self.operacion_activa and self.operacion_activa.estado == 'ACTIVA':
            tendencia_anterior = self.operacion_activa.tendencia
            self._memory_logger.log(f"OPERACIÓN FINALIZADA: Modo '{tendencia_anterior}' terminado. Razón: {reason}", "INFO")

            capital_actual = self.operacion_activa.capital_inicial_usdt + self.operacion_activa.pnl_realizado_usdt
            
            base_size = self.operacion_activa.tamaño_posicion_base_usdt
            max_pos = self.operacion_activa.max_posiciones_logicas
            leverage = self.operacion_activa.apalancamiento
            
            op_neutral = Operacion(
                id=f"op_neutral_{uuid.uuid4()}",
                estado='EN_ESPERA', tendencia='NEUTRAL',
                tamaño_posicion_base_usdt=base_size, max_posiciones_logicas=max_pos,
                apalancamiento=leverage, sl_posicion_individual_pct=0.0,
                tsl_activacion_pct=0.0, tsl_distancia_pct=0.0,
                capital_inicial_usdt=capital_actual,
                posiciones_activas=self.operacion_activa.posiciones_activas
            )
            self.operacion_activa = op_neutral
            self._position_state.sync_logical_positions(self.operacion_activa.posiciones_activas)
            
            # (COMENTADO) Se elimina la llamada al método inexistente `save_state`.
            # self.save_state()

    def _can_open_new_position(self, side: str) -> bool:
        if self._session_tp_hit or not self.operacion_activa: return False
        open_positions_count = len(self.operacion_activa.posiciones_activas.get(side, []))
        if open_positions_count >= self.operacion_activa.max_posiciones_logicas:
            return False
        if self._balance_manager.get_available_margin(side) < 1.0:
            return False
        return True

    def _open_logical_position(self, side: str, entry_price: float, timestamp: datetime.datetime):
        if not self.operacion_activa: return
        open_positions_count = len(self.operacion_activa.posiciones_activas.get(side, []))
        available_slots = self.operacion_activa.max_posiciones_logicas - open_positions_count
        if available_slots <= 0: return
        available_margin = self._balance_manager.get_available_margin(side)
        margin_per_slot = self._utils.safe_division(available_margin, available_slots)
        margin_to_use = min(self.operacion_activa.tamaño_posicion_base_usdt, margin_per_slot)
        if margin_to_use < 1.0:
            self._memory_logger.log(f"Apertura omitida: Margen a usar ({margin_to_use:.4f} USDT) es menor al umbral mínimo.", level="WARN")
            return
            
        # --- INICIO DE LA MODIFICACIÓN: Pasar parámetros de TSL al ejecutor ---
        result = self._executor.execute_open(
            side=side, entry_price=entry_price, timestamp=timestamp, 
            margin_to_use=margin_to_use, 
            sl_pct=self.operacion_activa.sl_posicion_individual_pct,
            leverage=self.operacion_activa.apalancamiento,
            tsl_activation_pct=self.operacion_activa.tsl_activacion_pct,
            tsl_distance_pct=self.operacion_activa.tsl_distancia_pct
        )
        # --- FIN DE LA MODIFICACIÓN ---

        if result and result.get('success'):
            new_pos_obj = result.get('logical_position_object')
            if new_pos_obj:
                self.operacion_activa.posiciones_activas[side].append(new_pos_obj)
                self._position_state.add_logical_position_obj(side, new_pos_obj)


    def _update_trailing_stop(self, side, position_obj: LogicalPosition, index: int, current_price: float):
        if not self.operacion_activa: return
        
        # --- INICIO DE LA MODIFICACIÓN: Leer parámetros de TSL desde la posición, no de la operación ---
        activation_pct = position_obj.tsl_activation_pct_at_open
        distance_pct = position_obj.tsl_distance_pct_at_open
        # --- FIN DE LA MODIFICACIÓN ---
        
        is_ts_active = position_obj.ts_is_active
        entry_price = position_obj.entry_price
        
        if not is_ts_active and activation_pct > 0 and entry_price:
            activation_price = entry_price * (1 + activation_pct / 100) if side == 'long' else entry_price * (1 - activation_pct / 100)
            if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                self.operacion_activa.posiciones_activas[side][index].ts_is_active = True
                self.operacion_activa.posiciones_activas[side][index].ts_peak_price = current_price
        
        # Re-evaluar el estado `ts_is_active` por si acaba de cambiar en la línea anterior
        if self.operacion_activa.posiciones_activas[side][index].ts_is_active:
            peak_price = self.operacion_activa.posiciones_activas[side][index].ts_peak_price or current_price
            if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                self.operacion_activa.posiciones_activas[side][index].ts_peak_price = current_price
            
            new_peak_price = self.operacion_activa.posiciones_activas[side][index].ts_peak_price
            new_stop_price = new_peak_price * (1 - distance_pct / 100) if side == 'long' else new_peak_price * (1 + distance_pct / 100)
            self.operacion_activa.posiciones_activas[side][index].ts_stop_price = new_stop_price

    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> bool:
        if not self._executor or not self.operacion_activa: return False
        
        pos_to_close = self.operacion_activa.posiciones_activas[side][index]
        result = self._executor.execute_close(pos_to_close, side, exit_price, timestamp, reason)
        
        if result and result.get('success', False):
            self.operacion_activa.posiciones_activas[side].pop(index)
            self._position_state.remove_logical_position(side, index)

            pnl = result.get('pnl_net_usdt', 0.0)
            if side == 'long': self._total_realized_pnl_long += pnl
            else: self._total_realized_pnl_short += pnl
            
            self.operacion_activa.pnl_realizado_usdt += pnl
            self.operacion_activa.comercios_cerrados_contador += 1

            transfer_amount = result.get('amount_transferable_to_profit', 0.0)
            if _transfer_executor and transfer_amount >= getattr(self._config, 'POSITION_MIN_TRANSFER_AMOUNT_USDT', 0.1):
                transferred = _transfer_executor.execute_transfer(amount=transfer_amount, from_account_side=side, exchange_adapter=self._exchange, config=self._config, balance_manager=self._balance_manager)
                if transferred > 0: self._balance_manager.record_real_profit_transfer(transferred)
        
        return result.get('success', False)

    def _handle_position_management_on_force_trigger(self, long_pos_action: str, short_pos_action: str):
        # (COMENTADO) Esta función estaba relacionada con Hitos y ya no se usa en el flujo principal.
        # Se mantiene para evitar romper alguna dependencia indirecta no prevista.
        self._memory_logger.log(f"Gestión de posiciones pre-activación: LONGS={long_pos_action}, SHORTS={short_pos_action}", "INFO")
        reason = "FORCE_TRIGGER_TRANSITION"
        if long_pos_action == 'close': self.close_all_logical_positions('long', reason=reason)
        if short_pos_action == 'close': self.close_all_logical_positions('short', reason=reason)