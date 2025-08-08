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
    asdict = lambda x: x
    class Operacion:
        def __init__(self, id: str):
            self.id = id; self.estado = 'DETENIDA'; self.posiciones: list = []
            self.capital_flows: list = []; self.sub_period_returns: list = []
            self.capital_inicial_usdt = 0.0; self.apalancamiento = 10.0
            self.tipo_cond_entrada = None; self.valor_cond_entrada = None
            self.tiempo_inicio_ejecucion = None; self.pnl_realizado_usdt = 0.0
            self.comisiones_totales_usdt = 0.0; self.total_reinvertido_usdt = 0.0
            self.profit_balance_acumulado = 0.0
        def reset(self): pass
        @property
        def capital_operativo_logico_actual(self) -> float: return 0.0
        @property
        def posiciones_abiertas(self) -> list: return []
    class LogicalPosition: pass
    class CapitalFlow: pass
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    sm_api = None
    utils = type('obj', (object,), {'safe_division': lambda n, d: 0 if d == 0 else n / d})()

class OperationManager:
    """
    Gestiona el ciclo de vida y la configuración de las operaciones estratégicas
    (LONG y SHORT). Actualizado para manejar capital por posición y TWRR.
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
        self._memory_logger.log("OperationManager inicializado con operaciones LONG y SHORT en estado DETENIDA.", level="INFO")

    def is_initialized(self) -> bool:
        return self._initialized

    def _get_operation_by_side_internal(self, side: str) -> Optional[Operacion]:
        if side == 'long': return self.long_operation
        elif side == 'short': return self.short_operation
        self._memory_logger.log(f"WARN [OM]: Intento de acceso a lado inválido '{side}' en _get_operation_by_side_internal.", "WARN")
        return None

    def get_operation_by_side(self, side: str) -> Optional[Operacion]:
        with self._lock:
            original_op = self._get_operation_by_side_internal(side)
            if not original_op: return None
            
            copied_op = Operacion(id=original_op.id)
            for attr, value in original_op.__dict__.items():
                if attr not in ['posiciones', 'capital_flows', 'sub_period_returns']:
                    setattr(copied_op, attr, value)
            
            # Realizamos una copia profunda de las posiciones para evitar mutaciones accidentales
            copied_op.posiciones = copy.deepcopy(original_op.posiciones)
            copied_op.capital_flows = copy.deepcopy(original_op.capital_flows)
            copied_op.sub_period_returns = original_op.sub_period_returns[:] 
            return copied_op

    def create_or_update_operation(self, side: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op: return False, f"Lado de operación inválido '{side}'."

            estado_original = target_op.estado
            changes_log = []
            
            # --- INICIO DE LA CORRECCIÓN CLAVE ---
            # El PM nos enviará una lista de objetos `LogicalPosition`.
            nuevas_posiciones = params.get('posiciones')

            nuevo_capital_operativo = 0.0
            if nuevas_posiciones is not None:
                # Calculamos el capital directamente desde los objetos
                nuevo_capital_operativo = sum(p.capital_asignado for p in nuevas_posiciones)
            # --- FIN DE LA CORRECCIÓN CLAVE ---
            
            capital_operativo_anterior = target_op.capital_operativo_logico_actual
            diferencia_capital = nuevo_capital_operativo - capital_operativo_anterior

            if estado_original in ['ACTIVA', 'EN_ESPERA', 'PAUSADA'] and abs(diferencia_capital) > 1e-9:
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
                changes_log.append(f"Flujo de Capital Registrado: {diferencia_capital:+.2f}$ (TWRR)")

            for key, value in params.items():
                if key not in ['posiciones'] and hasattr(target_op, key) and not callable(getattr(target_op, key)):
                    old_value = getattr(target_op, key)
                    if old_value != value:
                        setattr(target_op, key, value)
                        changes_log.append(f"'{key}': {old_value} -> {value}")
            
            # --- INICIO DE LA CORRECCIÓN CLAVE ---
            if nuevas_posiciones is not None:
                # Asignamos directamente la lista de objetos, usando deepcopy para seguridad.
                target_op.posiciones = copy.deepcopy(nuevas_posiciones)
                changes_log.append(f"'posiciones': actualizadas a {len(target_op.posiciones)} posiciones.")
            # --- FIN DE LA CORRECCIÓN CLAVE ---

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

        if changes_log:
            symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
            new_leverage = target_op.apalancamiento
            
            if self._trading_api and symbol and new_leverage:
                target_account_name = None
                if side == 'long':
                    target_account_name = self._config.BOT_CONFIG["ACCOUNTS"]["LONGS"]
                elif side == 'short':
                    target_account_name = self._config.BOT_CONFIG["ACCOUNTS"]["SHORTS"]

                if target_account_name:
                    self._memory_logger.log(f"OM: Actualizando apalancamiento a {new_leverage}x para '{symbol}' en la cuenta '{target_account_name}'...", "INFO")
                    self._trading_api.set_leverage(
                        symbol=symbol, 
                        buy_leverage=str(new_leverage), 
                        sell_leverage=str(new_leverage),
                        account_name=target_account_name
                    )
                else:
                    self._memory_logger.log(f"OM WARN: No se encontró una cuenta para el lado '{side}' para establecer el apalancamiento.", "WARN")

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