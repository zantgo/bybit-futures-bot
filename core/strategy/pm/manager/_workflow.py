"""
Módulo del Position Manager: Workflow.

v4.4 (Corrección de Cascada Inmutable):
- La lógica en `process_triggered_milestone` ha sido refactorizada para seguir
  un patrón de "reconstrucción de estado" inmutable. En lugar de modificar
  la lista de hitos mientras se itera, se construye una nueva lista con los
  estados actualizados, garantizando que la cascada (cancelación de hermanos
  y activación de hijos) se aplique de forma atómica y correcta.
"""
import datetime
from typing import Any

class _Workflow:
    """Clase base que contiene los métodos de workflow del PositionManager."""

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
        """Punto de entrada para señales desde el `event_processor`."""
        if not self._initialized or not self._executor or not self.operacion_activa: return
        tendencia_operacion = self.operacion_activa.configuracion.tendencia
        side_to_open = 'long' if signal == "BUY" else 'short'
        side_allowed = (side_to_open == 'long' and tendencia_operacion in ["LONG_ONLY", "LONG_SHORT"]) or \
                       (side_to_open == 'short' and tendencia_operacion in ["SHORT_ONLY", "LONG_SHORT"])
        if side_allowed and self._can_open_new_position(side_to_open):
            self._open_logical_position(side_to_open, entry_price, timestamp)

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """Revisa SL y TS para todas las posiciones abiertas en cada tick."""
        if not self._initialized or not self._executor or not self.operacion_activa: return
        for side in ['long', 'short']:
            open_positions = self.operacion_activa.posiciones_activas.get(side, [])
            if not open_positions: continue
            indices_to_close, reasons = [], {}
            for i, pos in enumerate(open_positions):
                sl_price = pos.stop_loss_price
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    indices_to_close.append(i); reasons[i] = "SL"; continue
                self._update_trailing_stop(side, pos, i, current_price)
                pos_actualizada = self.operacion_activa.posiciones_activas[side][i]
                ts_stop_price = pos_actualizada.ts_stop_price
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                    indices_to_close.append(i); reasons[i] = "TS"
            for index in sorted(list(set(indices_to_close)), reverse=True):
                self._close_logical_position(side, index, current_price, timestamp, reason=reasons.get(index, "UNKNOWN"))

    def process_triggered_milestone(self, milestone_id: str):
        """Procesa la cascada de un hito cumplido, reconstruyendo el estado del árbol."""
        triggered_hito = next((m for m in self._milestones if m.id == milestone_id), None)
        if not triggered_hito: return
        
        if self.operacion_activa and self.operacion_activa.configuracion.tendencia != 'NEUTRAL':
             self._end_operation("Hito completado, iniciando nueva operación")

        # --- INICIO DE LA MODIFICACIÓN: Lógica de reconstrucción de estado ---
        
        next_milestones_state = []
        parent_id_of_triggered = triggered_hito.parent_id

        for hito in self._milestones:
            # Por defecto, mantenemos el hito como está
            new_hito = hito
            
            # 1. Actualizar el hito que se disparó
            if hito.id == milestone_id:
                new_hito.status = 'COMPLETED'
            
            # 2. Cancelar a los hermanos (hitos con el mismo padre)
            elif hito.parent_id == parent_id_of_triggered and hito.status in ['ACTIVE', 'PENDING']:
                new_hito.status = 'CANCELLED'
                self._memory_logger.log(f"Cascada: Hito hermano ...{hito.id[-6:]} cancelado.", "DEBUG")
            
            # 3. Activar a los hijos
            elif hito.parent_id == milestone_id and hito.status == 'PENDING':
                new_hito.status = 'ACTIVE'
                self._memory_logger.log(f"Cascada: Hito hijo ...{hito.id[-6:]} activado.", "DEBUG")

            next_milestones_state.append(new_hito)
        
        # 4. Reemplazar la lista antigua por la nueva, de forma atómica.
        self._milestones = next_milestones_state
        
        # --- (COMENTADO) Lógica anterior de modificación en el lugar ---
        # # 1. Marcar el hito activado como COMPLETADO.
        # triggered_hito.status = 'COMPLETED'
        # # 2. CANCELAR a todos los "hermanos" del hito completado.
        # parent_id = triggered_hito.parent_id
        # for hito in self._milestones:
        #     if hito.parent_id == parent_id and hito.id != milestone_id and hito.status in ['PENDING', 'ACTIVE']:
        #         hito.status = 'CANCELLED'
        #         self._memory_logger.log(f"Cascada: Hito hermano ...{hito.id[-6:]} cancelado.", "DEBUG")
        # # 3. ACTIVAR a todos los "hijos" directos del hito completado.
        # for hito in self._milestones:
        #     if hito.parent_id == milestone_id and hito.status == 'PENDING':
        #         hito.status = 'ACTIVE'
        #         self._memory_logger.log(f"Cascada: Hito hijo ...{hito.id[-6:]} activado.", "DEBUG")
        # --- FIN DE LA MODIFICACIÓN ---

        # 5. Ejecutar la acción del hito
        if triggered_hito.tipo_hito == 'INICIALIZACION':
            config_nueva_op = triggered_hito.accion.configuracion_nueva_operacion
            if config_nueva_op:
                self._start_operation(config_nueva_op, triggered_hito.id)

        elif triggered_hito.tipo_hito == 'FINALIZACION':
            if triggered_hito.accion.cerrar_posiciones_al_finalizar:
                 self.close_all_logical_positions('long', reason=f"HITO_FIN_{milestone_id[-6:]}")
                 self.close_all_logical_positions('short', reason=f"HITO_FIN_{milestone_id[-6:]}")

        # 6. Limpiar hitos obsoletos del árbol
        self._cleanup_completed_milestones()