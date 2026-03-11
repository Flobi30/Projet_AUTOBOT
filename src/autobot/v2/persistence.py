"""
Persistence - Sauvegarde et récupération d'état SQLite
Point #4: Crash recovery pour AUTOBOT V2
"""

import logging
import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path
import threading

logger = logging.getLogger(__name__)


class StatePersistence:
    """
    Persistance d'état SQLite pour recovery après crash.
    
    Sauvegarde:
    - Positions ouvertes (pour récupération)
    - État des instances
    - Historique des trades
    """
    
    def __init__(self, db_path: str = "data/autobot_state.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        
        # Initialise la base de données
        self._init_db()
        
        logger.info(f"💾 Persistance initialisée: {self.db_path}")
    
    def _init_db(self):
        """Crée les tables si elles n'existent pas"""
        with sqlite3.connect(self.db_path) as conn:
            # CORRECTION: Activer WAL mode pour meilleure concurrence
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")  # 5 secondes timeout
            # Positions ouvertes (pour recovery crash)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    buy_price REAL NOT NULL,
                    volume REAL NOT NULL,
                    status TEXT DEFAULT 'open',
                    open_time TEXT NOT NULL,
                    strategy TEXT,
                    metadata TEXT  -- JSON
                )
            """)
            
            # État des instances
            conn.execute("""
                CREATE TABLE IF NOT EXISTS instance_state (
                    instance_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    current_capital REAL NOT NULL,
                    allocated_capital REAL NOT NULL,
                    win_count INTEGER DEFAULT 0,
                    loss_count INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Historique des trades
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    side TEXT NOT NULL,  -- 'buy', 'sell'
                    price REAL NOT NULL,
                    volume REAL NOT NULL,
                    profit REAL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (position_id) REFERENCES positions(id)
                )
            """)
            
            # CORRECTION: Index pour performances
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_instance ON trades(instance_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
            
            conn.commit()
            logger.debug("📁 Tables SQLite initialisées")
    
    def save_position(self, position_id: str, instance_id: str, 
                      buy_price: float, volume: float,
                      status: str = "open", strategy: str = "",
                      metadata: Optional[Dict] = None) -> bool:
        """
        Sauvegarde une position ouverte.
        Appelé quand une position est créée.
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO positions 
                        (id, instance_id, buy_price, volume, status, open_time, strategy, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        position_id, instance_id, buy_price, volume, status,
                        datetime.now().isoformat(), strategy,
                        json.dumps(metadata) if metadata else None
                    ))
                    conn.commit()
                    
            logger.debug(f"💾 Position sauvegardée: {instance_id}/{position_id}")
            return True
            
        except Exception as e:
            logger.exception(f"❌ Erreur sauvegarde position: {e}")
            return False
    
    def update_position_status(self, position_id: str, status: str) -> bool:
        """
        Met à jour le statut d'une position.
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        UPDATE positions SET status = ? WHERE id = ?
                    """, (status, position_id))
                    conn.commit()
                    logger.debug(f"📝 Position mise à jour: {position_id} -> {status}")
                    
            return True
            
        except Exception as e:
            logger.exception(f"❌ Erreur mise à jour position: {e}")
            return False

    def close_position_and_record_trade(self, position_id: str, 
                                        trade_data: Dict[str, Any]) -> bool:
        """
        CORRECTION: Opération atomique - ferme position ET enregistre le trade
        dans une seule transaction. Évite les "ghost positions".
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Transaction atomique
                    with conn:  # Auto-commit/rollback
                        # 1. Supprime la position
                        conn.execute("DELETE FROM positions WHERE id = ?", (position_id,))
                        
                        # 2. Enregistre le trade
                        conn.execute("""
                            INSERT INTO trades
                            (position_id, instance_id, side, price, volume, profit, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            position_id,
                            trade_data['instance_id'],
                            trade_data['side'],
                            trade_data['price'],
                            trade_data['volume'],
                            trade_data.get('profit'),
                            trade_data['timestamp']
                        ))
                    
                    logger.debug(f"🗑️ Position {position_id} fermée + trade enregistré (atomique)")
                    
            return True
            
        except Exception as e:
            logger.exception(f"❌ Erreur fermeture position atomique: {e}")
            return False
    
    def save_instance_state(self, instance_id: str, status: str,
                           current_capital: float, allocated_capital: float,
                           win_count: int, loss_count: int) -> bool:
        """
        Sauvegarde l'état d'une instance.
        Appelé périodiquement et à l'arrêt.
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO instance_state
                        (instance_id, status, current_capital, allocated_capital, 
                         win_count, loss_count, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        instance_id, status, current_capital, allocated_capital,
                        win_count, loss_count, datetime.now().isoformat()
                    ))
                    conn.commit()
                    
            logger.debug(f"💾 État instance sauvegardé: {instance_id}")
            return True
            
        except Exception as e:
            logger.exception(f"❌ Erreur sauvegarde état instance: {e}")
            return False
    
    def record_trade(self, position_id: str, instance_id: str,
                    side: str, price: float, volume: float,
                    profit: Optional[float] = None) -> bool:
        """
        Enregistre un trade dans l'historique.
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT INTO trades
                        (position_id, instance_id, side, price, volume, profit, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        position_id, instance_id, side, price, volume, profit,
                        datetime.now().isoformat()
                    ))
                    conn.commit()
                    
            logger.debug(f"💾 Trade enregistré: {instance_id} {side} {volume}")
            return True
            
        except Exception as e:
            logger.exception(f"❌ Erreur enregistrement trade: {e}")
            return False
    
    def recover_positions(self, instance_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les positions ouvertes après un crash.
        Appelé au démarrage d'une instance.
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute("""
                        SELECT * FROM positions 
                        WHERE instance_id = ? AND status = 'open'
                    """, (instance_id,))
                    
                    positions = []
                    for row in cursor.fetchall():
                        pos = dict(row)
                        if pos.get('metadata'):
                            pos['metadata'] = json.loads(pos['metadata'])
                        positions.append(pos)
                        
            if positions:
                logger.warning(f"🔄 Recovery: {len(positions)} position(s) ouverte(s) trouvée(s) pour {instance_id}")
            else:
                logger.debug(f"✅ Pas de positions à récupérer pour {instance_id}")
                
            return positions
            
        except Exception as e:
            logger.exception(f"❌ Erreur récupération positions: {e}")
            return []
    
    def recover_instance_state(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère l'état sauvegardé d'une instance.
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute("""
                        SELECT * FROM instance_state 
                        WHERE instance_id = ?
                    """, (instance_id,))
                    
                    row = cursor.fetchone()
                    if row:
                        return dict(row)
                    return None
                    
        except Exception as e:
            logger.exception(f"❌ Erreur récupération état instance: {e}")
            return None
    
    def cleanup_old_data(self, days: int = 30) -> int:
        """
        Nettoie les vieilles données (trades fermés, etc.).
        Retourne le nombre de lignes supprimées.
        """
        try:
            cutoff = datetime.now().timestamp() - (days * 24 * 3600)
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Supprime les trades vieux de plus de N jours
                    cursor = conn.execute("""
                        DELETE FROM trades 
                        WHERE julianday('now') - julianday(timestamp) > ?
                    """, (days,))
                    deleted = cursor.rowcount
                    conn.commit()
                    
            if deleted > 0:
                logger.info(f"🧹 Nettoyage: {deleted} vieux trades supprimés")
            return deleted
            
        except Exception as e:
            logger.exception(f"❌ Erreur nettoyage: {e}")
            return 0


# Singleton global - CORRECTION Phase 4: Thread-safe
_persistence_instance: Optional[StatePersistence] = None
_persistence_lock = threading.Lock()


def get_persistence(db_path: str = "data/autobot_state.db") -> StatePersistence:
    """
    Retourne l'instance singleton de persistance (thread-safe).

    CORRECTION Phase 4: Utilise un lock pour éviter race condition
    si deux threads appellent get_persistence() simultanément.
    """
    global _persistence_instance

    with _persistence_lock:
        if _persistence_instance is None:
            _persistence_instance = StatePersistence(db_path)
        return _persistence_instance


def reset_persistence():
    """Reset le singleton (pour tests)"""
    global _persistence_instance
    _persistence_instance = None
