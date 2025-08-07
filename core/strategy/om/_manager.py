import datetime
import uuid
import threading
from typing import Optional, Dict, Any, Tuple

try:
    # --- INICIO DE LA MODIFICACIÓN #1 ---
    # Se corrige la importación para apuntar a la ubicación centralizada.
    from core.strategy.entities import Operacion, LogicalBalances
    # --- FIN DE LA MODIFICACIÓN #1 ---
    from core.logging import memory_logger
    import config as config_module
except ImportError:
    # Fallback for isolated testing or type checking
    class Operacion:
        def __init__(self, id: str):
            self.estado = 'DETENIDA'
            self.balances = LogicalBalances()
            self.capital_inicial_usdt = 0.0
            self.capital_actual_usdt = 0.0
            self.tipo_cond_entrada = None
            self.valor_cond_entrada = None
            self.tiempo_inicio_ejecucion = None
        def reset(self): pass

    class LogicalBalances:
        def __init__(self):
            self.operational_margin = 0.0
            
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    config_module = None

class OperationManager:
    """
    Gestiona el ciclo de vida y la configuración de las operaciones estratégicas
    (LONG y SHORT).
    """
    def __init__(self, config: Any, memory_logger_instance: Any):
        self._config = config
        self._memory_logger = memory_logger_instance
        self._initialized: bool = False
        
        self.long_operation: Optional[Operacion] = None
        self.short_operation: Optional[Operacion] = None
        
        self._lock = threading.RLock()

        self.initialize()

    def initialize(self):
        """Inicializa las instancias de operación para LONG y SHORT."""
        with self._lock:
            if not self.long_operation:
                self.long_operation = Operacion(id=f"op_long_{uuid.uuid4()}")
            if not self.short_operation:
                self.short_operation = Operacion(id=f"op_short_{uuid.uuid4()}")
            self._initialized = True
        self._memory_logger.log("OperationManager inicializado con operaciones LONG y SHORT en estado DETENIDA.", level="INFO")

    def is_initialized(self) -> bool:
        """Verifica si el gestor ha sido inicializado."""
        return self._initialized

    def _get_operation_by_side_internal(self, side: str) -> Optional[Operacion]:
        """Obtiene el objeto de operación interno (sin copia) para un lado específico."""
        if side == 'long':
            return self.long_operation
        elif side == 'short':
            return self.short_operation
        self._memory_logger.log(f"WARN [OM]: Intento de acceso a lado inválido '{side}' en _get_operation_by_side_internal.", "WARN")
        return None

    def get_operation_by_side(self, side: str) -> Optional[Operacion]:
        """Obtiene una copia segura del estado de la operación para un lado específico."""
        with self._lock:
            operation = self._get_operation_by_side_internal(side)
            if operation:
                import copy
                return copy.deepcopy(operation)
        return None

    def create_or_update_operation(self, side: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Crea o actualiza una operación. Si la operación está DETENIDA, la configura
        y la transiciona a EN_ESPERA o ACTIVA. Si ya está activa, solo actualiza
        los parámetros.
        """
        from core.strategy.sm import api as sm_api
        
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation:
                return False, f"Lado de operación inválido '{side}'."

            estado_original = target_operation.estado
            changes_log = []
            
            capital_anterior = target_operation.capital_actual_usdt
            
            for key, value in params.items():
                if hasattr(target_operation, key):
                    old_value = getattr(target_operation, key)
                    if old_value != value:
                        setattr(target_operation, key, value)
                        changes_log.append(f"'{key}': {old_value} -> {value}")
            
            operational_margin_nuevo = params.get('operational_margin')
            if operational_margin_nuevo is not None:
                if not hasattr(target_operation, 'balances') or not target_operation.balances:
                    target_operation.balances = LogicalBalances()
                
                # --- INICIO DE LA MODIFICACIÓN #2 ---
                # Lógica simplificada para gestionar capital inicial y actual.
                if estado_original == 'DETENIDA':
                    # Es la primera asignación de capital.
                    target_operation.capital_inicial_usdt = float(operational_margin_nuevo)
                    target_operation.capital_actual_usdt = float(operational_margin_nuevo)
                    target_operation.balances.operational_margin = float(operational_margin_nuevo)
                    changes_log.append(f"'capital_operativo': {target_operation.capital_actual_usdt:.2f}$ (asignado)")
                
                elif estado_original in ['ACTIVA', 'EN_ESPERA', 'PAUSADA']:
                    # Es una modificación de capital.
                    diferencia_capital = float(operational_margin_nuevo) - capital_anterior
                    if abs(diferencia_capital) > 1e-9: # Usar tolerancia para flotantes
                        target_operation.capital_actual_usdt = float(operational_margin_nuevo)
                        target_operation.balances.operational_margin = float(operational_margin_nuevo)
                        changes_log.append(f"'capital_operativo': {capital_anterior:.2f}$ -> {target_operation.capital_actual_usdt:.2f}$")
                        self._memory_logger.log(f"CAPITAL LÓGICO AJUSTADO ({side.upper()}): {diferencia_capital:+.2f}$", "WARN")
                # --- FIN DE LA MODIFICACIÓN #2 ---


            # --- Lógica de Transición de Estado (SIN CAMBIOS) ---
            if estado_original == 'DETENIDA' and params:
                if target_operation.tipo_cond_entrada == 'MARKET':
                    target_operation.estado = 'ACTIVA'
                    target_operation.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
                else:
                    target_operation.estado = 'EN_ESPERA'
                changes_log.append(f"'estado': DETENIDA -> {target_operation.estado}")

            elif estado_original == 'ACTIVA' and 'tipo_cond_entrada' in params:
                summary = sm_api.get_session_summary()
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
        """Pausa una operación, impidiendo la apertura de nuevas posiciones."""
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
        """Reanuda una operación que estaba en estado PAUSADA."""
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
        """Fuerza la activación de una operación que está EN_ESPERA."""
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
        """Activa una operación porque su condición de entrada de precio se ha cumplido."""
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
        """Inicia el proceso de detención de una operación."""
        from core.strategy.pm import api as pm_api
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado == 'DETENIDA':
                return False, f"La operación {side.upper()} ya está detenida o no existe."

            target_operation.estado = 'DETENIENDO'
            self._memory_logger.log(f"OPERACIÓN {side.upper()} en estado DETENIENDO. Esperando cierre de posiciones por PM.", "WARN")

            # Si no hay posiciones, podemos detenerla inmediatamente.
            if not target_operation.posiciones_activas.get(side):
                self.revisar_y_transicionar_a_detenida(side)
                return True, f"Operación {side.upper()} detenida y reseteada (sin posiciones abiertas)."

        return True, f"Proceso de detención para {side.upper()} iniciado. Se cerrarán posiciones existentes."

    def actualizar_pnl_realizado(self, side: str, pnl_amount: float):
        """Acumula el PNL realizado de las posiciones cerradas."""
        with self._lock:
            operacion = self._get_operation_by_side_internal(side)
            if operacion:
                operacion.pnl_realizado_usdt += pnl_amount

    def actualizar_comisiones_totales(self, side: str, fee_amount: float):
        """Acumula las comisiones totales de las operaciones."""
        with self._lock:
            operacion = self._get_operation_by_side_internal(side)
            if operacion:
                if hasattr(operacion, 'comisiones_totales_usdt'):
                    operacion.comisiones_totales_usdt += abs(fee_amount)
    
    def revisar_y_transicionar_a_detenida(self, side: str):
        """
        Revisa si una operación en PAUSADA o DETENIENDO ya no tiene posiciones
        abiertas para resetear su estado a DETENIDA.
        """
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado not in ['PAUSADA', 'DETENIENDO']:
                return

            if not target_operation.posiciones_activas.get(side):
                log_msg = f"OPERACIÓN {side.upper()}: Última posición cerrada. Transicionando a DETENIDA y reseteando estado."
                self._memory_logger.log(log_msg, "INFO")
                target_operation.reset()