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
        
        operacion = self._om_api.get_operation()
        if not operacion: return False
        
        count = len(operacion.posiciones_activas[side])
        if count == 0: return True
        
        for i in range(count - 1, -1, -1):
            self._close_logical_position(side, i, price, datetime.datetime.now(timezone.utc), reason)
        return True