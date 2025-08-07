"""
Módulo del Position Manager: Workflow.
"""
import datetime
from typing import Any, List, Dict

class _Workflow:
    """Clase base que contiene los métodos de workflow del PositionManager."""

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
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
        if not self._initialized or not self._executor:
            return

        for side in ['long', 'short']:
            operacion = self._om_api.get_operation_by_side(side)
            
            if not operacion:
                continue

            if operacion.estado == 'DETENIENDO':
                open_positions_count = len(operacion.posiciones_activas.get(side, []))
                if open_positions_count > 0:
                    self._memory_logger.log(f"PM Workflow: Detectado estado DETENIENDO para {side.upper()}. "
                                            f"Iniciando cierre de {open_positions_count} posiciones.", "WARN")
                    self.close_all_logical_positions(side, reason="FORCE_STOP")
                continue

            # --- INICIO DE LA CORRECCIÓN ---
            # Permitimos la gestión de posiciones existentes si la operación está ACTIVA o PAUSADA.
            if operacion.estado not in ['ACTIVA', 'PAUSADA']:
                continue
            # --- FIN DE LA CORRECCIÓN ---

            open_positions = list(operacion.posiciones_activas.get(side, []))
            
            if not open_positions:
                continue
            
            positions_to_close: List[Dict[str, Any]] = []
            for i, pos in enumerate(open_positions):
                sl_price = pos.stop_loss_price
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    positions_to_close.append({'index': i, 'reason': 'SL'})
                    continue 
                
                self._update_trailing_stop(side, pos, i, current_price)
                
                operacion_actualizada = self._om_api.get_operation_by_side(side)
                if not operacion_actualizada: continue
                
                if i < len(operacion_actualizada.posiciones_activas.get(side, [])):
                    pos_actualizada = operacion_actualizada.posiciones_activas[side][i]
                    ts_stop_price = pos_actualizada.ts_stop_price
                    if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                        if not any(d['index'] == i for d in positions_to_close):
                            positions_to_close.append({'index': i, 'reason': 'TS'})

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
                    
                    self._om_api.actualizar_pnl_realizado(
                        side=side,
                        pnl_amount=realized_pnl
                    )
                    
                    if commission_fee > 0:
                        self._om_api.actualizar_comisiones_totales(
                            side=side,
                            fee_amount=commission_fee
                        )