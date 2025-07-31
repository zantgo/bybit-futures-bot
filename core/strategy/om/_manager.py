"""
Módulo Gestor de la Operación Estratégica (Operation Manager).

Define la clase `OperationManager`, que es el componente central de la lógica
de negocio para las operaciones estratégicas. Es responsable de mantener,
modificar y gestionar el ciclo de vida de los objetos `Operacion` de forma
independiente para los lados LONG y SHORT.
"""
import datetime
import uuid
from typing import Optional, Dict, Any, Tuple

# --- Dependencias del Proyecto ---
try:
    # La entidad principal que este manager gestiona
    from ._entities import Operacion
    # Dependencias inyectadas para logging y configuración
    from core.logging import memory_logger
    import config as config_module
except ImportError:
    # Fallbacks para análisis estático y resiliencia
    class Operacion: pass
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
        Crea las operaciones iniciales para LONG y SHORT, ambas en estado NEUTRAL.
        """
        # Crear la operación neutral para el lado LONG
        self.long_operation = Operacion(
            id=f"op_long_{uuid.uuid4()}",
            estado='EN_ESPERA',
            tendencia='NEUTRAL',
            tamaño_posicion_base_usdt=0.0,
            max_posiciones_logicas=0,
            apalancamiento=0.0,
            sl_posicion_individual_pct=0.0,
            tsl_activacion_pct=0.0,
            tsl_distancia_pct=0.0
        )
        # Crear la operación neutral para el lado SHORT
        self.short_operation = Operacion(
            id=f"op_short_{uuid.uuid4()}",
            estado='EN_ESPERA',
            tendencia='NEUTRAL',
            tamaño_posicion_base_usdt=0.0,
            max_posiciones_logicas=0,
            apalancamiento=0.0,
            sl_posicion_individual_pct=0.0,
            tsl_activacion_pct=0.0,
            tsl_distancia_pct=0.0
        )
        
        self._initialized = True
        self._memory_logger.log("OperationManager inicializado con operaciones LONG y SHORT independientes.", level="INFO")

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
        Actualiza la operación estratégica para un lado específico con nuevos parámetros.
        """
        target_operation = self.get_operation_by_side(side)
        if not target_operation:
            return False, f"Error: No se puede modificar una operación para el lado '{side}'."

        try:
            changes_log = []
            for key, value in params.items():
                if hasattr(target_operation, key):
                    old_value = getattr(target_operation, key)
                    if old_value != value:
                        setattr(target_operation, key, value)
                        changes_log.append(f"'{key}': {old_value} -> {value}")

            # Si se modificó la condición de entrada, la operación debe volver a esperar
            if 'tipo_cond_entrada' in params or 'valor_cond_entrada' in params:
                if target_operation.estado == 'ACTIVA':
                    target_operation.estado = 'EN_ESPERA'
                    target_operation.tiempo_inicio_ejecucion = None
                    changes_log.append("'estado': ACTIVA -> EN_ESPERA (cond. de entrada modificada)")
            
            if not changes_log:
                return True, f"No se realizaron cambios en la operación {side.upper()}."

            log_message = f"Parámetros de la operación {side.upper()} actualizados: " + ", ".join(changes_log)
            self._memory_logger.log(log_message, "WARN")
            return True, f"Operación {side.upper()} actualizada con éxito."
            
        except Exception as e:
            error_msg = f"Error al actualizar la operación {side.upper()}: {e}"
            self._memory_logger.log(error_msg, "ERROR")
            return False, error_msg

    def force_start_operation(self, side: str) -> Tuple[bool, str]:
        """
        Fuerza el inicio de la operación para un lado específico, cambiando su estado a 'ACTIVA'.
        """
        target_operation = self.get_operation_by_side(side)
        if not target_operation:
            return False, f"No hay operación para el lado '{side}' para iniciar."
        if target_operation.estado == 'ACTIVA':
            return False, f"La operación {side.upper()} ya está activa."
        
        target_operation.estado = 'ACTIVA'
        target_operation.tiempo_inicio_ejecucion = datetime.datetime.now(datetime.timezone.utc)
        self._memory_logger.log(f"OPERACIÓN {side.upper()} INICIADA FORZOSAMENTE: Modo '{target_operation.tendencia}' está ahora ACTIVO.", "WARN")
        return True, f"Operación {side.upper()} iniciada forzosamente."

    def force_stop_operation(self, side: str) -> Tuple[bool, str]:
        """
        Fuerza la finalización de la operación activa para un lado específico, revirtiéndola a un estado
        de espera (EN_ESPERA) y neutral.
        """
        target_operation = self.get_operation_by_side(side)
        if not target_operation:
            return False, f"No hay operación {side.upper()} para detener."

        if target_operation.tendencia == 'NEUTRAL' and target_operation.estado != 'ACTIVA':
             return False, f"No hay una operación de trading {side.upper()} activa para finalizar."

        tendencia_anterior = target_operation.tendencia
        self._memory_logger.log(f"OPERACIÓN {side.upper()} DETENIDA: Modo '{tendencia_anterior}' desactivado. Volviendo a EN_ESPERA.", "INFO")
        
        # Revierte el estado a neutral y en espera
        target_operation.estado = 'EN_ESPERA'
        target_operation.tendencia = 'NEUTRAL'
        target_operation.tiempo_inicio_ejecucion = None
        # Reseteamos contadores para la próxima ejecución
        target_operation.pnl_realizado_usdt = 0.0
        target_operation.comercios_cerrados_contador = 0

        return True, f"Operación {side.upper()} finalizada. El sistema está en espera para este lado."