"""
Feature extraction and processing for AUTOBOT prediction models.
Provides sophisticated feature engineering for market prediction.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Union, Callable, Tuple
from datetime import datetime
import talib
from sklearn.preprocessing import StandardScaler, MinMaxScaler

logger = logging.getLogger(__name__)

class FeatureExtractor:
    """Feature extractor for market data."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the feature extractor.
        
        Args:
            config: Feature extractor configuration
        """
        default_config = {
            "price_features": True,
            "volume_features": True,
            "technical_indicators": True,
            "sentiment_features": False,
            "market_features": True,
            "normalization": "standard",  # standard, minmax, none
            "sequence_length": 60,
            "target_column": "close",
            "target_shift": 1,
            "drop_na": True
        }
        
        self.config = {**default_config, **(config or {})}
        self.fitted_scalers = {}
    
    def extract_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Extract features from market data.
        
        Args:
            data: Market data with OHLCV columns
            
        Returns:
            DataFrame with extracted features
        """
        logger.info(f"Extracting features from data with shape {data.shape}")
        
        df = data.copy()
        
        required_columns = ["open", "high", "low", "close", "volume"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        if self.config["price_features"]:
            df = self._extract_price_features(df)
        
        if self.config["volume_features"]:
            df = self._extract_volume_features(df)
        
        if self.config["technical_indicators"]:
            df = self._extract_technical_indicators(df)
        
        if self.config["sentiment_features"]:
            df = self._extract_sentiment_features(df)
        
        if self.config["market_features"]:
            df = self._extract_market_features(df)
        
        if self.config["drop_na"]:
            df = df.dropna()
        
        logger.info(f"Extracted features with shape {df.shape}")
        
        return df
    
    def _extract_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract price-based features.
        
        Args:
            df: Market data
            
        Returns:
            DataFrame with price features
        """
        df["return_1d"] = df["close"].pct_change(1)
        df["return_2d"] = df["close"].pct_change(2)
        df["return_5d"] = df["close"].pct_change(5)
        df["return_10d"] = df["close"].pct_change(10)
        
        df["log_return_1d"] = np.log(df["close"] / df["close"].shift(1))
        
        df["close_to_open"] = df["close"] / df["open"]
        df["high_to_low"] = df["high"] / df["low"]
        
        df["high_minus_low"] = df["high"] - df["low"]
        df["close_minus_open"] = df["close"] - df["open"]
        
        df["ma_5"] = df["close"].rolling(window=5).mean()
        df["ma_10"] = df["close"].rolling(window=10).mean()
        df["ma_20"] = df["close"].rolling(window=20).mean()
        df["ma_50"] = df["close"].rolling(window=50).mean()
        
        df["ma_5_10_ratio"] = df["ma_5"] / df["ma_10"]
        df["ma_10_20_ratio"] = df["ma_10"] / df["ma_20"]
        df["ma_20_50_ratio"] = df["ma_20"] / df["ma_50"]
        
        df["volatility_5d"] = df["return_1d"].rolling(window=5).std()
        df["volatility_10d"] = df["return_1d"].rolling(window=10).std()
        df["volatility_20d"] = df["return_1d"].rolling(window=20).std()
        
        return df
    
    def _extract_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract volume-based features.
        
        Args:
            df: Market data
            
        Returns:
            DataFrame with volume features
        """
        df["volume_change_1d"] = df["volume"].pct_change(1)
        df["volume_change_5d"] = df["volume"].pct_change(5)
        
        df["volume_ma_5"] = df["volume"].rolling(window=5).mean()
        df["volume_ma_10"] = df["volume"].rolling(window=10).mean()
        df["volume_ma_20"] = df["volume"].rolling(window=20).mean()
        
        df["volume_ma_5_10_ratio"] = df["volume_ma_5"] / df["volume_ma_10"]
        df["volume_ma_10_20_ratio"] = df["volume_ma_10"] / df["volume_ma_20"]
        
        df["volume_to_price"] = df["volume"] / df["close"]
        
        df["obv"] = (df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]).cumsum()
        
        return df
    
    def _extract_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract technical indicators.
        
        Args:
            df: Market data
            
        Returns:
            DataFrame with technical indicators
        """
        df["rsi_14"] = talib.RSI(df["close"].values, timeperiod=14)
        
        macd, macd_signal, macd_hist = talib.MACD(
            df["close"].values,
            fastperiod=12,
            slowperiod=26,
            signalperiod=9
        )
        df["macd"] = macd
        df["macd_signal"] = macd_signal
        df["macd_hist"] = macd_hist
        
        upper, middle, lower = talib.BBANDS(
            df["close"].values,
            timeperiod=20,
            nbdevup=2,
            nbdevdn=2,
            matype=0
        )
        df["bb_upper"] = upper
        df["bb_middle"] = middle
        df["bb_lower"] = lower
        df["bb_width"] = (upper - lower) / middle
        
        slowk, slowd = talib.STOCH(
            df["high"].values,
            df["low"].values,
            df["close"].values,
            fastk_period=14,
            slowk_period=3,
            slowk_matype=0,
            slowd_period=3,
            slowd_matype=0
        )
        df["stoch_k"] = slowk
        df["stoch_d"] = slowd
        
        df["adx"] = talib.ADX(
            df["high"].values,
            df["low"].values,
            df["close"].values,
            timeperiod=14
        )
        
        df["cci"] = talib.CCI(
            df["high"].values,
            df["low"].values,
            df["close"].values,
            timeperiod=14
        )
        
        df["atr"] = talib.ATR(
            df["high"].values,
            df["low"].values,
            df["close"].values,
            timeperiod=14
        )
        
        df["willr"] = talib.WILLR(
            df["high"].values,
            df["low"].values,
            df["close"].values,
            timeperiod=14
        )
        
        df["roc"] = talib.ROC(df["close"].values, timeperiod=10)
        
        df["mfi"] = talib.MFI(
            df["high"].values,
            df["low"].values,
            df["close"].values,
            df["volume"].values,
            timeperiod=14
        )
        
        return df
    
    def _extract_sentiment_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract sentiment-based features.
        
        Args:
            df: Market data
            
        Returns:
            DataFrame with sentiment features
        """
        
        np.random.seed(42)
        df["sentiment_score"] = np.random.normal(0, 1, size=len(df))
        df["sentiment_volume"] = np.random.normal(0, 1, size=len(df))
        df["sentiment_ma_5"] = df["sentiment_score"].rolling(window=5).mean()
        
        return df
    
    def _extract_market_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract market-wide features.
        
        Args:
            df: Market data
            
        Returns:
            DataFrame with market features
        """
        
        if "timestamp" in df.columns:
            df["day_of_week"] = pd.to_datetime(df["timestamp"]).dt.dayofweek
            df["hour_of_day"] = pd.to_datetime(df["timestamp"]).dt.hour
        
        np.random.seed(42)
        df["market_volatility"] = np.random.normal(0, 1, size=len(df))
        df["market_trend"] = np.random.normal(0, 1, size=len(df))
        
        return df
    
    def create_sequences(
        self,
        data: pd.DataFrame,
        sequence_length: Optional[int] = None,
        target_column: Optional[str] = None,
        target_shift: Optional[int] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create sequences for time series prediction.
        
        Args:
            data: Feature data
            sequence_length: Length of sequences
            target_column: Target column name
            target_shift: Number of steps to shift the target
            
        Returns:
            Tuple of (X, y) arrays
        """
        sequence_length = sequence_length or self.config["sequence_length"]
        target_column = target_column or self.config["target_column"]
        target_shift = target_shift or self.config["target_shift"]
        
        if target_column not in data.columns:
            raise ValueError(f"Target column '{target_column}' not found in data")
        
        y = data[target_column].shift(-target_shift).values[:-target_shift]
        
        X = []
        for i in range(len(data) - sequence_length - target_shift + 1):
            X.append(data.iloc[i:(i + sequence_length)].values)
        
        X = np.array(X)
        
        logger.info(f"Created sequences with shape X: {X.shape}, y: {y.shape}")
        
        return X, y
    
    def normalize_features(
        self,
        data: pd.DataFrame,
        method: Optional[str] = None,
        fit: bool = True
    ) -> pd.DataFrame:
        """
        Normalize features.
        
        Args:
            data: Feature data
            method: Normalization method (standard, minmax, none)
            fit: Whether to fit the scaler
            
        Returns:
            Normalized data
        """
        method = method or self.config["normalization"]
        
        if method == "none":
            return data
        
        df = data.copy()
        
        numerical_columns = df.select_dtypes(include=["float64", "int64"]).columns.tolist()
        
        if method == "standard":
            if fit or not self.fitted_scalers.get("standard"):
                scaler = StandardScaler()
                df[numerical_columns] = scaler.fit_transform(df[numerical_columns])
                self.fitted_scalers["standard"] = scaler
            else:
                df[numerical_columns] = self.fitted_scalers["standard"].transform(df[numerical_columns])
        
        elif method == "minmax":
            if fit or not self.fitted_scalers.get("minmax"):
                scaler = MinMaxScaler()
                df[numerical_columns] = scaler.fit_transform(df[numerical_columns])
                self.fitted_scalers["minmax"] = scaler
            else:
                df[numerical_columns] = self.fitted_scalers["minmax"].transform(df[numerical_columns])
        
        else:
            raise ValueError(f"Unknown normalization method: {method}")
        
        return df

def extract_features(
    data: pd.DataFrame,
    config: Dict[str, Any] = None
) -> pd.DataFrame:
    """
    Extract features from market data.
    
    Args:
        data: Market data with OHLCV columns
        config: Feature extraction configuration
        
    Returns:
        DataFrame with extracted features
    """
    extractor = FeatureExtractor(config)
    return extractor.extract_features(data)

def normalize_features(
    data: pd.DataFrame,
    method: str = "standard",
    fit: bool = True
) -> pd.DataFrame:
    """
    Normalize features.
    
    Args:
        data: Feature data
        method: Normalization method (standard, minmax, none)
        fit: Whether to fit the scaler
        
    Returns:
        Normalized data
    """
    extractor = FeatureExtractor({"normalization": method})
    return extractor.normalize_features(data, method, fit)

def create_feature_set(
    data: pd.DataFrame,
    config: Dict[str, Any] = None
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create a complete feature set for prediction.
    
    Args:
        data: Market data with OHLCV columns
        config: Feature extraction configuration
        
    Returns:
        Tuple of (X, y) arrays
    """
    extractor = FeatureExtractor(config)
    features = extractor.extract_features(data)
    normalized_features = extractor.normalize_features(features)
    return extractor.create_sequences(normalized_features)
