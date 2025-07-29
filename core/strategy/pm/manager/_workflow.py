"""
Módulo del Position Manager: Workflow.

v6.1 (Consolidación de Entidades):
- Se actualizan las referencias para acceder a los parámetros de la
  operación directamente desde `operacion_activa`, eliminando el
  sub-objeto `configuracion`.
- Se comenta la lógica obsoleta de procesamiento de hitos.
"""
import datetime
from typing import Any

class _Workflow:
    """Clase base que contiene los métodos de workflow del PositionManager."""

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
        """Punto de entrada para señales desde el `event_processor`."""
        operacion = self._om_api.get_operation()
        if not self._initialized or not self._executor or not operacion: return
        
        tendencia_operacion = operacion.tendencia
        side_to_open = 'long' if signal == "BUY" else 'short'
        side_allowed = (side_to_open == 'long' and tendencia_operacion in ["LONG_ONLY", "LONG_SHORT"]) or \
                       (side_to_open == 'short' and tendencia_operacion in ["SHORT_ONLY", "LONG_SHORT"])
                       
        if side_allowed and self._can_open_new_position(side_to_open):
            self._open_logical_position(side_to_open, entry_price, timestamp)

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """Revisa SL y TS para todas las posiciones abiertas en cada tick."""
        operacion = self._om_api.get_operation()
        if not self._initialized or not self._executor or not operacion: return
        
        for side in ['long', 'short']:
            # Hacemos una copia para evitar problemas de modificación durante la iteración
            open_positions = list(operacion.posiciones_activas.get(side, []))
            
            if not open_positions: continue
            
            indices_to_close, reasons = [], {}
            for i, pos in enumerate(open_positions):
                sl_price = pos.stop_loss_price
                # Comprobación de Stop Loss
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    indices_to_close.append(i)
                    reasons[i] = "SL"
                    continue # Si salta SL, no necesitamos comprobar TS
                
                # Actualización y comprobación de Trailing Stop
                self._update_trailing_stop(side, pos, i, current_price)
                
                # Leemos la posición actualizada del estado del manager
                pos_actualizada = operacion.posiciones_activas[side][i]
                ts_stop_price = pos_actualizada.ts_stop_price
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                    indices_to_close.append(i)
                    reasons[i] = "TS"

            # Cerramos las posiciones marcadas, iterando en orden inverso para no alterar los índices
            for index in sorted(list(set(indices_to_close)), reverse=True):
                self._close_logical_position(side, index, current_price, timestamp, reason=reasons.get(index, "UNKNOWN"))