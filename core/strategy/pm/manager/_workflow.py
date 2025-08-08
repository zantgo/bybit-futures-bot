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

# Reemplaza la función completa en /core/strategy/pm/manager/_workflow.py

def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
    """
    Revisa todas las posiciones abiertas para posible cierre por SL, TSL o detención forzosa.
    Refactorizado para separar la fase de actualización de estado de la fase de decisión,
    lo que soluciona el problema de retardo de 1 tick en el TSL.
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

        # Obtenemos los índices de las posiciones que están abiertas ANTES de cualquier modificación.
        initial_open_indices = [i for i, p in enumerate(operacion.posiciones) if p.estado == 'ABIERTA']
        
        if not initial_open_indices:
            continue

        # --- FASE 1: ACTUALIZAR EL ESTADO DE TODOS LOS TRAILING STOPS ---
        # En esta fase, solo modificamos el estado. No tomamos decisiones de cierre.
        # Esto asegura que el estado esté completamente actualizado para el tick actual
        # ANTES de que empecemos a comprobar las condiciones de cierre.
        for index in initial_open_indices:
            self._update_trailing_stop(side, index, current_price)

        # --- FASE 2: TOMAR DECISIONES DE CIERRE BASADO EN EL ESTADO FINAL Y COHERENTE ---
        # Obtenemos el estado final y completamente actualizado de la operación para este tick.
        # Ahora contiene todos los cambios realizados en la Fase 1.
        operacion_actualizada = self._om_api.get_operation_by_side(side)
        if not operacion_actualizada:
            continue

        positions_to_close = []
        # Iteramos de nuevo sobre los índices originales para comprobar las condiciones de cierre
        # sobre el estado ya actualizado.
        for index in initial_open_indices:
            if index >= len(operacion_actualizada.posiciones):
                continue
            
            pos = operacion_actualizada.posiciones[index]
            
            # Comprobación de Stop Loss (SL)
            sl_price = pos.stop_loss_price
            if sl_price and ((side == 'long' and current_price <= sl_price) or \
                             (side == 'short' and current_price >= sl_price)):
                positions_to_close.append({'index': index, 'reason': 'SL'})
                # Usamos 'continue' porque si se activa el SL, no hay necesidad de comprobar el TSL.
                # La prioridad es del SL.
                continue

            # Comprobación de Trailing Stop Loss (TSL)
            ts_stop_price = pos.ts_stop_price
            if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or \
                                  (side == 'short' and current_price >= ts_stop_price)):
                positions_to_close.append({'index': index, 'reason': 'TS'})

        # --- FASE 3: EJECUTAR CIERRES ---
        # Si hay posiciones para cerrar, las procesamos en orden inverso de índice para no
        # invalidar los índices de las demás posiciones en la lista.
        if positions_to_close:
            # Ordenamos por índice en reversa para un cierre seguro.
            for close_info in sorted(positions_to_close, key=lambda x: x['index'], reverse=True):
                self._close_logical_position(
                    side, 
                    close_info['index'], 
                    current_price, 
                    timestamp, 
                    reason=close_info.get('reason', "UNKNOWN")
                )
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

            all_positions = list(operacion.posiciones)
            open_position_indices = [i for i, p in enumerate(all_positions) if p.estado == 'ABIERTA']
            
            if not open_position_indices:
                continue
            
            positions_to_close: List[Dict[str, Any]] = []

            for index in open_position_indices:
                current_operacion = self._om_api.get_operation_by_side(side)
                if not current_operacion or index >= len(current_operacion.posiciones):
                    continue
                
                pos = current_operacion.posiciones[index]
                original_index = index

                sl_price = pos.stop_loss_price
                
                # --- INICIO DE LA MODIFICACIÓN (Mejora de Robustez) ---
                # Se elimina la palabra clave 'continue'. Esto asegura que, para cada
                # posición en cada tick, SIEMPRE se evalúe tanto el SL como la lógica del TSL.
                # Esto previene casos borde y hace el flujo más predecible.
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    positions_to_close.append({'index': original_index, 'reason': 'SL'})
                    # continue # <-- LÍNEA ORIGINAL ELIMINADA
                # --- FIN DE LA MODIFICACIÓN ---
                
                self._update_trailing_stop(side, original_index, current_price)
                
                operacion_actualizada = self._om_api.get_operation_by_side(side)
                if not operacion_actualizada: continue
                
                if original_index < len(operacion_actualizada.posiciones):
                    pos_actualizada = operacion_actualizada.posiciones[original_index]
                    ts_stop_price = pos_actualizada.ts_stop_price
                    if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                        # Nos aseguramos de no añadir la misma posición a la lista de cierre
                        # si ya fue marcada por el SL en este mismo tick.
                        if not any(d['index'] == original_index for d in positions_to_close):
                            positions_to_close.append({'index': original_index, 'reason': 'TS'})

            # Es crucial ordenar por índice en reversa para no invalidar los índices de las posiciones restantes.
            for close_info in sorted(positions_to_close, key=lambda x: x['index'], reverse=True):
                self._close_logical_position(
                    side, 
                    close_info['index'], 
                    current_price, 
                    timestamp, 
                    reason=close_info.get('reason', "UNKNOWN")
                )