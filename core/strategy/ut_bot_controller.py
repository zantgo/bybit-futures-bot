# =============== INICIO ARCHIVO: core/strategy/ut_bot_controller.py (NUEVO) ===============
"""
Módulo del Controlador de Estrategia de Alto Nivel (UT Bot Alerts).

Este módulo es responsable de:
1.  Recibir ticks de precio en tiempo real desde el event_processor.
2.  Agregar (resample) estos ticks en barras de tiempo OHLC (Open, High, Low, Close)
    según el intervalo definido en la configuración (UT_BOT_SIGNAL_INTERVAL_SECONDS).
3.  Calcular la señal del indicador "UT Bot Alerts" sobre estas barras de tiempo.
4.  Proporcionar la última señal generada ("BUY", "SELL", "HOLD") al runner principal
    para que este pueda gestionar el estado de alto nivel del bot (régimen long/short).

Diseñado para ejecutarse en su propio hilo para no bloquear el procesamiento de ticks.
"""
import time
import datetime
import traceback
import pandas as pd
import pandas_ta as ta # Dependencia para calcular ATR, debe estar en requirements.txt
import numpy as np
from typing import Optional, Dict, Any, List

# --- Definición de la Clase UTBotController ---

class UTBotController:
    """
    Gestiona la lógica de la estrategia de alto nivel UT Bot.
    """
    def __init__(self, config_module: Any, utils_module: Any):
        """
        Inicializa el controlador del UT Bot.

        Args:
            config_module (Any): El módulo de configuración del bot (config.py).
            utils_module (Any): El módulo de utilidades del bot (core/utils.py).
        """
        print("[UT Bot Controller] Inicializando...")

        if not config_module or not utils_module:
            raise ValueError("UTBotController requiere los módulos 'config' y 'utils'.")

        self._config = config_module
        self._utils = utils_module

        # --- Parámetros de la Estrategia ---
        self._key_value: float = float(getattr(self._config, 'UT_BOT_KEY_VALUE', 1.0))
        self._atr_period: int = int(getattr(self._config, 'UT_BOT_ATR_PERIOD', 10))
        self._signal_interval_seconds: int = int(getattr(self._config, 'UT_BOT_SIGNAL_INTERVAL_SECONDS', 3600))
        print(f"  - Parámetros UT Bot: KeyValue={self._key_value}, ATR Period={self._atr_period}")
        print(f"  - Intervalo de Señal: {self._signal_interval_seconds} segundos")

        # --- Buffers y Estado Interno ---
        self._tick_buffer: List[Dict[str, Any]] = []
        self._ohlc_data: pd.DataFrame = pd.DataFrame(columns=['open', 'high', 'low', 'close'])
        self._last_aggregation_time: Optional[datetime.datetime] = None
        self._latest_signal: str = "HOLD" # Señal inicial por defecto

        print("[UT Bot Controller] Inicializado.")

    def add_tick(self, price: float, timestamp: datetime.datetime):
        """
        Añade un nuevo tick de precio al buffer interno.
        Este método es llamado desde el event_processor en cada tick.

        Args:
            price (float): El precio del tick.
            timestamp (datetime.datetime): El timestamp del tick.
        """
        if self._last_aggregation_time is None:
            # En el primer tick, establece el tiempo de inicio para la primera barra.
            self._last_aggregation_time = timestamp

        self._tick_buffer.append({'price': price, 'timestamp': timestamp})

    def _aggregate_ticks_to_ohlc(self) -> bool:
        """
        Procesa el buffer de ticks para crear una nueva barra OHLC si ha pasado
        el intervalo de tiempo definido.
        
        Returns:
            bool: True si se generó una nueva barra OHLC, False en caso contrario.
        """
        if not self._tick_buffer:
            return False # No hay nada que agregar

        # El timestamp del último tick en el buffer determina el tiempo actual.
        current_time = self._tick_buffer[-1]['timestamp']

        # Comprueba si ha pasado el intervalo para crear una nueva barra.
        if (current_time - self._last_aggregation_time).total_seconds() >= self._signal_interval_seconds:
            
            # Convierte el buffer a un DataFrame para un fácil procesamiento
            df_buffer = pd.DataFrame(self._tick_buffer)
            
            # Calcula OHLC de los ticks en el buffer
            open_price = df_buffer['price'].iloc[0]
            high_price = df_buffer['price'].max()
            low_price = df_buffer['price'].min()
            close_price = df_buffer['price'].iloc[-1]
            bar_timestamp = self._last_aggregation_time # El timestamp de la barra es el inicio del período

            new_bar = pd.DataFrame([{
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price
            }], index=[bar_timestamp])
            
            # Concatena la nueva barra al DataFrame principal de OHLC
            self._ohlc_data = pd.concat([self._ohlc_data, new_bar])
            
            # Limpia el buffer de ticks y actualiza el tiempo de la última agregación
            self._tick_buffer = []
            self._last_aggregation_time = current_time
            
            print(f"DEBUG [UT Bot Controller]: Nueva barra OHLC generada a las {bar_timestamp}. Total barras: {len(self._ohlc_data)}")
            return True

        return False

    def _calculate_ut_bot_signal(self):
        """
        Calcula la señal del UT Bot usando la lógica del indicador sobre el
        DataFrame de datos OHLC.
        """
        if len(self._ohlc_data) < self._atr_period + 1:
            # No hay suficientes datos para calcular el ATR y la señal de forma fiable
            self._latest_signal = "HOLD"
            return

        data = self._ohlc_data.copy()

        try:
            # 1. Calcular ATR usando pandas_ta
            atr_col_name = f'ATRr_{self._atr_period}'
            data.ta.atr(length=self._atr_period, append=True)
            
            if atr_col_name not in data.columns:
                 print(f"ERROR [UT Bot Calc]: La columna ATR '{atr_col_name}' no fue creada por pandas_ta.")
                 self._latest_signal = "HOLD"
                 return

            data.rename(columns={atr_col_name: 'atr'}, inplace=True)
            data['nLoss'] = self._key_value * data['atr']
            data.fillna(0, inplace=True) # Rellenar NaNs para evitar errores en el bucle

            # 2. Lógica secuencial del Trailing Stop
            data['xATRTrailingStop'] = 0.0
            data['pos'] = 0
            
            # Itera desde la segunda fila para tener siempre un i-1
            for i in range(1, len(data)):
                close_i = data['close'].iloc[i]
                close_i_minus_1 = data['close'].iloc[i-1]
                xATRTrailingStop_i_minus_1 = data['xATRTrailingStop'].iloc[i-1]
                nLoss_i = data['nLoss'].iloc[i]

                # Lógica del Trailing Stop
                if close_i > xATRTrailingStop_i_minus_1 and close_i_minus_1 > xATRTrailingStop_i_minus_1:
                    data.iat[i, data.columns.get_loc('xATRTrailingStop')] = max(xATRTrailingStop_i_minus_1, close_i - nLoss_i)
                elif close_i < xATRTrailingStop_i_minus_1 and close_i_minus_1 < xATRTrailingStop_i_minus_1:
                    data.iat[i, data.columns.get_loc('xATRTrailingStop')] = min(xATRTrailingStop_i_minus_1, close_i + nLoss_i)
                elif close_i > xATRTrailingStop_i_minus_1:
                    data.iat[i, data.columns.get_loc('xATRTrailingStop')] = close_i - nLoss_i
                else:
                    data.iat[i, data.columns.get_loc('xATRTrailingStop')] = close_i + nLoss_i

            # 3. Determinar la señal final (cruce)
            above_cond = (data['close'].shift(1) < data['xATRTrailingStop'].shift(1)) & (data['close'] > data['xATRTrailingStop'])
            below_cond = (data['close'].shift(1) > data['xATRTrailingStop'].shift(1)) & (data['close'] < data['xATRTrailingStop'])
            
            # Obtener la señal de la última barra
            if above_cond.iloc[-1]:
                self._latest_signal = "BUY"
            elif below_cond.iloc[-1]:
                self._latest_signal = "SELL"
            else:
                # Si no hay cruce, mantenemos la señal anterior.
                # Para evitar estados "pegajosos", es mejor que vuelva a HOLD si no hay señal explícita.
                self._latest_signal = "HOLD" 
            
            print(f"INFO [UT Bot Controller]: Nueva señal de alto nivel generada: {self._latest_signal}")

        except Exception as e:
            print(f"ERROR [UT Bot Controller]: Excepción calculando señal UT Bot: {e}")
            traceback.print_exc()
            self._latest_signal = "HOLD" # Fallback a HOLD en caso de error

    def get_latest_signal(self) -> str:
        """
        Orquesta la agregación y el cálculo, y devuelve la última señal generada.
        Este es el método principal que será llamado por el hilo del controlador.
        
        Returns:
            str: La última señal ("BUY", "SELL", "HOLD").
        """
        # Intenta agregar los ticks acumulados a una nueva barra OHLC
        new_bar_generated = self._aggregate_ticks_to_ohlc()

        if new_bar_generated:
            # Si se generó una nueva barra, recalcula la señal del UT Bot
            self._calculate_ut_bot_signal()
        
        # Devuelve la última señal almacenada (sea nueva o la anterior)
        return self._latest_signal

# =============== FIN ARCHIVO: core/strategy/ut_bot_controller.py (NUEVO) ===============