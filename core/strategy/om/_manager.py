# ./core/strategy/om/_manager.py

import datetime
import uuid
import threading
from typing import Optional, Dict, Any, Tuple

try:
    from core.strategy.entities import Operacion, LogicalPosition, CapitalFlow
    from core.logging import memory_logger
    from core.strategy.sm import api as sm_api
    from core._utils import safe_division
except ImportError:
    # Fallback for isolated testing or type checking
    class Operacion:
        def __init__(self, id: str):
            self.id = id
            self.estado = 'DETENIDA'
            self.posiciones: list = []
            self.capital_flows: list = []
            self.sub_period_returns: list = []
            self.pnl_no_realizado_usdt_vivo: float = 0.0
            self.capital_inicial_usdt = 0.0
            self.apalancamiento = 10.0 # Re-añadido al fallback
            self.tipo_cond_entrada = None
            self.valor_cond_entrada = None
            self.tiempo_inicio_ejecucion = None
            self.pnl_realizado_usdt = 0.0
            self.comisiones_totales_usdt = 0.0
            self.total_reinvertido_usdt = 0.0
            self.profit_balance_acumulado = 0.0
        def reset(self): pass
        @property
        def capital_operativo_logico_actual(self) -> float: return 0.0
        @property
        def equity_actual_vivo(self) -> float: return 0.0
        @property
        def posiciones_abiertas(self) -> list: return []
    
    class LogicalPosition: pass
    class CapitalFlow: pass

    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    sm_api = None
    def safe_division(numerator, denominator): return 0 if denominator == 0 else numerator / denominator


