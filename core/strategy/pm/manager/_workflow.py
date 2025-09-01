# Contenido completo y corregido para: core/strategy/pm/manager/_workflow.py
import datetime
import time
from typing import Any, List, Dict
# ¡Importante! Añadir esta importación para acceder a la función de cierre total.
from core import api as core_api 

class _Workflow:
    """
    Clase base que contiene los métodos de workflow del PositionManager.
    
    Esta versión unifica y refina la lógica del "Heartbeat" de seguridad:
    - `sync_physical_positions` contiene la lógica de sincronización.
    - `check_and_close_positions` ha sido simplificada, ya que asume que la
      sincronización ya fue ejecutada proactivamente por el EventProcessor.
    """

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

    def sync_physical_positions(self, side: str):
        """
        Contiene la LÓGICA del Heartbeat de seguridad. Comprueba la existencia real
        de una posición en el exchange y sincroniza el estado interno del bot si
        hay una discrepancia grave (ej. liquidación, cierre manual).
        """
        if self._manual_close_in_progress:
            self._memory_logger.log(f"Heartbeat omitido para {side.upper()}: Cierre manual en progreso.", "DEBUG")
            return

        if self._config.BOT_CONFIG["PAPER_TRADING_MODE"]:
            return

        operacion = self._om_api.get_operation_by_side(side)
        
        if not (operacion and operacion.posiciones_abiertas_count > 0 and operacion.estado in ['ACTIVA', 'DETENIENDO']):
            return

        try:
            account_purpose = 'longs' if side == 'long' else 'shorts'
            symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
            
            physical_positions = self._exchange.get_positions(
                symbol=symbol,
                account_purpose=account_purpose
            )

            if physical_positions is None:
                self._memory_logger.log(f"HEARTBEAT WARN ({side.upper()}): No se pudo obtener el estado de las posiciones del exchange (error de API). Se reintentará en el siguiente tick.", "WARN")
                return

            if not physical_positions:
                reason = f"LIQUIDACIÓN DETECTADA: {operacion.posiciones_abiertas_count} pos. {side.upper()} no encontradas ."

                self._memory_logger.log(reason, "WARN")
                
                self._om_api.handle_liquidation_event(side, reason)
        except Exception as e:
            self._memory_logger.log(f"PM ERROR: Excepción durante el heartbeat de sincronización de posiciones ({side}): {e}", "ERROR")

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """
        Revisa todas las posiciones abiertas para posible cierre por SL, TSL o detención forzosa.
        """
        if not self._initialized or not self._executor:
            return

        for side in ['long', 'short']:
            operacion = self._om_api.get_operation_by_side(side)
            if not operacion:
                continue

            # --- GESTIÓN DE DETENCIÓN FORZOSA ---
            if operacion.estado == 'DETENIENDO':
                if operacion.posiciones_abiertas_count > 0:
                    self._memory_logger.log(f"PM Workflow: Estado DETENIENDO confirmado para {side.upper()}. "
                                            f"Iniciando cierre forzoso de TODAS las posiciones físicas.", "WARN")
                    
                    symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
                    account_key = f"{side.upper()}S"
                    account_name = self._config.BOT_CONFIG["ACCOUNTS"].get(account_key)
                    side_to_close_api = 'Buy' if side == 'long' else 'Sell'

                    if account_name:
                        success = core_api.close_position_by_side(
                            symbol=symbol,
                            side_to_close=side_to_close_api,
                            account_name=account_name
                        )

                        if success:
                            self._memory_logger.log(f"PM Workflow: Orden de cierre total para {side.upper()} enviada con éxito.", "INFO")
                        else:
                            self._memory_logger.log(f"PM Workflow: Cierre total para {side.upper()} completado (o no se encontraron posiciones).", "INFO")

                        # --- INICIO DE LA CORRECCIÓN: Pasar el precio de cierre ---
                        #
                        # Se pasa el `current_price` a la función de finalización
                        # para que pueda calcular el PNL real y preciso del cierre.
                        #
                        reason = operacion.estado_razon
                        self._om_api.finalize_forced_closure(side, reason, current_price)
                        # --- FIN DE LA CORRECCIÓN ---

                    else:
                        self._memory_logger.log(f"PM Workflow ERROR: No se encontró el nombre de la cuenta para el lado {side.upper()} (Clave buscada: '{account_key}')", "ERROR")
                    
                continue # Importante: No continuar con la lógica de SL/TSL si estamos deteniendo.

            if operacion.estado not in ['ACTIVA', 'PAUSADA', 'EN_ESPERA']:
                continue

            initial_open_indices = [i for i, p in enumerate(operacion.posiciones) if p.estado == 'ABIERTA']
            
            if not initial_open_indices:
                continue

            # Actualizar trailing stops primero
            for index in initial_open_indices:
                self._update_trailing_stop(side, index, current_price)

            # Volver a obtener el estado por si el TSL se actualizó
            operacion_actualizada = self._om_api.get_operation_by_side(side)
            if not operacion_actualizada:
                continue

            # Comprobar condiciones de cierre por SL/TSL
            positions_to_close = []
            for index in initial_open_indices:
                if index >= len(operacion_actualizada.posiciones):
                    continue
                
                pos = operacion_actualizada.posiciones[index]
                
                # Comprobar Stop Loss
                sl_price = pos.stop_loss_price
                if sl_price and ((side == 'long' and current_price <= sl_price) or \
                                    (side == 'short' and current_price >= sl_price)):
                    positions_to_close.append({'index': index, 'reason': 'SL'})
                    continue

                # Comprobar Trailing Stop
                ts_stop_price = pos.ts_stop_price
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or \
                                        (side == 'short' and current_price >= ts_stop_price)):
                    positions_to_close.append({'index': index, 'reason': 'TS'})

            # Ejecutar cierres por SL/TSL
            if positions_to_close:
                
                # --- INICIO DE LA SOLUCIÓN: Añadir el bloque try...finally ---
                self._manual_close_in_progress = True
                self._memory_logger.log(f"Bandera de protección de cierre (WORKFLOW) ACTIVADA para {side.upper()}.", "DEBUG")
                try:
                # --- FIN DE LA SOLUCIÓN ---

                    for close_info in sorted(positions_to_close, key=lambda x: x['index'], reverse=True):
                        self._close_logical_position(
                            side, 
                            close_info['index'], 
                            current_price, 
                            timestamp, 
                            reason=close_info.get('reason', "UNKNOWN")
                        )

                # --- INICIO DE LA SOLUCIÓN: Añadir el bloque try...finally ---
                finally:
                    # Esta pausa es importante para dar tiempo a que las actualizaciones de estado se propaguen
                    # antes de que la bandera se desactive y el siguiente heartbeat pueda ejecutarse.
                    time.sleep(0.1) 
                    self._manual_close_in_progress = False
                    self._memory_logger.log(f"Bandera de protección de cierre (WORKFLOW) DESACTIVADA para {side.upper()}.", "DEBUG")
                # --- FIN DE LA SOLUCIÓN ---