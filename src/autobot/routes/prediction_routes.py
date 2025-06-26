"""
Prediction routes for AUTOBOT.
Provides API endpoints for market prediction.
"""
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

from ..prediction.engine import PredictionEngine, create_prediction_engine, PredictionResult
from ..prediction.models import get_model


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Prediction"])

_prediction_engines = {}

def get_prediction_engine(model_name: str = "default") -> PredictionEngine:
    """
    Get or create a prediction engine.
    
    Args:
        model_name: Model name
        
    Returns:
        Prediction engine
    """
    if model_name not in _prediction_engines:
        _prediction_engines[model_name] = create_prediction_engine({
            "model_name": model_name,
            "model_type": "LSTMModel"
        })
    
    return _prediction_engines[model_name]

@router.post("/api/prediction/train", summary="Train a prediction model")
async def train_model(
    data: Dict[str, Any] = Body(...),
    model_name: str = Query("default", description="Model name"),
    model_type: str = Query("LSTMModel", description="Model type")
):
    """
    Train a prediction model.
    
    Args:
        data: Training data
        model_name: Model name
        model_type: Model type
        current_user: Current authenticated user
        
    Returns:
        Training metrics
    """
    try:
        logger.info(f"Training model {model_name} of type {model_type}")
        
        df = pd.DataFrame(data["data"])
        
        engine = create_prediction_engine({
            "model_name": model_name,
            "model_type": model_type
        })
        
        metrics = engine.train(df)
        
        _prediction_engines[model_name] = engine
        
        return {
            "status": "success",
            "message": f"Model {model_name} trained successfully",
            "metrics": metrics
        }
    
    except Exception as e:
        logger.error(f"Error training model: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error training model: {str(e)}")

@router.post("/api/prediction/predict", summary="Make predictions")
async def predict(
    data: Dict[str, Any] = Body(...),
    model_name: str = Query("default", description="Model name")
):
    """
    Make predictions.
    
    Args:
        data: Input data
        model_name: Model name
        current_user: Current authenticated user
        
    Returns:
        Prediction result
    """
    try:
        logger.info(f"Making predictions with model {model_name}")
        
        engine = get_prediction_engine(model_name)
        
        df = pd.DataFrame(data["data"])
        
        result = engine.predict(df)
        
        return {
            "status": "success",
            "prediction": result.to_dict()
        }
    
    except Exception as e:
        logger.error(f"Error making predictions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error making predictions: {str(e)}")

@router.post("/api/prediction/evaluate", summary="Evaluate a prediction model")
async def evaluate_model(
    data: Dict[str, Any] = Body(...),
    model_name: str = Query("default", description="Model name")
):
    """
    Evaluate a prediction model.
    
    Args:
        data: Evaluation data
        model_name: Model name
        current_user: Current authenticated user
        
    Returns:
        Evaluation metrics
    """
    try:
        logger.info(f"Evaluating model {model_name}")
        
        engine = get_prediction_engine(model_name)
        
        df = pd.DataFrame(data["data"])
        
        metrics = engine.evaluate(df)
        
        return {
            "status": "success",
            "metrics": metrics
        }
    
    except Exception as e:
        logger.error(f"Error evaluating model: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error evaluating model: {str(e)}")

@router.get("/api/prediction/models", summary="Get available models")
async def get_models():
    """
    Get available prediction models.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        List of available models
    """
    try:
        models = []
        
        for name, engine in _prediction_engines.items():
            if engine.model:
                models.append(engine.model.get_info())
        
        return {
            "status": "success",
            "models": models
        }
    
    except Exception as e:
        logger.error(f"Error getting models: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting models: {str(e)}")

@router.post("/api/prediction/save/{model_name}", summary="Save a prediction model")
async def save_model(
    model_name: str,
    path: str = Body(..., embed=True)
):
    """
    Save a prediction model.
    
    Args:
        model_name: Model name
        path: Path to save the model
        current_user: Current authenticated user
        
    Returns:
        Save result
    """
    try:
        logger.info(f"Saving model {model_name} to {path}")
        
        engine = get_prediction_engine(model_name)
        
        paths = engine.save(path)
        
        return {
            "status": "success",
            "message": f"Model {model_name} saved successfully",
            "paths": paths
        }
    
    except Exception as e:
        logger.error(f"Error saving model: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving model: {str(e)}")

@router.post("/api/prediction/load", summary="Load a prediction model")
async def load_model(
    path: str = Body(..., embed=True)
):
    """
    Load a prediction model.
    
    Args:
        path: Path to load the model from
        current_user: Current authenticated user
        
    Returns:
        Load result
    """
    try:
        logger.info(f"Loading model from {path}")
        
        engine = PredictionEngine.load(path)
        
        _prediction_engines[engine.model.name] = engine
        
        return {
            "status": "success",
            "message": f"Model {engine.model.name} loaded successfully",
            "model_info": engine.model.get_info()
        }
    
    except Exception as e:
        logger.error(f"Error loading model: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading model: {str(e)}")

@router.delete("/api/prediction/models/{model_name}", summary="Delete a prediction model")
async def delete_model(
    model_name: str
):
    """
    Delete a prediction model.
    
    Args:
        model_name: Model name
        current_user: Current authenticated user
        
    Returns:
        Delete result
    """
    try:
        logger.info(f"Deleting model {model_name}")
        
        if model_name in _prediction_engines:
            del _prediction_engines[model_name]
            
            return {
                "status": "success",
                "message": f"Model {model_name} deleted successfully"
            }
        else:
            raise HTTPException(status_code=404, detail=f"Model {model_name} not found")
    
    except Exception as e:
        logger.error(f"Error deleting model: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting model: {str(e)}")
