# core/strategy/signal/_generator.py

"""
Módulo Generador de Señales (Versión de Clase).

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
        """
        # Dependencias inyectadas para desacoplamiento y pruebas
        self._config = dependencies.get('config_module', config)
        
        # Dependencias internas del paquete (se asume que no cambiarán)
        self._data_handler = _data_handler
        self._rules = _rules

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
    
        # 2. Evaluar la lógica de la estrategia (si está habilitada en la config)
        elif self._config.STRATEGY_ENABLED:
            # Delega la evaluación de las reglas al módulo de reglas
            signal, reason = self._rules.evaluate_strategy(price, ema, inc_pct, dec_pct, w_inc, w_dec)
    
        # Si la estrategia no está habilitada, se mantiene en HOLD por defecto.
        else:
            signal = "HOLD_STRATEGY_DISABLED"
            reason = "Estrategia desactivada en config.py"

        # 3. Construir el diccionario de salida final usando el manejador de datos
        return self._data_handler.build_signal_dict(
            timestamp, price, ema, inc_pct, dec_pct, w_inc, w_dec, signal, reason
        )