# core/strategy/pm/manager/_workflow.py

"""
Módulo del Position Manager: Workflow.

Contiene los puntos de entrada principales que son llamados por el
`event_processor` en cada ciclo (tick) del bot para interactuar con
la lógica del PositionManager.
"""
# --- INICIO DE LA CORRECCIÓN ---
import datetime
# --- FIN DE LA CORRECCIÓN ---
from typing import Any

class _Workflow:
    """Clase base que contiene los métodos de workflow del PositionManager."""

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
        """Punto de entrada para señales desde el `event_processor`."""
        # --- INICIO DE LA MODIFICACIÓN: Adaptar a la Operación Activa ---
        if not self._initialized or not self._executor or not self.operacion_activa:
            return

        # trend_mode = self._active_trend['config'].mode # Comentado
        tendencia_operacion = self.operacion_activa.configuracion.tendencia
        side_to_open = 'long' if signal == "BUY" else 'short'
        
        side_allowed = (side_to_open == 'long' and tendencia_operacion in ["LONG_ONLY", "LONG_SHORT"]) or \
                       (side_to_open == 'short' and tendencia_operacion in ["SHORT_ONLY", "LONG_SHORT"])
        
        if side_allowed and self._can_open_new_position(side_to_open):
            self._open_logical_position(side_to_open, entry_price, timestamp)
        # --- FIN DE LA MODIFICACIÓN ---

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """Revisa SL y TS para todas las posiciones abiertas en cada tick."""
        if not self._initialized or not self._executor or not self.operacion_activa: return

        for side in ['long', 'short']:
            # --- INICIO DE LA MODIFICACIÓN: Leer posiciones de la operación activa ---
            open_positions = self.operacion_activa.posiciones_activas.get(side, [])
            # open_positions = self._position_state.get_open_logical_positions(side) # Comentado
            if not open_positions: continue

            indices_to_close, reasons = [], {}
            for i, pos in enumerate(open_positions):
                sl_price = pos.stop_loss_price
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    indices_to_close.append(i); reasons[i] = "SL"; continue

                # La lógica de TSL ahora usa los parámetros de la operación activa
                self._update_trailing_stop(side, pos, i, current_price)
                
                # Leemos el valor actualizado de la posición en la operación
                pos_actualizada = self.operacion_activa.posiciones_activas[side][i]
                ts_stop_price = pos_actualizada.ts_stop_price
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                    indices_to_close.append(i); reasons[i] = "TS"

            for index in sorted(list(set(indices_to_close)), reverse=True):
                self._close_logical_position(side, index, current_price, timestamp, reason=reasons.get(index, "UNKNOWN"))
            # --- FIN DE LA MODIFICACIÓN ---

    def process_triggered_milestone(self, milestone_id: str):
        """Procesa la cascada de un hito cumplido."""
        triggered_hito = next((m for m in self._milestones if m.id == milestone_id), None)
        if not triggered_hito: return
        
        # --- INICIO DE LA MODIFICACIÓN: Lógica basada en tipo de hito ---

        # 1. Finalizar la operación anterior (si existe y no es la inicial)
        # self._end_trend("Hito completado") # Comentado
        if self.operacion_activa and self.operacion_activa.configuracion.tendencia != 'NEUTRAL':
             self._end_operation("Hito completado, iniciando nueva operación")

        # 2. Actualizar el estado de los hitos en el árbol (lógica de cascada)
        parent_id = triggered_hito.parent_id
        for hito in self._milestones:
            if hito.id == milestone_id:
                hito.status = 'COMPLETED'
            elif hito.parent_id == parent_id and hito.status in ['PENDING', 'ACTIVE']:
                hito.status = 'CANCELLED'
            elif hito.parent_id == milestone_id and hito.status == 'PENDING':
                hito.status = 'ACTIVE'

        # 3. Crear e iniciar la nueva operación basada en la acción del hito
        # self._start_trend(triggered_milestone) # Comentado
        if triggered_hito.tipo_hito == 'INICIALIZACION':
            # La acción contiene la configuración para la nueva operación de trading
            config_nueva_op = triggered_hito.accion.configuracion_nueva_operacion
            if config_nueva_op:
                self._start_operation(config_nueva_op, triggered_hito.id)

        elif triggered_hito.tipo_hito == 'FINALIZACION':
            # La acción es finalizar y volver a NEUTRAL
            # La lógica de `_end_operation` se encarga de crear la nueva operación NEUTRAL
            if triggered_hito.accion.cerrar_posiciones_al_finalizar:
                 self.close_all_logical_positions('long', reason=f"HITO_FIN_{milestone_id[-6:]}")
                 self.close_all_logical_positions('short', reason=f"HITO_FIN_{milestone_id[-6:]}")

        # 4. Limpiar hitos obsoletos del árbol
        self._cleanup_completed_milestones()
        # --- FIN DE LA MODIFICACIÓN ---