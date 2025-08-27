# Contenido completo para: core/strategy/pm/manager/_workflow.py
import datetime
from typing import Any, List, Dict

class _Workflow:
    """Clase base que contiene los métodos de workflow del PositionManager."""

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
        """Gestiona una señal de bajo nivel (BUY/SELL) para potencialmente abrir una posición."""
        if not self._initialized or not self._executor:
            return
        
        side_to_open = 'long' if signal == "BUY" else 'short' if signal == "SELL" else None
        
        if not side_to_open:
            return

        operacion = self._om_api.get_operation_by_side(side_to_open)
        
        if operacion and operacion.estado == 'ACTIVA' and self._can_open_new_position(side_to_open):
            self._open_logical_position(side_to_open, entry_price, timestamp)

# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función 1 de 2) ---
# ==============================================================================

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """
        Revisa todas las posiciones abiertas para posible cierre por SL, TSL o detención forzosa.
        Ahora integra la sincronización física antes de actuar en estado DETENIENDO.
        """
        if not self._initialized or not self._executor:
            return

        for side in ['long', 'short']:
            operacion = self._om_api.get_operation_by_side(side)
            if not operacion:
                continue

            # --- INICIO DE LA MODIFICACIÓN: Lógica de Detención Robusta ---
            # # --- CÓDIGO ORIGINAL COMENTADO ---
            # # --- GESTIÓN DE DETENCIÓN FORZOSA ---
            # if operacion.estado == 'DETENIENDO':
            #     if operacion.posiciones_abiertas_count > 0:
            #         self._memory_logger.log(f"PM Workflow: Detectado estado DETENIENDO para {side.upper()}. "
            #                                 f"Iniciando cierre de {operacion.posiciones_abiertas_count} posiciones.", "WARN")
            #         self.close_all_logical_positions(side, reason="FORCE_STOP")
            #     continue
            # # --- FIN CÓDIGO ORIGINAL COMENTADO ---

            # --- CÓDIGO NUEVO Y CORREGIDO ---
            if operacion.estado == 'DETENIENDO':
                # 1. Primero, sincronizar para saber la verdad del exchange.
                self.sync_physical_positions(side)
                
                # 2. Volver a obtener el estado, que podría haber sido limpiado por la sincronización.
                operacion_actualizada = self._om_api.get_operation_by_side(side)
                if not operacion_actualizada: continue

                # 3. Solo si AÚN quedan posiciones abiertas, intentar cerrarlas.
                if operacion_actualizada.posiciones_abiertas_count > 0:
                    self._memory_logger.log(f"PM Workflow: Estado DETENIENDO confirmado para {side.upper()}. "
                                            f"Intentando cierre forzoso de {operacion_actualizada.posiciones_abiertas_count} posiciones.", "WARN")
                    self.close_all_logical_positions(side, reason="FORCE_STOP")
                
                # En cualquier caso, se detiene el procesamiento normal para este lado.
                continue
            # --- FIN CÓDIGO NUEVO Y CORREGIDO ---
            # --- FIN DE LA MODIFICACIÓN ---

            if operacion.estado not in ['ACTIVA', 'PAUSADA']:
                continue

            initial_open_indices = [i for i, p in enumerate(operacion.posiciones) if p.estado == 'ABIERTA']
            
            if not initial_open_indices:
                continue

            for index in initial_open_indices:
                self._update_trailing_stop(side, index, current_price)

            operacion_actualizada = self._om_api.get_operation_by_side(side)
            if not operacion_actualizada:
                continue

            positions_to_close = []
            for index in initial_open_indices:
                if index >= len(operacion_actualizada.posiciones):
                    continue
                
                pos = operacion_actualizada.posiciones[index]
                
                sl_price = pos.stop_loss_price
                if sl_price and ((side == 'long' and current_price <= sl_price) or \
                                 (side == 'short' and current_price >= sl_price)):
                    positions_to_close.append({'index': index, 'reason': 'SL'})
                    continue

                ts_stop_price = pos.ts_stop_price
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or \
                                      (side == 'short' and current_price >= ts_stop_price)):
                    positions_to_close.append({'index': index, 'reason': 'TS'})

            if positions_to_close:
                for close_info in sorted(positions_to_close, key=lambda x: x['index'], reverse=True):
                    self._close_logical_position(
                        side, 
                        close_info['index'], 
                        current_price, 
                        timestamp, 
                        reason=close_info.get('reason', "UNKNOWN")
                    )

# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================

# ==============================================================================
# --- INICIO DEL CÓDIGO A AÑADIR (Nueva Función) ---
# ==============================================================================

    def sync_physical_positions(self, side: str):
        """
        Comprueba la existencia real de una posición en el exchange y sincroniza
        el estado interno del bot si hay una discrepancia.
        """
        # No ejecutar en modo de simulación
        if self._config.BOT_CONFIG["PAPER_TRADING_MODE"]:
            return

        operacion = self._om_api.get_operation_by_side(side)
        
        # Solo actuar si el bot cree que hay posiciones abiertas
        if not (operacion and operacion.posiciones_abiertas_count > 0):
            return
            
        # El estado ACTIVA o DETENIENDO son los únicos relevantes para esta comprobación
        if operacion.estado not in ['ACTIVA', 'DETENIENDO']:
            return

        try:
            account_purpose = 'longs' if side == 'long' else 'shorts'
            symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
            
            # Llamada a la API para obtener la posición física real
            physical_positions = self._exchange.get_positions(
                symbol=symbol,
                account_purpose=account_purpose
            )

            # Si la lista está vacía, significa que no hay posición en el exchange
            if not physical_positions:
                reason = (
                    f"CIERRE INESPERADO DETECTADO ({side.upper()}): "
                    f"El bot registraba {operacion.posiciones_abiertas_count} pos. abiertas, "
                    f"pero no se encontró ninguna en el exchange. Posible liquidación."
                )
                self._memory_logger.log(reason, "WARN")
                
                # Llamar al manejador de liquidación para resetear el estado
                self._om_api.handle_liquidation_event(side, reason)
        except Exception as e:
            self._memory_logger.log(f"PM ERROR: Excepción durante la sincronización física de posiciones ({side}): {e}", "ERROR")

# ==============================================================================
# --- FIN DEL CÓDIGO A AÑADIR ---
# ==============================================================================
