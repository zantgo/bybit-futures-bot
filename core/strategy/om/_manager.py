"""
Módulo Gestor de la Operación Estratégica (Operation Manager).

Define la clase `OperationManager`, que es el componente central de la lógica
de negocio para una única operación estratégica. Es responsable de mantener,
modificar y gestionar el ciclo de vida del objeto `Operacion`.
"""
import datetime
import uuid
from typing import Optional, Dict, Any, Tuple
from datetime import timezone

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
    Gestiona el estado y la lógica de negocio de la operación estratégica.
    Esta clase es el "cerebro" de la estrategia.
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
        
        # El atributo principal que almacena el estado de la operación actual.
        self.operacion_actual: Optional[Operacion] = None
        
        self.initialize()

    def initialize(self):
        """
        Crea la operación inicial en estado NEUTRAL. Esta es la operación
        por defecto con la que arranca el bot, lista para ser configurada.
        """
        self.operacion_actual = Operacion(
            id=f"op_neutral_{uuid.uuid4()}",
            estado='EN_ESPERA',
            tendencia='NEUTRAL',
            # Se usan valores seguros para una operación neutral.
            tamaño_posicion_base_usdt=0.0,
            max_posiciones_logicas=0,
            apalancamiento=0.0,
            sl_posicion_individual_pct=0.0,
            tsl_activacion_pct=0.0,
            tsl_distancia_pct=0.0
        )
        self._initialized = True
        self._memory_logger.log("OperationManager inicializado con una operación NEUTRAL.", level="INFO")

    def is_initialized(self) -> bool:
        """Verifica si el Operation Manager ha sido inicializado."""
        return self._initialized

    def get_operation(self) -> Optional[Operacion]:
        """Devuelve el objeto de la operación estratégica actual."""
        return self.operacion_actual

    def create_or_update_operation(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Actualiza la operación estratégica actual con un nuevo conjunto de parámetros.
        """
        if not self.operacion_actual:
            return False, "Error: No hay una operación activa para modificar."

        try:
            changes_log = []
            for key, value in params.items():
                if hasattr(self.operacion_actual, key):
                    old_value = getattr(self.operacion_actual, key)
                    if old_value != value:
                        setattr(self.operacion_actual, key, value)
                        changes_log.append(f"'{key}': {old_value} -> {value}")

            # Si se modificó la condición de entrada, la operación debe volver a esperar
            if 'tipo_cond_entrada' in params or 'valor_cond_entrada' in params:
                if self.operacion_actual.estado == 'ACTIVA':
                    self.operacion_actual.estado = 'EN_ESPERA'
                    self.operacion_actual.tiempo_inicio_ejecucion = None
                    changes_log.append("'estado': ACTIVA -> EN_ESPERA (cond. de entrada modificada)")

            if not changes_log:
                return True, "No se realizaron cambios en la operación."

            log_message = "Parámetros de la operación actualizados: " + ", ".join(changes_log)
            self._memory_logger.log(log_message, "WARN")
            return True, "Operación actualizada con éxito."
            
        except Exception as e:
            error_msg = f"Error al actualizar la operación: {e}"
            self._memory_logger.log(error_msg, "ERROR")
            return False, error_msg

    def force_start_operation(self) -> Tuple[bool, str]:
        """
        Fuerza el inicio de la operación, cambiando su estado a 'ACTIVA'.
        """
        if not self.operacion_actual:
            return False, "No hay operación para iniciar."
        if self.operacion_actual.estado == 'ACTIVA':
            return False, "La operación ya está activa."
        
        self.operacion_actual.estado = 'ACTIVA'
        self.operacion_actual.tiempo_inicio_ejecucion = datetime.datetime.now(timezone.utc)
        self._memory_logger.log(f"OPERACIÓN INICIADA FORZOSAMENTE: Modo '{self.operacion_actual.tendencia}' está ahora ACTIVO.", "WARN")
        return True, "Operación iniciada forzosamente."

    def force_stop_operation(self) -> Tuple[bool, str]:
        """
        Fuerza la finalización de la operación activa actual, revirtiéndola a un estado
        de espera (EN_ESPERA) pero manteniendo sus parámetros para una posible reactivación.
        No cierra posiciones, esa es responsabilidad del PositionManager.
        """
        if not self.operacion_actual:
            return False, "No hay operación para detener."

        if self.operacion_actual.tendencia == 'NEUTRAL' and self.operacion_actual.estado != 'ACTIVA':
             return False, "No hay una operación de trading activa para finalizar."

        tendencia_anterior = self.operacion_actual.tendencia
        self._memory_logger.log(f"OPERACIÓN DETENIDA: Modo '{tendencia_anterior}' desactivado. Volviendo a EN_ESPERA.", "INFO")
        
        # Revierte el estado, pero no crea una nueva operación NEUTRAL.
        # Esto permite que la TUI inicie una nueva operación con la config anterior
        # o la modifique.
        self.operacion_actual.estado = 'EN_ESPERA'
        self.operacion_actual.tendencia = 'NEUTRAL'
        self.operacion_actual.tiempo_inicio_ejecucion = None
        # Reseteamos contadores para la próxima ejecución
        self.operacion_actual.pnl_realizado_usdt = 0.0
        self.operacion_actual.comercios_cerrados_contador = 0

        return True, "Operación finalizada. El sistema está en espera."