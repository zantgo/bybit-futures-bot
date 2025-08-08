"""
Módulo del Position Manager: API de Acciones.
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
        pass

    # --- Métodos de Gestión de Posiciones ---

    def manual_close_logical_position_by_index(self, side: str, index: int) -> Tuple[bool, str]:
        """Cierra una posición lógica específica por su índice relativo a las posiciones abiertas."""
        price = self.get_current_market_price()
        if not price:
            return False, "No se pudo obtener el precio de mercado actual para el cierre."
        
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion:
            return False, f"No se encontró la operación para el lado {side.upper()}."

        open_positions = operacion.posiciones_abiertas
        if not (0 <= index < len(open_positions)):
            return False, f"Índice {index} fuera de rango. Solo hay {len(open_positions)} posiciones abiertas."

        pos_to_close = open_positions[index]
        try:
            original_index = next(i for i, p in enumerate(operacion.posiciones) if p.id == pos_to_close.id)
        except StopIteration:
            return False, f"Error interno: No se pudo encontrar la posición con ID {pos_to_close.id}."

        result = self._close_logical_position(
            side, original_index, price, datetime.datetime.now(timezone.utc), reason="MANUAL_SINGLE"
        )
        
        success = result and result.get('success', False)
        message = result.get('message', 'Fallo al enviar la orden de cierre.')
        
        return success, message

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
        
        # --- INICIO DE LA MODIFICACIÓN (Solución al AttributeError) ---
        # La lógica anterior creaba un diccionario {'pos': objeto, 'index': int}, lo cual causaba el error.
        # La nueva lógica, similar a la de _workflow.py, trabaja directamente con los índices.
        
        all_positions = operacion.posiciones
        # 1. Obtenemos una lista de los índices de las posiciones que están abiertas.
        indices_to_close = [i for i, p in enumerate(all_positions) if p.estado == 'ABIERTA']
        
        count = len(indices_to_close)
        # --- FIN DE LA MODIFICACIÓN ---
        
        if count == 0:
            return True, f"No hay posiciones {side.upper()} para cerrar."
        
        self._memory_logger.log(f"Iniciando cierre de {count} posiciones del lado {side.upper()}...", "INFO")
        
        success_count = 0
        # --- INICIO DE LA MODIFICACIÓN ---
        # 2. Iteramos sobre los índices en orden inverso para evitar problemas al modificar la lista.
        #    La llamada a _close_logical_position ahora es directa y correcta.
        # for pos_info in sorted(positions_to_close_with_indices, key=lambda x: x['original_index'], reverse=True): # <-- LÍNEA ORIGINAL
        for index_to_close in sorted(indices_to_close, reverse=True):
            # index_to_close = pos_info['original_index'] # <-- LÍNEA ORIGINAL
            result = self._close_logical_position(side, index_to_close, price, datetime.datetime.now(timezone.utc), reason)
            if result and result.get('success', False):
                success_count += 1
        # --- FIN DE LA MODIFICACIÓN ---
        
        if success_count == count:
            return True, f"Éxito: Se enviaron órdenes de cierre para las {count} posiciones {side.upper()}."
        else:
            msg = f"Advertencia: Solo se pudieron cerrar {success_count} de {count} posiciones {side.upper()}."
            self._memory_logger.log(msg, level="WARN")
            return False, msg