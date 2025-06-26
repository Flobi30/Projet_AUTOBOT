"""
Sentiment Analysis Agent for AUTOBOT

This agent analyzes market sentiment from various sources including social media,
news, and financial reports to enhance trading decisions.
"""

import logging
import time
import threading
import queue
from typing import Dict, List, Any, Optional, Tuple, Union
import numpy as np
from datetime import datetime
import re
import json
from dataclasses import dataclass
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

@dataclass
class SentimentData:
    """Represents sentiment data from a source"""
    source: str
    timestamp: float
    text: str
    entities: List[str]
    raw_score: float
    normalized_score: float
    confidence: float
    relevance: float
    source_reliability: float


class SentimentClassifier(nn.Module):
    """Neural network for financial sentiment classification"""
    
    def __init__(self, vocab_size: int, embedding_dim: int = 100, hidden_dim: int = 128, num_classes: int = 3):
        """
        Initialize the sentiment classifier
        
        Args:
            vocab_size: Size of vocabulary
            embedding_dim: Dimension of word embeddings
            hidden_dim: Dimension of hidden layers
            num_classes: Number of sentiment classes (negative, neutral, positive)
        """
        super(SentimentClassifier, self).__init__()
        
        self.embedding = nn.Embedding(vocab_size, embedding_dim)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim, batch_first=True, bidirectional=True)
        self.attention = nn.Linear(hidden_dim * 2, 1)
        self.fc = nn.Linear(hidden_dim * 2, num_classes)
        
        self.apply(self._init_weights)
    
    def _init_weights(self, module):
        """Initialize network weights"""
        if isinstance(module, nn.Linear):
            nn.init.xavier_normal_(module.weight)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0, std=0.1)
    
    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network
        
        Args:
            x: Input tensor of token indices
            lengths: Sequence lengths
            
        Returns:
            Sentiment class logits
        """
        embedded = self.embedding(x)
        
        packed = nn.utils.rnn.pack_padded_sequence(
            embedded, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        
        lstm_out, _ = self.lstm(packed)
        
        lstm_out, _ = nn.utils.rnn.pad_packed_sequence(lstm_out, batch_first=True)
        
        attention_weights = F.softmax(self.attention(lstm_out), dim=1)
        context_vector = torch.sum(attention_weights * lstm_out, dim=1)
        
        logits = self.fc(context_vector)
        
        return logits


class EntityExtractor:
    """Extracts financial entities from text"""
    
    def __init__(self):
        """Initialize the entity extractor"""
        self.company_patterns = [
            r'\b[A-Z][a-z]+\s[A-Z][a-z]+\b',  # Company names like "Apple Inc"
            r'\b[A-Z]{2,5}\b'  # Stock tickers like "AAPL"
        ]
        
        self.financial_terms = [
            r'\b(?:stock|share|bond|etf|fund|market|index|crypto|bitcoin|ethereum)\b',
            r'\b(?:bull|bear|rally|crash|correction|recession|boom)\b',
            r'\b(?:dividend|yield|earnings|revenue|profit|loss|growth|decline)\b'
        ]
        
        self.patterns = []
        for pattern in self.company_patterns + self.financial_terms:
            self.patterns.append(re.compile(pattern, re.IGNORECASE))
    
    def extract_entities(self, text: str) -> List[str]:
        """
        Extract financial entities from text
        
        Args:
            text: Input text
            
        Returns:
            List of extracted entities
        """
        entities = []
        
        for pattern in self.patterns:
            matches = pattern.findall(text)
            entities.extend(matches)
        
        unique_entities = list(set([e.lower() for e in entities]))
        
        return unique_entities


class SentimentAnalysisAgent:
    """
    Agent that analyzes market sentiment from various sources
    to enhance trading decisions.
    """
    
    def __init__(
        self,
        symbols: List[str],
        update_interval: int = 300,
        sentiment_threshold: float = 0.6,
        device: str = "auto"
    ):
        """
        Initialize the sentiment analysis agent
        
        Args:
            symbols: List of trading symbols to monitor
            update_interval: Interval in seconds between sentiment updates
            sentiment_threshold: Threshold for significant sentiment
            device: Device to use for model inference
        """
        self.symbols = symbols
        self.update_interval = update_interval
        self.sentiment_threshold = sentiment_threshold
        
        if device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)
        
        logger.info(f"Sentiment Analysis Agent initialized with device: {self.device}")
        
        self.sentiment_data = {}
        for symbol in symbols:
            self.sentiment_data[symbol] = []
        
        self.entity_extractor = EntityExtractor()
        
        self.model = SentimentClassifier(vocab_size=10000)
        
        self.vocab = {"<PAD>": 0, "<UNK>": 1}
        
        self.source_reliability = {
            "twitter": 0.6,
            "reddit": 0.5,
            "news": 0.8,
            "financial_reports": 0.9,
            "blogs": 0.4
        }
        
        self.event_queue = queue.Queue()
        
        self.running = True
        self.update_thread = threading.Thread(target=self._update_sentiment_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
    
    def add_text(self, source: str, text: str, symbols: Optional[List[str]] = None) -> None:
        """
        Add text for sentiment analysis
        
        Args:
            source: Source of the text
            text: Text content
            symbols: List of symbols the text is relevant to (None for all)
        """
        entities = self.entity_extractor.extract_entities(text)
        
        relevant_symbols = symbols or self.symbols
        
        sentiment_score, confidence = self._analyze_sentiment(text)
        
        relevance = self._calculate_relevance(text, entities, relevant_symbols)
        
        source_reliability = self.source_reliability.get(source.lower(), 0.5)
        
        sentiment_data = SentimentData(
            source=source,
            timestamp=time.time(),
            text=text,
            entities=entities,
            raw_score=sentiment_score,
            normalized_score=self._normalize_sentiment(sentiment_score),
            confidence=confidence,
            relevance=relevance,
            source_reliability=source_reliability
        )
        
        for symbol in relevant_symbols:
            if symbol in self.sentiment_data:
                self.sentiment_data[symbol].append(sentiment_data)
                
                max_items = 1000
                if len(self.sentiment_data[symbol]) > max_items:
                    self.sentiment_data[symbol] = self.sentiment_data[symbol][-max_items:]
        
        if abs(sentiment_data.normalized_score) > self.sentiment_threshold and confidence > 0.7:
            self.event_queue.put((relevant_symbols, sentiment_data))
    
    def _analyze_sentiment(self, text: str) -> Tuple[float, float]:
        """
        Analyze sentiment of text
        
        Args:
            text: Input text
            
        Returns:
            Tuple of (sentiment_score, confidence)
        """
        
        positive_words = ["bullish", "growth", "profit", "gain", "up", "rise", "positive", "good", "strong"]
        negative_words = ["bearish", "loss", "down", "fall", "negative", "bad", "weak", "decline", "crash"]
        
        text_lower = text.lower()
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        total_count = positive_count + negative_count
        
        if total_count == 0:
            return 0.0, 0.5  # Neutral with medium confidence
        
        sentiment_score = (positive_count - negative_count) / total_count
        confidence = min(0.5 + 0.1 * total_count, 0.9)  # More words = higher confidence, up to 0.9
        
        return sentiment_score, confidence
    
    def _normalize_sentiment(self, raw_score: float) -> float:
        """
        Normalize sentiment score to [-1, 1] range
        
        Args:
            raw_score: Raw sentiment score
            
        Returns:
            Normalized sentiment score
        """
        return max(min(raw_score, 1.0), -1.0)
    
    def _calculate_relevance(self, text: str, entities: List[str], symbols: List[str]) -> float:
        """
        Calculate relevance of text to symbols
        
        Args:
            text: Input text
            entities: Extracted entities
            symbols: Relevant symbols
            
        Returns:
            Relevance score [0, 1]
        """
        text_lower = text.lower()
        symbol_mentions = sum(1 for symbol in symbols if symbol.lower() in text_lower)
        
        if symbol_mentions > 0:
            return min(0.5 + 0.1 * symbol_mentions, 1.0)
        
        if entities:
            return 0.3 + 0.2 * min(len(entities) / 5, 1.0)
        
        return 0.1  # Low relevance if no symbols or entities
    
    def _update_sentiment_loop(self) -> None:
        """Background thread for periodically updating sentiment"""
        while self.running:
            try:
                self._update_sentiment()
                time.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in sentiment update loop: {e}")
                time.sleep(10)  # Wait before retrying
    
    def _update_sentiment(self) -> None:
        """Update sentiment for all symbols"""
        for symbol in self.symbols:
            if symbol not in self.sentiment_data or not self.sentiment_data[symbol]:
                continue
            
            recent_data = self._get_recent_sentiment(symbol, 3600)  # Last hour
            
            if not recent_data:
                continue
            
            weighted_scores = []
            weights = []
            
            current_time = time.time()
            
            for data in recent_data:
                time_diff = current_time - data.timestamp
                recency_weight = np.exp(-time_diff / 3600)  # 1-hour half-life
                
                weight = recency_weight * data.confidence * data.relevance * data.source_reliability
                
                weighted_scores.append(data.normalized_score * weight)
                weights.append(weight)
            
            if sum(weights) > 0:
                aggregate_sentiment = sum(weighted_scores) / sum(weights)
                logger.debug(f"Updated aggregate sentiment for {symbol}: {aggregate_sentiment:.2f}")
    
    def _get_recent_sentiment(self, symbol: str, time_window: int) -> List[SentimentData]:
        """
        Get recent sentiment data for a symbol
        
        Args:
            symbol: Trading symbol
            time_window: Time window in seconds
            
        Returns:
            List of recent sentiment data
        """
        if symbol not in self.sentiment_data:
            return []
        
        current_time = time.time()
        return [data for data in self.sentiment_data[symbol] if current_time - data.timestamp <= time_window]
    
    def get_sentiment_events(self) -> List[Tuple[List[str], SentimentData]]:
        """
        Get all pending sentiment events
        
        Returns:
            List of (symbols, sentiment_data) tuples
        """
        events = []
        while not self.event_queue.empty():
            try:
                events.append(self.event_queue.get_nowait())
            except queue.Empty:
                break
        return events
    
    def get_symbol_sentiment(self, symbol: str, time_window: Optional[int] = None) -> Dict[str, Any]:
        """
        Get current sentiment for a symbol
        
        Args:
            symbol: Trading symbol
            time_window: Time window in seconds (None for all data)
            
        Returns:
            Dict with sentiment information
        """
        if symbol not in self.sentiment_data:
            return {
                "symbol": symbol,
                "sentiment_score": 0.0,
                "confidence": 0.0,
                "data_points": 0,
                "sources": []
            }
        
        if time_window is not None:
            data = self._get_recent_sentiment(symbol, time_window)
        else:
            data = self.sentiment_data[symbol]
        
        if not data:
            return {
                "symbol": symbol,
                "sentiment_score": 0.0,
                "confidence": 0.0,
                "data_points": 0,
                "sources": []
            }
        
        weighted_scores = []
        weights = []
        sources = set()
        
        current_time = time.time()
        
        for item in data:
            time_diff = current_time - item.timestamp
            recency_weight = np.exp(-time_diff / 3600)  # 1-hour half-life
            
            weight = recency_weight * item.confidence * item.relevance * item.source_reliability
            
            weighted_scores.append(item.normalized_score * weight)
            weights.append(weight)
            sources.add(item.source)
        
        if sum(weights) > 0:
            aggregate_sentiment = sum(weighted_scores) / sum(weights)
            
            confidence = min(0.5 + 0.1 * len(data) / 10, 0.9) * (sum(weights) / len(data))
            
            return {
                "symbol": symbol,
                "sentiment_score": aggregate_sentiment,
                "confidence": confidence,
                "data_points": len(data),
                "sources": list(sources)
            }
        else:
            return {
                "symbol": symbol,
                "sentiment_score": 0.0,
                "confidence": 0.0,
                "data_points": len(data),
                "sources": list(sources)
            }
    
    def shutdown(self) -> None:
        """Shutdown the agent"""
        self.running = False
        if self.update_thread.is_alive():
            self.update_thread.join(timeout=1)
        logger.info("Sentiment Analysis Agent shut down")


def create_sentiment_analysis_agent(symbols: List[str]) -> SentimentAnalysisAgent:
    """
    Create a new sentiment analysis agent
    
    Args:
        symbols: List of trading symbols to monitor
        
    Returns:
        SentimentAnalysisAgent: New sentiment analysis agent
    """
    return SentimentAnalysisAgent(symbols)
