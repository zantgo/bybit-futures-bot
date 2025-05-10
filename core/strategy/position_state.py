# =============== INICIO ARCHIVO: core/strategy/position_state.py (Refactorizado con LPT v2) ===============
"""
Módulo para almacenar y gestionar el estado de las posiciones lógicas
(delegado a LogicalPositionTable) y físicas (agregadas).
v7.0 (Refactorizado para usar LogicalPositionTable)

Correcciones v2:
- Corregir error Pylance "Variable not allowed in type expression".
"""
import datetime
# <<< CORRECCIÓN: Importar Union desde typing >>>
from typing import List, Dict, Optional, Any, TYPE_CHECKING, Union
import copy
import traceback
import numpy as np # Necesario para np.isfinite

# --- Importar LogicalPositionTable ---
try:
    # Asumimos que está en el mismo directorio
    from .logical_position_table import LogicalPositionTable
except ImportError as e:
    print(f"ERROR CRITICO [Position State Import]: No se pudo importar LogicalPositionTable: {e}")
    LogicalPositionTable = None # Definir como None si falla

# --- Importar Dependencias (utils, config, live_ops) ---
# Estas dependencias ahora son necesarias para inicializar LogicalPositionTable
try:
    import os
    import sys
    # Añadir raíz del proyecto al path si no está
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path: sys.path.insert(0, project_root)
    import config
    from core import utils
    try:
        from core import live_operations # Opcional, solo para modo live
    except ImportError:
        live_operations = None
except ImportError as e_core:
    print(f"WARN [Position State Import]: No se pudo importar dependencia core ({e_core.name}). Funcionalidad limitada.")
    config = None; utils = None; live_operations = None
except Exception as e_imp:
     print(f"ERROR inesperado importando dependencias en position_state: {e_imp}")
     config = None; utils = None; live_operations = None

# --- Estado del Módulo ---
_initialized: bool = False
# <<< Reemplazar listas con instancias de LogicalPositionTable (inicializar a None) >>>
# <<< CORRECCIÓN: Usar Any para los tipos de tabla aquí también >>>
_long_table: Optional[Any] = None # Antes: Optional[LogicalPositionTable]
_short_table: Optional[Any] = None # Antes: Optional[LogicalPositionTable]
# <<< Mantener el estado físico aquí >>>
_physical_long_position: Dict[str, Any] = {}
_physical_short_position: Dict[str, Any] = {}

# --- Funciones Públicas ---

# <<< CORRECCIÓN: Añadir Any a type hints si se usan módulos como tipo >>>
# <<< O definir tipos específicos si existen >>>
def initialize_state(
    is_live_mode: bool = False,
    # Añadir dependencias como args opcionales para pasar a LPT
    config_dependency: Optional[Any] = None,
    utils_dependency: Optional[Any] = None,
    live_ops_dependency: Optional[Any] = None
    ):
    """
    Resetea el estado físico y crea/reinicializa las instancias
    de LogicalPositionTable para long y short.
    """
    global _initialized, _long_table, _short_table
    global _physical_long_position, _physical_short_position
    # Usar dependencias pasadas o las globales si no se pasan
    current_config = config_dependency if config_dependency else config
    current_utils = utils_dependency if utils_dependency else utils
    current_live_ops = live_ops_dependency if live_ops_dependency else live_operations

    print("[Position State] Inicializando estado...")
    _initialized = False

    # --- Resetear Estado Físico ---
    reset_physical_position_state('long')
    reset_physical_position_state('short')

    # --- Crear/Reinicializar Tablas Lógicas ---
    if not LogicalPositionTable: print("ERROR CRITICO [PS Init]: Clase LogicalPositionTable no importada."); _long_table = None; _short_table = None; return

    # Verificar dependencias necesarias para las tablas
    if not current_config or not current_utils: print("ERROR CRITICO [PS Init]: Faltan dependencias (config, utils) para inicializar LogicalPositionTable."); _long_table = None; _short_table = None; return
    if is_live_mode and not current_live_ops: print("WARN [PS Init]: Modo Live pero live_operations no disponible para LogicalPositionTable.")

    try:
        _long_table = LogicalPositionTable(
            side='long',
            is_live_mode=is_live_mode,
            config=current_config,
            utils=current_utils,
            live_operations=current_live_ops if is_live_mode else None
        )
        _short_table = LogicalPositionTable(
            side='short',
            is_live_mode=is_live_mode,
            config=current_config,
            utils=current_utils,
            live_operations=current_live_ops if is_live_mode else None
        )
        _initialized = True
        print("[Position State] Estado y Tablas Lógicas inicializados.")

    except Exception as table_init_err: print(f"ERROR CRITICO [PS Init]: Falló la inicialización de LogicalPositionTable: {table_init_err}"); traceback.print_exc(); _long_table = None; _short_table = None; _initialized = False


