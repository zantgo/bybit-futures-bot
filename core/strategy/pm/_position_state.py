# ./core/strategy/pm/_position_state.py

"""
Módulo del PositionState.

Define la clase PositionState, responsable de almacenar y gestionar el estado
de las posiciones lógicas (delegado a instancias de LogicalPositionTable) y
físicas (agregadas) para ambos lados (long y short).

v2.2 (Sincronización):
- Añadido el método `sync_logical_positions` para permitir la resincronización
  completa del estado lógico, necesario al transicionar entre Operaciones.
- Mejorado el tipado de los métodos para operar con objetos `LogicalPosition`.
"""
import datetime
import copy
import traceback
from typing import List, Dict, Optional, Any

# --- Dependencias del Proyecto ---
try:
    from ._logical_table import LogicalPositionTable
    # --- INICIO DE LA MODIFICACIÓN ---
    # Se corrige la importación para apuntar a la ubicación centralizada.
    from core.strategy.entities import LogicalPosition, PhysicalPosition
    # --- FIN DE LA MODIFICACIÓN ---
    from core.exchange import AbstractExchange
    from core.logging import memory_logger
except ImportError:
    # Fallbacks
    class LogicalPositionTable: pass
    class LogicalPosition: pass
    class PhysicalPosition: pass
    class AbstractExchange: pass
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()


