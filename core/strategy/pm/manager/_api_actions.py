# core/strategy/pm/manager/_api_actions.py

"""
Módulo del Position Manager: API de Acciones.

Agrupa todos los métodos públicos que la TUI y otros módulos utilizan
para modificar el estado o ejecutar acciones en el PositionManager.
"""
import datetime
import time
from typing import Optional, Dict, Any, Tuple
import uuid

# Importamos timezone para crear datetimes "aware"
from datetime import timezone

# --- Dependencias de Tipado ---
try:
    # --- INICIO DE LA MODIFICACIÓN: Importar nuevas entidades ---
    from .._entities import (
        Hito, CondicionHito, AccionHito, ConfiguracionOperacion
    )
    # from .._entities import Milestone, MilestoneCondition, MilestoneAction, TrendConfig # Comentadas las antiguas
    # --- FIN DE LA MODIFICACIÓN ---
except ImportError:
    # --- INICIO DE LA MODIFICACIÓN: Añadir fallbacks para nuevas entidades ---
    class Hito: pass
    class CondicionHito: pass
    class AccionHito: pass
    class ConfiguracionOperacion: pass
    # class Milestone: pass
    # class MilestoneCondition: pass
    # class MilestoneAction: pass
    # class TrendConfig: pass
    # --- FIN DE LA MODIFICACIÓN ---

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

    # --- (COMENTADO) add_milestone ---
    # def add_milestone(self, condition_data: Dict, action_data: Dict, parent_id: Optional[str] = None) -> Tuple[bool, str]:
    #     """Añade un nuevo hito al árbol de decisiones."""
    #     try:
    #         condition = MilestoneCondition(**condition_data)
    #         trend_config = TrendConfig(**action_data['params'])
    #         action = MilestoneAction(type=action_data['type'], params=trend_config)
            
    #         level, status = 1, 'ACTIVE'
    #         if parent_id:
    #             parent = next((m for m in self._milestones if m.id == parent_id), None)
    #             if not parent: return False, f"Hito padre con ID '{parent_id}' no encontrado."
    #             level = parent.level + 1
    #             status = 'PENDING'
            
    #         milestone_id = f"mstone_{int(time.time() * 1000)}"
    #         new_milestone = Milestone(id=milestone_id, condition=condition, action=action, parent_id=parent_id, level=level, status=status)
    #         self._milestones.append(new_milestone)
    #         self._memory_logger.log(f"HITO CREADO: ID ...{milestone_id[-6:]}, Nivel {level}, Estado {status}", "INFO")
    #         return True, f"Hito '{milestone_id[-6:]}' añadido en Nivel {level}."
    #     except Exception as e:
    #         return False, f"Error creando hito: {e}"

    # --- INICIO DE LA MODIFICACIÓN: Nuevo add_milestone para el modelo de Operaciones ---
    def add_milestone(self, tipo_hito: str, condicion: CondicionHito, accion: AccionHito, parent_id: Optional[str] = None) -> Tuple[bool, str]:
        """Añade un nuevo hito al árbol de decisiones bajo el nuevo modelo."""
        try:
            level, status = 1, 'ACTIVE'
            if parent_id:
                parent = next((m for m in self._milestones if m.id == parent_id), None)
                if not parent: return False, f"Hito padre con ID '{parent_id}' no encontrado."
                
                # Validación de secuencia lógica
                if parent.tipo_hito == tipo_hito:
                    return False, f"Error de secuencia: Un hito de '{tipo_hito}' no puede seguir a otro de '{parent.tipo_hito}'."
                
                level = parent.level + 1
                status = 'PENDING'
            elif tipo_hito == 'FINALIZACION':
                return False, "Error: Un hito de Finalización no puede ser de Nivel 1 (sin padre)."

            milestone_id = f"hito_{uuid.uuid4()}"
            new_hito = Hito(
                id=milestone_id, tipo_hito=tipo_hito, condicion=condicion, accion=accion,
                parent_id=parent_id, level=level, status=status
            )
            self._milestones.append(new_hito)
            self._memory_logger.log(f"HITO CREADO: ID ...{milestone_id[-6:]}, Tipo {tipo_hito}, Nivel {level}", "INFO")
            return True, f"Hito '{milestone_id[-6:]}' añadido con éxito."
        except Exception as e:
            return False, f"Error creando hito: {e}"
    # --- FIN DE LA MODIFICACIÓN ---

    # --- (COMENTADO) update_milestone ---
    # def update_milestone(self, milestone_id: str, condition_data: Dict, action_data: Dict) -> Tuple[bool, str]:
    #     """Busca un hito por su ID y actualiza sus datos."""
    #     for i, m in enumerate(self._milestones):
    #         if m.id == milestone_id:
    #             if m.status not in ['PENDING', 'ACTIVE']:
    #                 return False, "No se puede modificar un hito completado o cancelado."
    #             try:
    #                 new_condition = MilestoneCondition(**condition_data)
    #                 new_trend_config = TrendConfig(**action_data['params'])
    #                 new_action = MilestoneAction(params=new_trend_config, type=action_data['type'])
                    
    #                 self._milestones[i].condition = new_condition
    #                 self._milestones[i].action = new_action
                    
    #                 self._memory_logger.log(f"HITO ACTUALIZADO: ID ...{milestone_id[-6:]}", "INFO")
    #                 return True, f"Hito ...{milestone_id[-6:]} actualizado."
    #             except Exception as e:
    #                 return False, f"Error actualizando hito: {e}"
    #     return False, "Hito no encontrado para actualizar."

    # --- INICIO DE LA MODIFICACIÓN: Nuevo update_milestone ---
    def update_milestone(self, milestone_id: str, nueva_condicion: CondicionHito, nueva_accion: AccionHito) -> Tuple[bool, str]:
        """Busca un hito por su ID y actualiza sus objetos de condición y acción."""
        for i, hito in enumerate(self._milestones):
            if hito.id == milestone_id:
                if hito.status not in ['PENDING', 'ACTIVE']:
                    return False, "No se puede modificar un hito completado o cancelado."
                
                self._milestones[i].condicion = nueva_condicion
                self._milestones[i].accion = nueva_accion
                self._memory_logger.log(f"HITO ACTUALIZADO: ID ...{milestone_id[-6:]}", "INFO")
                return True, f"Hito ...{milestone_id[-6:]} actualizado."
        return False, "Hito no encontrado para actualizar."
    # --- FIN DE LA MODIFICACIÓN ---

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
        hito = next((m for m in self._milestones if m.id == milestone_id), None)
        if not hito:
            return False, "Hito no encontrado."
        if hito.status != 'ACTIVE':
            return False, f"Solo se pueden forzar hitos con estado 'ACTIVE'. Estado actual: {hito.status}."
        
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
        hito = next((m for m in self._milestones if m.id == milestone_id), None)
        if not hito:
            return False, "Hito no encontrado para forzar activación."
        if hito.status != 'ACTIVE':
            return False, f"Solo se pueden forzar hitos con estado 'ACTIVE'. Estado actual: {hito.status}."

        self._handle_position_management_on_force_trigger(
            long_pos_action, short_pos_action
        )

        self._memory_logger.log(f"FORZANDO HITO: ID ...{milestone_id[-6:]} activado manualmente tras gestión de posiciones.", "WARN")
        self.process_triggered_milestone(milestone_id)
        
        return True, f"Hito ...{hito.id[-6:]} activado forzosamente. Posiciones gestionadas."

    # --- (COMENTADO) update_active_trend_parameters ---
    # def update_active_trend_parameters(self, params_to_update: Dict[str, Any]) -> Tuple[bool, str]:
    #     """
    #     Actualiza los parámetros de configuración de la tendencia activa en tiempo real.
    #     """
    #     if not self._active_trend:
    #         return False, "No hay ninguna tendencia activa para modificar."
    #     try:
    #         trend_config_object = self._active_trend['config']
    #         changes_log = []
    #         for key, value in params_to_update.items():
    #             if hasattr(trend_config_object, key):
    #                 old_value = getattr(trend_config_object, key)
    #                 setattr(trend_config_object, key, value)
    #                 changes_log.append(f"'{key}': {old_value} -> {value}")
            
    #         if not changes_log:
    #             return True, "No se realizaron cambios en los parámetros de la tendencia."

    #         log_message = "Parámetros de la tendencia activa actualizados en tiempo real: " + ", ".join(changes_log)
    #         self._memory_logger.log(log_message, "WARN")
    #         return True, "Parámetros de la tendencia activa actualizados con éxito."

    #     except Exception as e:
    #         error_msg = f"Error al actualizar los parámetros de la tendencia activa: {e}"
    #         self._memory_logger.log(error_msg, "ERROR")
    #         return False, error_msg

    # --- INICIO DE LA MODIFICACIÓN: Nueva función para actualizar la Operación Activa ---
    def update_active_operation_parameters(self, params_to_update: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Actualiza los parámetros de configuración de la operación activa en tiempo real.
        """
        if not self.operacion_activa or self.operacion_activa.configuracion.tendencia == 'NEUTRAL':
            return False, "No hay ninguna operación de trading activa para modificar."

        try:
            config_obj = self.operacion_activa.configuracion
            changes_log = []
            for key, value in params_to_update.items():
                if hasattr(config_obj, key):
                    old_value = getattr(config_obj, key)
                    setattr(config_obj, key, value)
                    changes_log.append(f"'{key}': {old_value} -> {value}")
            
            if not changes_log:
                return True, "No se realizaron cambios en los parámetros de la operación."

            log_message = "Parámetros de la operación activa actualizados: " + ", ".join(changes_log)
            self._memory_logger.log(log_message, "WARN")
            return True, "Parámetros de la operación activa actualizados con éxito."
        except Exception as e:
            error_msg = f"Error al actualizar parámetros de la operación: {e}"
            self._memory_logger.log(error_msg, "ERROR")
            return False, error_msg
    # --- FIN DE LA MODIFICACIÓN ---

    # --- (COMENTADO) end_current_trend_and_ask ---
    # def end_current_trend_and_ask(self):
    #     """Llamado por los limit checkers para finalizar una tendencia."""
    #     self._end_trend(reason="Límite de tendencia alcanzado")

    # --- (COMENTADO) force_end_trend ---
    # def force_end_trend(self, close_positions: bool = False) -> Tuple[bool, str]:
    #     """Fuerza la finalización de la tendencia activa actual."""
    #     if not self._active_trend:
    #         return False, "No hay ninguna tendencia activa para finalizar."
        
    #     if close_positions:
    #         self._memory_logger.log("Cierre forzoso de todas las posiciones por finalización de tendencia.", "WARN")
    #         self.close_all_logical_positions('long', reason="TREND_FORCE_CLOSED")
    #         self.close_all_logical_positions('short', reason="TREND_FORCE_CLOSED")

    #     self._end_trend(reason="Finalización forzada por el usuario")
    #     return True, "Tendencia activa finalizada."
        
    # --- INICIO DE LA MODIFICACIÓN: Nuevas funciones para finalizar la Operación ---
    def end_current_operation_and_neutralize(self, reason: str):
        """Finaliza la operación actual y transiciona a una operación NEUTRAL."""
        self._end_operation(reason=reason)

    def force_end_operation(self, close_positions: bool = False) -> Tuple[bool, str]:
        """Fuerza la finalización de la operación de trading activa actual."""
        if not self.operacion_activa or self.operacion_activa.configuracion.tendencia == 'NEUTRAL':
            return False, "No hay ninguna operación de trading activa para finalizar."
        
        if close_positions:
            self._memory_logger.log("Cierre forzoso de todas las posiciones por finalización de operación.", "WARN")
            self.close_all_logical_positions('long', reason="OPERATION_FORCE_CLOSED")
            self.close_all_logical_positions('short', reason="OPERATION_FORCE_CLOSED")

        self._end_operation(reason="Finalización forzada por el usuario")
        return True, "Operación activa finalizada. Transicionando a NEUTRAL."
    # --- FIN DE LA MODIFICACIÓN ---

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
        
        if not self.operacion_activa: return False
        
        count = len(self.operacion_activa.posiciones_activas[side])
        if count == 0: return True
        
        # Iterar en reversa para evitar problemas con los índices al eliminar
        for i in range(count - 1, -1, -1):
            self._close_logical_position(side, i, price, datetime.datetime.now(timezone.utc), reason)
        return True
    
    # --- (COMENTADO) Funciones de TUI que ahora son parte de la Configuración de Operación ---
    # def add_max_logical_position_slot(self) -> Tuple[bool, str]:
    #     """Incrementa el número máximo de posiciones simultáneas."""
    #     self._max_logical_positions += 1
    #     return True, f"Slot añadido. Máximo ahora: {self._max_logical_positions}"

    # def remove_max_logical_position_slot(self) -> Tuple[bool, str]:
    #     """Decrementa el número máximo de posiciones, si es seguro hacerlo."""
    #     if self._max_logical_positions <= 1:
    #         return False, "No se puede reducir más (mínimo 1)."
    #     self._max_logical_positions -= 1
    #     return True, f"Slot eliminado. Máximo ahora: {self._max_logical_positions}"

    # def set_base_position_size(self, new_size_usdt: float) -> Tuple[bool, str]:
    #     """Establece el tamaño base de las nuevas posiciones."""
    #     if new_size_usdt <= 0:
    #         return False, "El tamaño debe ser positivo."
    #     self._initial_base_position_size_usdt = new_size_usdt
    #     return True, f"Tamaño base actualizado a {new_size_usdt:.2f} USDT."

    # def set_leverage(self, new_leverage: float) -> Tuple[bool, str]:
    #     """Establece el apalancamiento para futuras operaciones."""
    #     if not (1.0 <= new_leverage <= 100.0):
    #         return False, "Apalancamiento debe estar entre 1.0 y 100.0."
    #     self._leverage = new_leverage
    #     return True, f"Apalancamiento actualizado a {new_leverage:.1f}x."