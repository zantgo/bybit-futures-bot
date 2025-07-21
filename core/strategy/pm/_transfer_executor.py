"""
Módulo dedicado a la ejecución de transferencias de fondos entre cuentas.

Esta lógica ha sido extraída de PositionExecutor para cumplir con el Principio
de Responsabilidad Única (SRP). Su única responsabilidad es manejar la
mecánica de las transferencias, ya sea a través de la API en modo live o
mediante simulación en modo backtest.
"""
import time
import traceback
from typing import Optional, Any

# --- Dependencias del Proyecto ---
try:
    from core.logging import memory_logger
except ImportError:
    # Fallback si las dependencias no están disponibles durante el desarrollo o pruebas
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

# --- Constantes de Configuración de Transferencia ---
MAX_TRANSFER_RETRIES = 1
TRANSFER_RETRY_DELAY_SECONDS = 0.2
TRANSFER_API_PRECISION = 4 # Precisión decimal para el monto de la transferencia

def execute_transfer(
    amount: float,
    from_account_side: str,
    # --- Dependencias Inyectadas ---
    is_live_mode: bool,
    config: Any,
    live_manager: Optional[Any],
    live_operations: Optional[Any],
    balance_manager: Optional[Any]
) -> float:
    """
    Orquesta la transferencia de un monto desde una cuenta operativa a la cuenta de profits.

    Args:
        amount (float): La cantidad de USDT a transferir.
        from_account_side (str): El lado desde el cual se origina el profit ('long' o 'short').
        is_live_mode (bool): Flag que indica si se debe ejecutar contra la API real.
        config (Any): Módulo de configuración del bot.
        live_manager (Optional[Any]): Gestor de conexiones para realizar la llamada API.
        live_operations (Optional[Any]): Módulo de operaciones API.
        balance_manager (Optional[Any]): Gestor de balances para simulación en backtest.

    Returns:
        float: La cantidad que fue efectivamente transferida (0.0 si falló).
    """
    memory_logger.log(f"TRANSFERENCIA -> Solicitud para transferir {amount:.{TRANSFER_API_PRECISION}f} USDT desde {from_account_side.upper()}", level="INFO")

    if not isinstance(amount, (int, float)) or amount <= 1e-9:
        memory_logger.log("  -> Omitida: Monto inválido o cero.", level="DEBUG")
        return 0.0

    transferred_amount = 0.0
    try:
        if is_live_mode:
            transferred_amount = _execute_live_transfer(
                amount=amount,
                from_account_side=from_account_side,
                config=config,
                live_manager=live_manager
            )
        else:
            transferred_amount = _execute_simulated_transfer(
                amount=amount,
                from_account_side=from_account_side,
                balance_manager=balance_manager
            )
    except Exception as e:
        memory_logger.log(f"ERROR [Transfer Executor]: Excepción inesperada: {e}", level="ERROR")
        traceback.print_exc()
        transferred_amount = 0.0

    if transferred_amount > 0:
        memory_logger.log(f"TRANSFERENCIA -> ÉXITO. Monto: {transferred_amount:.{TRANSFER_API_PRECISION}f} USDT.", level="INFO")
    else:
        memory_logger.log(f"TRANSFERENCIA -> FALLO.", level="ERROR")
        
    return transferred_amount

