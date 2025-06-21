# =============== INICIO ARCHIVO: core/strategy/logical_position_table.py (v1.1 - Sync con Reintentos) ===============
"""
Módulo que define la clase LogicalPositionTable para gestionar una lista de
posiciones lógicas abiertas para un lado específico (long/short).

Incluye funcionalidades para añadir, remover, actualizar, sincronizar (live, con reintentos)
y visualizar las posiciones lógicas.
v1.1: Añadidos reintentos a sync_entry_price_after_open.
"""
import datetime
import traceback
import copy
import time # Necesario para los reintentos
from typing import Optional, Dict, Any, List, Tuple, Union, TYPE_CHECKING
import pandas as pd # Para visualización en tabla

# --- Dependencias (se inyectan en __init__) ---
if TYPE_CHECKING:
    import config as cfg_mod
    from core import utils as ut_mod
    from core import live_operations as lo_mod

# --- Lógica de Reintentos ---
MAX_RETRIES = 1 # Número de intentos (configurable si se desea)
RETRY_DELAY = 0.01 # Segundos entre intentos (configurable si se desea)

class LogicalPositionTable:
    """
    Gestiona una tabla (lista) de posiciones lógicas para un lado (long/short).
    """
    def __init__(self,
                 side: str,
                 is_live_mode: bool,
                 config: Optional[Any] = None,
                 utils: Optional[Any] = None,
                 live_operations: Optional[Any] = None
                 ):
        """
        Inicializa la tabla de posiciones lógicas.
        (Constructor sin cambios respecto a la v2)
        """
        if side not in ['long', 'short']: raise ValueError(f"Lado inválido '{side}'.")
        if is_live_mode and not live_operations: print(f"WARN [LPT Init {side}]: Modo Live pero live_operations no fue proporcionado.")

        self.side = side
        self.is_live_mode = is_live_mode
        self._config = config
        self._utils = utils
        self._live_operations = live_operations
        self._positions: List[Dict[str, Any]] = []

        print(f"[LPT {self.side.upper()}] Tabla inicializada. Modo Live: {self.is_live_mode}")

    # --- Métodos de Gestión Básica ---
    # (add_position, remove_position_by_index, remove_position_by_id, update_position_details SIN CAMBIOS)
    def add_position(self, position_data: Dict[str, Any]) -> bool:
        if not isinstance(position_data, dict): print(f"ERROR [LPT {self.side.upper()} Add]: Dato no es dict."); return False
        if 'id' not in position_data: print(f"ERROR [LPT {self.side.upper()} Add]: Falta 'id'."); return False
        self._positions.append(copy.deepcopy(position_data))
        print(f"DEBUG [LPT {self.side.upper()} Add]: Posición ID ...{str(position_data['id'])[-6:]} añadida. Total: {len(self._positions)}")
        return True

    def remove_position_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        try:
            if 0 <= index < len(self._positions):
                removed_position = self._positions.pop(index)
                print(f"DEBUG [LPT {self.side.upper()} Remove Idx]: Posición índice {index} (ID ...{str(removed_position.get('id','N/A'))[-6:]}) eliminada. Total: {len(self._positions)}")
                return copy.deepcopy(removed_position)
            else: print(f"ERROR [LPT {self.side.upper()} Remove Idx]: Índice {index} fuera de rango."); return None
        except Exception as e: print(f"ERROR [LPT {self.side.upper()} Remove Idx]: Excepción {index}: {e}"); traceback.print_exc(); return None

    def remove_position_by_id(self, position_id: str) -> Optional[Dict[str, Any]]:
        index_to_remove = -1
        for i, pos in enumerate(self._positions):
            if pos.get('id') == position_id: index_to_remove = i; break
        if index_to_remove != -1: return self.remove_position_by_index(index_to_remove)
        else: print(f"WARN [LPT {self.side.upper()} Remove ID]: ID {position_id} no encontrado."); return None

    def update_position_details(self, position_id: str, details_to_update: Dict[str, Any]) -> bool:
        if not isinstance(details_to_update, dict): print(f"ERROR [LPT {self.side.upper()} Update]: details no es dict."); return False
        found = False
        for i, pos in enumerate(self._positions):
            if pos.get('id') == position_id:
                try: self._positions[i].update(details_to_update); print(f"DEBUG [LPT {self.side.upper()} Update]: Pos ID ...{position_id[-6:]} actualizada con: {details_to_update}"); found = True; break
                except Exception as e: print(f"ERROR [LPT {self.side.upper()} Update]: Excepción ID {position_id}: {e}"); traceback.print_exc(); return False
        if not found: print(f"WARN [LPT {self.side.upper()} Update]: ID {position_id} no encontrado.")
        return found

    # --- Métodos de Acceso y Cálculo ---
    # (get_positions, get_position_by_id, get_position_by_index, get_count, get_total_size, get_total_used_margin, get_average_entry_price SIN CAMBIOS)
    def get_positions(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self._positions)

    def get_position_by_id(self, position_id: str) -> Optional[Dict[str, Any]]:
        for pos in self._positions:
            if pos.get('id') == position_id: return copy.deepcopy(pos)
        return None

    def get_position_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        try:
            if 0 <= index < len(self._positions): return copy.deepcopy(self._positions[index])
            else: print(f"WARN [LPT {self.side.upper()} Get Idx]: Índice {index} fuera de rango."); return None
        except Exception as e: print(f"ERROR [LPT {self.side.upper()} Get Idx]: Excepción {index}: {e}"); return None

    def get_count(self) -> int:
        return len(self._positions)

    def get_total_size(self) -> float:
        if not self._utils: return 0.0
        total_size = 0.0
        for pos in self._positions: total_size += self._utils.safe_float_convert(pos.get('size_contracts'), 0.0)
        return total_size

    def get_total_used_margin(self) -> float:
         if not self._utils: return 0.0
         total_margin = 0.0
         for pos in self._positions: total_margin += self._utils.safe_float_convert(pos.get('margin_usdt'), 0.0)
         return total_margin

    def get_average_entry_price(self) -> float:
        if not self._utils: return 0.0
        total_value = 0.0; total_size = 0.0
        for pos in self._positions:
            size = self._utils.safe_float_convert(pos.get('size_contracts'), 0.0)
            price = self._utils.safe_float_convert(pos.get('entry_price'), 0.0)
            if size > 0 and price > 0: total_value += size * price; total_size += size
        return self._utils.safe_division(total_value, total_size, default=0.0)

    # --- Sincronización (Modo Live) ---
    # <<< MODIFICADO: Añadida lógica de reintentos >>>
    def sync_entry_price_after_open(self, position_id: str, order_id: str) -> bool:
        """
        Consulta la API para obtener los detalles de ejecución de una orden de apertura
        y actualiza la posición lógica. Incluye reintentos.
        """
        if not self.is_live_mode: print(f"WARN [LPT {self.side.upper()} Sync]: Sincronización no aplicable."); return False
        if not self._live_operations or not self._config or not self._utils: print(f"ERROR [LPT {self.side.upper()} Sync]: Faltan dependencias."); return False
        if not order_id or order_id == 'N/A': print(f"WARN [LPT {self.side.upper()} Sync]: ID de orden inválido ('{order_id}')."); return False

        symbol = getattr(self._config, 'TICKER_SYMBOL', None)
        if not symbol: print(f"ERROR [LPT {self.side.upper()} Sync]: TICKER_SYMBOL no definido."); return False

        print(f"DEBUG [LPT {self.side.upper()} Sync]: Buscando ejecuciones para Orden ID: {order_id} (Pos Lógica ID: ...{position_id[-6:]})")

        # --- Lógica de Reintentos ---
        max_retries = MAX_RETRIES # Número de intentos (configurable si se desea)
        retry_delay = RETRY_DELAY # Segundos entre intentos (configurable si se desea)
        executions = None # Inicializar a None

        for attempt in range(max_retries):
            print(f"  Sync Attempt #{attempt+1}/{max_retries}...")
            try:
                if not hasattr(self._live_operations, 'get_order_execution_history'):
                    raise AttributeError("Método get_order_execution_history no encontrado en live_operations")

                executions = self._live_operations.get_order_execution_history(
                    category="linear", symbol=symbol, order_id=order_id, limit=50
                )

                # Verificar si la respuesta es válida y si tiene ejecuciones
                if isinstance(executions, list) and len(executions) > 0:
                    print(f"  -> Éxito [Get Executions] Intento #{attempt+1}: {len(executions)} ejecuciones encontradas.")
                    break # Salir del bucle si se encontraron ejecuciones
                elif isinstance(executions, list): # Lista vacía
                    print(f"  WARN [LPT Sync] Intento #{attempt+1}: No se encontraron ejecuciones para Orden ID: {order_id}.")
                    if attempt < max_retries - 1:
                        print(f"    Reintentando en {retry_delay} segundos...")
                        time.sleep(retry_delay)
                    else:
                         print(f"    Máximo de reintentos ({max_retries}) alcanzado sin encontrar ejecuciones.")
                         # No salir del bucle aquí, simplemente executions seguirá siendo None o lista vacía
                else: # Respuesta inesperada (no es lista)
                     print(f"  WARN [LPT Sync] Intento #{attempt+1}: Respuesta inesperada de get_order_execution_history (tipo: {type(executions)}).")
                     # Considerar esto como un fallo o intentar de nuevo? Por ahora, reintentar.
                     if attempt < max_retries - 1:
                          print(f"    Reintentando en {retry_delay} segundos...")
                          time.sleep(retry_delay)
                     else:
                          print(f"    Máximo de reintentos ({max_retries}) alcanzado con respuesta inesperada.")


            except Exception as e:
                print(f"ERROR [LPT {self.side.upper()} Sync]: Excepción en intento #{attempt+1} para orden {order_id}: {e}")
                traceback.print_exc()
                return False # Fallo definitivo si hay excepción

        # --- Procesar Ejecuciones (si se encontraron después de los intentos) ---
        if not executions: # Si executions sigue None o es lista vacía
            print(f"WARN [LPT {self.side.upper()} Sync]: No se encontraron ejecuciones para Orden ID: {order_id} después de {max_retries} intentos.")
            return False # Fallo si no hay ejecuciones después de reintentos

        try:
            total_filled_value = 0.0
            total_filled_qty = 0.0
            for exec_trade in executions:
                qty = self._utils.safe_float_convert(exec_trade.get('execQty'), 0.0)
                price = self._utils.safe_float_convert(exec_trade.get('execPrice'), 0.0)
                if qty > 0 and price > 0:
                    total_filled_value += qty * price
                    total_filled_qty += qty

            if total_filled_qty <= 1e-12: print(f"WARN [LPT Sync]: Cantidad total llenada 0 para Orden ID: {order_id}."); return False
            avg_fill_price = self._utils.safe_division(total_filled_value, total_filled_qty, 0.0)
            if avg_fill_price <= 0: print(f"WARN [LPT Sync]: Precio promedio llenado 0 para Orden ID: {order_id}."); return False

            # Actualizar la posición lógica correspondiente
            details_to_update = {
                'entry_price': avg_fill_price,
                'size_contracts': total_filled_qty,
                'api_avg_fill_price': avg_fill_price,
                'api_filled_qty': total_filled_qty
            }
            update_success = self.update_position_details(position_id, details_to_update)

            if update_success:
                 price_prec = int(getattr(self._config, 'PRICE_PRECISION', 4))
                 qty_prec = int(getattr(self._config, 'DEFAULT_QTY_PRECISION', 3))
                 print(f"  -> SYNC OK [LPT {self.side.upper()}]: Pos ID ...{position_id[-6:]} actualizada. Fill Px: {avg_fill_price:.{price_prec}f}, Fill Qty: {total_filled_qty:.{qty_prec}f}")
                 return True
            else: return False

        except Exception as e_proc:
            print(f"ERROR [LPT {self.side.upper()} Sync]: Excepción procesando ejecuciones orden {order_id}: {e_proc}")
            traceback.print_exc(); return False


    # --- Visualización ---
    # (display_table SIN CAMBIOS)
    def display_table(self):
        if not self._positions: print(f"\n--- Tabla Posiciones Lógicas {self.side.upper()} ---\n(Vacía)\n" + "-" * 60); return
        data_for_df = []
        columns = ['ID', 'Entry Time', 'Entry Price', 'Size', 'Margin', 'Leverage', 'TP Price', 'API Order ID', 'API Fill Px', 'API Fill Qty']
        price_prec = 4; qty_prec = 3
        if self._config:
             try: price_prec = int(getattr(self._config, 'PRICE_PRECISION', 4)); qty_prec = int(getattr(self._config, 'DEFAULT_QTY_PRECISION', 3))
             except Exception: print("WARN [LPT Display]: Error obteniendo precisiones config."); price_prec = 4; qty_prec = 3
        for pos in self._positions:
            entry_ts = pos.get('entry_timestamp'); entry_ts_str = self._utils.format_datetime(entry_ts, '%Y-%m-%d %H:%M:%S') if self._utils and entry_ts else "N/A"
            data_for_df.append({
                'ID': str(pos.get('id', 'N/A'))[-6:], 'Entry Time': entry_ts_str,
                'Entry Price': f"{self._utils.safe_float_convert(pos.get('entry_price'), 0.0):.{price_prec}f}" if self._utils else pos.get('entry_price'),
                'Size': f"{self._utils.safe_float_convert(pos.get('size_contracts'), 0.0):.{qty_prec}f}" if self._utils else pos.get('size_contracts'),
                'Margin': f"{self._utils.safe_float_convert(pos.get('margin_usdt'), 0.0):.2f}" if self._utils else pos.get('margin_usdt'),
                'Leverage': f"{float(pos.get('leverage', 1.0)):.1f}x" if pos.get('leverage') else 'N/A',
                'TP Price': f"{self._utils.safe_float_convert(pos.get('take_profit_price'), 0.0):.{price_prec}f}" if self._utils and pos.get('take_profit_price') else 'N/A',
                'API Order ID': str(pos.get('api_order_id', 'N/A'))[-8:],
                'API Fill Px': f"{self._utils.safe_float_convert(pos.get('api_avg_fill_price'), 0.0):.{price_prec}f}" if self._utils and pos.get('api_avg_fill_price') else '-',
                'API Fill Qty': f"{self._utils.safe_float_convert(pos.get('api_filled_qty'), 0.0):.{qty_prec}f}" if self._utils and pos.get('api_filled_qty') else '-'
            })
        try:
             df = pd.DataFrame(data_for_df, columns=columns)
             print(f"\n--- Tabla Posiciones Lógicas {self.side.upper()} (Total: {len(self._positions)}) ---")
             if not df.empty: table_string = df.to_string(index=False, justify='right'); print(table_string); print("-" * (len(table_string.split('\n')[0]) if table_string else 60))
             else: print("(Tabla vacía)"); print("-" * 60)
        except Exception as e_df: print(f"ERROR [LPT Display]: Creando DataFrame: {e_df}"); print("-" * 60)

# =============== FIN ARCHIVO: core/strategy/logical_position_table.py (v1.1) ===============
