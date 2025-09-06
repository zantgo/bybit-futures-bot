"""
Orquestador Principal del Procesamiento de Eventos.
"""
import sys
import os
import datetime
import traceback
import pandas as pd
import numpy as np
import threading
from typing import Optional, Dict, Any, TYPE_CHECKING

# --- Dependencias de Tipado ---
if TYPE_CHECKING:
    from core.strategy.pm import PositionManager
    from core.strategy.ta import TAManager
    from core.strategy.signal import SignalGenerator
    from core.strategy.entities import Operacion # Importación para type hint

# --- Importaciones de Módulos del Proyecto ---
try:
    import config
    from core import utils
    from core.logging import memory_logger, signal_logger
    from core.strategy.pm import api as pm_api
    from core.strategy.om import api as om_api
except ImportError as e:
    print(f"ERROR CRÍTICO [Event Proc Import]: Falló importación: {e}")
    traceback.print_exc()
    sys.exit(1)


class EventProcessor:
    """
    Orquesta el flujo de trabajo completo para procesar eventos de precio,
    desde el cálculo de indicadores hasta la interacción con los gestores de
    operación y posición. Ahora es una clase para una gestión de estado limpia.
    """
    def __init__(self, dependencies: Dict[str, Any]):
        """
        Inicializa el EventProcessor inyectando todas sus dependencias.
        """
        self._config = dependencies.get('config_module')
        self._utils = dependencies.get('utils_module')
        self._exchange_adapter = dependencies.get('exchange_adapter')
        self._memory_logger = dependencies.get('memory_logger_module')
        self._signal_logger = dependencies.get('signal_logger_module')
        self._pm_api = dependencies.get('position_manager_api_module')
        self._om_api = dependencies.get('operation_manager_api_module')
        
        self._ta_manager: 'TAManager' = dependencies.get('ta_manager') 
        self._signal_generator: 'SignalGenerator' = dependencies.get('signal_generator')

        self._operation_mode: str = "unknown"
        self._latest_signal_data: Dict[str, Any] = {}
        self._pm_instance: Optional['PositionManager'] = None
        self._previous_raw_event_price: float = np.nan
        self._is_first_event: bool = True

    def initialize(
        self,
        operation_mode: str,
        pm_instance: 'PositionManager',
    ):
        """
        Inicializa el orquestador para una nueva sesión, reseteando su estado.
        """
        self._memory_logger.log("Event Processor: Inicializando orquestador...", level="INFO")

        self._operation_mode = operation_mode
        self._pm_instance = pm_instance
        
        self._latest_signal_data = {}
        self._previous_raw_event_price = np.nan
        self._is_first_event = True

        if self._ta_manager:
            self._ta_manager.initialize()
        
        if self._signal_generator:
            self._signal_generator.initialize()
        
        self._memory_logger.log("Event Processor: Orquestador inicializado.", level="INFO")

    def get_latest_signal_data(self) -> Dict[str, Any]:
        """Devuelve una copia de la última señal generada."""
        return self._latest_signal_data.copy()

    def process_event(self, intermediate_ticks_info: list, final_price_info: dict):
        """
        Orquesta el flujo de trabajo completo para procesar un único evento de precio.
        """
        
        if not self._pm_instance:
            return

        if not final_price_info:
            self._memory_logger.log("Evento de precio final vacío, saltando tick.", level="WARN")
            return

        current_timestamp = final_price_info.get("timestamp")
        current_price = self._utils.safe_float_convert(final_price_info.get("price"), default=np.nan)
        if not isinstance(current_timestamp, (datetime.datetime, pd.Timestamp)) or pd.isna(current_price) or current_price <= 0:
            self._memory_logger.log(f"Timestamp/Precio inválido. Saltando. TS:{current_timestamp}, P:{current_price}", level="WARN")
            return

        try:
            # 1. Heartbeat de Sincronización Proactiva
            for side in ['long', 'short']:
                self._pm_api.sync_physical_positions(side)

            # 2. Comprobar Triggers de la Operación (lógica predictiva de liquidación, SL/TP, etc.)
            self._check_operation_triggers(current_price)

            # 3. Procesar datos y generar señal de bajo nivel
            signal_data = self._process_tick_and_generate_signal(current_timestamp, current_price)
            
            # 4. Interacción con el Position Manager
            if self._pm_instance:
                self._pm_instance.check_and_close_positions(current_price, current_timestamp)
                self._pm_instance.handle_low_level_signal(
                    signal=signal_data.get("signal", "HOLD"),
                    entry_price=current_price,
                    timestamp=current_timestamp
                )

        except Exception as e:
            self._memory_logger.log(f"ERROR INESPERADO en el flujo de trabajo de process_event: {e}", level="ERROR")
            self._memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")

    def _process_tick_and_generate_signal(self, timestamp: datetime.datetime, price: float) -> Dict[str, Any]:
        """
        Procesa el tick para generar un evento crudo y luego usa TAManager y
        el SignalGenerator para obtener una señal de bajo nivel.
        """
        increment, decrement = 0, 0
        if not self._is_first_event and pd.notna(self._previous_raw_event_price):
            if price > self._previous_raw_event_price: increment = 1
            elif price < self._previous_raw_event_price: decrement = 1
        self._is_first_event = False

        raw_event = {'timestamp': timestamp, 'price': price, 'increment': increment, 'decrement': decrement}
        
        processed_data = None
        if self._ta_manager and self._config.SESSION_CONFIG["TA"]["ENABLED"]:
            processed_data = self._ta_manager.process_raw_price_event(raw_event)
        
        signal_data = {"signal": "HOLD_NO_TA"}
        if self._signal_generator and processed_data:
             signal_data = self._signal_generator.generate_signal(processed_data)
        
        self._latest_signal_data = signal_data
        
        if self._signal_logger and self._config.BOT_CONFIG["LOGGING"]["LOG_SIGNAL_OUTPUT"]:
            self._signal_logger.log_signal_event(signal_data.copy())
        
        self._previous_raw_event_price = price
        return signal_data
