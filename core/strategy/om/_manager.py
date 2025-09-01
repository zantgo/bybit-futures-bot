# Contenido completo y corregido para: core/strategy/om/_manager.py

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
    # ... (fallback de importaciones sin cambios) ...
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
    # ... (funciones __init__ hasta activar_por_condicion sin cambios) ...
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
                pos_map_actual = {p.id: p for p in target_op.posiciones}
                ids_nuevas_posiciones = {p.id for p in nuevas_posiciones}
    
                target_op.posiciones = [p for p in target_op.posiciones if p.id in ids_nuevas_posiciones]
    
                for pos_actualizada in nuevas_posiciones:
                    if pos_actualizada.id in pos_map_actual:
                        pos_existente = pos_map_actual[pos_actualizada.id]
                        for key, value in pos_actualizada.__dict__.items():
                            if hasattr(pos_existente, key):
                                setattr(pos_existente, key, value)
                    else:
                        target_op.posiciones.append(copy.deepcopy(pos_actualizada))
                
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
    
                estado_nuevo = target_op.estado
                
                is_market_entry = all(v is None for v in [
                    target_op.cond_entrada_above,
                    target_op.cond_entrada_below,
                    target_op.tiempo_espera_minutos
                ])
                
                if is_market_entry and estado_original != 'PAUSADA':
                    if estado_original != 'ACTIVA':
                        estado_nuevo = 'ACTIVA'
                        target_op.estado_razon = "Operación iniciada/actualizada a condición de mercado."
                        now = datetime.datetime.now(datetime.timezone.utc)
                        target_op.tiempo_ultimo_inicio_activo = now
                        if not target_op.tiempo_inicio_ejecucion:
                            target_op.tiempo_inicio_ejecucion = now
                elif any(key in changed_keys for key in ['cond_entrada_above', 'cond_entrada_below', 'tiempo_espera_minutos']) and estado_original in ['DETENIDA', 'PAUSADA']:
                    estado_nuevo = 'EN_ESPERA'
                    target_op.estado_razon = "Operación en espera de nueva condición de entrada."
                    if target_op.tiempo_espera_minutos is not None and target_op.tiempo_inicio_espera is None:
                        target_op.tiempo_inicio_espera = datetime.datetime.now(datetime.timezone.utc)
    
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

        return True, f"Proceso de detención para {side.upper()} iniciado. Esperando cierre de posiciones."

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

    def revisar_y_transicionar_a_detenida(self, side: str):
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            
            if not target_op or target_op.estado != 'DETENIENDO':
                return
            
            # La condición sigue siendo la misma: la transición final ocurre
            # cuando ya no hay posiciones abiertas.
            if not target_op.posiciones_abiertas:
                estado_original = target_op.estado
                log_msg = (
                    f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> 'DETENIDA'. Razón final: '{target_op.estado_razon}'"
                )
                self._memory_logger.log(log_msg, "INFO")
                
                # --- INICIO DE LA NUEVA LÓGICA: RESETEAR EN LUGAR DE ELIMINAR ---
                #
                # En lugar de eliminar las posiciones pendientes, ahora iteramos sobre todas
                # las posiciones existentes y las revertimos a su estado PENDIENTE original.
                #
                for pos in target_op.posiciones:
                    pos.estado = 'PENDIENTE'
                    pos.entry_timestamp = None
                    pos.entry_price = None
                    pos.margin_usdt = 0.0
                    pos.size_contracts = None
                    pos.stop_loss_price = None
                    pos.est_liq_price = None
                    pos.ts_is_active = False
                    pos.ts_peak_price = None
                    pos.ts_stop_price = None
                    pos.api_order_id = None
                    pos.api_avg_fill_price = None
                    pos.api_filled_qty = None
                
                # Finalmente, cambiamos el estado. El resto del snapshot (PNL, etc.) se preserva.
                target_op.estado = 'DETENIDA'

    def handle_liquidation_event(self, side: str, reason: Optional[str] = None):
        """
        Gestiona la PARTE CONTABLE de un evento de liquidación o cierre forzoso.
        En ambos casos, la pérdida registrada es el capital de las posiciones
        que estaban abiertas en ese momento.
        """
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            
            if not target_op or target_op.estado == 'DETENIDA':
                return

            estado_original = target_op.estado
            
            # --- INICIO DE LA LÓGICA CONTABLE UNIFICADA Y CORREGIDA ---
            
            # No es necesario diferenciar el cálculo, solo el log.
            # En ambos casos (liquidación o cierre forzoso), la pérdida es el capital en riesgo.
            if target_op.posiciones_abiertas:
                capital_at_risk = sum(p.capital_asignado for p in target_op.posiciones_abiertas)
                target_op.pnl_realizado_usdt -= capital_at_risk
                
                # El mensaje de log sí diferencia la causa
                log_event_type = "liquidación" if reason and "HEARTBEAT" in reason.upper() else "cierre forzoso"
                self._memory_logger.log(f"OM: Pérdida de ${capital_at_risk:.4f} (capital en uso) registrada por {log_event_type}.", "WARN")

            # Marcamos las posiciones abiertas como 'CERRADA' para la transición.
            for p in target_op.posiciones:
                if p.estado == 'ABIERTA':
                    p.estado = 'CERRADA'
            
            # --- FIN DE LA LÓGICA CONTABLE ---

            if target_op.estado != 'DETENIENDO':
                 target_op.estado = 'DETENIENDO'
            
            if reason is not None:
                target_op.estado_razon = reason
            
            self._memory_logger.log(
                f"CAMBIO DE ESTADO ({side.upper()}): '{estado_original}' -> 'DETENIENDO'. Razón: {target_op.estado_razon}",
                "WARN"
            )
            
            # Llama a la función que completará la transición y el reseteo de posiciones.
            self.revisar_y_transicionar_a_detenida(side)

    # --- INICIO DE LA NUEVA FUNCIÓN ---
    def finalize_forced_closure(self, side: str, reason: Optional[str] = None):
        """
        Gestiona la finalización de un cierre forzoso controlado (NO liquidación).
        Registra la pérdida del capital en riesgo y luego resetea las posiciones a PENDIENTE.
        """
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op:
                return
            
            self._memory_logger.log(f"OM: Finalizando cierre forzoso para {side.upper()}.", "INFO")

            if target_op.posiciones_abiertas:
                capital_at_risk = sum(p.capital_asignado for p in target_op.posiciones_abiertas)
                target_op.pnl_realizado_usdt -= capital_at_risk
                self._memory_logger.log(f"OM: Pérdida de ${capital_at_risk:.4f} (capital en uso) registrada por cierre forzoso.", "WARN")

            # Marcamos las posiciones abiertas como 'CERRADA' para la transición.
            for p in target_op.posiciones:
                if p.estado == 'ABIERTA':
                    p.estado = 'CERRADA'
            
            # Aseguramos que el estado y la razón estén correctos
            if target_op.estado != 'DETENIENDO':
                target_op.estado = 'DETENIENDO'
            if reason is not None:
                target_op.estado_razon = reason
            
            # Llamamos a la función que completará la transición y el reseteo de posiciones a PENDIENTE.
            self.revisar_y_transicionar_a_detenida(side)
    # --- FIN DE LA NUEVA FUNCIÓN ---