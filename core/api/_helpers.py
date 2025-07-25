"""
Módulo de funciones auxiliares para el paquete de la API.

Contiene utilidades compartidas por los módulos de datos de mercado,
cuenta y trading para evitar la duplicación de código y las
dependencias circulares.
"""
from typing import Optional, Dict
from decimal import Decimal, InvalidOperation
import sys
import os

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias con rutas absolutas desde la raíz del proyecto
try:
    from core.logging import memory_logger
except ImportError as e:
    # Este print es aceptable, ya que el logger no estaría disponible para loguear su propio error de importación.
    print(f"ERROR [API Helpers Import]: No se pudo importar módulo necesario: {e}")
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

# --- Funciones Auxiliares ---

def _get_qty_precision_from_step(step_str: str) -> int:
    """
    Calcula el número de decimales a partir del qtyStep usando el tipo Decimal
    para mayor robustez y precisión.
    """
    if not isinstance(step_str, str) or not step_str.strip():
        memory_logger.log(f"WARN [_get_qty_precision]: qtyStep inválido o vacío ('{step_str}'). Asumiendo 0 decimales.", level="WARN")
        return 0
    try:
        # Usar Decimal para manejar correctamente todos los formatos numéricos
        step_decimal = Decimal(step_str)

        # Si el valor no es finito (inf, nan) o es cero, no se puede determinar la precisión.
        if not step_decimal.is_finite():
            memory_logger.log(f"WARN [_get_qty_precision]: qtyStep no es un número finito ('{step_str}'). Asumiendo 0.", level="WARN")
            return 0

        # El exponente del Decimal nos da directamente el número de decimales.
        exponent = step_decimal.as_tuple().exponent
        if exponent < 0:
            return abs(exponent)
        else:
            return 0

    except InvalidOperation:
        memory_logger.log(f"WARN [_get_qty_precision]: No se pudo convertir qtyStep ('{step_str}') a Decimal. Asumiendo 0.", level="WARN")
        return 0

def _handle_api_error_generic(response: Optional[Dict], operation_tag: str) -> bool:
    """Maneja respuestas de error comunes de la API Bybit v5."""
    if response and response.get('retCode') == 0:
        return False # No hubo error

    ret_code = response.get('retCode', -1) if response else -1
    ret_msg = response.get('retMsg', 'No Response') if response else 'No Response'
    
    memory_logger.log(f"ERROR API [{operation_tag}]: Código={ret_code}, Mensaje='{ret_msg}'", level="ERROR")
    if ret_code in (110007, 180024): memory_logger.log("    -> Sugerencia: ¿Fondos/Margen insuficiente?", level="DEBUG")
    elif ret_code in (10001, 110017): memory_logger.log("    -> Sugerencia: ¿Error en parámetros?", level="DEBUG")
    elif ret_code == 110043: memory_logger.log("    -> Sugerencia: ¿Qty inválida / ReduceOnly / Apalancamiento ya seteado?", level="DEBUG")
    elif ret_code == 110041: memory_logger.log("    -> Sugerencia: ¿positionIdx vs modo?", level="DEBUG")
    elif ret_code == 180034: memory_logger.log("    -> Sugerencia: ¿Qty fuera de límites?", level="DEBUG")
    elif ret_code == 110020: memory_logger.log("    -> Sugerencia: ¿Posición opuesta (One-Way)?", level="DEBUG")
    elif ret_code == 10006: memory_logger.log("    -> Sugerencia: ¿Error de Conexión / Timeout?", level="DEBUG")
    elif ret_code == 10002: memory_logger.log("    -> Sugerencia: ¿Parámetro Inválido?", level="DEBUG")
    elif ret_code == 110001: memory_logger.log("    -> Sugerencia: ¿Orden/Posición no encontrada?", level="DEBUG")
    
    return True # Sí hubo error