# Reemplaza esta función completa en core/strategy/_event_processor.py

    def _check_operation_triggers(self, current_price: float):
        """
        Evalúa las condiciones de riesgo y salida para las operaciones en cada tick
        y llama a los métodos del OM para transicionar el estado.
        """
        if not (self._om_api and self._om_api.is_initialized() and self._pm_api and self._pm_api.is_initialized()):
            return

        from core.strategy.pm import _calculations as pm_calculations
        
        try:
            for side in ['long', 'short']:
                operacion: 'Operacion' = self._om_api.get_operation_by_side(side)
                if not operacion or operacion.estado == 'DETENIDA':
                    continue

                # 1. VIGILANCIA DE RIESGO (Solo si hay posiciones abiertas)
                if operacion.posiciones_abiertas_count > 0:
                    
                    open_positions_dicts = [p.__dict__ for p in operacion.posiciones_abiertas]
                    estimated_liq_price = pm_calculations.calculate_aggregate_liquidation_price(
                        open_positions=open_positions_dicts,
                        leverage=operacion.apalancamiento,
                        side=side
                    )
                    if estimated_liq_price is not None:
                        if (side == 'long' and current_price <= estimated_liq_price) or \
                           (side == 'short' and current_price >= estimated_liq_price):
                            reason = f"LIQUIDACIÓN DETECTADA: Precio ({current_price:.4f}) cruzó umbral ({estimated_liq_price:.4f})"
                            self._memory_logger.log(reason, "WARN")
                            self._om_api.handle_liquidation_event(side, reason)
                            continue 

                    live_performance = operacion.get_live_performance(current_price, self._utils)
                    roi = live_performance.get("roi_twrr_vivo", 0.0)
                    
                    risk_condition_met, risk_reason, risk_action = False, "", ""

                    # 1.2. Prioridad 2: Comprobación de todos los Stop Loss
                    if not risk_condition_met and operacion.be_sl:
                        break_even_price = operacion.get_live_break_even_price()
                        if break_even_price:
                            sl_dist = operacion.be_sl['distancia']
                            sl_price = break_even_price * (1 - sl_dist / 100) if side == 'long' else break_even_price * (1 + sl_dist / 100)
                            if (side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price):
                                risk_condition_met = True
                                risk_reason = f"BE-SL: Precio ({current_price:.4f}) cruzó Stop ({sl_price:.4f})"
                                risk_action = operacion.be_sl['accion']
                    
                    if not risk_condition_met and operacion.roi_sl:
                        sl_roi_pct = operacion.roi_sl['valor']
                        if roi <= sl_roi_pct:
                            risk_condition_met = True
                            risk_reason = f"ROI-SL: ROI ({roi:.2f}%) <= Límite ({sl_roi_pct}%)"
                            risk_action = operacion.roi_sl['accion']
                    
                    if not risk_condition_met and operacion.dynamic_roi_sl:
                        realized_roi = operacion.realized_twrr_roi
                        sl_roi_target = realized_roi - operacion.dynamic_roi_sl['distancia']
                        if roi <= sl_roi_target:
                            risk_condition_met = True
                            risk_reason = f"Dynamic ROI-SL: ROI ({roi:.2f}%) <= Límite ({sl_roi_target:.2f}%)"
                            risk_action = operacion.dynamic_roi_sl['accion']
                    
                    # 1.3. Prioridad 3: Comprobación de Take Profits y Trailings
                    if not risk_condition_met and operacion.roi_tsl:
                        tsl_config = operacion.roi_tsl
                        if not operacion.tsl_roi_activo and roi >= tsl_config['activacion']:
                            self._om_api.create_or_update_operation(side, {'tsl_roi_activo': True, 'tsl_roi_peak_pct': roi})
                            operacion = self._om_api.get_operation_by_side(side)
                        
                        if operacion.tsl_roi_activo:
                            if roi > operacion.tsl_roi_peak_pct:
                                self._om_api.create_or_update_operation(side, {'tsl_roi_peak_pct': roi})
                                operacion = self._om_api.get_operation_by_side(side)
                            
                            umbral_disparo = operacion.tsl_roi_peak_pct - tsl_config['distancia']
                            if roi <= umbral_disparo:
                                risk_condition_met = True
                                risk_reason = f"TSL-ROI: ROI ({roi:.2f}%) <= Stop ({umbral_disparo:.2f}%)"
                                risk_action = tsl_config['accion']
                    
                    if not risk_condition_met and operacion.be_tp:
                        break_even_price = operacion.get_live_break_even_price()
                        if break_even_price:
                            tp_dist = operacion.be_tp['distancia']
                            tp_price = break_even_price * (1 + tp_dist / 100) if side == 'long' else break_even_price * (1 - tp_dist / 100)
                            if (side == 'long' and current_price >= tp_price) or (side == 'short' and current_price <= tp_price):
                                risk_condition_met = True
                                risk_reason = f"BE-TP: Precio ({current_price:.4f}) cruzó TP ({tp_price:.4f})"
                                risk_action = operacion.be_tp['accion']

                    if not risk_condition_met and operacion.roi_tp:
                        tp_roi_pct = operacion.roi_tp['valor']
                        if roi >= tp_roi_pct:
                            risk_condition_met = True
                            risk_reason = f"ROI-TP: ROI ({roi:.2f}%) >= Límite ({tp_roi_pct}%)"
                            risk_action = operacion.roi_tp['accion']

                    # 1.4. Ejecución de la Acción de Riesgo
                    if risk_condition_met:
                        log_msg = f"CONDICIÓN DE RIESGO CUMPLIDA ({side.upper()}): {risk_reason}. Acción: {risk_action.upper()}."
                        self._memory_logger.log(log_msg, "WARN")
                        if risk_action == 'DETENER':
                            self._om_api.detener_operacion(side, forzar_cierre_posiciones=True, reason=risk_reason, price=current_price)
                        else: # PAUSAR
                            self._om_api.pausar_operacion(side, reason=risk_reason, price=current_price)
                        continue
                
                # 2. Lógica de ENTRADA (Solo se ejecuta si está EN_ESPERA)
                if operacion.estado == 'EN_ESPERA':
                    entry_condition_met = False
                    
                    # --- (INICIO DE LA MODIFICACIÓN) ---
                    activation_reason = ""
                    # --- (FIN DE LA MODIFICACIÓN) ---
                    
                    is_market_entry = all(v is None for v in [operacion.cond_entrada_above, operacion.cond_entrada_below, operacion.tiempo_espera_minutos])

                    if is_market_entry:
                        entry_condition_met = True
                        # --- (INICIO DE LA MODIFICACIÓN) ---
                        activation_reason = "Activada por condición de mercado (inmediata)."
                        # --- (FIN DE LA MODIFICACIÓN) ---
                    else:
                        if operacion.cond_entrada_below is not None:
                            if current_price < operacion.cond_entrada_below:
                                entry_condition_met = True
                                # --- (INICIO DE LA MODIFICACIÓN) ---
                                activation_reason = f"Activada por precio < {operacion.cond_entrada_below:.4f}"
                                # --- (FIN DE LA MODIFICACIÓN) ---

                        if not entry_condition_met and operacion.cond_entrada_above is not None:
                            if current_price > operacion.cond_entrada_above:
                                entry_condition_met = True
                                # --- (INICIO DE LA MODIFICACIÓN) ---
                                activation_reason = f"Activada por precio > {operacion.cond_entrada_above:.4f}"
                                # --- (FIN DE LA MODIFICACIÓN) ---
                        
                        if not entry_condition_met and operacion.tiempo_inicio_espera and operacion.tiempo_espera_minutos:
                            elapsed_minutes = (datetime.datetime.now(datetime.timezone.utc) - operacion.tiempo_inicio_espera).total_seconds() / 60.0
                            if elapsed_minutes >= operacion.tiempo_espera_minutos:
                                entry_condition_met = True
                                # --- (INICIO DE LA MODIFICACIÓN) ---
                                activation_reason = f"Activada por tiempo ({operacion.tiempo_espera_minutos} min)."
                                # --- (FIN DE LA MODIFICACIÓN) ---
                    
                    if entry_condition_met:
                        # --- (INICIO DE LA MODIFICACIÓN) ---
                        # --- (LÍNEA ORIGINAL COMENTADA) ---
                        # self._om_api.activar_por_condicion(side, price=current_price)
                        # --- (LÍNEA CORREGIDA) ---
                        self._om_api.activar_por_condicion(side, price=current_price, razon_activacion=activation_reason)
                        # --- (FIN DE LA MODIFICACIÓN) ---
                        continue
                
                # 3. Lógica de LÍMITES DE SALIDA (Se ejecuta siempre que no esté DETENIDA)
                if operacion.estado in ['ACTIVA', 'PAUSADA']:
                    exit_triggered, exit_reason, accion_final = False, "", ""
                    
                    # 3.1 GESTIÓN DE SALIDA POR PRECIO FIJO
                    # --- (INICIO DE LA MODIFICACIÓN) ---
                    # Se mueve la condición `if operacion.posiciones_abiertas_count > 0:`
                    # para que envuelva solo las salidas por precio, no las operativas.
                    # --- (LÍNEA ORIGINAL ELIMINADA) ---
                    # if operacion.posiciones_abiertas_count > 0:
                    
                    if not exit_triggered and operacion.cond_salida_above:
                        cond = operacion.cond_salida_above
                        valor_limite = cond.get('valor', float('inf'))
                        if current_price > valor_limite:
                            exit_triggered = True
                            exit_reason = f"Límite de Salida por precio > {valor_limite:.4f} alcanzado"
                            accion_final = cond.get('accion', 'PAUSAR')
                    
                    if not exit_triggered and operacion.cond_salida_below:
                        cond = operacion.cond_salida_below
                        valor_limite = cond.get('valor', 0.0)
                        if current_price < valor_limite:
                            exit_triggered = True
                            exit_reason = f"Límite de Salida por precio < {valor_limite:.4f} alcanzado"
                            accion_final = cond.get('accion', 'PAUSAR')

                    # 3.2 LÍMITES OPERATIVOS (Se evalúan siempre)
                    # --- (FIN DE LA MODIFICACIÓN) ---
                    if not exit_triggered and operacion.max_comercios is not None and operacion.comercios_cerrados_contador >= operacion.max_comercios:
                        exit_triggered = True
                        exit_reason = f"Límite de {operacion.max_comercios} trades alcanzado"
                        accion_final = operacion.accion_por_limite_trades

                    if not exit_triggered and operacion.tiempo_maximo_min is not None and operacion.tiempo_ultimo_inicio_activo:
                        elapsed_seconds = operacion.tiempo_acumulado_activo_seg
                        if operacion.estado == 'ACTIVA':
                            elapsed_seconds += (datetime.datetime.now(datetime.timezone.utc) - operacion.tiempo_ultimo_inicio_activo).total_seconds()
                        
                        if (elapsed_seconds / 60.0) >= operacion.tiempo_maximo_min:
                            exit_triggered = True
                            exit_reason = f"Límite de tiempo de operación ({operacion.tiempo_maximo_min} min) alcanzado"
                            accion_final = operacion.accion_por_limite_tiempo
                    
                    # 3.3 EJECUCIÓN DE ACCIÓN DE SALIDA
                    if exit_triggered:
                        log_msg = f"CONDICIÓN DE SALIDA ALCANZADA ({side.upper()}): {exit_reason}. Acción: {accion_final.upper()}."
                        self._memory_logger.log(log_msg, "WARN")
                        
                        if accion_final == 'DETENER': 
                            self._om_api.detener_operacion(side, True, reason=exit_reason, price=current_price)
                        elif accion_final == 'PAUSAR' and operacion.estado not in ['DETENIENDO', 'DETENIDA']:
                            self._om_api.pausar_operacion(side, reason=exit_reason, price=current_price)
                        continue      
        except Exception as e:
            self._memory_logger.log(f"ERROR CRÍTICO [Check Triggers]: {e}", level="ERROR")
            self._memory_logger.log(traceback.format_exc(), level="ERROR")