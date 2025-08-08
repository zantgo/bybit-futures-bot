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
    from core.strategy.entities import Operacion, LogicalPosition
except ImportError:
    class Operacion: pass
    class LogicalPosition: pass


class _ApiActions:
    """Clase base que contiene las acciones públicas de la API del PositionManager."""
    
    def force_balance_update(self):
        """Delega la llamada para forzar una actualización de la caché de balances reales."""
        # Esta funcionalidad está obsoleta, pero se mantiene la estructura por si se reutiliza.
        # if self._initialized and self._balance_manager:
        #     self._balance_manager.force_update_real_balances_cache()
        pass

    # --- Métodos de Gestión de Posiciones ---

    # --- INICIO DE LA MODIFICACIÓN (Implementar Cierre Manual) ---
    # Se añade esta nueva función pública que será expuesta a través de la API.
    # Centraliza la lógica para cerrar manualmente una posición específica.
    def manual_close_logical_position_by_index(self, side: str, index: int) -> Tuple[bool, str]:
        """Cierra una posición lógica específica por su índice."""
        # 1. Obtener precio actual para el cierre
        price = self.get_current_market_price()
        if not price:
            return False, "No se pudo obtener el precio de mercado actual para el cierre."
        
        # 2. Obtener la operación para encontrar la posición correcta
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion:
            return False, f"No se encontró la operación para el lado {side.upper()}."

        # 3. Validar el índice
        open_positions = operacion.posiciones_abiertas
        if not (0 <= index < len(open_positions)):
            return False, f"Índice {index} fuera de rango. Solo hay {len(open_positions)} posiciones abiertas."

        # 4. Encontrar el índice original en la lista completa de posiciones
        pos_to_close = open_positions[index]
        try:
            original_index = next(i for i, p in enumerate(operacion.posiciones) if p.id == pos_to_close.id)
        except StopIteration:
            return False, f"Error interno: No se pudo encontrar la posición con ID {pos_to_close.id}."

        # 5. Llamar al método de cierre interno
        result = self._close_logical_position(
            side, original_index, price, datetime.datetime.now(timezone.utc), reason="MANUAL_SINGLE"
        )
        
        # 6. Devolver un resultado claro a la TUI
        success = result and result.get('success', False)
        message = result.get('message', 'Fallo al enviar la orden de cierre.')
        
        return success, message
    # --- FIN DE LA MODIFICACIÓN ---

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
        
        all_positions = operacion.posiciones
        positions_to_close_with_indices = [
            {'pos': p, 'original_index': i} 
            for i, p in enumerate(all_positions) 
            if p.estado == 'ABIERTA'
        ]
        count = len(positions_to_close_with_indices)
        
        if count == 0:
            return True, f"No hay posiciones {side.upper()} para cerrar."
        
        self._memory_logger.log(f"Iniciando cierre de {count} posiciones del lado {side.upper()}...", "INFO")
        
        success_count = 0
        for pos_info in sorted(positions_to_close_with_indices, key=lambda x: x['original_index'], reverse=True):
            index_to_close = pos_info['original_index']
            result = self._close_logical_position(side, index_to_close, price, datetime.datetime.now(timezone.utc), reason)
            if result and result.get('success', False):
                success_count += 1
        
        if success_count == count:
            return True, f"Éxito: Se enviaron órdenes de cierre para las {count} posiciones {side.upper()}."
        else:
            msg = f"Advertencia: Solo se pudieron cerrar {success_count} de {count} posiciones {side.upper()}."
            self._memory_logger.log(msg, level="WARN")
            return False, msg