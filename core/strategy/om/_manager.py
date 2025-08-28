# core/strategy/om/_manager.py

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
            self.tipo_cond_entrada = None; self.valor_cond_entrada = None
            self.tiempo_inicio_ejecucion = None; self.pnl_realizado_usdt = 0.0
            self.comisiones_totales_usdt = 0.0; self.total_reinvertido_usdt = 0.0
            self.profit_balance_acumulado = 0.0
            self.tsl_roi_activo = False # Añadido para fallback
            self.tsl_roi_peak_pct = 0.0 # Añadido para fallback
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
            
            return copy.deepcopy(original_op)
# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función 1 de 3) ---
# ==============================================================================

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
                    self._memory_logger.log(f"ERROR [OM]: Se intentó actualizar la operación {side} con un formato de posiciones inválido.", "ERROR")
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

            # --- INICIO DE LA MODIFICACIÓN: Lógica de Transición de Estado Refactorizada ---
            if changed_keys:
                if estado_original == 'DETENIDA':
                    target_op.pnl_realizado_usdt = 0.0
                    target_op.comisiones_totales_usdt = 0.0
                    target_op.reinvestable_profit_balance = 0.0
                    target_op.capital_inicial_usdt = nuevo_capital_operativo if nuevas_posiciones is not None else target_op.capital_operativo_logico_actual
                    target_op.tiempo_acumulado_activo_seg = 0.0 # Resetear acumulador
                    target_op.tiempo_ultimo_inicio_activo = None
                
                # Transición a ACTIVA
                if target_op.tipo_cond_entrada == 'MARKET':
                    if target_op.estado != 'ACTIVA':
                        target_op.estado = 'ACTIVA'
                        target_op.estado_razon = "Operación iniciada/actualizada a condición de mercado."
                        now = datetime.datetime.now(datetime.timezone.utc)
                        target_op.tiempo_ultimo_inicio_activo = now
                        target_op.tiempo_inicio_ejecucion = now
                # Transición a EN_ESPERA (desde DETENIDA o PAUSADA)
                elif 'tipo_cond_entrada' in changed_keys and estado_original in ['DETENIDA', 'PAUSADA']:
                    target_op.estado = 'EN_ESPERA'
                    target_op.estado_razon = "Operación en espera de nueva condición de entrada."
                    if target_op.tipo_cond_entrada == 'TIME_DELAY':
                        target_op.tiempo_inicio_espera = datetime.datetime.now(datetime.timezone.utc)
            # --- FIN DE LA MODIFICACIÓN ---

            if 'apalancamiento' in changed_keys:
                symbol = self._config.BOT_CONFIG["TICKER"]["SYMBOL"]
                # ... (resto de la lógica de apalancamiento sin cambios)

        return True, f"Operación {side.upper()} actualizada con éxito."
        
# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================

# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función 2 de 3) ---
# ==============================================================================

    def pausar_operacion(self, side: str, reason: Optional[str] = None) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado not in ['ACTIVA', 'EN_ESPERA']:
                return False, f"Solo se puede pausar una operación ACTIVA o EN_ESPERA del lado {side.upper()}."
            
            # --- INICIO DE LA MODIFICACIÓN: Lógica de Pausa Mejorada ---
            if target_op.estado == 'ACTIVA' and target_op.tiempo_ultimo_inicio_activo:
                elapsed_seconds = (datetime.datetime.now(datetime.timezone.utc) - target_op.tiempo_ultimo_inicio_activo).total_seconds()
                target_op.tiempo_acumulado_activo_seg += elapsed_seconds
            
            # Detener y resetear el cronómetro de duración y las condiciones de entrada
            target_op.tiempo_ultimo_inicio_activo = None
            target_op.tiempo_inicio_ejecucion = None # Limpiamos también el antiguo por consistencia
            target_op.tipo_cond_entrada = None
            target_op.valor_cond_entrada = None
            target_op.tiempo_espera_minutos = None
            target_op.tiempo_inicio_espera = None
            # --- FIN DE LA MODIFICACIÓN ---

            target_op.estado = 'PAUSADA'
            target_op.estado_razon = reason if reason else "Pausada manualmente por el usuario."
        
        msg = f"OPERACIÓN {side.upper()} PAUSADA (Razón: {target_op.estado_razon}). No se abrirán nuevas posiciones."
        self._memory_logger.log(msg, "WARN")
        return True, msg

# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función 3 de 3) ---
# ==============================================================================

    def reanudar_operacion(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado != 'PAUSADA':
                return False, f"Solo se puede reanudar una operación PAUSADA del lado {side.upper()}."

            # --- INICIO DE LA MODIFICACIÓN: Lógica de Reanudación Simplificada ---
            # Reanudar siempre significa volver a estar ACTIVO.
            # La lógica para entrar en EN_ESPERA ahora se maneja en create_or_update_operation.
            target_op.estado = 'ACTIVA'
            target_op.estado_razon = "Reanudada manualmente por el usuario."
            
            # Reiniciar y empezar el cronómetro de duración desde cero.
            target_op.tiempo_acumulado_activo_seg = 0.0
            now = datetime.datetime.now(datetime.timezone.utc)
            target_op.tiempo_ultimo_inicio_activo = now
            target_op.tiempo_inicio_ejecucion = now
            # --- FIN DE LA MODIFICACIÓN ---
            
            target_op.tsl_roi_activo = False
            target_op.tsl_roi_peak_pct = 0.0
                
        msg = f"OPERACIÓN {side.upper()} REANUDADA. Nuevo estado: {target_op.estado}."
        self._memory_logger.log(msg, "WARN")
        return True, msg

# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================

    def forzar_activacion_manual(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado not in ['EN_ESPERA', 'PAUSADA']:
                return False, f"Solo se puede forzar la activación desde EN_ESPERA o PAUSADA."
            
            target_op.estado = 'ACTIVA'
            target_op.estado_razon = "Activación forzada manualmente."
            
            now = datetime.datetime.now(datetime.timezone.utc)
            target_op.tiempo_ultimo_inicio_activo = now
            target_op.tiempo_inicio_ejecucion = now # <-- LÍNEA AÑADIDA
            
        msg = f"OPERACIÓN {side.upper()} FORZADA A ESTADO ACTIVO manualmente."
        self._memory_logger.log(msg, "WARN")
        return True, msg
# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================

# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función 4 de 5) ---
# ==============================================================================


# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función 3 de 4) ---
# ==============================================================================
    def activar_por_condicion(self, side: str) -> Tuple[bool, str]:
        with self._lock:
            target_op = self._get_operation_by_side_internal(side)
            if not target_op or target_op.estado not in ['EN_ESPERA', 'PAUSADA']:
                return False, "La operación no estaba esperando una condición."

            cond_type = target_op.tipo_cond_entrada
            if cond_type == 'TIME_DELAY':
                reason = f"Activada por tiempo ({target_op.tiempo_espera_minutos} min)."
            elif cond_type == 'PRICE_ABOVE':
                reason = f"Activada por precio > {target_op.valor_cond_entrada:.4f}."
            elif cond_type == 'PRICE_BELOW':
                reason = f"Activada por precio < {target_op.valor_cond_entrada:.4f}."
            else:
                reason = "Condición de entrada alcanzada."
            
            target_op.estado = 'ACTIVA'
            target_op.estado_razon = reason
            
            now = datetime.datetime.now(datetime.timezone.utc)
            target_op.tiempo_ultimo_inicio_activo = now
            target_op.tiempo_inicio_ejecucion = now # <-- LÍNEA AÑADIDA
            
        msg = f"OPERACIÓN {side.upper()} ACTIVADA AUTOMÁTICAMENTE. Razón: {target_op.estado_razon}"
        self._memory_logger.log(msg, "WARN")
        return True, msg

# Verifica que esta función en core/strategy/om/_manager.py se vea así

def detener_operacion(self, side: str, forzar_cierre_posiciones: bool, reason: Optional[str] = None) -> Tuple[bool, str]:
    with self._lock:
        target_op = self._get_operation_by_side_internal(side)
        if not target_op or target_op.estado == 'DETENIDA':
            return False, f"La operación {side.upper()} ya está detenida o no existe."
        
        if target_op.estado == 'ACTIVA' and target_op.tiempo_ultimo_inicio_activo:
            elapsed_seconds = (datetime.datetime.now(datetime.timezone.utc) - target_op.tiempo_ultimo_inicio_activo).total_seconds()
            target_op.tiempo_acumulado_activo_seg += elapsed_seconds
            target_op.tiempo_ultimo_inicio_activo = None

        target_op.estado = 'DETENIENDO'
        
        # Esta es la línea clave. Si 'reason' viene del EventProcessor, se usará.
        # Si la detención es manual (desde la TUI), `reason` será None y se usará el texto por defecto.
        target_op.estado_razon = reason if reason else "Detenida manualmente por el usuario."
        
        log_msg = f"OPERACIÓN {side.upper()} en estado DETENIENDO (Razón: {target_op.estado_razon}). Esperando cierre de posiciones."
        self._memory_logger.log(log_msg, "WARN")

        if not target_op.posiciones_abiertas:
            self.revisar_y_transicionar_a_detenida(side)
            return True, f"Operación {side.upper()} detenida y reseteada (sin posiciones abiertas)."
            
    return True, f"Proceso de detención para {side.upper()} iniciado."
