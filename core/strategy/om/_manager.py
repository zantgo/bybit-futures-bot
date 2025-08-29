# ./core/strategy/om/_manager.py

import datetime
import uuid
import threading
import copy
from typing import Optional, Dict, Any, Tuple
from dataclasses import asdict

try:
    from core.strategy.entities import Operacion, LogicalPosition, CapitalFlow
    from core.logging import memory_logger
    from core.strategy.sm import api as sm_api
    from core import utils
except ImportError:
    asdict = lambda x: x
    class Operacion:
        def __init__(self, id: str):
            self.id = id; self.estado = 'DETENIDA'; self.estado_razon = 'Inicial'; self.posiciones: list = []
            self.capital_flows: list = []; self.sub_period_returns: list = []
            self.capital_inicial_usdt = 0.0; self.apalancamiento = 10.0
            self.cond_entrada_above: Optional[float] = None
            self.cond_entrada_below: Optional[float] = None
            self.cond_salida_above: Optional[Dict[str, Any]] = None
            self.cond_salida_below: Optional[Dict[str, Any]] = None
            self.tiempo_espera_minutos: Optional[int] = None
            self.tiempo_inicio_espera: Optional[datetime.datetime] = None
            self.tiempo_inicio_ejecucion = None; self.pnl_realizado_usdt = 0.0
            self.comisiones_totales_usdt = 0.0; self.total_reinvertido_usdt = 0.0
            self.profit_balance_acumulado = 0.0
            self.tsl_roi_activo = False
            self.tsl_roi_peak_pct = 0.0
        def reset(self): pass
        @property
        def capital_operativo_logico_actual(self) -> float: return 0.0
        @property
        def posiciones_abiertas(self) -> list: return []
        @property
        def posiciones_pendientes(self) -> list: return []
    class LogicalPosition: pass
    class CapitalFlow: pass
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    sm_api = None
    utils = type('obj', (object,), {'safe_division': lambda n, d, default=0.0: 0 if d == 0 else n / d})()