def add_logical_position(side: str, position_data: Dict[str, Any]) -> bool:
    """Añade una nueva posición lógica (delegando a la tabla apropiada)."""
    if not _initialized: print("ERROR [PS Add]: No inicializado."); return False
    table = _long_table if side == 'long' else _short_table
    if table:
        return table.add_position(position_data)
    else:
        print(f"ERROR [PS Add]: Tabla lógica para lado '{side}' no disponible."); return False

def remove_logical_position(side: str, index: int) -> Optional[Dict[str, Any]]:
    """Elimina una posición lógica por índice (delegando a la tabla)."""
    if not _initialized: print("ERROR [PS Remove Idx]: No inicializado."); return None
    table = _long_table if side == 'long' else _short_table
    if table:
        return table.remove_position_by_index(index)
    else:
        print(f"ERROR [PS Remove Idx]: Tabla lógica para lado '{side}' no disponible."); return None

def remove_logical_position_by_id(side: str, position_id: str) -> Optional[Dict[str, Any]]:
    """Elimina una posición lógica por su ID (delegando a la tabla)."""
    if not _initialized: print("ERROR [PS Remove ID]: No inicializado."); return None
    table = _long_table if side == 'long' else _short_table
    if table:
        return table.remove_position_by_id(position_id)
    else:
        print(f"ERROR [PS Remove ID]: Tabla lógica para lado '{side}' no disponible."); return None


def get_open_logical_positions(side: str) -> List[Dict[str, Any]]:
    """Devuelve una COPIA PROFUNDA de la lista de posiciones lógicas (desde la tabla)."""
    if not _initialized: return []
    table = _long_table if side == 'long' else _short_table
    if table:
        return table.get_positions() # get_positions ya devuelve copia profunda
    else: return []

def get_used_margin(side: str) -> float:
    """Calcula la suma del margen USDT usado (delegando a la tabla)."""
    if not _initialized: return 0.0
    table = _long_table if side == 'long' else _short_table
    if table:
        if hasattr(table, 'get_total_used_margin'): return table.get_total_used_margin()
        else: print(f"WARN [PS Get Margin]: Método get_total_used_margin no encontrado en LPT {side}. Calculando manualmente."); total_used_margin = 0.0; positions_list = table.get_positions()
        for pos in positions_list: margin = pos.get('margin_usdt', 0.0);
        if isinstance(margin, (int, float)) and np.isfinite(margin): total_used_margin += margin
        return total_used_margin
    else: return 0.0

# --- Nuevas Funciones de Delegación ---

def sync_new_logical_entry_price(side: str, position_id: str, order_id: str) -> bool:
    """Solicita a la tabla lógica que sincronice el precio de entrada post-apertura."""
    if not _initialized: print("ERROR [PS Sync Entry]: No inicializado."); return False
    table = _long_table if side == 'long' else _short_table
    if table:
        if hasattr(table, 'sync_entry_price_after_open'): return table.sync_entry_price_after_open(position_id, order_id)
        else: print(f"ERROR [PS Sync Entry]: Método 'sync_entry_price_after_open' no encontrado en LPT {side}."); return False
    else: print(f"ERROR [PS Sync Entry]: Tabla lógica para lado '{side}' no disponible."); return False

