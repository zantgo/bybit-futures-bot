"""
Módulo del Position Manager: Lógica Privada.

Contiene todos los métodos privados (que comienzan con '_') que encapsulan
la lógica de negocio interna y la gestión de estado del PositionManager.
"""
import datetime
from typing import Any

# --- Dependencias de Tipado ---
try:
    from .._entities import Milestone
    from .. import _transfer_executor
except ImportError:
    class Milestone: pass
    _transfer_executor = None

class _PrivateLogic:
    """Clase base que contiene la lógica interna y privada del PositionManager."""

    def _reset_all_states(self):
        """Resetea todos los atributos de estado del manager a sus valores iniciales."""
        self._initialized = False; self._operation_mode = "unknown"; self._leverage = 1.0
        self._max_logical_positions = 1; self._initial_base_position_size_usdt = 0.0
        self._total_realized_pnl_long = 0.0; self._total_realized_pnl_short = 0.0
        self._session_tp_hit = False; self._session_start_time = None
        self._global_stop_loss_roi_pct = None; self._global_take_profit_roi_pct = None
        self._milestones = []; self._active_trend = None

    def _start_trend(self, milestone: Milestone):
        """Activa una nueva tendencia basada en la configuración de un hito."""
        if self._active_trend:
            self._memory_logger.log(f"ADVERTENCIA: Se intentó iniciar una nueva tendencia mientras otra estaba activa.", "WARN")
            self._end_trend("Iniciando nueva tendencia")
        
        self._active_trend = {
            "milestone_id": milestone.id, "config": milestone.action.params,
            "start_time": datetime.datetime.now(datetime.timezone.utc),
            "trades_executed": 0,
            "initial_pnl": self.get_total_pnl_realized()
        }
        mode = self._active_trend['config'].mode
        self._memory_logger.log(f"TENDENCIA INICIADA: Modo '{mode}' activado por hito ...{milestone.id[-6:]}", "INFO")

    def _end_trend(self, reason: str):
        """Finaliza la tendencia activa y vuelve al estado NEUTRAL."""
        if self._active_trend:
            mode = self._active_trend['config'].mode
            self._memory_logger.log(f"TENDENCIA FINALIZADA: Modo '{mode}' terminado. Razón: {reason}", "INFO")
            self._active_trend = None

    def _can_open_new_position(self, side: str) -> bool:
        """Verifica si es posible abrir una nueva posición lógica."""
        if self._session_tp_hit or not self._active_trend: return False
        
        trend_config = self._active_trend['config']
        if trend_config.limit_trade_count is not None and self._active_trend['trades_executed'] >= trend_config.limit_trade_count:
            return False
            
        open_positions_count = len(self._position_state.get_open_logical_positions(side))
        if open_positions_count >= self._max_logical_positions:
            return False
            
        if self._balance_manager.get_available_margin(side) < 1.0: # Umbral de ~1 USDT
            return False
            
        return True

    def _open_logical_position(self, side: str, entry_price: float, timestamp: datetime.datetime):
        """Calcula el margen a usar y delega la apertura al ejecutor."""
        if not self._active_trend: return

        open_positions_count = len(self._position_state.get_open_logical_positions(side))
        available_slots = self._max_logical_positions - open_positions_count
        if available_slots <= 0: return

        available_margin = self._balance_manager.get_available_margin(side)
        margin_per_slot = self._utils.safe_division(available_margin, available_slots)
        
        margin_to_use = min(self._initial_base_position_size_usdt, margin_per_slot)

        if margin_to_use < 1.0:
            self._memory_logger.log(f"Apertura omitida: Margen a usar ({margin_to_use:.4f} USDT) es menor al umbral mínimo.", level="WARN")
            return

        trend_config = self._active_trend['config']
        result = self._executor.execute_open(
            side=side, entry_price=entry_price, timestamp=timestamp, 
            margin_to_use=margin_to_use, sl_pct=trend_config.individual_sl_pct
        )
        if result and result.get('success'):
            self._active_trend['trades_executed'] += 1

    def _update_trailing_stop(self, side, position_data, current_price):
        """Actualiza el estado del Trailing Stop para una posición."""
        if not self._active_trend: return
        trend_config = self._active_trend['config']
        activation_pct = trend_config.trailing_stop_activation_pct
        distance_pct = trend_config.trailing_stop_distance_pct
        is_ts_active = position_data.get('ts_is_active', False)
        entry_price = position_data.get('entry_price')
        if not is_ts_active and activation_pct > 0 and entry_price:
            activation_price = entry_price * (1 + activation_pct / 100) if side == 'long' else entry_price * (1 - activation_pct / 100)
            if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                position_data['ts_is_active'] = True
                position_data['ts_peak_price'] = current_price
        if position_data.get('ts_is_active'):
            peak_price = position_data.get('ts_peak_price', current_price)
            if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                position_data['ts_peak_price'] = current_price
            new_stop_price = position_data['ts_peak_price'] * (1 - distance_pct / 100) if side == 'long' else position_data['ts_peak_price'] * (1 + distance_pct / 100)
            position_data['ts_stop_price'] = new_stop_price
            self._position_state.update_logical_position_details(side, position_data['id'], position_data)
            
    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> bool:
        """Delega el cierre de una posición al ejecutor y maneja el resultado."""
        if not self._executor: return False
        result = self._executor.execute_close(side, index, exit_price, timestamp, reason)
        if result and result.get('success', False):
            pnl = result.get('pnl_net_usdt', 0.0)
            if side == 'long': self._total_realized_pnl_long += pnl
            else: self._total_realized_pnl_short += pnl
            transfer_amount = result.get('amount_transferable_to_profit', 0.0)
            if _transfer_executor and transfer_amount >= getattr(self._config, 'POSITION_MIN_TRANSFER_AMOUNT_USDT', 0.1):
                transferred = _transfer_executor.execute_transfer(
                    amount=transfer_amount, 
                    from_account_side=side,
                    exchange_adapter=self._exchange,
                    config=self._config,
                    balance_manager=self._balance_manager
                )
                if transferred > 0: self._balance_manager.record_real_profit_transfer(transferred)
        return result.get('success', False)

    # --- INICIO DE LA MODIFICACIÓN (REQ-06) ---
    def _handle_position_management_on_force_trigger(
        self,
        long_pos_action: str,
        short_pos_action: str
    ):
        """
        Ejecuta las acciones de cierre sobre las posiciones existentes antes de
        forzar una nueva tendencia.
        """
        self._memory_logger.log(
            f"Gestión de posiciones pre-activación: LONGS={long_pos_action}, SHORTS={short_pos_action}",
            "INFO"
        )
        
        reason = "FORCE_TRIGGER_TRANSITION"

        if long_pos_action == 'close':
            self.close_all_logical_positions('long', reason=reason)
        
        if short_pos_action == 'close':
            self.close_all_logical_positions('short', reason=reason)
            
        # La acción 'keep' no requiere ninguna operación, las posiciones simplemente se mantienen.
    # --- FIN DE LA MODIFICACIÓN ---

    def _cleanup_completed_milestones(self):
        """Limpia el árbol, eliminando hitos obsoletos para evitar acumulación."""
        completed_milestones = sorted(
            [m for m in self._milestones if m.status == 'COMPLETED'],
            key=lambda m: m.created_at,
            reverse=True
        )
        
        last_completed = completed_milestones[0] if completed_milestones else None
        
        def should_keep(milestone: Milestone) -> bool:
            if milestone.status in ['PENDING', 'ACTIVE']: return True
            if milestone == last_completed: return True
            return False

        initial_count = len(self._milestones)
        self._milestones = [m for m in self._milestones if should_keep(m)]
        removed_count = initial_count - len(self._milestones)
        if removed_count > 0:
            self._memory_logger.log(f"LIMPIEZA DE HITOS: {removed_count} hito(s) obsoletos eliminados.", "INFO")