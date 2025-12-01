# ./core/strategy/pm/_transfer_executor.py

"""
Módulo dedicado a la ejecución de transferencias de fondos entre cuentas.
"""
import time
import traceback
from typing import Optional, Any

try:
    from core.logging import memory_logger
    from core.exchange import AbstractExchange
except ImportError:
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
    class AbstractExchange: pass

def execute_transfer(
    amount: float,
    from_account_side: str,
    exchange_adapter: AbstractExchange,
    config: Any
) -> float:
    """
    Orquesta la transferencia de un monto desde una cuenta operativa a la cuenta de profits.
    En modo Paper Trading, simula la transferencia.
    """
    memory_logger.log(f"TRANSFERENCIA -> Solicitud para transferir {amount:.4f} USDT desde {from_account_side.upper()}", level="INFO")

    if not isinstance(amount, (int, float)) or amount <= 1e-9:
        memory_logger.log("  -> Omitida: Monto inválido o cero.", level="DEBUG")
        return 0.0

    if config.BOT_CONFIG["PAPER_TRADING_MODE"]:
        memory_logger.log(f"  -> MODO PAPEL: Simulación de transferencia de {amount:.4f} USDT exitosa.", "WARN")
        return amount

    try:
        from_purpose = 'longs' if from_account_side == 'long' else 'shorts'
        to_purpose = 'profit'
        
        success = exchange_adapter.transfer_funds(
            amount=amount,
            from_purpose=from_purpose,
            to_purpose=to_purpose,
            coin="USDT"
        )
        
        if success:
            memory_logger.log(f"TRANSFERENCIA -> ÉXITO. Monto: {amount:.4f} USDT.", level="INFO")
            return amount
        else:
            memory_logger.log(f"TRANSFERENCIA -> FALLO.", level="ERROR")
            return 0.0

    except Exception as e:
        memory_logger.log(f"ERROR [Transfer Executor]: Excepción inesperada: {e}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")
        return 0.0
