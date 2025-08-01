"""
Módulo Gestor de la Operación Estratégica (Operation Manager).

v8.0 (Capital Lógico por Operación):
- `create_or_update_operation` ahora gestiona la asignación y el ajuste dinámico
  del capital lógico de cada operación a través del objeto `LogicalBalances`.
- `detener_operacion` ahora resetea el balance lógico de la operación.
"""
import datetime
import uuid
from typing import Optional, Dict, Any, Tuple

# --- Dependencias del Proyecto ---
try:
    # --- INICIO DE LA MODIFICACIÓN ---
    # La entidad principal que este manager gestiona, ahora con su balance.
    from ._entities import Operacion, LogicalBalances
    # --- FIN DE LA MODIFICACIÓN ---
    # Dependencias inyectadas para logging y configuración
    from core.logging import memory_logger
    import config as config_module
except ImportError:
    # Fallbacks para análisis estático y resiliencia
    class Operacion: pass
    # --- INICIO DE LA MODIFICACIÓN ---
    class LogicalBalances: pass
    # --- FIN DE LA MODIFICACIÓN ---
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
        
        # Atributos principales que almacenan el estado de las operaciones
        self.long_operation: Optional[Operacion] = None
        self.short_operation: Optional[Operacion] = None
        
        self.initialize()

    def initialize(self):
        """
        Crea las operaciones iniciales para LONG y SHORT, ambas en estado DETENIDA.
        """
        self.long_operation = Operacion(
            id=f"op_long_{uuid.uuid4()}",
            estado='DETENIDA',
            tendencia=None
        )
        self.short_operation = Operacion(
            id=f"op_short_{uuid.uuid4()}",
            estado='DETENIDA',
            tendencia=None
        )
        self._initialized = True
        self._memory_logger.log("OperationManager inicializado con operaciones LONG y SHORT en estado DETENIDA.", level="INFO")

    def is_initialized(self) -> bool:
        """Verifica si el Operation Manager ha sido inicializado."""
        return self._initialized

    def get_operation_by_side(self, side: str) -> Optional[Operacion]:
        """Devuelve el objeto de la operación estratégica para un lado específico."""
        if side == 'long':
            return self.long_operation
        elif side == 'short':
            return self.short_operation
        
        self._memory_logger.log(f"Error: Se solicitó operación para un lado inválido '{side}'.", "ERROR")
        return None

    def create_or_update_operation(self, side: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Crea o actualiza una operación. Gestiona las transiciones de estado y el ajuste
        dinámico del capital lógico para operaciones activas.
        """
        # Comentario: La dependencia de pm_api se mantiene por si se necesita para alguna lógica futura.
        from core.strategy.pm import api as pm_api

        target_operation = self.get_operation_by_side(side)
        if not target_operation:
            return False, f"Lado de operación inválido '{side}'."

        estado_original = target_operation.estado
        changes_log = []

        # --- INICIO DE LA MODIFICACIÓN: Lógica de Capital Lógico ---
        # Capturar el capital lógico operativo ANTES de cualquier cambio para detectar ajustes.
        capital_logico_anterior = target_operation.balances.operational_margin
        
        # --- Aplicar cambios de parámetros ---
        for key, value in params.items():
            if hasattr(target_operation, key):
                old_value = getattr(target_operation, key)
                if old_value != value:
                    setattr(target_operation, key, value)
                    changes_log.append(f"'{key}': {old_value} -> {value}")
        
        # --- Lógica de transición de estado y asignación/ajuste de capital ---
        if estado_original == 'DETENIDA' and params: # Configurando una NUEVA operación
            # Se asigna el capital lógico proporcionado por el usuario (desde el wizard).
            # El wizard debe pasar un parámetro 'operational_margin'.
            new_operational_margin = params.get('operational_margin')
            if new_operational_margin is not None:
                target_operation.balances.operational_margin = float(new_operational_margin)
                # El capital inicial histórico se fija en este momento.
                target_operation.capital_inicial_usdt = float(new_operational_margin)
                changes_log.append(f"'capital_logico': {target_operation.capital_inicial_usdt:.2f}$ (asignado)")

            # Lógica de transición de estado (sin cambios)
            if target_operation.tipo_cond_entrada == 'MARKET':
                target_operation.estado = 'ACTIVA'
                target_operation.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
            else:
                target_operation.estado = 'EN_ESPERA'
            changes_log.append(f"'estado': DETENIDA -> {target_operation.estado}")

        elif estado_original in ['ACTIVA', 'EN_ESPERA', 'PAUSADA']: # MODIFICANDO una operación en curso
            
            # 1. Ajuste dinámico del capital lógico
            capital_logico_nuevo = target_operation.balances.operational_margin
            diferencia_capital = capital_logico_nuevo - capital_logico_anterior

            if abs(diferencia_capital) > 1e-9: # Si hubo un cambio
                # El capital_inicial_usdt se ajusta para reflejar el "depósito" o "retiro" lógico.
                # Esto mantiene la consistencia en el cálculo del ROI.
                target_operation.capital_inicial_usdt += diferencia_capital
                changes_log.append(f"'capital_logico': {capital_logico_anterior:.2f}$ -> {capital_logico_nuevo:.2f}$")
                changes_log.append(f"'capital_inicial_historico': ajustado en {diferencia_capital:+.2f}$")
                self._memory_logger.log(f"CAPITAL LÓGICO AJUSTADO ({side.upper()}): {diferencia_capital:+.2f}$. Nuevo capital base ROI: {target_operation.capital_inicial_usdt:.2f}$", "WARN")

            # 2. Transición ACTIVA -> EN_ESPERA (si aplica, sin cambios en la lógica)
            if estado_original == 'ACTIVA' and 'tipo_cond_entrada' in params:
                current_price = pm_api.get_current_market_price() or 0.0
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

        # --- FIN DE LA MODIFICACIÓN ---

        if not changes_log:
            return True, f"No se realizaron cambios en la operación {side.upper()}."

        log_message = f"Operación {side.upper()} actualizada: " + ", ".join(changes_log)
        self._memory_logger.log(log_message, "WARN")
        return True, f"Operación {side.upper()} actualizada con éxito."

    def pausar_operacion(self, side: str) -> Tuple[bool, str]:
        """Pone una operación ACTIVA o EN_ESPERA en estado PAUSADA."""
        target_operation = self.get_operation_by_side(side)
        if not target_operation or target_operation.estado not in ['ACTIVA', 'EN_ESPERA']:
            return False, f"Solo se puede pausar una operación ACTIVA o EN_ESPERA del lado {side.upper()}."

        target_operation.estado = 'PAUSADA'
        msg = f"OPERACIÓN {side.upper()} PAUSADA. No se abrirán nuevas posiciones ni se evaluarán condiciones de entrada."
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def reanudar_operacion(self, side: str) -> Tuple[bool, str]:
        """Reanuda una operación PAUSADA, devolviéndola a su estado previo a la pausa (ACTIVA o EN_ESPERA)."""
        target_operation = self.get_operation_by_side(side)
        if not target_operation or target_operation.estado != 'PAUSADA':
            return False, f"Solo se puede reanudar una operación PAUSADA del lado {side.upper()}."

        # Por simplicidad y control del usuario, la reanudamos a ACTIVA.
        target_operation.estado = 'ACTIVA'
        
        if not target_operation.tiempo_inicio_ejecucion:
            target_operation.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
        
        msg = f"OPERACIÓN {side.upper()} REANUDADA. El sistema está ahora ACTIVO para este lado."
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def forzar_activacion_manual(self, side: str) -> Tuple[bool, str]:
        """Activa manualmente una operación que está EN_ESPERA, ignorando su condición de entrada."""
        target_operation = self.get_operation_by_side(side)
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
        target_operation = self.get_operation_by_side(side)
        if not target_operation or target_operation.estado != 'EN_ESPERA':
            return False, "La operación no estaba esperando una condición."

        target_operation.estado = 'ACTIVA'
        target_operation.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
        
        msg = f"OPERACIÓN {side.upper()} ACTIVADA AUTOMÁTICAMENTE por condición de entrada."
        self._memory_logger.log(msg, "WARN")
        return True, msg

    def detener_operacion(self, side: str, forzar_cierre_posiciones: bool) -> Tuple[bool, str]:
        """Detiene una operación, llevándola al estado final DETENIDA y reseteando sus contadores."""
        from core.strategy.pm import api as pm_api

        target_operation = self.get_operation_by_side(side)
        if not target_operation or target_operation.estado == 'DETENIDA':
            return False, f"La operación {side.upper()} ya está detenida o no existe."

        if forzar_cierre_posiciones:
            self._memory_logger.log(f"DETENIENDO OPERACIÓN {side.upper()}: Forzando cierre de posiciones...", "WARN")
            pm_api.close_all_logical_positions(side, reason=f"OPERATION_{side.upper()}_STOPPED")

        tendencia_anterior = target_operation.tendencia
        
        # Resetear la operación a su estado "limpio"
        target_operation.estado = 'DETENIDA'
        target_operation.tendencia = None
        target_operation.tiempo_inicio_ejecucion = None
        target_operation.capital_inicial_usdt = 0.0
        target_operation.pnl_realizado_usdt = 0.0
        target_operation.comercios_cerrados_contador = 0
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se resetea el balance lógico a un estado vacío.
        target_operation.balances = LogicalBalances()
        # --- FIN DE LA MODIFICACIÓN ---
        
        msg = f"OPERACIÓN {side.upper()} ({tendencia_anterior}) DETENIDA. El sistema está ahora inactivo para este lado."
        self._memory_logger.log(msg, "INFO")
        return True, msg

    def revisar_y_transicionar_a_detenida(self, side: str):
        """
        Comprueba si una operación PAUSADA ya no tiene posiciones abiertas.
        Si es así, la transiciona a DETENIDA. Es invocado por el PM tras cada cierre.
        """
        from core.strategy.pm import api as pm_api

        target_operation = self.get_operation_by_side(side)
        if not target_operation or target_operation.estado != 'PAUSADA':
            return

        summary = pm_api.get_position_summary()
        if summary and not summary.get('error'):
            pos_count_key = f'open_{side}_positions_count'
            if summary.get(pos_count_key) == 0:
                self._memory_logger.log(f"OPERACIÓN {side.upper()}: Última posición cerrada mientras estaba pausada. Transicionando a DETENIDA.", "INFO")
                self.detener_operacion(side, forzar_cierre_posiciones=False)