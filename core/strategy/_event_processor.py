"""
Orquestador Principal del Procesamiento de Eventos.

v8.3 (Dashboard Enriquecido):
- Se añade el atributo `_latest_signal_data` para almacenar la última señal.
- Se añade el método `get_latest_signal_data` para exponerla.

v8.2 (Refactor Signal Generator):
- Se actualiza el constructor para recibir una instancia de la clase SignalGenerator.
- La generación de señales ahora se delega al método de la instancia inyectada.

v8.1 (Refactor TA Manager):
- Se actualiza el constructor para recibir una instancia de la clase TAManager.

v8.0 (Refactor a Clase):
- Toda la lógica del módulo se ha encapsulado en la clase `EventProcessor`.
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

# --- INICIO DE LA MODIFICACIÓN ---
# Se elimina la excepción personalizada, ya que no se usará.
# class GlobalStopLossException(Exception):
#     """Excepción para ser lanzada cuando se activa el Global Stop Loss."""
#     pass
# --- FIN DE LA MODIFICACIÓN ---


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
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se eliminan los atributos relacionados con los disyuntores de sesión.
        # self._global_stop_loss_event: Optional[threading.Event] = None
        # self._global_stop_loss_triggered: bool = False
        # --- FIN DE LA MODIFICACIÓN ---


    def initialize(
        self,
        operation_mode: str,
        pm_instance: 'PositionManager',
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se elimina el argumento global_stop_loss_event
        # global_stop_loss_event: Optional[threading.Event] = None
        # --- FIN DE LA MODIFICACIÓN ---
    ):
        """
        Inicializa el orquestador para una nueva sesión, reseteando su estado.
        """
        self._memory_logger.log("Event Processor: Inicializando orquestador...", level="INFO")

        self._operation_mode = operation_mode
        self._pm_instance = pm_instance
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se elimina la asignación de los atributos de disyuntores.
        # self._global_stop_loss_event = global_stop_loss_event
        # self._global_stop_loss_triggered = False
        # --- FIN DE LA MODIFICACIÓN ---

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

    # --- INICIO DE LA MODIFICACIÓN ---
    # Se elimina el método has_global_stop_loss_triggered
    # def has_global_stop_loss_triggered(self) -> bool:
    #     """
    #     Devuelve si el Global Stop Loss se ha activado para esta instancia.
    #     """
    #     return self._global_stop_loss_triggered
    # --- FIN DE LA MODIFICACIÓN ---

    def process_event(self, intermediate_ticks_info: list, final_price_info: dict):
        """
        Orquesta el flujo de trabajo completo para procesar un único evento de precio.
        """
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se elimina la comprobación de _global_stop_loss_triggered
        if not self._pm_instance:
            return
        # --- FIN DE LA MODIFICACIÓN ---

        if not final_price_info:
            self._memory_logger.log("Evento de precio final vacío, saltando tick.", level="WARN")
            return

        current_timestamp = final_price_info.get("timestamp")
        current_price = self._utils.safe_float_convert(final_price_info.get("price"), default=np.nan)
        if not isinstance(current_timestamp, (datetime.datetime, pd.Timestamp)) or pd.isna(current_price) or current_price <= 0:
            self._memory_logger.log(f"Timestamp/Precio inválido. Saltando. TS:{current_timestamp}, P:{current_price}", level="WARN")
            return

        try:
            # 1. Comprobar Triggers de la Operación (lógica de activación/desactivación automática)
            self._check_operation_triggers(current_price)

            # 2. Procesar datos y generar señal de bajo nivel
            signal_data = self._process_tick_and_generate_signal(current_timestamp, current_price)
            
            # 3. Interacción con el Position Manager
            if self._pm_instance:
                self._pm_instance.check_and_close_positions(current_price, current_timestamp)
                self._pm_instance.handle_low_level_signal(
                    signal=signal_data.get("signal", "HOLD"),
                    entry_price=current_price,
                    timestamp=current_timestamp
                )

            # --- INICIO DE LA MODIFICACIÓN ---
            # 4. Se elimina la llamada a la comprobación de límites de sesión
            # self._check_session_limits(current_price, current_timestamp)
            # --- FIN DE LA MODIFICACIÓN ---

        # --- INICIO DE LA MODIFICACIÓN ---
        # Se elimina la captura de GlobalStopLossException
        # except GlobalStopLossException as e:
        #     self._memory_logger.log(f"GlobalStopLossException capturada en Event Processor: {e}", level="ERROR")
        # --- FIN DE LA MODIFICACIÓN ---
        except Exception as e:
            self._memory_logger.log(f"ERROR INESPERADO en el flujo de trabajo de process_event: {e}", level="ERROR")
            self._memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")

    def _check_operation_triggers(self, current_price: float):
        """
        Evalúa las condiciones de entrada y salida para las operaciones en cada tick
        y llama a los métodos del OM para transicionar el estado.
        """
        if not (self._om_api and self._om_api.is_initialized() and self._pm_api and self._pm_api.is_initialized()):
            return

        try:
            for side in ['long', 'short']:
                operacion = self._om_api.get_operation_by_side(side)
                if not operacion:
                    continue

                if operacion.estado == 'EN_ESPERA':
                    cond_type = operacion.tipo_cond_entrada
                    cond_value = operacion.valor_cond_entrada
                    entry_condition_met = False
                    if cond_type == 'MARKET':
                        entry_condition_met = True
                    elif cond_value is not None:
                        if cond_type == 'PRICE_ABOVE' and current_price > cond_value: entry_condition_met = True
                        elif cond_type == 'PRICE_BELOW' and current_price < cond_value: entry_condition_met = True
                    if entry_condition_met: self._om_api.activar_por_condicion(side)

                elif operacion.estado == 'ACTIVA':
                    exit_condition_met = False
                    reason = ""
                    summary = self._pm_api.get_position_summary()
                    
                    # --- INICIO DE LA CORRECCIÓN ---
                    # Asegurarse de que el ROI es un número antes de usarlo.
                    roi = 0.0
                    if summary and 'error' not in summary:
                        unrealized_pnl_side = 0.0
                        open_positions_side = summary.get(f'open_{side}_positions', [])
                        for pos in open_positions_side:
                            entry = pos.get('entry_price', 0.0)
                            size = pos.get('size_contracts', 0.0)
                            if side == 'long': unrealized_pnl_side += (current_price - entry) * size
                            else: unrealized_pnl_side += (entry - current_price) * size
                        
                        total_pnl_side = operacion.pnl_realizado_usdt + unrealized_pnl_side
                        roi = self._utils.safe_division(total_pnl_side, operacion.capital_inicial_usdt) * 100

                        # Ahora que ROI es seguro, procedemos con las comprobaciones
                        tsl_act_pct = operacion.tsl_roi_activacion_pct
                        tsl_dist_pct = operacion.tsl_roi_distancia_pct
                        
                        if tsl_act_pct is not None and tsl_dist_pct is not None:
                            if not operacion.tsl_roi_activo and roi >= tsl_act_pct:
                                operacion.tsl_roi_activo = True
                                operacion.tsl_roi_peak_pct = roi
                                self._memory_logger.log(f"TSL-ROI para Operación {side.upper()} ACTIVADO. ROI: {roi:.2f}%, Pico: {operacion.tsl_roi_peak_pct:.2f}%", "INFO")
                            
                            if operacion.tsl_roi_activo:
                                if roi > operacion.tsl_roi_peak_pct: 
                                    operacion.tsl_roi_peak_pct = roi
                                
                                umbral_disparo = operacion.tsl_roi_peak_pct - tsl_dist_pct
                                if roi <= umbral_disparo: 
                                    exit_condition_met, reason = True, f"TSL-ROI (Pico: {operacion.tsl_roi_peak_pct:.2f}%, Actual: {roi:.2f}%)"

                        sl_roi_pct = operacion.sl_roi_pct
                        if not exit_condition_met and sl_roi_pct is not None and roi <= -abs(sl_roi_pct):
                            exit_condition_met, reason = True, f"SL-ROI alcanzado ({roi:.2f}%)"
                    # --- FIN DE LA CORRECCIÓN ---

                    if not exit_condition_met and operacion.max_comercios is not None and operacion.comercios_cerrados_contador >= operacion.max_comercios:
                        exit_condition_met, reason = True, f"Límite de {operacion.max_comercios} trades"
                    
                    start_time = operacion.tiempo_inicio_ejecucion
                    if not exit_condition_met and operacion.tiempo_maximo_min is not None and start_time:
                        elapsed_min = (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds() / 60.0
                        if elapsed_min >= operacion.tiempo_maximo_min: exit_condition_met, reason = True, f"Límite de tiempo ({operacion.tiempo_maximo_min} min)"

                    exit_type, exit_value = operacion.tipo_cond_salida, operacion.valor_cond_salida
                    if not exit_condition_met and exit_type and exit_value is not None:
                        if exit_type == 'PRICE_ABOVE' and current_price > exit_value: exit_condition_met, reason = True, f"Precio de salida ({current_price:.4f}) > ({exit_value:.4f})"
                        elif exit_type == 'PRICE_BELOW' and current_price < exit_value: exit_condition_met, reason = True, f"Precio de salida ({current_price:.4f}) < ({exit_value:.4f})"

                    if exit_condition_met:
                        accion_final = operacion.accion_al_finalizar
                        log_msg = f"CONDICIÓN DE SALIDA CUMPLIDA ({side.upper()}): {reason}. Acción: {accion_final.upper()}"
                        self._memory_logger.log(log_msg, "WARN")
                        if accion_final == 'PAUSAR': self._om_api.pausar_operacion(side)
                        elif accion_final == 'DETENER': self._om_api.detener_operacion(side, forzar_cierre_posiciones=True)
                        else: self._om_api.pausar_operacion(side)
        except Exception as e:
            self._memory_logger.log(f"ERROR CRÍTICO [Check Triggers]: {e}", level="ERROR")
            self._memory_logger.log(traceback.format_exc(), level="ERROR")

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
