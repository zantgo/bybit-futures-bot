"""
Módulo del Position Manager: API de Acciones.

Agrupa todos los métodos públicos que la TUI y otros módulos utilizan
para modificar el estado o ejecutar acciones en el PositionManager.
"""
import datetime
import time
from typing import Optional, Dict, Any, Tuple

# Importamos timezone para crear datetimes "aware"
from datetime import timezone

# --- Dependencias de Tipado ---
try:
    from .._entities import Milestone, MilestoneCondition, MilestoneAction, TrendConfig
except ImportError:
    class Milestone: pass
    class MilestoneCondition: pass
    class MilestoneAction: pass
    class TrendConfig: pass

class _ApiActions:
    """Clase base que contiene las acciones públicas de la API del PositionManager."""
    
    def force_balance_update(self):
        """Delega la llamada para forzar una actualización de la caché de balances reales."""
        if self._initialized and self._balance_manager:
            self._balance_manager.force_update_real_balances_cache()

    def set_global_stop_loss_pct(self, value: float) -> Tuple[bool, str]:
        """Establece el disyuntor de SL global de la sesión."""
        self._global_stop_loss_roi_pct = value
        msg = f"Stop Loss Global de Sesión actualizado a -{value}%." if value > 0 else "Stop Loss Global de Sesión desactivado."
        self._memory_logger.log(f"CONFIGURACIÓN: {msg}", "WARN")
        return True, msg

    def set_global_take_profit_pct(self, value: float) -> Tuple[bool, str]:
        """Establece el disyuntor de TP global de la sesión."""
        self._global_take_profit_roi_pct = value
        self._session_tp_hit = False
        msg = f"Take Profit Global de Sesión actualizado a +{value}%." if value > 0 else "Take Profit Global de Sesión desactivado."
        self._memory_logger.log(f"CONFIGURACIÓN: {msg}", "WARN")
        return True, msg

    def add_milestone(self, condition_data: Dict, action_data: Dict, parent_id: Optional[str] = None) -> Tuple[bool, str]:
        """Añade un nuevo hito al árbol de decisiones."""
        try:
            condition = MilestoneCondition(**condition_data)
            trend_config = TrendConfig(**action_data['params'])
            action = MilestoneAction(type=action_data['type'], params=trend_config)
            
            level, status = 1, 'ACTIVE'
            if parent_id:
                parent = next((m for m in self._milestones if m.id == parent_id), None)
                if not parent: return False, f"Hito padre con ID '{parent_id}' no encontrado."
                level = parent.level + 1
                status = 'PENDING'
            
            milestone_id = f"mstone_{int(time.time() * 1000)}"
            new_milestone = Milestone(id=milestone_id, condition=condition, action=action, parent_id=parent_id, level=level, status=status)
            self._milestones.append(new_milestone)
            self._memory_logger.log(f"HITO CREADO: ID ...{milestone_id[-6:]}, Nivel {level}, Estado {status}", "INFO")
            return True, f"Hito '{milestone_id[-6:]}' añadido en Nivel {level}."
        except Exception as e:
            return False, f"Error creando hito: {e}"
            
    def update_milestone(self, milestone_id: str, condition_data: Dict, action_data: Dict) -> Tuple[bool, str]:
        """Busca un hito por su ID y actualiza sus datos."""
        for i, m in enumerate(self._milestones):
            if m.id == milestone_id:
                if m.status not in ['PENDING', 'ACTIVE']:
                    return False, "No se puede modificar un hito completado o cancelado."
                try:
                    new_condition = MilestoneCondition(**condition_data)
                    new_trend_config = TrendConfig(**action_data['params'])
                    new_action = MilestoneAction(params=new_trend_config, type=action_data['type'])
                    
                    self._milestones[i].condition = new_condition
                    self._milestones[i].action = new_action
                    
                    self._memory_logger.log(f"HITO ACTUALIZADO: ID ...{milestone_id[-6:]}", "INFO")
                    return True, f"Hito ...{milestone_id[-6:]} actualizado."
                except Exception as e:
                    return False, f"Error actualizando hito: {e}"
        return False, "Hito no encontrado para actualizar."

    def remove_milestone(self, milestone_id: str) -> Tuple[bool, str]:
        """Implementa borrado en cascada."""
        ids_to_remove = {milestone_id}
        ids_to_check = [milestone_id]
        while ids_to_check:
            parent_id = ids_to_check.pop(0)
            children = [m.id for m in self._milestones if m.parent_id == parent_id]
            ids_to_remove.update(children)
            ids_to_check.extend(children)
        
        initial_len = len(self._milestones)
        self._milestones = [m for m in self._milestones if m.id not in ids_to_remove]
        
        if len(self._milestones) < initial_len:
             self._memory_logger.log(f"HITOS ELIMINADOS: {len(ids_to_remove)} hito(s) en cascada desde ...{milestone_id[-6:]}", "WARN")
             return True, f"{len(ids_to_remove)} hito(s) eliminados."
        else:
             return False, "No se encontró el hito."
        
    def force_trigger_milestone(self, milestone_id: str) -> Tuple[bool, str]:
        """Fuerza la activación de un hito como si su condición de precio se hubiera cumplido."""
        milestone = next((m for m in self._milestones if m.id == milestone_id), None)
        if not milestone:
            return False, "Hito no encontrado."
        if milestone.status != 'ACTIVE':
            return False, f"Solo se pueden forzar hitos con estado 'ACTIVE'. Estado actual: {milestone.status}."
        
        self._memory_logger.log(f"FORZANDO HITO: ID ...{milestone_id[-6:]} activado manualmente.", "WARN")
        self.process_triggered_milestone(milestone_id)
        return True, f"Hito ...{milestone_id[-6:]} activado forzosamente."

    def force_trigger_milestone_with_pos_management(
        self,
        milestone_id: str,
        long_pos_action: str = 'keep',
        short_pos_action: str = 'keep'
    ) -> Tuple[bool, str]:
        """
        Gestiona las posiciones existentes según las acciones especificadas y luego
        fuerza la activación de un nuevo hito.
        """
        milestone = next((m for m in self._milestones if m.id == milestone_id), None)
        if not milestone:
            return False, "Hito no encontrado para forzar activación."
        if milestone.status != 'ACTIVE':
            return False, f"Solo se pueden forzar hitos con estado 'ACTIVE'. Estado actual: {milestone.status}."

        self._handle_position_management_on_force_trigger(
            long_pos_action, short_pos_action
        )

        self._memory_logger.log(f"FORZANDO HITO: ID ...{milestone_id[-6:]} activado manualmente tras gestión de posiciones.", "WARN")
        self.process_triggered_milestone(milestone_id)
        
        return True, f"Hito ...{milestone_id[-6:]} activado forzosamente. Posiciones gestionadas."

    # --- INICIO DE LA MODIFICACIÓN (REQ-10) ---
    def update_active_trend_parameters(self, params_to_update: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Actualiza los parámetros de configuración de la tendencia activa en tiempo real.
        """
        # 1. Validar que hay una tendencia activa.
        if not self._active_trend:
            return False, "No hay ninguna tendencia activa para modificar."

        # 2. Actualizar los parámetros.
        try:
            # Iterar sobre los nuevos parámetros y actualizar el objeto TrendConfig
            trend_config_object = self._active_trend['config']
            changes_log = []
            for key, value in params_to_update.items():
                if hasattr(trend_config_object, key):
                    old_value = getattr(trend_config_object, key)
                    setattr(trend_config_object, key, value)
                    changes_log.append(f"'{key}': {old_value} -> {value}")
            
            if not changes_log:
                return True, "No se realizaron cambios en los parámetros de la tendencia."

            log_message = "Parámetros de la tendencia activa actualizados en tiempo real: " + ", ".join(changes_log)
            self._memory_logger.log(log_message, "WARN")
            return True, "Parámetros de la tendencia activa actualizados con éxito."

        except Exception as e:
            error_msg = f"Error al actualizar los parámetros de la tendencia activa: {e}"
            self._memory_logger.log(error_msg, "ERROR")
            return False, error_msg
    # --- FIN DE LA MODIFICACIÓN ---

    def end_current_trend_and_ask(self):
        """Llamado por los limit checkers para finalizar una tendencia."""
        self._end_trend(reason="Límite de tendencia alcanzado")

    def force_end_trend(self, close_positions: bool = False) -> Tuple[bool, str]:
        """Fuerza la finalización de la tendencia activa actual."""
        if not self._active_trend:
            return False, "No hay ninguna tendencia activa para finalizar."
        
        if close_positions:
            self._memory_logger.log("Cierre forzoso de todas las posiciones por finalización de tendencia.", "WARN")
            self.close_all_logical_positions('long', reason="TREND_FORCE_CLOSED")
            self.close_all_logical_positions('short', reason="TREND_FORCE_CLOSED")

        self._end_trend(reason="Finalización forzada por el usuario")
        return True, "Tendencia activa finalizada."

    def manual_close_logical_position_by_index(self, side: str, index: int) -> Tuple[bool, str]:
        """Cierra una posición lógica específica por su índice."""
        price = self.get_current_market_price()
        if not price: return False, "No se pudo obtener el precio de mercado actual."
        success = self._close_logical_position(side, index, price, datetime.datetime.now(timezone.utc), reason="MANUAL")
        return (True, f"Orden de cierre para {side.upper()} #{index} enviada.") if success else (False, f"Fallo al enviar orden de cierre.")

    def close_all_logical_positions(self, side: str, reason: str = "MANUAL_ALL") -> bool:
        """Cierra TODAS las posiciones lógicas de un lado."""
        price = self.get_current_market_price()
        if not price: 
            self._memory_logger.log(f"CIERRE TOTAL FALLIDO: Sin precio para {side.upper()}.", level="ERROR")
            return False
        
        count = len(self._position_state.get_open_logical_positions(side))
        if count == 0: return True
        
        for i in range(count - 1, -1, -1):
            self._close_logical_position(side, i, price, datetime.datetime.now(timezone.utc), reason)
        return True
    
    def add_max_logical_position_slot(self) -> Tuple[bool, str]:
        """Incrementa el número máximo de posiciones simultáneas."""
        self._max_logical_positions += 1
        return True, f"Slot añadido. Máximo ahora: {self._max_logical_positions}"

    def remove_max_logical_position_slot(self) -> Tuple[bool, str]:
        """Decrementa el número máximo de posiciones, si es seguro hacerlo."""
        if self._max_logical_positions <= 1:
            return False, "No se puede reducir más (mínimo 1)."
        self._max_logical_positions -= 1
        return True, f"Slot eliminado. Máximo ahora: {self._max_logical_positions}"

    def set_base_position_size(self, new_size_usdt: float) -> Tuple[bool, str]:
        """Establece el tamaño base de las nuevas posiciones."""
        if new_size_usdt <= 0:
            return False, "El tamaño debe ser positivo."
        self._initial_base_position_size_usdt = new_size_usdt
        return True, f"Tamaño base actualizado a {new_size_usdt:.2f} USDT."

    def set_leverage(self, new_leverage: float) -> Tuple[bool, str]:
        """Establece el apalancamiento para futuras operaciones."""
        if not (1.0 <= new_leverage <= 100.0):
            return False, "Apalancamiento debe estar entre 1.0 y 100.0."
        self._leverage = new_leverage
        return True, f"Apalancamiento actualizado a {new_leverage:.1f}x."
