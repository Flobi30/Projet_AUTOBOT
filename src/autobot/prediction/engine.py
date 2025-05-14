"""
Prediction engine for AUTOBOT.
Provides a flexible framework for creating and using prediction models.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Union, Callable, Tuple
from datetime import datetime
import os
import json

from .models import BaseModel, get_model
from .features import FeatureExtractor, extract_features, normalize_features

logger = logging.getLogger(__name__)

class ModelConfig:
    """Configuration for prediction models."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the model configuration.
        
        Args:
            config: Model configuration
        """
        default_config = {
            "model_type": "LSTMModel",
            "model_name": "default_model",
            "model_params": {},
            "feature_params": {},
            "training_params": {
                "validation_split": 0.2,
                "shuffle": True,
                "epochs": 100,
                "batch_size": 32,
                "early_stopping": True,
                "patience": 10
            },
            "prediction_params": {
                "threshold": 0.5,
                "window_size": 1
            }
        }
        
        self.config = {**default_config, **(config or {})}
    
    def get_model_type(self) -> str:
        """
        Get the model type.
        
        Returns:
            Model type
        """
        return self.config["model_type"]
    
    def get_model_name(self) -> str:
        """
        Get the model name.
        
        Returns:
            Model name
        """
        return self.config["model_name"]
    
    def get_model_params(self) -> Dict[str, Any]:
        """
        Get the model parameters.
        
        Returns:
            Model parameters
        """
        return self.config["model_params"]
    
    def get_feature_params(self) -> Dict[str, Any]:
        """
        Get the feature parameters.
        
        Returns:
            Feature parameters
        """
        return self.config["feature_params"]
    
    def get_training_params(self) -> Dict[str, Any]:
        """
        Get the training parameters.
        
        Returns:
            Training parameters
        """
        return self.config["training_params"]
    
    def get_prediction_params(self) -> Dict[str, Any]:
        """
        Get the prediction parameters.
        
        Returns:
            Prediction parameters
        """
        return self.config["prediction_params"]
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the configuration to a dictionary.
        
        Returns:
            Dictionary representation of the configuration
        """
        return self.config
    
    def save(self, path: str) -> str:
        """
        Save the configuration to a file.
        
        Args:
            path: Path to save the configuration
            
        Returns:
            Full path to the saved configuration
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(self.config, f, indent=4)
        
        logger.info(f"Configuration saved to {path}")
        return path
    
    @classmethod
    def load(cls, path: str) -> 'ModelConfig':
        """
        Load a configuration from a file.
        
        Args:
            path: Path to the configuration file
            
        Returns:
            Loaded configuration
        """
        with open(path, 'r') as f:
            config = json.load(f)
        
        logger.info(f"Configuration loaded from {path}")
        return cls(config)

class PredictionResult:
    """Result of a prediction operation."""
    
    def __init__(
        self,
        predictions: np.ndarray,
        timestamps: Optional[List[str]] = None,
        confidence: Optional[np.ndarray] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the prediction result.
        
        Args:
            predictions: Prediction values
            timestamps: Optional timestamps for the predictions
            confidence: Optional confidence scores for the predictions
            metadata: Optional metadata
        """
        self.predictions = predictions
        self.timestamps = timestamps
        self.confidence = confidence
        self.metadata = metadata or {}
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the result to a dictionary.
        
        Returns:
            Dictionary representation of the result
        """
        return {
            "predictions": self.predictions.tolist() if isinstance(self.predictions, np.ndarray) else self.predictions,
            "timestamps": self.timestamps,
            "confidence": self.confidence.tolist() if isinstance(self.confidence, np.ndarray) else self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at
        }
    
    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert the result to a DataFrame.
        
        Returns:
            DataFrame representation of the result
        """
        data = {
            "prediction": self.predictions
        }
        
        if self.confidence is not None:
            data["confidence"] = self.confidence
        
        if self.timestamps is not None:
            data["timestamp"] = self.timestamps
        
        return pd.DataFrame(data)
    
    def get_prediction(self, index: int = 0) -> float:
        """
        Get a prediction value.
        
        Args:
            index: Index of the prediction
            
        Returns:
            Prediction value
        """
        return float(self.predictions[index])
    
    def get_confidence(self, index: int = 0) -> Optional[float]:
        """
        Get a confidence score.
        
        Args:
            index: Index of the confidence score
            
        Returns:
            Confidence score
        """
        if self.confidence is None:
            return None
        
        return float(self.confidence[index])
    
    def get_timestamp(self, index: int = 0) -> Optional[str]:
        """
        Get a timestamp.
        
        Args:
            index: Index of the timestamp
            
        Returns:
            Timestamp
        """
        if self.timestamps is None:
            return None
        
        return self.timestamps[index]

