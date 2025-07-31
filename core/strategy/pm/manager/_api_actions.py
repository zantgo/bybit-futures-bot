"""
Módulo del Position Manager: API de Acciones.

v8.0 (Operaciones Duales):
- Se corrige `close_all_logical_positions` para que obtenga la operación
  específica del lado a cerrar (`long` o `short`) usando la nueva
  om_api, solucionando el `AttributeError` final.
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

    # --- Métodos de Gestión de Posiciones ---

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
        
        # --- INICIO DE LA CORRECCIÓN ---
        # Se obtiene la operación específica del lado que se está cerrando.
        operacion = self._om_api.get_operation_by_side(side)
        # --- FIN DE LA CORRECCIÓN ---
        
        if not operacion:
            self._memory_logger.log(f"CIERRE TOTAL FALLIDO: No se encontró la operación para el lado {side.upper()}.", level="ERROR")
            return False
        
        # El resto de la lógica no cambia, ya que opera sobre el 'side' correcto.
        # Se accede a .get() para evitar un KeyError si no hay posiciones de ese lado en el diccionario.
        count = len(operacion.posiciones_activas.get(side, []))
        if count == 0:
            return True
        
        self._memory_logger.log(f"Iniciando cierre de {count} posiciones del lado {side.upper()}...", "INFO")
        
        # Iterar en orden inverso para evitar problemas de índice al eliminar elementos.
        for i in range(count - 1, -1, -1):
            self._close_logical_position(side, i, price, datetime.datetime.now(timezone.utc), reason)
        
        return True