class PositionState:
    """Gestiona el estado de las posiciones lógicas y físicas."""

    def __init__(self,
                 config: Any,
                 utils: Any,
                 exchange_adapter: AbstractExchange
                 ):
        """
        Inicializa el gestor de estado de posiciones.
        """
        # Inyección de dependencias
        self._config = config
        self._utils = utils
        self._exchange = exchange_adapter
        
        # Atributos de estado de la instancia
        self._initialized: bool = False
        self._long_table: Optional[LogicalPositionTable] = None
        self._short_table: Optional[LogicalPositionTable] = None
        self.physical_long_position: PhysicalPosition = PhysicalPosition()
        self.physical_short_position: PhysicalPosition = PhysicalPosition()

    def initialize(self, is_live_mode: bool):
        """
        Inicializa o resetea el estado para una nueva sesión.
        Crea las instancias de LogicalPositionTable.
        """
        print("[Position State] Inicializando estado...")
        self._initialized = False

        # Resetear estado físico
        self.reset_physical_position_state('long')
        self.reset_physical_position_state('short')

        # Validar dependencias para las tablas lógicas
        if not all([self._config, self._utils, self._exchange, LogicalPositionTable]):
            memory_logger.log("ERROR CRITICO [PS Init]: Faltan dependencias para LogicalPositionTable.", level="ERROR")
            return

        try:
            # Crear instancias de las tablas lógicas, inyectando el adaptador de exchange
            self._long_table = LogicalPositionTable(
                side='long',
                is_live_mode=is_live_mode,
                config_param=self._config,
                utils=self._utils,
                exchange_adapter=self._exchange if is_live_mode else None
            )
            self._short_table = LogicalPositionTable(
                side='short',
                is_live_mode=is_live_mode,
                config_param=self._config,
                utils=self._utils,
                exchange_adapter=self._exchange if is_live_mode else None
            )
            self._initialized = True
            print("[Position State] Estado y Tablas Lógicas inicializados.")

        except Exception as e:
            memory_logger.log(f"ERROR CRITICO [PS Init]: Falló la inicialización de LogicalPositionTable: {e}", level="ERROR")
            memory_logger.log(traceback.format_exc(), level="ERROR")
            self._initialized = False

    # --- INICIO DE LA MODIFICACIÓN: Implementación del método ---
    def sync_logical_positions(self, all_positions: Dict[str, List[LogicalPosition]]):
        """
        Sincroniza el estado de las tablas lógicas con un nuevo conjunto completo de posiciones.

        Args:
            all_positions: Un diccionario con claves 'long' y 'short' que contiene
                           las listas completas de las nuevas posiciones lógicas.
        """
        if not self._initialized: return
        
        long_positions = all_positions.get('long', [])
        short_positions = all_positions.get('short', [])
        
        if self._long_table:
            self._long_table.sync_positions(long_positions)
            
        if self._short_table:
            self._short_table.sync_positions(short_positions)
        
        memory_logger.log("PositionState sincronizado con el nuevo estado de la Operación.", level="DEBUG")
    # --- FIN DE LA MODIFICACIÓN ---

    def _get_table_for_side(self, side: str) -> Optional[LogicalPositionTable]:
        """Método auxiliar para obtener la tabla correcta."""
        if side == 'long':
            return self._long_table
        elif side == 'short':
            return self._short_table
        return None

    # --- Métodos para Posiciones Lógicas (con tipado mejorado) ---
    
    def add_logical_position_obj(self, side: str, position_obj: LogicalPosition) -> bool:
        """Añade una nueva posición lógica (objeto) a la tabla correspondiente."""
        if not self._initialized: return False
        table = self._get_table_for_side(side)
        return table.add_position(position_obj) if table else False

    def remove_logical_position(self, side: str, index: int) -> Optional[LogicalPosition]:
        """Elimina una posición lógica por índice y devuelve el objeto."""
        if not self._initialized: return None
        table = self._get_table_for_side(side)
        return table.remove_position_by_index(index) if table else None

    def get_open_logical_positions_objects(self, side: str) -> List[LogicalPosition]:
        """Devuelve una copia de las posiciones lógicas abiertas como objetos."""
        if not self._initialized: return []
        table = self._get_table_for_side(side)
        return table.get_positions() if table else []
        
    def update_logical_position_details(self, side: str, position_id: str, details_to_update: Dict[str, Any]) -> bool:
        """Actualiza detalles de una posición lógica específica."""
        if not self._initialized: return False
        table = self._get_table_for_side(side)
        return table.update_position_details(position_id, details_to_update) if table else False

    # --- (COMENTADO) Métodos antiguos que operaban con diccionarios. ---
    # Se mantienen comentados para referencia, pero la nueva lógica usa los métodos
    # basados en objetos (`_obj`) para mayor seguridad de tipos.
    """
    def add_logical_position(self, side: str, position_data: Dict[str, Any]) -> bool:
        #Esta función ha sido reemplazada por add_logical_position_obj
        if not self._initialized: return False
        try:
            pos_obj = LogicalPosition(**position_data)
            table = self._get_table_for_side(side)
            return table.add_position(pos_obj) if table else False
        except TypeError as e:
            memory_logger.log(f"ERROR [PS add_logical_position]: Datos de posición inválidos: {e}", "ERROR")
            return False

    def get_open_logical_positions(self, side: str) -> List[Dict[str, Any]]:
        #Esta función ha sido reemplazada por get_open_logical_positions_objects
        from dataclasses import asdict
        if not self._initialized: return []
        table = self._get_table_for_side(side)
        if table:
            return [asdict(pos) for pos in table.get_positions()]
        return []
    """

    def display_logical_table(self, side: str):
        """Solicita a la tabla lógica que imprima su estado."""
        if not self._initialized: return
        table = self._get_table_for_side(side)
        if table:
            table.display_table()

    # --- Métodos para Posiciones Físicas ---

    def get_physical_position_state(self, side: str) -> Dict[str, Any]:
        """Devuelve una copia del estado físico en formato de diccionario."""
        if not self._initialized: return {}
        
        target_physical: PhysicalPosition = self.physical_long_position if side == 'long' else self.physical_short_position
        
        from dataclasses import asdict
        state_dict = asdict(target_physical)
        
        ts = state_dict.get('last_update_ts')
        if self._utils and ts and isinstance(ts, datetime.datetime):
            state_dict['last_update_ts'] = self._utils.format_datetime(ts)
        elif ts is not None:
            state_dict['last_update_ts'] = str(ts)
            
        return state_dict

    def update_physical_position_state(
        self,
        side: str,
        avg_price: float,
        total_size: float,
        total_margin: float,
        liq_price: Optional[float],
        timestamp: datetime.datetime
    ):
        """Actualiza el estado de la posición física."""
        if not self._initialized: return
        
        target_physical = self.physical_long_position if side == 'long' else self.physical_short_position
        
        target_physical.avg_entry_price = self._utils.safe_float_convert(avg_price, 0.0)
        target_physical.total_size_contracts = self._utils.safe_float_convert(total_size, 0.0)
        target_physical.total_margin_usdt = self._utils.safe_float_convert(total_margin, 0.0)
        target_physical.est_liq_price = self._utils.safe_float_convert(liq_price)
        target_physical.last_update_ts = timestamp

    def reset_physical_position_state(self, side: str):
        """Resetea el estado físico a sus valores por defecto."""
        if side == 'long':
            self.physical_long_position = PhysicalPosition()
        elif side == 'short':
            self.physical_short_position = PhysicalPosition()