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
        # _close_logical_position devuelve un dict, debemos comprobar el éxito
        result = self._close_logical_position(side, index, price, datetime.datetime.now(timezone.utc), reason="MANUAL")
        success = result and result.get('success', False)
        return (True, f"Orden de cierre para {side.upper()} #{index} enviada.") if success else (False, f"Fallo al enviar orden de cierre.")

    # --- INICIO DE LA MODIFICACIÓN ---
    def close_all_logical_positions(self, side: str, reason: str = "MANUAL_ALL") -> Tuple[bool, str]:
        """
        Cierra TODAS las posiciones lógicas de un lado.
        Ahora devuelve una tupla (bool, str) con el resultado.
        """
        price = self.get_current_market_price()
        if not price: 
            msg = f"CIERRE TOTAL FALLIDO: Sin precio para {side.upper()}."
            self._memory_logger.log(msg, level="ERROR")
            return False, msg
        
        operacion = self._om_api.get_operation_by_side(side)
        
        if not operacion:
            msg = f"CIERRE TOTAL FALLIDO: No se encontró la operación para el lado {side.upper()}."
            self._memory_logger.log(msg, level="ERROR")
            return False, msg
        
        positions_to_close = list(operacion.posiciones_activas.get(side, []))
        count = len(positions_to_close)
        
        if count == 0:
            return True, f"No hay posiciones {side.upper()} para cerrar."
        
        self._memory_logger.log(f"Iniciando cierre de {count} posiciones del lado {side.upper()}...", "INFO")
        
        success_count = 0
        # Iterar en orden inverso para evitar problemas de índice al eliminar elementos.
        for i in range(count - 1, -1, -1):
            result = self._close_logical_position(side, i, price, datetime.datetime.now(timezone.utc), reason)
            if result and result.get('success', False):
                success_count += 1
        
        if success_count == count:
            return True, f"Éxito: Se enviaron órdenes de cierre para las {count} posiciones {side.upper()}."
        else:
            msg = f"Advertencia: Solo se pudieron cerrar {success_count} de {count} posiciones {side.upper()}."
            self._memory_logger.log(msg, level="WARN")
            return False, msg
    # --- FIN DE LA MODIFICACIÓN ---