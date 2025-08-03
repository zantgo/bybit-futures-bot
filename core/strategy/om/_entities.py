"""
Módulo de Entidades de Dominio para el Operation Manager (OM).

v8.0 (Capital Lógico por Operación):
- La entidad `Operacion` ahora contiene una instancia de `LogicalBalances`
  para gestionar su propio capital lógico, importada desde el paquete PM.
"""
import datetime
# Eliminamos InitVar ya que no se usará en la clase normal
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# --- Dependencia Cruzada ---
# La Operación contiene entidades gestionadas por el Position Manager.
# Por lo tanto, importamos las entidades desde su módulo.
try:
    # El código original ya tenía estas importaciones, las mantenemos.
    from core.strategy.pm._entities import LogicalPosition, LogicalBalances
except ImportError:
    # Fallback para permitir análisis estático y evitar errores de importación circular
    # si los archivos se cargan en un orden inesperado.
    class LogicalPosition: pass
    class LogicalBalances: pass

# --- Entidad de Operación Única ---

# --- INICIO DE LA MODIFICACIÓN: La dataclass no es mutable y dificulta añadir atributos dinámicos.
# Se convierte a una clase normal para tener un control explícito sobre la inicialización y los métodos.
# @dataclass (COMENTADO)
class Operacion:
# --- FIN DE LA MODIFICACIÓN ---
    """
    Representa una única Operación Estratégica configurable. Contiene toda la
    lógica de estado, condiciones y parámetros de trading. Sigue un ciclo de vida
    ACTIVA <-> PAUSADA -> DETENIDA.
    """
    # --- INICIO DE LA MODIFICACIÓN: Se crea un constructor __init__ para manejar la inicialización de atributos
    # que antes era gestionada por @dataclass.
    def __init__(self, id: str):
        # --- Identificación y Estado ---
        self.id: str = id
        self.estado: str = 'DETENIDA'  # Valores: 'DETENIDA', 'EN_ESPERA', 'ACTIVA', 'PAUSADA'

        # --- Condición de Entrada ---
        self.tipo_cond_entrada: Optional[str] = 'MARKET'
        self.valor_cond_entrada: Optional[float] = 0.0
        
        # --- Parámetros de Trading ---
        self.tendencia: Optional[str] = None # Valores: 'LONG_ONLY' o 'SHORT_ONLY'
        self.tamaño_posicion_base_usdt: float = 1.0
        self.max_posiciones_logicas: int = 5
        self.apalancamiento: float = 10.0
        self.sl_posicion_individual_pct: float = 10.0
        self.tsl_activacion_pct: float = 0.4
        self.tsl_distancia_pct: float = 0.1

        # --- Condiciones de Salida (Límites) ---
        self.tsl_roi_activacion_pct: Optional[float] = None
        self.tsl_roi_distancia_pct: Optional[float] = None
        self.sl_roi_pct: Optional[float] = None
        self.tiempo_maximo_min: Optional[int] = None
        self.max_comercios: Optional[int] = None
        self.tipo_cond_salida: Optional[str] = None
        self.valor_cond_salida: Optional[float] = None
        self.accion_al_finalizar: str = 'PAUSAR'  # Valores: 'PAUSAR', 'DETENER'

        # --- Estado Dinámico ---
        self.capital_inicial_usdt: float = 0.0
        self.pnl_realizado_usdt: float = 0.0
        self.comercios_cerrados_contador: int = 0
        self.tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
        self.posiciones_activas: Dict[str, List[LogicalPosition]] = {'long': [], 'short': []}

        # Campos para el estado dinámico del TSL por ROI
        self.tsl_roi_activo: bool = False
        self.tsl_roi_peak_pct: float = 0.0
        
        # --- INICIO DE LA MODIFICACIÓN: Añadir comisiones y balances ---
        # Se añade el nuevo atributo para almacenar el total de comisiones.
        # Esto soluciona el AttributeError al asegurar que el atributo siempre exista.
        self.comisiones_totales_usdt: float = 0.0
        # Se inicializa la entidad de balances lógicos.
        self.balances: LogicalBalances = LogicalBalances()
        # --- FIN DE LA MODIFICACIÓN ---
    # --- FIN DE LA MODIFICACIÓN del constructor __init__ ---

    def reset(self):
        """Resetea el estado dinámico de la operación a sus valores por defecto."""
        self.estado = 'DETENIDA'
        self.capital_inicial_usdt = 0.0
        self.pnl_realizado_usdt = 0.0
        self.comercios_cerrados_contador = 0
        self.tiempo_inicio_ejecucion = None
        self.tsl_roi_activo = False
        self.tsl_roi_peak_pct = 0.0
        
        # --- INICIO DE LA MODIFICACIÓN: Resetear comisiones y balances ---
        # Se añade el reseteo del nuevo atributo de comisiones para que cada
        # ciclo de ejecución de la operación comience desde cero.
        self.comisiones_totales_usdt = 0.0
        # Se asegura que los balances lógicos también se reseteen.
        if hasattr(self, 'balances') and self.balances:
            # Asumimos que LogicalBalances tiene un método reset()
            if hasattr(self.balances, 'reset'):
                self.balances.reset()
            else: # Fallback por si no lo tuviera
                self.balances = LogicalBalances()
        # --- FIN DE LA MODIFICACIÓN ---