class OperationManager:
    """
    Gestiona el ciclo de vida y la configuración de las operaciones estratégicas
    (LONG y SHORT). Actualizado para manejar capital por posición y TWRR.
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
            original_op = self._get_operation_by_side_internal(side)
            if not original_op:
                return None
            
            import copy
            copied_op = Operacion(id=original_op.id)
            for attr, value in original_op.__dict__.items():
                if attr not in ['posiciones', 'capital_flows', 'sub_period_returns']:
                    setattr(copied_op, attr, value)
            
            copied_op.posiciones = [copy.copy(p) for p in original_op.posiciones]
            copied_op.capital_flows = [copy.copy(cf) for cf in original_op.capital_flows]
            copied_op.sub_period_returns = original_op.sub_period_returns[:] 
            return copied_op

    def create_or_update_operation(self, side: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op:
                return False, f"Lado de operación inválido '{side}'."

            estado_original = target_op.estado
            changes_log = []
            
            nuevas_posiciones_config = params.get('posiciones')
            nuevo_capital_operativo = 0.0
            if nuevas_posiciones_config is not None:
                nuevo_capital_operativo = sum(p.get('capital_asignado', 0) for p in nuevas_posiciones_config)
            
            capital_operativo_anterior = target_op.capital_operativo_logico_actual
            diferencia_capital = nuevo_capital_operativo - capital_operativo_anterior

            if estado_original in ['ACTIVA', 'EN_ESPERA', 'PAUSADA'] and abs(diferencia_capital) > 1e-9:
                equity_before_flow = target_op.equity_actual_vivo
                equity_inicial_periodo = target_op.capital_inicial_usdt
                if target_op.capital_flows:
                    last_flow = target_op.capital_flows[-1]
                    equity_inicial_periodo = last_flow.equity_before_flow + last_flow.flow_amount
                pnl_periodo = equity_before_flow - equity_inicial_periodo
                retorno_periodo = safe_division(pnl_periodo, equity_inicial_periodo)
                target_op.sub_period_returns.append(1 + retorno_periodo)
                flow_event = CapitalFlow(timestamp=datetime.datetime.now(datetime.timezone.utc), equity_before_flow=equity_before_flow, flow_amount=diferencia_capital)
                target_op.capital_flows.append(flow_event)
                changes_log.append(f"Flujo de Capital Registrado: {diferencia_capital:+.2f}$ (TWRR)")

            for key, value in params.items():
                if key not in ['posiciones'] and hasattr(target_op, key) and not callable(getattr(target_op, key)):
                    old_value = getattr(target_op, key)
                    if old_value != value:
                        setattr(target_op, key, value)
                        changes_log.append(f"'{key}': {old_value} -> {value}")
            
            # --- INICIO DE LA CORRECCIÓN FINAL ---
            # Ahora que `leverage` no está en LogicalPosition, la lógica de reconstrucción
            # debe simplemente ignorar cualquier clave de apalancamiento en los diccionarios de posición.
            if nuevas_posiciones_config is not None:
                reconstructed_positions = []
                for pos_dict in nuevas_posiciones_config:
                    # Hacemos una copia para no modificar el diccionario original
                    dict_para_objeto = pos_dict.copy()
                    
                    # Eliminamos CUALQUIER clave de apalancamiento antes de crear el objeto.
                    # El método pop con un segundo argumento (None) evita errores si la clave no existe.
                    dict_para_objeto.pop('leverage', None)
                    dict_para_objeto.pop('apalancamiento', None)
                    
                    # Creamos el objeto con el diccionario ya limpio.
                    reconstructed_positions.append(LogicalPosition(**dict_para_objeto))
                    
                target_op.posiciones = reconstructed_positions
                changes_log.append(f"'posiciones': actualizadas a {len(target_op.posiciones)} posiciones.")
            # --- FIN DE LA CORRECCIÓN FINAL ---

            if estado_original == 'DETENIDA' and params:
                target_op.capital_inicial_usdt = nuevo_capital_operativo
                changes_log.append(f"'capital_inicial_usdt' (Base ROI) fijado en: {target_op.capital_inicial_usdt:.2f}$")
                if target_op.tipo_cond_entrada == 'MARKET':
                    target_op.estado = 'ACTIVA'
                    target_op.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
                else:
                    target_op.estado = 'EN_ESPERA'
                changes_log.append(f"'estado': DETENIDA -> {target_op.estado}")

            elif estado_original == 'ACTIVA' and 'tipo_cond_entrada' in params:
                summary = sm_api.get_session_summary() if sm_api else {}
                current_price = summary.get('current_market_price', 0.0)
                cond_type = target_op.tipo_cond_entrada
                cond_value = target_op.valor_cond_entrada
                met = (cond_type == 'MARKET') or (cond_value is None) or \
                      (current_price > 0 and ((cond_type == 'PRICE_ABOVE' and current_price > cond_value) or \
                                              (cond_type == 'PRICE_BELOW' and current_price < cond_value)))
                if not met:
                    target_op.estado = 'EN_ESPERA'
                    changes_log.append(f"'estado': ACTIVA -> EN_ESPERA (nueva condición no se cumple)")

        if not changes_log:
            return True, f"No se realizaron cambios en la operación {side.upper()}."

        log_message = f"Operación {side.upper()} actualizada: " + ", ".join(changes_log)
        self._memory_logger.log(log_message, "WARN")
        return True, f"Operación {side.upper()} actualizada con éxito."

    def pausar_operacion(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado not in ['ACTIVA', 'EN_ESPERA']:
                return False, f"Solo se puede pausar una operación ACTIVA o EN_ESPERA del lado {side.upper()}."
            estado_anterior = target_op.estado
            target_op.estado = 'PAUSADA'
        msg = f"OPERACIÓN {side.upper()} PAUSADA (estado anterior: {estado_anterior}). No se abrirán nuevas posiciones."
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def reanudar_operacion(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado != 'PAUSADA':
                return False, f"Solo se puede reanudar una operación PAUSADA del lado {side.upper()}."
            target_op.estado = 'ACTIVA'
            if not target_op.tiempo_inicio_ejecucion:
                target_op.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
        msg = f"OPERACIÓN {side.upper()} REANUDADA. El sistema está ahora ACTIVO para este lado."
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def forzar_activacion_manual(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado != 'EN_ESPERA':
                return False, f"Solo se puede forzar la activación de una operación EN_ESPERA."
            target_op.estado = 'ACTIVA'
            if not target_op.tiempo_inicio_ejecucion:
                target_op.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
        msg = f"OPERACIÓN {side.upper()} FORZADA A ESTADO ACTIVO manualmente."
        self._memory_logger.log(msg, "WARN")
        return True, msg
        
    def activar_por_condicion(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado != 'EN_ESPERA':
                return False, "La operación no estaba esperando una condición."
            target_op.estado = 'ACTIVA'
            if not target_op.tiempo_inicio_ejecucion:
                 target_op.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
        msg = f"OPERACIÓN {side.upper()} ACTIVADA AUTOMÁTICAMENTE por condición de entrada."
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def detener_operacion(self, side: str, forzar_cierre_posiciones: bool) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado == 'DETENIDA':
                return False, f"La operación {side.upper()} ya está detenida o no existe."
            target_op.estado = 'DETENIENDO'
            self._memory_logger.log(f"OPERACIÓN {side.upper()} en estado DETENIENDO. Esperando cierre de posiciones.", "WARN")
            if not target_op.posiciones_abiertas:
                self.revisar_y_transicionar_a_detenida(side)
                return True, f"Operación {side.upper()} detenida y reseteada (sin posiciones abiertas)."
        return True, f"Proceso de detención para {side.upper()} iniciado."
    
    def actualizar_pnl_vivo(self, side: str, pnl_no_realizado: float):
        with self._lock:
            op = self._get_operation_by_side_internal(side)
            if op:
                op.pnl_no_realizado_usdt_vivo = pnl_no_realizado

    def actualizar_pnl_realizado(self, side: str, pnl_amount: float):
        with self._lock:
            op = self._get_operation_by_side_internal(side)
            if op:
                op.pnl_realizado_usdt += pnl_amount

    def actualizar_total_reinvertido(self, side: str, amount: float):
        with self._lock:
            op = self._get_operation_by_side_internal(side)
            if op:
                op.total_reinvertido_usdt += amount
    
    def actualizar_comisiones_totales(self, side: str, fee_amount: float):
        with self._lock:
            op = self._get_operation_by_side_internal(side)
            if op:
                op.comisiones_totales_usdt += abs(fee_amount)
    
    def revisar_y_transicionar_a_detenida(self, side: str):
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado not in ['PAUSADA', 'DETENIENDO']:
                return
            if not target_op.posiciones_abiertas:
                log_msg = f"OPERACIÓN {side.upper()}: Última posición cerrada. Transicionando a DETENIDA y reseteando estado."
                self._memory_logger.log(log_msg, "INFO")
                target_op.reset()