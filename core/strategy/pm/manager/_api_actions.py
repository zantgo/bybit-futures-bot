"""
Módulo del Position Manager: API de Acciones.

v6.1 (Corrección de Estado):
- Se elimina la llamada al método obsoleto `save_state()` dentro de
  `create_or_update_operation`, que causaba un `AttributeError`.
"""
import datetime
from typing import Optional, Dict, Any, Tuple
from datetime import timezone

try:
    from .._entities import Operacion
except ImportError:
    class Operacion: pass

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

    # --- Métodos para la Operación Estratégica Única ---

    def create_or_update_operation(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Actualiza la operación estratégica actual con un nuevo conjunto de parámetros.
        """
        if not self.operacion_activa:
            return False, "Error: No hay una operación activa para modificar."

        try:
            changes_log = []
            for key, value in params.items():
                if hasattr(self.operacion_activa, key):
                    old_value = getattr(self.operacion_activa, key)
                    if old_value != value:
                        setattr(self.operacion_activa, key, value)
                        changes_log.append(f"'{key}': {old_value} -> {value}")

            if 'tipo_cond_entrada' in [log.split("'")[1] for log in changes_log] or \
               'valor_cond_entrada' in [log.split("'")[1] for log in changes_log]:
                if self.operacion_activa.estado == 'ACTIVA':
                    self.operacion_activa.estado = 'EN_ESPERA'
                    self.operacion_activa.tiempo_inicio_ejecucion = None
                    changes_log.append("'estado': ACTIVA -> EN_ESPERA (cond. de entrada modificada)")

            # --- INICIO DE LA CORRECCIÓN ---
            # (COMENTADO) Se elimina la llamada al método inexistente `save_state`.
            # Los cambios ya se aplican directamente al objeto en memoria.
            # self.save_state()
            # --- FIN DE LA CORRECCIÓN ---

            if not changes_log:
                return True, "No se realizaron cambios en la operación."

            log_message = "Parámetros de la operación actualizados: " + ", ".join(changes_log)
            self._memory_logger.log(log_message, "WARN")
            return True, "Operación actualizada con éxito."
        except Exception as e:
            error_msg = f"Error al actualizar la operación: {e}"
            self._memory_logger.log(error_msg, "ERROR")
            return False, error_msg

    def force_start_operation(self) -> Tuple[bool, str]:
        """
        Fuerza el inicio de la operación, cambiando su estado a 'ACTIVA'.
        """
        if not self.operacion_activa:
            return False, "No hay operación para iniciar."
        if self.operacion_activa.estado == 'ACTIVA':
            return False, "La operación ya está activa."
        
        self.operacion_activa.estado = 'ACTIVA'
        self.operacion_activa.tiempo_inicio_ejecucion = datetime.datetime.now(timezone.utc)
        self._memory_logger.log(f"OPERACIÓN INICIADA FORZOSAMENTE: Modo '{self.operacion_activa.tendencia}' está ahora ACTIVO.", "WARN")
        return True, "Operación iniciada forzosamente."

    def force_stop_operation(self, close_positions: bool = False) -> Tuple[bool, str]:
        """
        Fuerza la finalización de la operación activa actual y la resetea a NEUTRAL.
        """
        if not self.operacion_activa:
            return False, "No hay operación para detener."

        if self.operacion_activa.tendencia == 'NEUTRAL' and self.operacion_activa.estado != 'ACTIVA':
             return False, "No hay una operación de trading activa para finalizar."

        if close_positions:
            self._memory_logger.log("Cierre forzoso de todas las posiciones por finalización de operación.", "WARN")
            self.close_all_logical_positions('long', reason="OPERATION_FORCE_STOPPED")
            self.close_all_logical_positions('short', reason="OPERATION_FORCE_STOPPED")

        self._end_operation(reason="Finalización forzada por el usuario")
        return True, "Operación finalizada. Volviendo a modo NEUTRAL."

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
        
        for i in range(count - 1, -1, -1):
            self._close_logical_position(side, i, price, datetime.datetime.now(timezone.utc), reason)
        return True