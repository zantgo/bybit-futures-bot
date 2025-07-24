"""
Módulo del Position Manager: Workflow.

Contiene los puntos de entrada principales que son llamados por el
`event_processor` en cada ciclo (tick) del bot para interactuar con
la lógica del PositionManager.
"""
import datetime
from typing import Any

class _Workflow:
    """Clase base que contiene los métodos de workflow del PositionManager."""

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
        """Punto de entrada para señales desde el `event_processor`."""
        if not self._initialized or not self._executor or not self._active_trend:
            return

        trend_mode = self._active_trend['config'].mode
        side_to_open = 'long' if signal == "BUY" else 'short'
        
        side_allowed = (side_to_open == 'long' and trend_mode in ["LONG_ONLY", "LONG_SHORT"]) or \
                       (side_to_open == 'short' and trend_mode in ["SHORT_ONLY", "LONG_SHORT"])
        
        if side_allowed and self._can_open_new_position(side_to_open):
            self._open_logical_position(side_to_open, entry_price, timestamp)

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """Revisa SL y TS para todas las posiciones abiertas en cada tick."""
        if not self._initialized or not self._executor: return

        for side in ['long', 'short']:
            open_positions = self._position_state.get_open_logical_positions(side)
            if not open_positions: continue

            indices_to_close, reasons = [], {}
            for i, pos in enumerate(open_positions):
                sl_price = pos.get('stop_loss_price')
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    indices_to_close.append(i); reasons[i] = "SL"; continue

                self._update_trailing_stop(side, pos, current_price)
                ts_stop_price = pos.get('ts_stop_price')
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                    indices_to_close.append(i); reasons[i] = "TS"

            for index in sorted(list(set(indices_to_close)), reverse=True):
                self._close_logical_position(side, index, current_price, timestamp, reason=reasons.get(index, "UNKNOWN"))

    def process_triggered_milestone(self, milestone_id: str):
        """Procesa la cascada de un hito cumplido."""
        triggered_milestone = next((m for m in self._milestones if m.id == milestone_id), None)
        if not triggered_milestone: return
        
        self._end_trend("Hito completado")
        parent_id = triggered_milestone.parent_id
        for m in self._milestones:
            if m.id == milestone_id:
                m.status = 'COMPLETED'
            elif m.parent_id == parent_id and m.status in ['PENDING', 'ACTIVE']:
                m.status = 'CANCELLED'
            elif m.parent_id == milestone_id and m.status == 'PENDING':
                m.status = 'ACTIVE'

        self._start_trend(triggered_milestone)
        self._cleanup_completed_milestones()