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
        # --- INICIO DE LA SOLUCIÓN ADICIONAL: Aplicar la misma protección aquí ---
        self._manual_close_in_progress = True
        self._memory_logger.log(f"Bandera de cierre manual (SINGLE) ACTIVADA para {side.upper()}.", "DEBUG")
        try:
        # --- FIN DE LA SOLUCIÓN ADICIONAL ---
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
        # --- INICIO DE LA SOLUCIÓN ADICIONAL: Bloque finally ---
        finally:
            self._manual_close_in_progress = False
            self._memory_logger.log(f"Bandera de cierre manual (SINGLE) DESACTIVADA para {side.upper()}.", "DEBUG")
        # --- FIN DE LA SOLUCIÓN ADICIONAL ---

    def close_all_logical_positions(self, side: str, reason: str = "MANUAL_ALL") -> Tuple[bool, str]:
        """
        Cierra TODAS las posiciones lógicas de un lado.
        Ahora devuelve una tupla (bool, str) con el resultado.
        """
        # --- INICIO DE LA SOLUCIÓN: Activar la bandera y usar try...finally ---
        self._manual_close_in_progress = True
        self._memory_logger.log(f"Bandera de cierre manual (ALL) ACTIVADA para {side.upper()}.", "DEBUG")
        try:
        # --- FIN DE LA SOLUCIÓN ---
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
            indices_to_close = [i for i, p in enumerate(all_positions) if p.estado == 'ABIERTA']
            
            count = len(indices_to_close)
            
            if count == 0:
                return True, f"No hay posiciones {side.upper()} para cerrar."
            
            self._memory_logger.log(f"Iniciando cierre de {count} posiciones del lado {side.upper()}...", "INFO")
            
            success_count = 0
            for index_to_close in sorted(indices_to_close, reverse=True):
                result = self._close_logical_position(side, index_to_close, price, datetime.datetime.now(timezone.utc), reason)
                if result and result.get('success', False):
                    success_count += 1
            
            if success_count == count:
                return True, f"Éxito: Se enviaron órdenes de cierre para las {count} posiciones {side.upper()}."
            else:
                msg = f"Advertencia: Solo se pudieron cerrar {success_count} de {count} posiciones {side.upper()}."
                self._memory_logger.log(msg, level="WARN")
                return False, msg
        # --- INICIO DE LA SOLUCIÓN: Bloque finally para desactivar la bandera ---
        finally:
            self._manual_close_in_progress = False
            self._memory_logger.log(f"Bandera de cierre manual (ALL) DESACTIVADA para {side.upper()}.", "DEBUG")
        # --- FIN DE LA SOLUCIÓN ---
        
    def manual_open_next_pending_position(self, side: str) -> Tuple[bool, str]:
        """
        Abre manualmente la primera posición lógica PENDIENTE de una operación,
        ignorando la condición de distancia de promediación.
        """
        price = self.get_current_market_price()
        if not price:
            return False, "No se pudo obtener el precio de mercado actual para la apertura."
            
        operacion = self._om_api.get_operation_by_side(side)
        if not operacion:
            return False, f"No se encontró la operación para el lado {side.upper()}."

        if operacion.estado not in ['ACTIVA', 'PAUSADA']:
            return False, f"La apertura manual solo es posible si la operación está ACTIVA o PAUSADA. Estado actual: {operacion.estado}"

        # Llamar a la nueva función de lógica privada (que crearemos en el siguiente paso)
        # El método _manual_open_position se encargará de toda la lógica y ejecución.
        result = self._manual_open_position(
            side=side,
            entry_price=price,
            timestamp=datetime.datetime.now(timezone.utc)
        )
        
        # Procesar la respuesta del ejecutor
        success = result and result.get('success', False)
        message = result.get('message', 'Fallo al enviar la orden de apertura.')
        
        if not success and 'message' not in result:
             # Si no hay mensaje específico, ponemos uno genérico
             message = result.get('error', message)

        return success, message
# --- AÑADE ESTA FUNCIÓN en core/strategy/pm/manager/_api_actions.py ---
    def update_max_sync_failures(self, new_value: int):
        """Actualiza el umbral de fallos de sincronización en tiempo real."""
        if isinstance(new_value, int) and new_value > 0:
            self._MAX_SYNC_FAILURES = new_value
            self._memory_logger.log(f"PM: Umbral MAX_SYNC_FAILURES actualizado a {new_value}", "WARN")