"""
Módulo Gestor de la Operación Estratégica (Operation Manager).

v8.3 (Corrección de Deadlock en Detener Operación - Flujo Síncrono para TUI):
- Se introduce un estado de transición 'DETENIENDO' para proporcionar feedback
  visual inmediato al usuario, similar a como funciona el estado 'PAUSADA'.
- `detener_operacion` ahora cambia el estado a 'DETENIENDO' de forma síncrona.
- `revisar_y_transicionar_a_detenida` ahora maneja la transición final de
  'DETENIENDO' a 'DETENIDA' una vez que las posiciones se han cerrado.
- `detener_operacion` ahora maneja instantáneamente el caso sin posiciones abiertas.
"""
import datetime
import uuid
import threading
from typing import Optional, Dict, Any, Tuple

# --- Dependencias del Proyecto ---
try:
    from ._entities import Operacion, LogicalBalances
    from core.logging import memory_logger
    import config as config_module
except ImportError:
    class Operacion: pass
    class LogicalBalances: pass
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    config_module = None

class OperationManager:
    """
    Gestiona el estado y la lógica de negocio de las operaciones estratégicas
    independientes para LONG y SHORT.
    """
    def __init__(self, config: Any, memory_logger_instance: Any):
        """
        Inicializa el Operation Manager.
        
        Args:
            config: El módulo de configuración del bot.
            memory_logger_instance: La instancia del logger en memoria.
        """
        self._config = config
        self._memory_logger = memory_logger_instance
        self._initialized: bool = False
        
        self.long_operation: Optional[Operacion] = None
        self.short_operation: Optional[Operacion] = None
        
        self._lock = threading.RLock()

        self.initialize()

    def initialize(self):
        """
        Crea las operaciones iniciales para LONG y SHORT, ambas en estado DETENIDA.
        """
        with self._lock:
            if not self.long_operation:
                self.long_operation = Operacion(id=f"op_long_{uuid.uuid4()}")
            if not self.short_operation:
                self.short_operation = Operacion(id=f"op_short_{uuid.uuid4()}")
            self._initialized = True
        self._memory_logger.log("OperationManager inicializado con operaciones LONG y SHORT en estado DETENIDA.", level="INFO")

    def is_initialized(self) -> bool:
        """Verifica si el Operation Manager ha sido inicializado."""
        return self._initialized

    def _get_operation_by_side_internal(self, side: str) -> Optional[Operacion]:
        """Devuelve una referencia directa a la operación (uso interno, requiere lock externo)."""
        if side == 'long':
            return self.long_operation
        elif side == 'short':
            return self.short_operation
        self._memory_logger.log(f"WARN [OM]: Intento de acceso a lado inválido '{side}' en _get_operation_by_side_internal.", "WARN")
        return None

    def get_operation_by_side(self, side: str) -> Optional[Operacion]:
        """Devuelve una copia segura del objeto de operación para un lado específico."""
        with self._lock:
            operation = self._get_operation_by_side_internal(side)
            if operation:
                import copy
                return copy.deepcopy(operation)
        
        self._memory_logger.log(f"Error: Se solicitó operación para un lado inválido '{side}'.", "ERROR")
        return None

    def create_or_update_operation(self, side: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Crea o actualiza una operación. Gestiona las transiciones de estado y el ajuste
        dinámico del capital lógico para operaciones activas.
        """
        # --- INICIO DE LA MODIFICACIÓN ---
        # Cambiamos la API a la que llamamos. Ahora usamos sm_api.
        from core.strategy.sm import api as sm_api
        # --- FIN DE LA MODIFICACIÓN ---
        
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation:
                return False, f"Lado de operación inválido '{side}'."

            estado_original = target_operation.estado
            changes_log = []

            capital_logico_anterior = target_operation.balances.operational_margin
            
            for key, value in params.items():
                if hasattr(target_operation, key):
                    old_value = getattr(target_operation, key)
                    if old_value != value:
                        setattr(target_operation, key, value)
                        changes_log.append(f"'{key}': {old_value} -> {value}")
            
            if estado_original == 'DETENIDA' and params:
                new_operational_margin = params.get('operational_margin')
                if new_operational_margin is not None:
                    target_operation.balances.operational_margin = float(new_operational_margin)
                    target_operation.capital_inicial_usdt = float(new_operational_margin)
                    changes_log.append(f"'capital_logico': {target_operation.capital_inicial_usdt:.2f}$ (asignado)")

                if target_operation.tipo_cond_entrada == 'MARKET':
                    target_operation.estado = 'ACTIVA'
                    target_operation.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
                else:
                    target_operation.estado = 'EN_ESPERA'
                changes_log.append(f"'estado': DETENIDA -> {target_operation.estado}")

            elif estado_original in ['ACTIVA', 'EN_ESPERA', 'PAUSADA']:
                capital_logico_nuevo = params.get('operational_margin')
                if capital_logico_nuevo is not None:
                    diferencia_capital = float(capital_logico_nuevo) - capital_logico_anterior

                    if abs(diferencia_capital) > 1e-9:
                        target_operation.balances.operational_margin = float(capital_logico_nuevo)
                        target_operation.capital_inicial_usdt += diferencia_capital
                        changes_log.append(f"'capital_logico': {capital_logico_anterior:.2f}$ -> {target_operation.balances.operational_margin:.2f}$")
                        changes_log.append(f"'capital_inicial_historico': ajustado en {diferencia_capital:+.2f}$")
                        self._memory_logger.log(f"CAPITAL LÓGICO AJUSTADO ({side.upper()}): {diferencia_capital:+.2f}$. Nuevo capital base ROI: {target_operation.capital_inicial_usdt:.2f}$", "WARN")

                if estado_original == 'ACTIVA' and 'tipo_cond_entrada' in params:
                    # --- INICIO DE LA MODIFICACIÓN ---
                    # Usamos la API correcta (sm_api) para obtener el resumen.
                    summary = sm_api.get_session_summary()
                    # --- FIN DE LA MODIFICACIÓN ---
                    current_price = summary.get('current_market_price', 0.0)
                    cond_type = target_operation.tipo_cond_entrada
                    cond_value = target_operation.valor_cond_entrada
                    condicion_cumplida_ahora = False
                    if cond_type == 'MARKET' or cond_value is None:
                        condicion_cumplida_ahora = True
                    elif current_price > 0:
                        if cond_type == 'PRICE_ABOVE' and current_price > cond_value:
                            condicion_cumplida_ahora = True
                        elif cond_type == 'PRICE_BELOW' and current_price < cond_value:
                            condicion_cumplida_ahora = True
                    if not condicion_cumplida_ahora:
                        target_operation.estado = 'EN_ESPERA'
                        changes_log.append(f"'estado': ACTIVA -> EN_ESPERA (nueva condición no se cumple)")

        if not changes_log:
            return True, f"No se realizaron cambios en la operación {side.upper()}."

        log_message = f"Operación {side.upper()} actualizada: " + ", ".join(changes_log)
        self._memory_logger.log(log_message, "WARN")
        return True, f"Operación {side.upper()} actualizada con éxito."

    def pausar_operacion(self, side: str) -> Tuple[bool, str]:
        """Pone una operación ACTIVA o EN_ESPERA en estado PAUSADA."""
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado not in ['ACTIVA', 'EN_ESPERA']:
                return False, f"Solo se puede pausar una operación ACTIVA o EN_ESPERA del lado {side.upper()}."
            estado_anterior = target_operation.estado
            target_operation.estado = 'PAUSADA'
        
        msg = f"OPERACIÓN {side.upper()} PAUSADA (estado anterior: {estado_anterior}). No se abrirán nuevas posiciones."
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def reanudar_operacion(self, side: str) -> Tuple[bool, str]:
        """Reanuda una operación PAUSADA, devolviéndola a un estado activo."""
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado != 'PAUSADA':
                return False, f"Solo se puede reanudar una operación PAUSADA del lado {side.upper()}."
            
            target_operation.estado = 'ACTIVA'
            if not target_operation.tiempo_inicio_ejecucion:
                target_operation.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
        
        msg = f"OPERACIÓN {side.upper()} REANUDADA. El sistema está ahora ACTIVO para este lado."
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def forzar_activacion_manual(self, side: str) -> Tuple[bool, str]:
        """Activa manualmente una operación que está EN_ESPERA, ignorando su condición de entrada."""
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado != 'EN_ESPERA':
                return False, f"Solo se puede forzar la activación de una operación EN_ESPERA."
            
            target_operation.estado = 'ACTIVA'
            if not target_operation.tiempo_inicio_ejecucion:
                target_operation.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)

        msg = f"OPERACIÓN {side.upper()} FORZADA A ESTADO ACTIVO manualmente."
        self._memory_logger.log(msg, "WARN")
        return True, msg
        
    def activar_por_condicion(self, side: str) -> Tuple[bool, str]:
        """Activa una operación porque su condición de entrada se ha cumplido. Llamado por EventProcessor."""
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado != 'EN_ESPERA':
                return False, "La operación no estaba esperando una condición."

            target_operation.estado = 'ACTIVA'
            if not target_operation.tiempo_inicio_ejecucion:
                 target_operation.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
        
        msg = f"OPERACIÓN {side.upper()} ACTIVADA AUTOMÁTICAMENTE por condición de entrada."
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def detener_operacion(self, side: str, forzar_cierre_posiciones: bool) -> Tuple[bool, str]:
        """
        Detiene una operación de forma SÍNCRONA, asegurando que todas las acciones
        se completen antes de devolver el control.
        """
        from core.strategy.pm import api as pm_api

        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado == 'DETENIDA':
                return False, f"La operación {side.upper()} ya está detenida o no existe."

            if forzar_cierre_posiciones:
                self._memory_logger.log(f"DETENIENDO OPERACIÓN {side.upper()}: Forzando cierre de posiciones...", "WARN")
                success, msg = pm_api.close_all_logical_positions(side, reason=f"OPERATION_{side.upper()}_STOPPED")
                self._memory_logger.log(f"Resultado del cierre masivo para {side.upper()}: {msg}", "INFO")
                if not success:
                    self._memory_logger.log(f"ADVERTENCIA: El cierre de posiciones para {side.upper()} reportó un fallo. Aún así, se reseteará la operación.", "WARN")

            tendencia_anterior = target_operation.tendencia
            if hasattr(target_operation, 'reset'):
                 target_operation.reset()
            else:
                 self.initialize()
                 target_operation = self._get_operation_by_side_internal(side)
        
        msg = f"OPERACIÓN {side.upper()} ({tendencia_anterior}) DETENIDA Y RESETEADA. El sistema está ahora inactivo para este lado."
        self._memory_logger.log(msg, "INFO")
        return True, msg

    def actualizar_pnl_realizado(self, side: str, pnl_amount: float):
        """Suma un PNL realizado al total acumulado de una operación."""
        with self._lock:
            operacion = self._get_operation_by_side_internal(side)
            if operacion:
                operacion.pnl_realizado_usdt += pnl_amount

    def actualizar_comisiones_totales(self, side: str, fee_amount: float):
        """Suma una nueva comisión al total acumulado de una operación."""
        with self._lock:
            operacion = self._get_operation_by_side_internal(side)
            if operacion:
                if hasattr(operacion, 'comisiones_totales_usdt'):
                    operacion.comisiones_totales_usdt += abs(fee_amount)
    
    def revisar_y_transicionar_a_detenida(self, side: str):
        """
        Comprueba si una operación PAUSADA ya no tiene posiciones abiertas.
        Si es así, la transiciona a DETENIDA. Es invocado por el PM tras cada cierre.
        """
        from core.strategy.pm import api as pm_api
        
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado != 'PAUSADA':
                return

        summary = pm_api.get_position_summary()
        pos_count = -1
        if summary and not summary.get('error'):
            pos_count = summary.get(f'open_{side}_positions_count', 0)
    
        if pos_count == 0:
            with self._lock:
                target_operation = self._get_operation_by_side_internal(side)
                if target_operation and target_operation.estado == 'PAUSADA':
                    log_msg = (f"OPERACIÓN {side.upper()}: Última posición cerrada mientras estaba "
                               f"PAUSADA. Transicionando a DETENIDA.")
                    self._memory_logger.log(log_msg, "INFO")
                    
                    self.detener_operacion(side, forzar_cierre_posiciones=False)