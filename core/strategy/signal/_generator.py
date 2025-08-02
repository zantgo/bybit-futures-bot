"""
Módulo Generador de Señales (Versión de Clase).

v3.0 (Recarga en Caliente):
- Se añade el método `initialize()` y un estado interno `_strategy_is_ready` para
  permitir que el generador de señales sea reseteado dinámicamente.
- `generate_signal` ahora reporta explícitamente cuando los indicadores
  aún se están calculando ("calentando").
- Se inyecta `memory_logger` para registrar cuando la estrategia está lista.

v2.0 (Refactor a Clase):
- Toda la lógica se encapsula en la clase SignalGenerator.
- Las dependencias (config, _data_handler, _rules) se gestionan a través
  del constructor, promoviendo la inyección de dependencias.

Su única responsabilidad sigue siendo coordinar el proceso de generación de señales:
1. Utiliza `_data_handler` para extraer y validar los datos de entrada.
2. Utiliza `_rules` para evaluar la lógica de la estrategia.
3. Utiliza `_data_handler` para construir el diccionario de salida final.
"""
from typing import Dict, Any
import pandas as pd
import numpy as np

# Dependencias del proyecto y del paquete que actúan como "librerías" internas
from . import _data_handler
from . import _rules
import config # Se mantiene la importación para tipado y como fallback

class SignalGenerator:
    """
    Orquesta la evaluación de indicadores técnicos para generar una señal de trading
    (BUY, SELL, HOLD), encapsulando la lógica de reglas y manejo de datos.
    """

    def __init__(self, dependencies: Dict[str, Any]):
        """
        Inicializa el SignalGenerator inyectando sus dependencias.
        
        Args:
            dependencies (Dict[str, Any]): Diccionario que debe contener:
                - 'config_module': El módulo de configuración del sistema.
                - 'memory_logger_module': La instancia del logger en memoria.
        """
        # Dependencias inyectadas para desacoplamiento y pruebas
        self._config = dependencies.get('config_module', config)
        self._memory_logger = dependencies.get('memory_logger_module')
        
        # Dependencias internas del paquete (se asume que no cambiarán)
        self._data_handler = _data_handler
        self._rules = _rules

        # --- INICIO DE LA MODIFICACIÓN ---
        # Inicializar el estado interno al crear la instancia.
        self.initialize()
        # --- FIN DE LA MODIFICACIÓN ---

    # --- INICIO DE LA MODIFICACIÓN ---
    def initialize(self):
        """
        Resetea el estado del generador de señales a su estado inicial.
        Esencial para la recarga de la estrategia en caliente.
        """
        self._strategy_is_ready = False
        if self._memory_logger:
            self._memory_logger.log("SignalGenerator: Estado reseteado. Esperando cálculo de indicadores iniciales...", "INFO")
    # --- FIN DE LA MODIFICACIÓN ---


    def generate_signal(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Punto de entrada principal. Orquesta la evaluación de indicadores técnicos
        para generar una señal de trading.

        La lógica de esta función es idéntica a la versión funcional, pero ahora
        utiliza las dependencias almacenadas en la instancia.

        Args:
            processed_data (dict): Un diccionario que contiene los indicadores
                                   calculados desde el TAManager.

        Returns:
            dict: Un diccionario completo representando la señal y el estado de
                  los indicadores en ese momento.
        """
        # 1. Extraer y validar los datos de entrada usando el manejador de datos
        (timestamp, price, ema, inc_pct, dec_pct, w_inc, w_dec) = self._data_handler.extract_indicator_values(processed_data)

        # Validación básica de datos. Si los datos crudos son inválidos, no se puede continuar.
        if pd.isna(timestamp) or pd.isna(price):
            signal = "HOLD_INVALID_DATA"
            reason = "Timestamp o Precio inválido en los datos procesados"
        
        # --- INICIO DE LA MODIFICACIÓN ---
        else:
            # Comprobar si todos los indicadores necesarios tienen valores numéricos válidos.
            indicators_are_valid = (
                pd.notna(ema) and np.isfinite(ema) and
                pd.notna(w_inc) and np.isfinite(w_inc) and
                pd.notna(w_dec) and np.isfinite(w_dec)
            )

            if not indicators_are_valid:
                # Si los indicadores aún no están listos, estamos en fase de "calentamiento".
                signal = "HOLD_INITIALIZING"
                reason = "Calculando indicadores iniciales..."
            
            # 2. Evaluar la lógica de la estrategia (si está habilitada en la config)
            elif self._config.STRATEGY_ENABLED:
                # Loguear un único mensaje la primera vez que la estrategia está lista.
                if not self._strategy_is_ready and self._memory_logger:
                    self._memory_logger.log("SignalGenerator: ¡Estrategia lista! Todos los indicadores iniciales han sido calculados.", "INFO")
                    self._strategy_is_ready = True

                # Delega la evaluación de las reglas al módulo de reglas
                signal, reason = self._rules.evaluate_strategy(price, ema, inc_pct, dec_pct, w_inc, w_dec)
            
            # Si la estrategia no está habilitada, se mantiene en HOLD por defecto.
            else:
                signal = "HOLD_STRATEGY_DISABLED"
                reason = "Estrategia desactivada en config.py"
        # --- FIN DE LA MODIFICACIÓN ---

        # 3. Construir el diccionario de salida final usando el manejador de datos
        return self._data_handler.build_signal_dict(
            timestamp, price, ema, inc_pct, dec_pct, w_inc, w_dec, signal, reason
        )