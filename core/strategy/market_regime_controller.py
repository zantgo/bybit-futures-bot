# =============== INICIO ARCHIVO: core/strategy/market_regime_controller.py (CORREGIDO Y MEJORADO v2.3) ===============
"""
Módulo del Controlador de Régimen de Mercado (Estrategia de Alto Nivel v2.3).

Este módulo es responsable de:
1.  Agregar ticks en barras de tiempo OHLC.
2.  Calcular la tendencia principal usando Supertendencia.
3.  Calcular las zonas de operación óptimas usando Bandas de Bollinger.
4.  Filtrar mercados laterales sin volatilidad usando el Ancho de Banda de Bollinger (BBW).
5.  Proporcionar un contexto de mercado compuesto (ej. "TENDENCIA ALCISTA CERCA DE SOPORTE")
    para filtrar las señales de bajo nivel de forma inteligente.

v2.3:
- Corregido FutureWarning de pandas al usar .replace() con inplace=True.
v2.2:
- Corregido AttributeError al llamar a data.ta.bbw().
- Optimizado el cálculo de indicadores para mayor eficiencia y robustez.
- Mejorado el manejo de nombres de columna generados por pandas-ta.
- Añadida mayor seguridad en la validación de datos de indicadores.
"""
import time
import datetime
import traceback
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Optional, Dict, Any, List

