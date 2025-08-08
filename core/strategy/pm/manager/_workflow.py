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
        Refactorizado para separar la fase de actualización de estado de la fase de decisión.
        """
        if not self._initialized or not self._executor:
            return

        for side in ['long', 'short']:
            operacion = self._om_api.get_operation_by_side(side)
            if not operacion:
                continue

            # --- GESTIÓN DE DETENCIÓN FORZOSA ---
            if operacion.estado == 'DETENIENDO':
                if operacion.posiciones_abiertas_count > 0:
                    self._memory_logger.log(f"PM Workflow: Detectado estado DETENIENDO para {side.upper()}. "
                                            f"Iniciando cierre de {operacion.posiciones_abiertas_count} posiciones.", "WARN")
                    self.close_all_logical_positions(side, reason="FORCE_STOP")
                continue

            if operacion.estado not in ['ACTIVA', 'PAUSADA']:
                continue

            initial_open_indices = [i for i, p in enumerate(operacion.posiciones) if p.estado == 'ABIERTA']
            
            if not initial_open_indices:
                continue

            # --- FASE 1: ACTUALIZAR EL ESTADO DE TODOS LOS TRAILING STOPS ---
            for index in initial_open_indices:
                self._update_trailing_stop(side, index, current_price)

            # --- FASE 2: TOMAR DECISIONES DE CIERRE BASADO EN EL ESTADO FINAL ---
            operacion_actualizada = self._om_api.get_operation_by_side(side)
            if not operacion_actualizada:
                continue

            positions_to_close = []
            for index in initial_open_indices:
                if index >= len(operacion_actualizada.posiciones):
                    continue
                
                pos = operacion_actualizada.posiciones[index]
                
                # Comprobación de Stop Loss (SL)
                sl_price = pos.stop_loss_price
                if sl_price and ((side == 'long' and current_price <= sl_price) or \
                                 (side == 'short' and current_price >= sl_price)):
                    positions_to_close.append({'index': index, 'reason': 'SL'})
                    continue

                # Comprobación de Trailing Stop Loss (TSL)
                ts_stop_price = pos.ts_stop_price
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or \
                                      (side == 'short' and current_price >= ts_stop_price)):
                    positions_to_close.append({'index': index, 'reason': 'TS'})

            # --- FASE 3: EJECUTAR CIERRES ---
            if positions_to_close:
                for close_info in sorted(positions_to_close, key=lambda x: x['index'], reverse=True):
                    self._close_logical_position(
                        side, 
                        close_info['index'], 
                        current_price, 
                        timestamp, 
                        reason=close_info.get('reason', "UNKNOWN")
                    )