def _execute_live_transfer(
    amount: float,
    from_account_side: str,
    config: Any,
    live_manager: Optional[Any]
) -> float:
    """Lógica específica para ejecutar una transferencia real a través de la API."""
    if not all([live_manager, config]):
        memory_logger.log("ERROR [Live Transfer]: Dependencias (live_manager, config) no disponibles.", level="ERROR")
        return 0.0

    # Determinar cuentas de origen y destino
    from_acc_name = getattr(config, 'ACCOUNT_LONGS' if from_account_side == 'long' else 'ACCOUNT_SHORTS', None)
    to_acc_name = getattr(config, 'ACCOUNT_PROFIT', None)
    if not from_acc_name or not to_acc_name:
        memory_logger.log("ERROR [Live Transfer]: Cuentas de origen/destino no definidas en config.", level="ERROR")
        return 0.0

    # Obtener UIDs
    loaded_uids = getattr(config, 'LOADED_UIDS', {})
    from_uid = loaded_uids.get(from_acc_name)
    to_uid = loaded_uids.get(to_acc_name)
    if not from_uid or not to_uid:
        memory_logger.log(f"ERROR [Live Transfer]: UIDs no encontrados para las cuentas '{from_acc_name}' -> '{to_acc_name}'.", level="ERROR")
        return 0.0

    try:
        from_uid_int = int(from_uid)
        to_uid_int = int(to_uid)
    except ValueError:
        memory_logger.log(f"ERROR [Live Transfer]: UIDs inválidos (no son enteros). From: '{from_uid}', To: '{to_uid}'.", level="ERROR")
        return 0.0

    amount_str = f"{amount:.{TRANSFER_API_PRECISION}f}"
    
    # Obtener sesión API para la llamada
    main_acc_for_call = getattr(config, 'ACCOUNT_MAIN', 'main')
    session = live_manager.get_client(main_acc_for_call) or live_manager.get_client(from_acc_name)
    if not session:
        memory_logger.log(f"ERROR [Live Transfer]: No se pudo obtener una sesión API válida para realizar la transferencia.", level="ERROR")
        return 0.0

    for attempt in range(MAX_TRANSFER_RETRIES + 1):
        memory_logger.log(f"  -> Intento de transferencia API #{attempt + 1}/{MAX_TRANSFER_RETRIES + 1}...", level="DEBUG")
        response = None
        try:
            # Asumimos que create_universal_transfer existe en el live_manager
            response = session.create_universal_transfer(
                transferId=f"bot_{int(time.time()*1000)}", # Bybit requiere un transferId único
                coin="USDT",
                amount=amount_str,
                fromMemberId=from_uid_int,
                toMemberId=to_uid_int,
                fromAccountType=getattr(config, 'UNIVERSAL_TRANSFER_FROM_TYPE', 'UNIFIED'),
                toAccountType=getattr(config, 'UNIVERSAL_TRANSFER_TO_TYPE', 'UNIFIED')
            )
        except Exception as api_call_err:
            memory_logger.log(f"    -> Excepción en llamada API: {api_call_err}", level="ERROR")
            if attempt < MAX_TRANSFER_RETRIES:
                time.sleep(TRANSFER_RETRY_DELAY_SECONDS)
                continue
            else:
                break # Salir del bucle en el último intento

        if response and response.get('retCode') == 0:
            transfer_id = response.get('result', {}).get('transferId', 'N/A')
            status = response.get('result', {}).get('status', '?')
            memory_logger.log(f"    -> ÉXITO API. ID: {transfer_id}, Estado: {status}", level="DEBUG")
            return amount
        
        # Manejo de errores de la API
        ret_code = response.get('retCode', -1) if response else -1
        ret_msg = response.get('retMsg', 'No Response') if response else 'No Response'
        memory_logger.log(f"    -> FALLO API. Código={ret_code}, Mensaje='{ret_msg}'", level="WARN")
        
        non_retryable_codes = [131200, 131001, 131228, 10003, 10005, 10019, 131214, 131204, 131206, 131210]
        if ret_code in non_retryable_codes:
            memory_logger.log("      -> Error no recuperable, cancelando reintentos.", level="WARN")
            break
            
        if attempt < MAX_TRANSFER_RETRIES:
            time.sleep(TRANSFER_RETRY_DELAY_SECONDS)

    memory_logger.log(f"  -> Fallo API después de {MAX_TRANSFER_RETRIES + 1} intentos.", level="ERROR")
    return 0.0

def _execute_simulated_transfer(
    amount: float,
    from_account_side: str,
    balance_manager: Optional[Any]
) -> float:
    """Lógica específica para simular una transferencia en modo backtest."""
    if not balance_manager:
        memory_logger.log("ERROR [Simulated Transfer]: Gestor de balances no disponible.", level="ERROR")
        return 0.0

    memory_logger.log("  -> Ejecutando transferencia simulada (backtest)...", level="DEBUG")
    success = balance_manager.simulate_profit_transfer(from_account_side, amount)
    
    if success:
        memory_logger.log(f"    -> ÉXITO. {amount:.{TRANSFER_API_PRECISION}f} USDT reflejado en BalanceManager.", level="DEBUG")
        return amount
    else:
        memory_logger.log("    -> FALLO.", level="ERROR")
        return 0.0