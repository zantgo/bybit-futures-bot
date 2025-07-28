"""
Módulo del Position Manager: Ciclo de Vida.

Contiene la lógica de inicialización y configuración base de la clase PositionManager,
incluyendo el constructor y los métodos de arranque de la sesión.

v6.0 (Modelo de Operación Única):
- El ciclo de vida ahora se centra en la inicialización de una única
  `Operacion` estratégica en estado NEUTRAL y EN_ESPERA.
- Se elimina por completo la gestión de la lista de Hitos.
"""
import datetime
import time
import copy
from typing import Optional, Dict, Any, List
import uuid

# Importamos timezone para crear datetimes "aware"
from datetime import timezone

# --- Dependencias del Proyecto (inyectadas) ---
try:
    # La única entidad que necesitamos ahora es Operacion
    from .._entities import Operacion
    from core.exchange import AbstractExchange
except ImportError:
    # Fallbacks
    class Operacion: pass
    class AbstractExchange: pass

class _LifecycleManager:
    """Clase base que gestiona el ciclo de vida del PositionManager."""
    def __init__(self,
                 balance_manager: Any,
                 position_state: Any,
                 exchange_adapter: AbstractExchange,
                 config: Any,
                 utils: Any,
                 memory_logger: Any,
                 helpers: Any
                 ):
        # --- Inyección de Dependencias ---
        self._balance_manager = balance_manager
        self._position_state = position_state
        self._executor: Optional[Any] = None
        self._exchange = exchange_adapter
        self._config = config
        self._utils = utils
        self._memory_logger = memory_logger
        self._helpers = helpers

        # --- Estado de la Sesión (Global) ---
        self._initialized: bool = False
        self._operation_mode: str = "unknown"
        self._session_start_time: Optional[datetime.datetime] = None
        self._session_tp_hit: bool = False
        self._global_stop_loss_roi_pct: Optional[float] = None
        self._global_take_profit_roi_pct: Optional[float] = None
        
        # --- Estado de PNL (Global de la sesión) ---
        self._total_realized_pnl_long: float = 0.0
        self._total_realized_pnl_short: float = 0.0

        # (COMENTADO) La lista de hitos se elimina en favor de una única operación.
        # self._milestones: List[Hito] = []
        
        # El PM ahora gestiona una única Operacion estratégica.
        self.operacion_activa: Optional[Operacion] = None


    def set_executor(self, executor: Any):
        """Inyecta el executor después de la inicialización para romper la dependencia circular."""
        self._executor = executor
        
    def initialize(self, operation_mode: str, base_size: float, max_pos: int):
        """Inicializa el PM para una nueva sesión, creando la operación inicial."""
        self._reset_all_states()
        self._operation_mode = operation_mode
    
        self._session_start_time = datetime.datetime.now(timezone.utc)
        
        self._global_stop_loss_roi_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
        self._global_take_profit_roi_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)

        # --- INICIO DE LA MODIFICACIÓN: Crear directamente la Operacion inicial ---
        
        # 1. Obtener el capital inicial total para la sesión.
        initial_capital = self._balance_manager.get_initial_total_capital()
        if initial_capital <= 0:
             # Forzar una actualización si el balance no está listo
             self._balance_manager.force_update_real_balances_cache()
             time.sleep(1) # Dar tiempo a que se actualice
             initial_capital = self._balance_manager.get_initial_total_capital()

        # 2. Crear la instancia de la Operación inicial directamente con sus parámetros.
        #    Por defecto, comienza en estado NEUTRAL y EN_ESPERA, lista para ser configurada.
        self.operacion_activa = Operacion(
            id=f"op_neutral_{uuid.uuid4()}",
            estado='EN_ESPERA',
            tendencia='NEUTRAL',
            tamaño_posicion_base_usdt=base_size,
            max_posiciones_logicas=max_pos,
            apalancamiento=getattr(self._config, 'POSITION_LEVERAGE', 1.0),
            sl_posicion_individual_pct=0.0,
            tsl_activacion_pct=0.0,
            tsl_distancia_pct=0.0,
            capital_inicial_usdt=initial_capital
        )
        
        # (COMENTADO) Lógica anterior que usaba ConfiguracionOperacion
        # configuracion_neutral = ConfiguracionOperacion(
        #     tendencia='NEUTRAL',
        #     tamaño_posicion_base_usdt=base_size,
        #     max_posiciones_logicas=max_pos,
        #     apalancamiento=getattr(self._config, 'POSITION_LEVERAGE', 1.0),
        #     sl_posicion_individual_pct=0.0,
        #     tsl_activacion_pct=0.0,
        #     tsl_distancia_pct=0.0
        # )
        # self.operacion_activa = Operacion(
        #     id=f"op_{uuid.uuid4()}",
        #     configuracion=configuracion_neutral,
        #     capital_inicial_usdt=initial_capital
        # )
        # --- FIN DE LA MODIFICACIÓN ---

        self._balance_manager.set_state_manager(self)
        self._position_state.initialize(is_live_mode=True)
        
        self._initialized = True
        self._memory_logger.log("PositionManager inicializado bajo el nuevo modelo de Operación Única.", level="INFO")

    def _reset_all_states(self):
        """Resetea todos los atributos de estado del manager a sus valores iniciales."""
        self._initialized = False
        self._operation_mode = "unknown"
        self._total_realized_pnl_long = 0.0
        self._total_realized_pnl_short = 0.0
        self._session_tp_hit = False
        self._session_start_time = None
        self._global_stop_loss_roi_pct = None
        self._global_take_profit_roi_pct = None
        # (COMENTADO) La lista de hitos ya no existe.
        # self._milestones = []
        self.operacion_activa = None