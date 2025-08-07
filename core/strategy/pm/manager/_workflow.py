# ./core/strategy/pm/manager/_workflow.py

"""
Módulo del Position Manager: Workflow.
"""
import datetime
from typing import Any, List, Dict

class _Workflow:
    """Clase base que contiene los métodos de workflow del PositionManager."""

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
        """Gestiona una señal de bajo nivel (BUY/SELL) para potencialmente abrir una posición."""
        if not self._initialized or not self._executor:
            return
        
        side_to_open = 'long' if signal == "BUY" else 'short' if signal == "SELL" else None
        
        if not side_to_open:
            return

        operacion = self._om_api.get_operation_by_side(side_to_open)
        
        # Esta comprobación (estado == 'ACTIVA') ya previene nuevas aperturas en modo PAUSADO.
        if operacion and operacion.estado == 'ACTIVA' and self._can_open_new_position(side_to_open):
            self._open_logical_position(side_to_open, entry_price, timestamp)

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """
        Revisa todas las posiciones abiertas para posible cierre por SL, TSL o detención forzosa.
        """
        if not self._initialized or not self._executor:
            return

        for side in ['long', 'short']:
            operacion = self._om_api.get_operation_by_side(side)
            
            if not operacion:
                continue

            # <<-- CAMBIO: La lógica de cierre forzoso ahora usa la nueva propiedad de conteo.
            if operacion.estado == 'DETENIENDO':
                open_positions_count = operacion.posiciones_abiertas_count
                # <<-- ANTERIOR: open_positions_count = len(operacion.posiciones_activas.get(side, []))
                if open_positions_count > 0:
                    self._memory_logger.log(f"PM Workflow: Detectado estado DETENIENDO para {side.upper()}. "
                                            f"Iniciando cierre de {open_positions_count} posiciones.", "WARN")
                    self.close_all_logical_positions(side, reason="FORCE_STOP")
                continue

            # Permitimos la gestión de posiciones existentes si la operación está ACTIVA o PAUSADA.
            if operacion.estado not in ['ACTIVA', 'PAUSADA']:
                continue

            # <<-- CAMBIO: Se itera directamente sobre la lista de posiciones abiertas.
            open_positions = list(operacion.posiciones_abiertas)
            # <<-- ANTERIOR: open_positions = list(operacion.posiciones_activas.get(side, []))
            
            if not open_positions:
                continue
            
            positions_to_close: List[Dict[str, Any]] = []
            
            # Necesitamos la lista completa para encontrar el índice original.
            all_positions = list(operacion.posiciones)

            for pos in open_positions:
                # Encontrar el índice original de la posición en la lista completa.
                try:
                    original_index = next(i for i, p in enumerate(all_positions) if p.id == pos.id)
                except StopIteration:
                    continue # La posición no se encontró, omitir por seguridad.
                
                sl_price = pos.stop_loss_price
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    positions_to_close.append({'index': original_index, 'reason': 'SL'})
                    continue 
                
                # <<-- CAMBIO: Se pasa el índice original al TSL updater.
                self._update_trailing_stop(side, pos, original_index, current_price)
                
                operacion_actualizada = self._om_api.get_operation_by_side(side)
                if not operacion_actualizada: continue
                
                # Re-obtener la posición actualizada después del TSL
                if original_index < len(operacion_actualizada.posiciones):
                    pos_actualizada = operacion_actualizada.posiciones[original_index]
                    # <<-- ANTERIOR: pos_actualizada = operacion_actualizada.posiciones_activas[side][i]
                    ts_stop_price = pos_actualizada.ts_stop_price
                    if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                        if not any(d['index'] == original_index for d in positions_to_close):
                            positions_to_close.append({'index': original_index, 'reason': 'TS'})

            # Es crucial ordenar por índice en reversa para no invalidar los índices de las posiciones restantes.
            for close_info in sorted(positions_to_close, key=lambda x: x['index'], reverse=True):
                trade_result = self._close_logical_position(
                    side, 
                    close_info['index'], 
                    current_price, 
                    timestamp, 
                    reason=close_info.get('reason', "UNKNOWN")
                )
                if trade_result and trade_result.get('success'):
                    realized_pnl = trade_result.get('pnl_net_usdt', 0.0)
                    commission_fee = trade_result.get('commission_usdt', 0.0)
                    
                    # <<-- CAMBIO: Esta lógica ya está en _close_logical_position. Se comenta para evitar duplicidad.
                    # self._om_api.actualizar_pnl_realizado(
                    #     side=side,
                    #     pnl_amount=realized_pnl
                    # )
                    
                    # if commission_fee > 0:
                    #     self._om_api.actualizar_comisiones_totales(
                    #         side=side,
                    #         fee_amount=commission_fee
                    #     )