class MarketRegimeController:
    """
    Gestiona la lógica de la estrategia de alto nivel (Régimen de Mercado).
    """
    def __init__(self, config_module: Any, utils_module: Any):
        """
        Inicializa el Controlador de Régimen de Mercado.
        """
        print("[Market Regime Controller v2.3] Inicializando...")

        if not config_module or not utils_module:
            raise ValueError("MarketRegimeController requiere 'config' y 'utils'.")

        self._config = config_module
        self._utils = utils_module

        # Cargar todos los parámetros de configuración
        self._interval_seconds: int = int(getattr(self._config, 'MARKET_REGIME_INTERVAL_SECONDS', 300))
        
        # Supertendencia
        self._st_atr_period: int = int(getattr(self._config, 'MARKET_REGIME_SUPERTREND_ATR_PERIOD', 10))
        self._st_atr_mult: float = float(getattr(self._config, 'MARKET_REGIME_SUPERTREND_ATR_MULTIPLIER', 3.0))
        
        # Bandas de Bollinger y Ancho de Banda
        self._bb_length: int = int(getattr(self._config, 'MARKET_REGIME_BBANDS_LENGTH', 20))
        self._bb_std: float = float(getattr(self._config, 'MARKET_REGIME_BBANDS_STD', 2.0))
        self._bb_zone_pct: float = float(getattr(self._config, 'MARKET_REGIME_BBANDS_ZONE_PCT', 0.15))
        self._bbwp_chop_threshold: float = float(getattr(self._config, 'MARKET_REGIME_BBWP_CHOP_THRESHOLD', 0.1))

        print(f"  - Intervalo de Régimen: {self._interval_seconds} segundos")
        print(f"  - Supertendencia: ATR({self._st_atr_period}), Multiplicador({self._st_atr_mult})")
        print(f"  - Bandas Bollinger: Length({self._bb_length}), StdDev({self._bb_std}), Zona({self._bb_zone_pct*100}%)")
        print(f"  - Filtro Chop (BBW): Umbral({self._bbwp_chop_threshold*100}%)")

        # Estado interno
        self._tick_buffer: List[Dict[str, Any]] = []
        self._ohlc_data: pd.DataFrame = pd.DataFrame(columns=['open', 'high', 'low', 'close'])
        self._last_aggregation_time: Optional[datetime.datetime] = None
        
        self._market_regime: Dict[str, Any] = {
            "context": "UNKNOWN",
            "trend": "UNKNOWN",
            "zone": "UNKNOWN",
            "volatility": "UNKNOWN"
        }

        print("[Market Regime Controller v2.3] Inicializado.")

    def add_tick(self, price: float, timestamp: datetime.datetime):
        if self._last_aggregation_time is None:
            self._last_aggregation_time = timestamp
        self._tick_buffer.append({'price': price, 'timestamp': timestamp})

    def _aggregate_ticks_to_ohlc(self) -> bool:
        if not self._tick_buffer:
            return False
        current_time = self._tick_buffer[-1]['timestamp']
        if (current_time - self._last_aggregation_time).total_seconds() >= self._interval_seconds:
            df_buffer = pd.DataFrame(self._tick_buffer)
            new_bar = pd.DataFrame([{
                'open': df_buffer['price'].iloc[0],
                'high': df_buffer['price'].max(),
                'low': df_buffer['price'].min(),
                'close': df_buffer['price'].iloc[-1]
            }], index=[self._last_aggregation_time])
            
            self._ohlc_data = pd.concat([self._ohlc_data, new_bar])
            self._tick_buffer = []
            self._last_aggregation_time = current_time
            return True
        return False

    def _calculate_market_regime(self):
        """
        Calcula el régimen de mercado completo usando Supertendencia, BBands y BBW.
        """
        required_data_points = max(self._st_atr_period, self._bb_length) + 1
        if len(self._ohlc_data) < required_data_points:
            self._market_regime["context"] = "INSUFFICIENT_DATA"
            return

        data = self._ohlc_data.copy()

        try:
            # --- Bloque de Cálculo de Indicadores ---
            
            # 1. Supertendencia
            data.ta.supertrend(length=self._st_atr_period, multiplier=self._st_atr_mult, append=True)
            
            # 2. Bandas de Bollinger
            data.ta.bbands(length=self._bb_length, std=self._bb_std, append=True)

            # --- Nombres de columnas generados por pandas-ta ---
            st_dir_col = f'SUPERTd_{self._st_atr_period}_{self._st_atr_mult}'
            bb_lower_col = f'BBL_{self._bb_length}_{self._bb_std}'
            bb_middle_col = f'BBM_{self._bb_length}_{self._bb_std}'
            bb_upper_col = f'BBU_{self._bb_length}_{self._bb_std}'
            bbw_col = f'BBW_{self._bb_length}_{self._bb_std}'

            # 3. Ancho de Banda de Bollinger (BBW) - CÁLCULO MANUAL
            if all(col in data.columns for col in [bb_upper_col, bb_lower_col, bb_middle_col]):
                with np.errstate(divide='ignore', invalid='ignore'):
                    data[bbw_col] = (data[bb_upper_col] - data[bb_lower_col]) / data[bb_middle_col] * 100
                
                ### INICIO DE LA CORRECCIÓN (FutureWarning) ###
                # Se reemplaza la versión con "inplace=True" por esta reasignación,
                # que es la forma recomendada y elimina la advertencia.
                data[bbw_col] = data[bbw_col].replace([np.inf, -np.inf], np.nan)
                ### FIN DE LA CORRECCIÓN ###
            else:
                print(f"ADVERTENCIA [Market Regime]: Columnas de Bollinger no encontradas. BBW no se pudo calcular.")
                data[bbw_col] = np.nan

            # Extraer la última fila que contiene todos los valores calculados
            last_row = data.iloc[-1]

            # --- Procesar y Almacenar Estado ---
            
            # Tendencia
            trend = "NEUTRAL"
            if st_dir_col in last_row and pd.notna(last_row[st_dir_col]):
                trend = "UP" if last_row[st_dir_col] == 1 else "DOWN"
            self._market_regime["trend"] = trend

            # Zona
            zone = "UNKNOWN"
            if all(c in last_row for c in [bb_lower_col, bb_upper_col, 'close']) and \
               pd.notna(last_row[[bb_lower_col, bb_upper_col, 'close']]).all():
                band_range = last_row[bb_upper_col] - last_row[bb_lower_col]
                if band_range > 1e-9:
                    support_limit = last_row[bb_lower_col] + (band_range * self._bb_zone_pct)
                    resistance_limit = last_row[bb_upper_col] - (band_range * self._bb_zone_pct)
                    if last_row['close'] <= support_limit: zone = "NEAR_SUPPORT"
                    elif last_row['close'] >= resistance_limit: zone = "NEAR_RESISTANCE"
                    else: zone = "MID_RANGE"
                else:
                    zone = "FLAT_MARKET"
            self._market_regime["zone"] = zone

            # Volatilidad
            volatility = "VOLATILE"
            if bbw_col in last_row and pd.notna(last_row[bbw_col]):
                if (last_row[bbw_col] / 100.0) < self._bbwp_chop_threshold:
                    volatility = "CHOP"
            self._market_regime["volatility"] = volatility

            # --- Contexto Final Compuesto ---
            if volatility == "CHOP":
                self._market_regime["context"] = "CHOP_ZONE"
            elif trend == "UP" and zone == "NEAR_SUPPORT":
                self._market_regime["context"] = "TREND_UP_NEAR_SUPPORT"
            elif trend == "DOWN" and zone == "NEAR_RESISTANCE":
                self._market_regime["context"] = "TREND_DOWN_NEAR_RESISTANCE"
            else:
                self._market_regime["context"] = f"TREND_{trend}_{zone}"

        except Exception as e:
            print(f"ERROR [Market Regime]: Excepción calculando régimen: {e}")
            traceback.print_exc()
            self._market_regime["context"] = "EXCEPTION"

    def get_market_regime(self) -> Dict[str, Any]:
        new_bar_generated = self._aggregate_ticks_to_ohlc()
        if new_bar_generated:
            self._calculate_market_regime()
        return self._market_regime.copy()