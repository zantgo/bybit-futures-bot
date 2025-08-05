# ./core/strategy/om/_manager.py

import datetime
import uuid
import threading
from typing import Optional, Dict, Any, Tuple

try:
    from ._entities import Operacion, LogicalBalances # Se importa LogicalBalances desde aquí
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
    # ... (El resto del código de esta clase NO cambia) ...
    """
    Gestiona el estado y la lógica de negocio de las operaciones estratégicas
    independientes para LONG y SHORT.
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
        return self._initialized

    def _get_operation_by_side_internal(self, side: str) -> Optional[Operacion]:
        if side == 'long':
            return self.long_operation
        elif side == 'short':
            return self.short_operation
        self._memory_logger.log(f"WARN [OM]: Intento de acceso a lado inválido '{side}' en _get_operation_by_side_internal.", "WARN")
        return None

    def get_operation_by_side(self, side: str) -> Optional[Operacion]:
        with self._lock:
            operation = self._get_operation_by_side_internal(side)
            if operation:
                import copy
                return copy.deepcopy(operation)
        return None

    def create_or_update_operation(self, side: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        from core.strategy.sm import api as sm_api
        
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
            
            operational_margin_nuevo = params.get('operational_margin')
            if operational_margin_nuevo is not None:
                if not hasattr(target_operation, 'balances') or not target_operation.balances:
                    target_operation.balances = LogicalBalances()
                
                if estado_original == 'DETENIDA':
                    target_operation.balances.operational_margin = float(operational_margin_nuevo)
                    target_operation.capital_inicial_usdt = float(operational_margin_nuevo)
                    changes_log.append(f"'capital_logico': {target_operation.capital_inicial_usdt:.2f}$ (asignado)")
                elif estado_original in ['ACTIVA', 'EN_ESPERA', 'PAUSADA']:
                    diferencia_capital = float(operational_margin_nuevo) - capital_logico_anterior
                    if abs(diferencia_capital) > 1e-9:
                        target_operation.balances.operational_margin = float(operational_margin_nuevo)
                        target_operation.capital_inicial_usdt += diferencia_capital
                        changes_log.append(f"'capital_logico': {capital_logico_anterior:.2f}$ -> {target_operation.balances.operational_margin:.2f}$")
                        self._memory_logger.log(f"CAPITAL LÓGICO AJUSTADO ({side.upper()}): {diferencia_capital:+.2f}$. Nuevo capital base ROI: {target_operation.capital_inicial_usdt:.2f}$", "WARN")

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
        from core.strategy.pm import api as pm_api
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado == 'DETENIDA':
                return False, f"La operación {side.upper()} ya está detenida o no existe."

            target_operation.estado = 'DETENIENDO'
            self._memory_logger.log(f"OPERACIÓN {side.upper()} en estado DETENIENDO. Esperando cierre de posiciones por PM.", "WARN")

            if not target_operation.posiciones_activas.get(side):
                self.revisar_y_transicionar_a_detenida(side)
                return True, f"Operación {side.upper()} detenida y reseteada (sin posiciones abiertas)."

        return True, f"Proceso de detención para {side.upper()} iniciado. Se cerrarán posiciones existentes."

    def actualizar_pnl_realizado(self, side: str, pnl_amount: float):
        with self._lock:
            operacion = self._get_operation_by_side_internal(side)
            if operacion:
                operacion.pnl_realizado_usdt += pnl_amount

    def actualizar_comisiones_totales(self, side: str, fee_amount: float):
        with self._lock:
            operacion = self._get_operation_by_side_internal(side)
            if operacion:
                if hasattr(operacion, 'comisiones_totales_usdt'):
                    operacion.comisiones_totales_usdt += abs(fee_amount)
    
    def revisar_y_transicionar_a_detenida(self, side: str):
        with self._lock:
            target_operation = self._get_operation_by_side_internal(side)
            if not target_operation or target_operation.estado not in ['PAUSADA', 'DETENIENDO']:
                return

            if not target_operation.posiciones_activas.get(side):
                log_msg = f"OPERACIÓN {side.upper()}: Última posición cerrada. Transicionando a DETENIDA y reseteando estado."
                self._memory_logger.log(log_msg, "INFO")
                target_operation.reset()