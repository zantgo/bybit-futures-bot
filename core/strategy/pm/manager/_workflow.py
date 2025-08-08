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

            if operacion.estado == 'DETENIENDO':
                open_positions_count = operacion.posiciones_abiertas_count
                if open_positions_count > 0:
                    self._memory_logger.log(f"PM Workflow: Detectado estado DETENIENDO para {side.upper()}. "
                                            f"Iniciando cierre de {open_positions_count} posiciones.", "WARN")
                    self.close_all_logical_positions(side, reason="FORCE_STOP")
                continue

            if operacion.estado not in ['ACTIVA', 'PAUSADA']:
                continue

            open_positions = list(operacion.posiciones_abiertas)
            
            if not open_positions:
                continue
            
            positions_to_close: List[Dict[str, Any]] = []
            
            all_positions = list(operacion.posiciones)

            for pos in open_positions:
                try:
                    original_index = next(i for i, p in enumerate(all_positions) if p.id == pos.id)
                except StopIteration:
                    continue
                
                sl_price = pos.stop_loss_price
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    positions_to_close.append({'index': original_index, 'reason': 'SL'})
                    continue 
                
                # --- INICIO DE LA MODIFICACIÓN (Solución al bug del TSL) ---
                # 4. Se actualiza la llamada a _update_trailing_stop para no pasar el objeto 'pos',
                #    que podría estar obsoleto. Solo pasamos el 'index'.
                # self._update_trailing_stop(side, pos, original_index, current_price) # <-- LÍNEA ORIGINAL
                self._update_trailing_stop(side, original_index, current_price)
                # --- FIN DE LA MODIFICACIÓN ---
                
                operacion_actualizada = self._om_api.get_operation_by_side(side)
                if not operacion_actualizada: continue
                
                if original_index < len(operacion_actualizada.posiciones):
                    pos_actualizada = operacion_actualizada.posiciones[original_index]
                    ts_stop_price = pos_actualizada.ts_stop_price
                    if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                        if not any(d['index'] == original_index for d in positions_to_close):
                            positions_to_close.append({'index': original_index, 'reason': 'TS'})

            for close_info in sorted(positions_to_close, key=lambda x: x['index'], reverse=True):
                self._close_logical_position(
                    side, 
                    close_info['index'], 
                    current_price, 
                    timestamp, 
                    reason=close_info.get('reason', "UNKNOWN")
                )