class PredictionEngine:
    """Engine for making predictions."""
    
    def __init__(self, config: Optional[ModelConfig] = None):
        """
        Initialize the prediction engine.
        
        Args:
            config: Model configuration
        """
        self.config = config or ModelConfig()
        self.model = None
        self.feature_extractor = None
        self.is_initialized = False
    
    def initialize(self) -> None:
        """Initialize the prediction engine."""
        if self.is_initialized:
            return
        
        logger.info(f"Initializing prediction engine with model type {self.config.get_model_type()}")
        
        self.model = get_model(
            self.config.get_model_type(),
            self.config.get_model_name(),
            self.config.get_model_params()
        )
        
        self.feature_extractor = FeatureExtractor(self.config.get_feature_params())
        
        self.is_initialized = True
    
    def train(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Train the model.
        
        Args:
            data: Training data
            
        Returns:
            Training metrics
        """
        self.initialize()
        
        logger.info(f"Training model {self.model.name} with {len(data)} samples")
        
        features = self.feature_extractor.extract_features(data)
        
        normalized_features = self.feature_extractor.normalize_features(features)
        
        X, y = self.feature_extractor.create_sequences(normalized_features)
        
        metrics = self.model.train(X, y)
        
        return metrics
    
    def predict(self, data: pd.DataFrame) -> PredictionResult:
        """
        Make predictions.
        
        Args:
            data: Input data
            
        Returns:
            Prediction result
        """
        self.initialize()
        
        if not self.model.is_trained:
            raise ValueError("Model must be trained before making predictions")
        
        logger.info(f"Making predictions with model {self.model.name} for {len(data)} samples")
        
        features = self.feature_extractor.extract_features(data)
        
        normalized_features = self.feature_extractor.normalize_features(features, fit=False)
        
        sequence_length = self.config.get_feature_params().get("sequence_length", 60)
        
        if len(normalized_features) < sequence_length:
            raise ValueError(f"Not enough data for prediction. Need at least {sequence_length} samples.")
        
        prediction_data = normalized_features.iloc[-sequence_length:].values.reshape(1, sequence_length, -1)
        
        predictions = self.model.predict(prediction_data)
        
        timestamps = None
        if "timestamp" in data.columns:
            timestamps = data["timestamp"].iloc[-len(predictions):].tolist()
        
        result = PredictionResult(
            predictions=predictions,
            timestamps=timestamps,
            metadata={
                "model_name": self.model.name,
                "model_type": self.model.__class__.__name__,
                "feature_count": prediction_data.shape[2]
            }
        )
        
        return result
    
    def evaluate(self, data: pd.DataFrame) -> Dict[str, float]:
        """
        Evaluate the model.
        
        Args:
            data: Evaluation data
            
        Returns:
            Evaluation metrics
        """
        self.initialize()
        
        if not self.model.is_trained:
            raise ValueError("Model must be trained before evaluation")
        
        logger.info(f"Evaluating model {self.model.name} with {len(data)} samples")
        
        features = self.feature_extractor.extract_features(data)
        
        normalized_features = self.feature_extractor.normalize_features(features, fit=False)
        
        X, y = self.feature_extractor.create_sequences(normalized_features)
        
        metrics = self.model.evaluate(X, y)
        
        return metrics
    
    def save(self, path: str) -> Dict[str, str]:
        """
        Save the prediction engine.
        
        Args:
            path: Directory path to save the engine
            
        Returns:
            Dictionary with paths to saved components
        """
        self.initialize()
        
        os.makedirs(path, exist_ok=True)
        
        paths = {}
        
        model_path = os.path.join(path, f"{self.model.name}.model")
        paths["model"] = self.model.save(model_path)
        
        config_path = os.path.join(path, f"{self.model.name}.config.json")
        paths["config"] = self.config.save(config_path)
        
        logger.info(f"Prediction engine saved to {path}")
        
        return paths
    
    @classmethod
    def load(cls, path: str) -> 'PredictionEngine':
        """
        Load a prediction engine.
        
        Args:
            path: Directory path to load the engine from
            
        Returns:
            Loaded prediction engine
        """
        config_files = [f for f in os.listdir(path) if f.endswith(".config.json")]
        
        if not config_files:
            raise ValueError(f"No configuration files found in {path}")
        
        config_path = os.path.join(path, config_files[0])
        config = ModelConfig.load(config_path)
        
        engine = cls(config)
        engine.initialize()
        
        model_files = [f for f in os.listdir(path) if f.endswith(".model")]
        
        if not model_files:
            raise ValueError(f"No model files found in {path}")
        
        model_path = os.path.join(path, model_files[0])
        engine.model = BaseModel.load(model_path)
        
        logger.info(f"Prediction engine loaded from {path}")
        
        return engine

def create_prediction_engine(config: Dict[str, Any] = None) -> PredictionEngine:
    """
    Create a prediction engine.
    
    Args:
        config: Engine configuration
        
    Returns:
        Prediction engine
    """
    model_config = ModelConfig(config)
    return PredictionEngine(model_config)