class OperationManager:
    """
    Gestiona el ciclo de vida y la configuración de las operaciones estratégicas
    (LONG y SHORT).
    """
    def __init__(self, config: Any, utils: Any, trading_api: Any, memory_logger_instance: Any):
        self._config = config
        self._utils = utils
        self._trading_api = trading_api
        self._memory_logger = memory_logger_instance
        self._initialized: bool = False
        
        self.long_operation: Optional[Operacion] = None
        self.short_operation: Optional[Operacion] = None
        
        self._lock = threading.RLock()
        self.initialize()

    def initialize(self):
        with self._lock:
            if not self.long_operation: self.long_operation = Operacion(id=f"op_long_{uuid.uuid4()}")
            if not self.short_operation: self.short_operation = Operacion(id=f"op_short_{uuid.uuid4()}")
            self._initialized = True
        self._memory_logger.log("OperationManager inicializado.", level="INFO")

    def is_initialized(self) -> bool:
        return self._initialized

    def _get_operation_by_side_internal(self, side: str) -> Optional[Operacion]:
        if side == 'long': return self.long_operation
        elif side == 'short': return self.short_operation
        self._memory_logger.log(f"WARN [OM]: Lado inválido '{side}' en _get_operation_by_side_internal.", "WARN")
        return None

    def get_operation_by_side(self, side: str) -> Optional[Operacion]:
        with self._lock:
            original_op = self._get_operation_by_side_internal(side)
            if not original_op: return None
            return copy.deepcopy(original_op)

    def create_or_update_operation(self, side: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op: return False, f"Lado de operación inválido '{side}'."

            estado_original = target_op.estado
            changed_keys = set()
            nuevas_posiciones = params.get('posiciones')
            nuevo_capital_operativo = 0.0
            
            if nuevas_posiciones is not None:
                if isinstance(nuevas_posiciones, list) and all(isinstance(p, LogicalPosition) for p in nuevas_posiciones):
                    nuevo_capital_operativo = sum(p.capital_asignado for p in nuevas_posiciones)
                else:
                    nuevas_posiciones = None 
            
            capital_operativo_anterior = target_op.capital_operativo_logico_actual
            diferencia_capital = nuevo_capital_operativo - capital_operativo_anterior

            if estado_original in ['ACTIVA', 'EN_ESPERA', 'PAUSADA'] and nuevas_posiciones is not None and abs(diferencia_capital) > 1e-9:
                current_price = sm_api.get_session_summary().get('current_market_price', 0.0) if sm_api else 0.0
                live_performance = target_op.get_live_performance(current_price, self._utils)
                equity_before_flow = live_performance.get("equity_actual_vivo", target_op.equity_total_usdt)
                equity_inicial_periodo = target_op.capital_inicial_usdt
                if target_op.capital_flows:
                    last_flow = target_op.capital_flows[-1]
                    equity_inicial_periodo = last_flow.equity_before_flow + last_flow.flow_amount
                pnl_periodo = (target_op.equity_total_usdt + live_performance.get("pnl_no_realizado", 0.0)) - equity_inicial_periodo
                retorno_periodo = self._utils.safe_division(pnl_periodo, equity_inicial_periodo)
                target_op.sub_period_returns.append(1 + retorno_periodo)
                flow_event = CapitalFlow(timestamp=datetime.datetime.now(datetime.timezone.utc), equity_before_flow=equity_before_flow, flow_amount=diferencia_capital)
                target_op.capital_flows.append(flow_event)
                changed_keys.add('capital_flows')

            for key, value in params.items():
                if key not in ['posiciones'] and hasattr(target_op, key) and not callable(getattr(target_op, key)):
                    old_value = getattr(target_op, key)
                    if old_value != value:
                        setattr(target_op, key, value)
                        changed_keys.add(key)
            
            if nuevas_posiciones is not None:
                target_op.posiciones = copy.deepcopy(nuevas_posiciones)
                changed_keys.add('posiciones')

            if changed_keys:
                if estado_original == 'DETENIDA':
                    target_op.pnl_realizado_usdt = 0.0
                    target_op.comisiones_totales_usdt = 0.0
                    target_op.reinvestable_profit_balance = 0.0
                    target_op.capital_inicial_usdt = nuevo_capital_operativo if nuevas_posiciones is not None else target_op.capital_operativo_logico_actual
                    target_op.tiempo_acumulado_activo_seg = 0.0
                    target_op.tiempo_ultimo_inicio_activo = None
                
                if estado_original == 'DETENIENDO':
                    return True, f"Operación {side.upper()} actualizando en estado DETENIENDO."

                # --- INICIO DE LA LÓGICA DE TRANSICIÓN DE ESTADO CORREGIDA Y ROBUSTA ---
                estado_nuevo = target_op.estado

                # Determina si la configuración actual es para una entrada a mercado o condicional.
                is_market_entry = all(v is None for v in [
                    target_op.cond_entrada_above,
                    target_op.cond_entrada_below,
                    target_op.tiempo_espera_minutos
                ])
                
                # Caso 1: La operación está DETENIDA y se está configurando por primera vez.
                if estado_original == 'DETENIDA':
                    if is_market_entry:
                        estado_nuevo = 'ACTIVA'
                        target_op.estado_razon = "Operación iniciada a condición de mercado."
                        now = datetime.datetime.now(datetime.timezone.utc)
                        target_op.tiempo_ultimo_inicio_activo = now
                        if not target_op.tiempo_inicio_ejecucion:
                            target_op.tiempo_inicio_ejecucion = now
                    else: # Si tiene cualquier condición de entrada, pasa a EN_ESPERA.
                        estado_nuevo = 'EN_ESPERA'
                        target_op.estado_razon = "Operación en espera de condición de entrada."
                        if target_op.tiempo_espera_minutos is not None and target_op.tiempo_inicio_espera is None:
                            target_op.tiempo_inicio_espera = datetime.datetime.now(datetime.timezone.utc)
                
                # Caso 2: La operación está PAUSADA y el usuario AÑADE una nueva condición de entrada.
                # Esto es una acción explícita para "re-armar" la operación.
                elif estado_original == 'PAUSADA' and any(key in changed_keys for key in ['cond_entrada_above', 'cond_entrada_below', 'tiempo_espera_minutos']):
                    estado_nuevo = 'EN_ESPERA'
                    target_op.estado_razon = "Operación re-armada, en espera de nueva condición de entrada."
                    if target_op.tiempo_espera_minutos is not None and target_op.tiempo_inicio_espera is None:
                        target_op.tiempo_inicio_espera = datetime.datetime.now(datetime.timezone.utc)

                # Si no se cumple ninguna de estas condiciones explícitas de transición, el estado no se cambia.
                # Esto previene la "resurrección" automática de un estado PAUSADO.
                
                # --- FIN DE LA LÓGICA DE TRANSICIÓN DE ESTADO CORREGIDA Y ROBUSTA ---

                if estado_nuevo != estado_original:
                    self._memory_logger.log(
                        f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> '{estado_nuevo}'. Razón: {target_op.estado_razon}",
                        "WARN"
                    )
                    target_op.estado = estado_nuevo

        return True, f"Operación {side.upper()} actualizada con éxito."

    def pausar_operacion(self, side: str, reason: Optional[str] = None) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado not in ['ACTIVA', 'EN_ESPERA']:
                return False, f"Solo se puede pausar una operación ACTIVA o EN_ESPERA del lado {side.upper()}."
            
            estado_original = target_op.estado
            if target_op.estado == 'ACTIVA' and target_op.tiempo_ultimo_inicio_activo:
                elapsed_seconds = (datetime.datetime.now(datetime.timezone.utc) - target_op.tiempo_ultimo_inicio_activo).total_seconds()
                target_op.tiempo_acumulado_activo_seg += elapsed_seconds
            
            target_op.tiempo_ultimo_inicio_activo = None
            
            target_op.cond_entrada_above = None
            target_op.cond_entrada_below = None
            
            target_op.tiempo_espera_minutos = None
            target_op.tiempo_inicio_espera = None

            target_op.estado = 'PAUSADA'
            target_op.estado_razon = reason if reason else "Pausada manualmente por el usuario."
        
        msg = f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> 'PAUSADA'. Razón: {target_op.estado_razon}"
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def reanudar_operacion(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado != 'PAUSADA':
                return False, f"Solo se puede reanudar una operación PAUSADA del lado {side.upper()}."

            estado_original = target_op.estado
            target_op.estado = 'ACTIVA'
            target_op.estado_razon = "Reanudada manualmente por el usuario."
            
            now = datetime.datetime.now(datetime.timezone.utc)
            target_op.tiempo_ultimo_inicio_activo = now
            if not target_op.tiempo_inicio_ejecucion:
                target_op.tiempo_inicio_ejecucion = now
            
            target_op.tsl_roi_activo = False
            target_op.tsl_roi_peak_pct = 0.0
                
        msg = f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> 'ACTIVA'. Razón: {target_op.estado_razon}"
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def forzar_activacion_manual(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado not in ['EN_ESPERA', 'PAUSADA']:
                return False, f"Solo se puede forzar la activación desde EN_ESPERA o PAUSADA."
            
            estado_original = target_op.estado
            target_op.estado = 'ACTIVA'
            target_op.estado_razon = "Activación forzada manualmente."
            
            now = datetime.datetime.now(datetime.timezone.utc)
            target_op.tiempo_ultimo_inicio_activo = now
            if not target_op.tiempo_inicio_ejecucion:
                target_op.tiempo_inicio_ejecucion = now
            
        msg = f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> 'ACTIVA'. Razón: {target_op.estado_razon}"
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def activar_por_condicion(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado not in ['EN_ESPERA', 'PAUSADA']:
                return False, "La operación no estaba esperando una condición."

            estado_original = target_op.estado
            
            reason = "Condición de entrada alcanzada."
            if target_op.tiempo_espera_minutos is not None:
                 reason = f"Activada por tiempo ({target_op.tiempo_espera_minutos} min)."
            elif target_op.cond_entrada_above is not None:
                 reason = f"Activada por precio > {target_op.cond_entrada_above:.4f}."
            elif target_op.cond_entrada_below is not None:
                 reason = f"Activada por precio < {target_op.cond_entrada_below:.4f}."
            
            target_op.estado = 'ACTIVA'
            target_op.estado_razon = reason
            
            now = datetime.datetime.now(datetime.timezone.utc)
            target_op.tiempo_ultimo_inicio_activo = now
            if not target_op.tiempo_inicio_ejecucion:
                target_op.tiempo_inicio_ejecucion = now
            
        msg = f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> 'ACTIVA'. Razón: {target_op.estado_razon}"
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def detener_operacion(self, side: str, forzar_cierre_posiciones: bool, reason: Optional[str] = None) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado == 'DETENIDA':
                return False, f"La operación {side.upper()} ya está detenida o no existe."
            
            estado_original = target_op.estado
            if target_op.estado == 'ACTIVA' and target_op.tiempo_ultimo_inicio_activo:
                elapsed_seconds = (datetime.datetime.now(datetime.timezone.utc) - target_op.tiempo_ultimo_inicio_activo).total_seconds()
                target_op.tiempo_acumulado_activo_seg += elapsed_seconds
                target_op.tiempo_ultimo_inicio_activo = None

            target_op.estado = 'DETENIENDO'
            target_op.estado_razon = reason if reason else "Detenida manualmente por el usuario."
            
            log_msg = f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> 'DETENIENDO'. Razón: {target_op.estado_razon}"
            self._memory_logger.log(log_msg, "WARN")

            if not target_op.posiciones_abiertas:
                self.revisar_y_transicionar_a_detenida(side)
                return True, f"Operación {side.upper()} detenida y reseteada (sin posiciones abiertas)."
        return True, f"Proceso de detención para {side.upper()} iniciado."

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
            
            if not target_op or target_op.estado != 'DETENIENDO':
                return
            
            if not target_op.posiciones_abiertas:
                estado_original = target_op.estado
                log_msg = (
                    f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> 'DETENIDA'. Razón final: '{target_op.estado_razon}'"
                )
                self._memory_logger.log(log_msg, "INFO")
                target_op.estado = 'DETENIDA'

    def actualizar_reinvestable_profit(self, side: str, amount: float):
        with self._lock:
            op = self._get_operation_by_side_internal(side)
            if op:
                op.reinvestable_profit_balance += amount

    def distribuir_reinvestable_profits(self, side: str):
        with self._lock:
            op = self._get_operation_by_side_internal(side)
            if not op or op.reinvestable_profit_balance <= 1e-9:
                return

            pending_positions = op.posiciones_pendientes
            if not pending_positions:
                self._memory_logger.log(
                    f"REINVERSIÓN OMITIDA ({side.upper()}): Sin posiciones pendientes.",
                    "WARN"
                )
                return

            total_to_distribute = op.reinvestable_profit_balance
            amount_per_position = total_to_distribute / len(pending_positions)

            for pos in op.posiciones:
                if pos.estado == 'PENDIENTE':
                    pos.capital_asignado += amount_per_position
            
            op.reinvestable_profit_balance = 0.0
            self._memory_logger.log(
                f"REINVERSIÓN EJECUTADA ({side.upper()}): ${total_to_distribute:.4f} distribuidos.",
                "INFO"
            )

    def handle_liquidation_event(self, side: str, reason: str):
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            
            if not target_op or target_op.estado in ['DETENIDA', 'DETENIENDO']:
                return

            estado_original = target_op.estado
            self._memory_logger.log(
                f"OM: Procesando evento de liquidación para {side.upper()}.", "WARN"
            )

            target_op.estado = 'DETENIENDO'
            target_op.estado_razon = reason
            total_loss = target_op.capital_operativo_logico_actual
            target_op.pnl_realizado_usdt -= total_loss
            self._memory_logger.log(
                f"OM: Pérdida por liquidación de ${total_loss:.4f} registrada.", "WARN"
            )
            
            target_op.posiciones.clear()
            self._memory_logger.log(
                f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> 'DETENIENDO'. Razón: {target_op.estado_razon}",
                "WARN"
            )
            self.revisar_y_transicionar_a_detenida(side)