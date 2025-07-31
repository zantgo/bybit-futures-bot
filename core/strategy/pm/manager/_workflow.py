"""
Módulo del Position Manager: Workflow.

v7.0 (Operaciones Duales):
- Se refactorizan los métodos para usar la nueva om_api que gestiona
  operaciones LONG y SHORT de forma independiente.
- handle_low_level_signal ahora consulta la operación específica del
  lado de la señal (BUY -> long, SELL -> short).
- check_and_close_positions consulta la operación de cada lado dentro
  de su bucle de revisión.
"""
import datetime
from typing import Any

class _Workflow:
    """Clase base que contiene los métodos de workflow del PositionManager."""

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
        """Punto de entrada para señales desde el `event_processor`."""
        if not self._initialized or not self._executor:
            return
        
        # Determinar el lado objetivo basado en la señal de bajo nivel
        side_to_open = 'long' if signal == "BUY" else 'short' if signal == "SELL" else None
        
        # Si la señal no es de compra o venta, no hay nada que abrir.
        if not side_to_open:
            return

        # Obtener la operación específica para el lado que intentamos abrir
        operacion = self._om_api.get_operation_by_side(side_to_open)
        
        # Comprobar si la operación para este lado está ACTIVA y si podemos abrir una nueva posición
        if operacion and operacion.estado == 'ACTIVA' and self._can_open_new_position(side_to_open):
            self._open_logical_position(side_to_open, entry_price, timestamp)

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """Revisa SL y TS para todas las posiciones abiertas en cada tick."""
        if not self._initialized or not self._executor:
            return
        
        for side in ['long', 'short']:
            # Obtenemos la operación específica para el lado que estamos revisando
            operacion = self._om_api.get_operation_by_side(side)
            
            # Si no hay operación o no está activa para este lado, saltamos a la siguiente iteración
            if not operacion or operacion.estado != 'ACTIVA':
                continue

            # Hacemos una copia para evitar problemas de modificación durante la iteración
            open_positions = list(operacion.posiciones_activas.get(side, []))
            
            if not open_positions:
                continue
            
            indices_to_close, reasons = [], {}
            for i, pos in enumerate(open_positions):
                sl_price = pos.stop_loss_price
                # Comprobación de Stop Loss
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    indices_to_close.append(i)
                    reasons[i] = "SL"
                    continue # Si salta SL, no necesitamos comprobar TS
                
                # Actualización y comprobación de Trailing Stop
                # Esta llamada ahora es segura, ya que _update_trailing_stop también usará get_operation_by_side
                self._update_trailing_stop(side, pos, i, current_price)
                
                # Leemos la posición actualizada del estado del manager (es crucial recargar la operación
                # por si _update_trailing_stop la modificó)
                operacion_actualizada = self._om_api.get_operation_by_side(side)
                if not operacion_actualizada: continue # Doble check de seguridad
                pos_actualizada = operacion_actualizada.posiciones_activas[side][i]

                ts_stop_price = pos_actualizada.ts_stop_price
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                    # Asegurarse de que no esté ya en la lista por otra razón
                    if i not in indices_to_close:
                        indices_to_close.append(i)
                        reasons[i] = "TS"

            # Cerramos las posiciones marcadas, iterando en orden inverso para no alterar los índices
            for index in sorted(list(set(indices_to_close)), reverse=True):
                self._close_logical_position(side, index, current_price, timestamp, reason=reasons.get(index, "UNKNOWN"))