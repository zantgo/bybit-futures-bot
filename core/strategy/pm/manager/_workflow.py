"""
Módulo del Position Manager: Workflow.

v7.2 (Gestión de Estado DETENIENDO):
- `check_and_close_positions` ahora reconoce el nuevo estado de transición
  'DETENIENDO' de una Operación.
- Si detecta este estado, inicia el cierre masivo de todas las posiciones
  para ese lado, completando el flujo de detención asíncrono.
"""
import datetime
from typing import Any, List, Dict

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
            # Asumiendo que _open_logical_position está en la clase que hereda de _Workflow
            self._open_logical_position(side_to_open, entry_price, timestamp)

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """Revisa SL, TS y solicitudes de cierre forzoso para todas las posiciones abiertas en cada tick."""
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se elimina la comprobación 'or not self._private_logic' que causaba el AttributeError.
        if not self._initialized or not self._executor:
            return
        # --- FIN DE LA MODIFICACIÓN ---

        for side in ['long', 'short']:
            # Obtenemos la operación específica para el lado que estamos revisando
            operacion = self._om_api.get_operation_by_side(side)
            
            if not operacion:
                continue

            # --- INICIO DE LA MODIFICACIÓN: Reaccionar al estado DETENIENDO ---
            # Si el OM ha puesto la operación en estado 'DETENIENDO', el PM debe actuar.
            if operacion.estado == 'DETENIENDO':
                open_positions_count = len(operacion.posiciones_activas.get(side, []))
                if open_positions_count > 0:
                    self._memory_logger.log(f"PM Workflow: Detectado estado DETENIENDO para {side.upper()}. "
                                            f"Iniciando cierre de {open_positions_count} posiciones.", "WARN")
                    # Llama al método del propio PM para cerrar todas las posiciones, evitando deadlocks.
                    self.close_all_logical_positions(side, reason="FORCE_STOP")
                
                # Una vez que se inicia el cierre, no hay nada más que hacer en este tick para este lado.
                continue
            # --- FIN DE LA MODIFICACIÓN ---

            # Si la operación no está activa, no se deben abrir/cerrar posiciones por SL/TS.
            if operacion.estado != 'ACTIVA':
                continue

            # Hacemos una copia para evitar problemas de modificación durante la iteración
            open_positions = list(operacion.posiciones_activas.get(side, []))
            
            if not open_positions:
                continue
            
            positions_to_close: List[Dict[str, Any]] = []
            for i, pos in enumerate(open_positions):
                sl_price = pos.stop_loss_price
                # Comprobación de Stop Loss
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    positions_to_close.append({'index': i, 'reason': 'SL'})
                    continue # Si salta SL, no necesitamos comprobar TS
                
                # Actualización y comprobación de Trailing Stop
                # La siguiente línea asume que la instancia 'self' tiene acceso a '_private_logic'
                # lo cual es correcto debido a la herencia múltiple en PositionManager.
                self._update_trailing_stop(side, pos, i, current_price)
                
                # Leemos la posición actualizada del estado del manager
                operacion_actualizada = self._om_api.get_operation_by_side(side)
                if not operacion_actualizada: continue
                
                # Asegurarse de que la posición todavía existe en el índice esperado
                if i < len(operacion_actualizada.posiciones_activas.get(side, [])):
                    pos_actualizada = operacion_actualizada.posiciones_activas[side][i]
                    ts_stop_price = pos_actualizada.ts_stop_price
                    if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                        # Asegurarse de que no esté ya en la lista por otra razón
                        if not any(d['index'] == i for d in positions_to_close):
                            positions_to_close.append({'index': i, 'reason': 'TS'})

            # Cerramos las posiciones marcadas, iterando en orden inverso para no alterar los índices
            for close_info in sorted(positions_to_close, key=lambda x: x['index'], reverse=True):
                trade_result = self._close_logical_position(
                    side, 
                    close_info['index'], 
                    current_price, 
                    timestamp, 
                    reason=close_info.get('reason', "UNKNOWN")
                )
                if trade_result and trade_result.get('success'):
                    # Extraemos los datos relevantes del resultado del cierre.
                    realized_pnl = trade_result.get('pnl_net_usdt', 0.0)
                    commission_fee = trade_result.get('commission_usdt', 0.0)
                    
                    # 1. Actualizar el PNL realizado de la operación.
                    self._om_api.actualizar_pnl_realizado(
                        side=side,
                        pnl_amount=realized_pnl
                    )
                    
                    # 2. Si hubo una comisión, la registramos en la operación.
                    #    Esta es la conexión final del flujo de comisiones.
                    if commission_fee > 0:
                        self._om_api.actualizar_comisiones_totales(
                            side=side,
                            fee_amount=commission_fee
                        )