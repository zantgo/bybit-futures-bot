"""
Módulo para el Cierre de Posiciones.

Su única responsabilidad es contener la lógica para cerrar posiciones de trading
existentes, ya sea de forma masiva para un símbolo o individualmente por lado.
"""
from typing import Optional

# --- Dependencias del Proyecto ---
import config
from connection import manager as connection_manager
from core.logging import memory_logger
# Importamos funciones de módulos "primos" y "hermanos"
from .._account import get_active_position_details_api
from ._placing import place_market_order

def close_all_symbol_positions(symbol: str, account_name: Optional[str] = None) -> bool:
    """
    Intenta cerrar todas las posiciones activas (Long y Short) para un símbolo
    en una cuenta determinada.

    Args:
        symbol (str): El símbolo del instrumento.
        account_name (Optional[str]): Cuenta específica a usar. Si es None, se usará la principal.

    Returns:
        bool: True si todas las órdenes de cierre se enviaron con éxito, False en caso contrario.
    """
    if not (connection_manager and config and get_active_position_details_api):
        memory_logger.log("ERROR [Close All Positions]: Dependencias no disponibles.", level="ERROR")
        return False
        
    # Usamos `get_session_for_operation` para obtener la cuenta correcta.
    # Si `account_name` es None, se usará la principal por defecto.
    session, target_account = connection_manager.get_session_for_operation(
        purpose='general', specific_account=account_name
    )
    if not session:
        memory_logger.log(f"ERROR [Close All Positions]: No se pudo obtener sesión API válida (solicitada: {account_name}).", level="ERROR")
        return False
        
    memory_logger.log(f"Intentando cerrar TODAS las posiciones para {symbol} en cuenta '{target_account}'...", level="INFO")

    # Obtenemos las posiciones activas de la cuenta objetivo
    active_positions = get_active_position_details_api(symbol=symbol, account_name=target_account)
    if active_positions is None:
        memory_logger.log(f"ERROR [Close All Positions]: No se pudieron obtener posiciones para '{target_account}'.", level="ERROR")
        return False
    if not active_positions:
        memory_logger.log(f"INFO [Close All Positions]: No hay posiciones activas para {symbol} en '{target_account}'.", level="INFO")
        return True

    all_close_attempts_successful = True
    # Iteramos sobre las posiciones y enviamos órdenes de cierre para cada una
    for pos in active_positions:
        pos_side = pos.get('side') # 'Buy' o 'Sell'
        pos_size_str = pos.get('size', '0')
        pos_idx = pos.get('positionIdx', 0)
        
        if not pos_side or float(pos_size_str) <= 1e-9:
            continue

        # La orden de cierre es del lado opuesto
        close_order_side = "Sell" if pos_side == "Buy" else "Buy"
        
        memory_logger.log(f"-> Intentando cerrar {pos_side} PosIdx={pos_idx} (Tamaño: {pos_size_str}) en '{target_account}'...", level="DEBUG")
        
        # Reutilizamos la función `place_market_order` para cerrar
        close_response = place_market_order(
            symbol=symbol,
            side=close_order_side,
            quantity=pos_size_str,
            reduce_only=True,
            position_idx=pos_idx,
            account_name=target_account
        )
        if not close_response or close_response.get('retCode') != 0:
            memory_logger.log(f"FALLO al intentar cerrar {pos_side} PosIdx={pos_idx} en '{target_account}'.", level="ERROR")
            all_close_attempts_successful = False

    if all_close_attempts_successful:
        memory_logger.log(f"ÉXITO [Close All Positions]: Órdenes de cierre enviadas para todas las posiciones de {symbol} en '{target_account}'.", level="INFO")
    else:
        memory_logger.log(f"WARN [Close All Positions]: Fallaron algunos intentos de cierre para {symbol}. Verifica los logs.", level="WARN")
        
    return all_close_attempts_successful

def close_position_by_side(symbol: str, side_to_close: str, account_name: Optional[str] = None) -> bool:
    """
    Intenta cerrar la posición activa para un lado específico ('Buy' para Long, 'Sell' para Short).

    Args:
        symbol (str): El símbolo del instrumento.
        side_to_close (str): El lado de la posición a cerrar ('Buy' o 'Sell').
        account_name (Optional[str]): Cuenta específica a usar. Si es None, se usará la principal.

    Returns:
        bool: True si la orden de cierre se envió con éxito o no había posición, False si falló.
    """
    if not (connection_manager and config and get_active_position_details_api):
        memory_logger.log("ERROR [Close Position By Side]: Dependencias no disponibles.", level="ERROR")
        return False
    if side_to_close not in ["Buy", "Sell"]:
        memory_logger.log(f"ERROR [Close Position By Side]: Lado a cerrar inválido '{side_to_close}'. Debe ser 'Buy' o 'Sell'.", level="ERROR")
        return False
        
    # Obtenemos la sesión para la cuenta objetivo
    session, target_account = connection_manager.get_session_for_operation(
        purpose='general', specific_account=account_name
    )
    if not session:
        memory_logger.log(f"ERROR [Close Position By Side]: No se pudo obtener sesión API válida (solicitada: {account_name}).", level="ERROR")
        return False
        
    memory_logger.log(f"Buscando posición del lado '{side_to_close}' para {symbol} en cuenta '{target_account}'...", level="INFO")

    active_positions = get_active_position_details_api(symbol=symbol, account_name=target_account)
    if active_positions is None:
        memory_logger.log(f"ERROR [Close Position By Side]: No se pudieron obtener posiciones.", level="ERROR")
        return False

    # Encontrar la posición específica que coincide con el lado
    position_to_close = next((pos for pos in active_positions if pos.get('side') == side_to_close), None)
    
    if not position_to_close:
        memory_logger.log(f"INFO [Close Position By Side]: No se encontró posición activa del lado '{side_to_close}'.", level="INFO")
        return True # Consideramos éxito si no hay nada que cerrar

    pos_size_str = position_to_close.get('size', '0')
    pos_idx = position_to_close.get('positionIdx', 0)
    # La orden de cierre es del lado opuesto
    close_order_side = "Sell" if side_to_close == "Buy" else "Buy"

    memory_logger.log(f"-> Intentando cerrar posición {side_to_close} (PosIdx={pos_idx}, Tamaño: {pos_size_str})...", level="DEBUG")
    
    # Reutilizamos la función `place_market_order`
    close_response = place_market_order(
        symbol=symbol,
        side=close_order_side,
        quantity=pos_size_str,
        reduce_only=True,
        position_idx=pos_idx,
        account_name=target_account
    )
    
    if close_response and close_response.get('retCode') == 0:
        memory_logger.log(f"ÉXITO [Close Position By Side]: Orden de cierre para el lado '{side_to_close}' enviada.", level="INFO")
        return True
    else:
        memory_logger.log(f"FALLO [Close Position By Side]: No se pudo enviar orden de cierre para el lado '{side_to_close}'.", level="ERROR")
        return False