def update_logical_position_details(side: str, position_id: str, details_to_update: Dict[str, Any]) -> bool:
    """Actualiza detalles específicos de una posición lógica por ID (delegando a la tabla)."""
    if not _initialized: print("ERROR [PS Update Details]: No inicializado."); return False
    table = _long_table if side == 'long' else _short_table
    if table:
        if hasattr(table, 'update_position_details'): return table.update_position_details(position_id, details_to_update)
        else: print(f"ERROR [PS Update Details]: Método 'update_position_details' no encontrado en LPT {side}."); return False
    else: print(f"ERROR [PS Update Details]: Tabla lógica para lado '{side}' no disponible."); return False

def display_logical_table(side: str):
    """Solicita a la tabla lógica que imprima su estado."""
    if not _initialized: print("ERROR [PS Display]: No inicializado."); return
    table = _long_table if side == 'long' else _short_table
    if table:
        if hasattr(table, 'display_table'): table.display_table()
        else: print(f"ERROR [PS Display]: Método 'display_table' no encontrado en LPT {side}.")
    else: print(f"ERROR [PS Display]: Tabla lógica para lado '{side}' no disponible.")

# --- Gestión del Estado Físico (Se mantiene aquí) ---

def get_physical_position_state(side: str) -> Dict[str, Any]:
    """Devuelve una COPIA PROFUNDA del estado físico y formatea timestamp."""
    if not _initialized: return {}
    target_physical = _physical_long_position if side == 'long' else _physical_short_position
    if side not in ['long', 'short']: print(f"ERROR [PS Get Phys]: Lado inválido '{side}'."); return {}
    state_copy = copy.deepcopy(target_physical)
    ts = state_copy.get('last_update_ts')
    global utils # Necesario para el formateo
    if utils and ts and isinstance(ts, datetime.datetime): state_copy['last_update_ts'] = utils.format_datetime(ts)
    elif ts is not None: state_copy['last_update_ts'] = str(ts)
    return state_copy

def update_physical_position_state(side: str, avg_price: float, total_size: float, total_margin: float, liq_price: Optional[float], timestamp: datetime):
    """Actualiza el estado físico con datos calculados externamente."""
    if not _initialized: print("ERROR [PS Update Phys]: No inicializado."); return
    target_physical = _physical_long_position if side == 'long' else _physical_short_position
    if side not in ['long', 'short']: print(f"ERROR [PS Update Phys]: Lado inválido '{side}'."); return
    target_physical['avg_entry_price'] = float(avg_price) if isinstance(avg_price, (int, float)) else 0.0
    target_physical['total_size_contracts'] = float(total_size) if isinstance(total_size, (int, float)) else 0.0
    target_physical['total_margin_usdt'] = float(total_margin) if isinstance(total_margin, (int, float)) else 0.0
    target_physical['est_liq_price'] = float(liq_price) if isinstance(liq_price, (int, float)) else None
    target_physical['last_update_ts'] = timestamp if isinstance(timestamp, datetime.datetime) else None


def reset_physical_position_state(side: str):
    """Resetea el estado físico a valores por defecto."""
    default_state = { 'avg_entry_price': 0.0, 'total_size_contracts': 0.0,
                      'total_margin_usdt': 0.0, 'est_liq_price': None,
                      'last_update_ts': None }
    if side == 'long': global _physical_long_position; _physical_long_position = default_state.copy()
    elif side == 'short': global _physical_short_position; _physical_short_position = default_state.copy()

# =============== FIN ARCHIVO: core/strategy/position_state.py (Refactorizado con LPT v2) ===============