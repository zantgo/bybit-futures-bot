# core/strategy/pm/manager/_lifecycle.py

"""
Módulo del Position Manager: Ciclo de Vida.

Contiene la lógica de inicialización y configuración base de la clase PositionManager,
incluyendo el constructor y los métodos de arranque de la sesión.
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
    # --- INICIO DE LA MODIFICACIÓN: Importar nuevas entidades ---
    from .._entities import Hito, Operacion, ConfiguracionOperacion
    # from .._entities import Milestone # Comentada la antigua entidad
    # --- FIN DE LA MODIFICACIÓN ---
    from core.exchange import AbstractExchange
except ImportError:
    # --- INICIO DE LA MODIFICACIÓN: Añadir fallbacks para nuevas entidades ---
    class Hito: pass
    class Operacion: pass
    class ConfiguracionOperacion: pass
    # class Milestone: pass # Comentada la antigua entidad
    # --- FIN DE LA MODIFICACIÓN ---
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
        # -- (COMENTADO) Atributos que ahora pertenecerán a la Configuración de la Operación --
        # self._leverage: float = 1.0
        # self._max_logical_positions: int = 1
        # self._initial_base_position_size_usdt: float = 0.0

        self._session_start_time: Optional[datetime.datetime] = None
        self._session_tp_hit: bool = False
        self._global_stop_loss_roi_pct: Optional[float] = None
        self._global_take_profit_roi_pct: Optional[float] = None
        
        # --- Estado de PNL (Se mantendrá global para la sesión, la operación tendrá el suyo) ---
        self._total_realized_pnl_long: float = 0.0
        self._total_realized_pnl_short: float = 0.0

        # --- Estado del Árbol de Decisiones ---
        self._milestones: List[Hito] = []
        
        # --- (COMENTADO) Antiguo Modelo de Estado basado en Tendencia Activa ---
        # Si _active_trend es None, el bot está en modo NEUTRAL.
        # self._active_trend: Optional[Dict[str, Any]] = None

        # --- INICIO DE LA MODIFICACIÓN: Nuevo Modelo de Estado basado en Operación Activa ---
        self.operacion_activa: Optional[Operacion] = None
        # --- FIN DE LA MODIFICACIÓN ---


    def set_executor(self, executor: Any):
        """Inyecta el executor después de la inicialización para romper la dependencia circular."""
        self._executor = executor
        
    def initialize(self, operation_mode: str, base_size: float, max_pos: int):
        """Inicializa el PM para una nueva sesión."""
        self._reset_all_states()
        self._operation_mode = operation_mode
        
        # -- (COMENTADO) Estos valores ahora se usarán para la config de la primera operación --
        # self._leverage = getattr(self._config, 'POSITION_LEVERAGE', 1.0)
        # self._max_logical_positions = max_pos
        # self._initial_base_position_size_usdt = base_size
        
        # Se crea el timestamp de inicio de sesión como "aware" en UTC.
        self._session_start_time = datetime.datetime.now(timezone.utc)
        
        # Límites globales de la sesión (disyuntores)
        self._global_stop_loss_roi_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
        self._global_take_profit_roi_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)

        # --- INICIO DE LA MODIFICACIÓN: Inicializar la primera Operación NEUTRAL ---
        
        # 1. Crear la configuración para la operación inicial (NEUTRAL)
        configuracion_neutral = ConfiguracionOperacion(
            tendencia='NEUTRAL',
            tamaño_posicion_base_usdt=base_size,
            max_posiciones_logicas=max_pos,
            apalancamiento=getattr(self._config, 'POSITION_LEVERAGE', 1.0),
            sl_posicion_individual_pct=0.0, # Irrelevante para NEUTRAL
            tsl_activacion_pct=0.0,         # Irrelevante para NEUTRAL
            tsl_distancia_pct=0.0           # Irrelevante para NEUTRAL
        )

        # 2. Obtener el capital inicial total para la sesión
        initial_capital = self._balance_manager.get_initial_total_capital()
        if initial_capital <= 0:
             # Forzar una actualización si el balance no está listo
             self._balance_manager.force_update_real_balances_cache()
             time.sleep(1) # Dar tiempo a que se actualice
             initial_capital = self._balance_manager.get_initial_total_capital()

        # 3. Crear la instancia de la Operación inicial
        self.operacion_activa = Operacion(
            id=f"op_{uuid.uuid4()}",
            configuracion=configuracion_neutral,
            capital_inicial_usdt=initial_capital
        )
        # --- FIN DE LA MODIFICACIÓN ---

        self._balance_manager.set_state_manager(self)
        self._position_state.initialize(is_live_mode=True)
        
        self._initialized = True
        self._memory_logger.log("PositionManager inicializado bajo el nuevo modelo de Operaciones.", level="INFO")

    def _reset_all_states(self):
        """Resetea todos los atributos de estado del manager a sus valores iniciales."""
        self._initialized = False
        self._operation_mode = "unknown"
        
        # -- (COMENTADO) --
        # self._leverage = 1.0
        # self._max_logical_positions = 1
        # self._initial_base_position_size_usdt = 0.0

        self._total_realized_pnl_long = 0.0
        self._total_realized_pnl_short = 0.0
        self._session_tp_hit = False
        self._session_start_time = None
        self._global_stop_loss_roi_pct = None
        self._global_take_profit_roi_pct = None
        self._milestones = []
        
        # -- (COMENTADO) --
        # self._active_trend = None

        # --- INICIO DE LA MODIFICACIÓN ---
        self.operacion_activa = None
        # --- FIN DE LA MODIFICACIÓN ---