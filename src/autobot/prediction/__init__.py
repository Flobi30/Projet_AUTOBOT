"""
Advanced market prediction module for AUTOBOT.
Provides sophisticated prediction models for market analysis and trading decisions.
"""

from .models import (
    LSTMModel,
    TransformerModel,
    EnsembleModel,
    register_model,
    get_model
)

from .features import (
    extract_features,
    normalize_features,
    create_feature_set,
    FeatureExtractor
)

from .engine import (
    PredictionEngine,
    PredictionResult,
    ModelConfig,
    create_prediction_engine
)

__all__ = [
    'LSTMModel',
    'TransformerModel',
    'EnsembleModel',
    'register_model',
    'get_model',
    'extract_features',
    'normalize_features',
    'create_feature_set',
    'FeatureExtractor',
    'PredictionEngine',
    'PredictionResult',
    'ModelConfig',
    'create_prediction_engine'
]
