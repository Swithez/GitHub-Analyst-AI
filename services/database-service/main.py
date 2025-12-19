"""
Database Service - управление базой данных
Port: 8003
"""
import os
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Database Service", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация
DATABASE_PATH = os.getenv('DATABASE_PATH', './data/github_statistics.db')


class StatsSaveRequest(BaseModel):
    owner: str
    repo_name: str
    total_commits: int
    total_contributors: int
    avg_commits_per_day: float
    analysis_period_days: int
    activity_index: float = 0.0
    additional_data: Optional[Dict[str, Any]] = None


@contextmanager
def get_db_connection():
    """Контекстный менеджер для подключения к БД"""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def initialize_database():
    """Инициализация базы данных"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Основная таблица статистики
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS repo_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL,
                repo_name TEXT NOT NULL,
                total_commits INTEGER,
                total_contributors INTEGER,
                avg_commits_per_day REAL,
                analysis_period_days INTEGER,
                activity_index REAL DEFAULT 0.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                additional_data TEXT
            )
        ''')
        
        # Таблица для кеширования данных GitHub
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS github_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT UNIQUE NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        
        # Индексы
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_owner_repo 
            ON repo_stats(owner, repo_name)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON repo_stats(timestamp DESC)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cache_key 
            ON github_cache(cache_key)
        ''')
        
        conn.commit()
        logger.info(f"Database initialized at {DATABASE_PATH}")


# Инициализация при старте
initialize_database()


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "service": "database-service",
        "timestamp": datetime.utcnow().isoformat(),
        "database": DATABASE_PATH
    }


@app.post("/stats/save")
async def save_statistics(request: StatsSaveRequest):
    """Сохранить статистику в БД"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            additional_data_str = None
            if request.additional_data:
                import json
                additional_data_str = json.dumps(request.additional_data)
            
            cursor.execute('''
                INSERT INTO repo_stats 
                (owner, repo_name, total_commits, total_contributors, 
                 avg_commits_per_day, analysis_period_days, activity_index, additional_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                request.owner,
                request.repo_name,
                request.total_commits,
                request.total_contributors,
                request.avg_commits_per_day,
                request.analysis_period_days,
                request.activity_index,
                additional_data_str
            ))
            
            conn.commit()
            record_id = cursor.lastrowid
            
            logger.info(f"Statistics saved: {request.owner}/{request.repo_name} (ID: {record_id})")
            
            return {
                "success": True,
                "record_id": record_id,
                "message": "Statistics saved successfully"
            }
    
    except Exception as e:
        logger.error(f"Error saving statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/history")
async def get_history(limit: int = 50, offset: int = 0):
    """Получить историю запросов"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM repo_stats
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            rows = cursor.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    "id": row["id"],
                    "owner": row["owner"],
                    "repo_name": row["repo_name"],
                    "total_commits": row["total_commits"],
                    "total_contributors": row["total_contributors"],
                    "avg_commits_per_day": row["avg_commits_per_day"],
                    "analysis_period_days": row["analysis_period_days"],
                    "activity_index": row["activity_index"],
                    "timestamp": row["timestamp"]
                })
            
            # Подсчет общего количества записей
            cursor.execute('SELECT COUNT(*) as count FROM repo_stats')
            total = cursor.fetchone()["count"]
            
            return {
                "history": history,
                "total": total,
                "limit": limit,
                "offset": offset
            }
    
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/repo/{owner}/{repo_name}")
async def get_repo_history(owner: str, repo_name: str, limit: int = 10):
    """Получить историю для конкретного репозитория"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM repo_stats
                WHERE owner = ? AND repo_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (owner, repo_name, limit))
            
            rows = cursor.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    "id": row["id"],
                    "owner": row["owner"],
                    "repo_name": row["repo_name"],
                    "total_commits": row["total_commits"],
                    "total_contributors": row["total_contributors"],
                    "avg_commits_per_day": row["avg_commits_per_day"],
                    "analysis_period_days": row["analysis_period_days"],
                    "activity_index": row["activity_index"],
                    "timestamp": row["timestamp"]
                })
            
            return {
                "owner": owner,
                "repo_name": repo_name,
                "history": history,
                "count": len(history)
            }
    
    except Exception as e:
        logger.error(f"Error fetching repo history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cache/set")
async def set_cache(cache_key: str, data: str, ttl_seconds: int = 3600):
    """Сохранить данные в кеш"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            expires_at = datetime.utcnow().timestamp() + ttl_seconds
            expires_at_str = datetime.fromtimestamp(expires_at).isoformat()
            
            cursor.execute('''
                INSERT OR REPLACE INTO github_cache (cache_key, data, expires_at)
                VALUES (?, ?, ?)
            ''', (cache_key, data, expires_at_str))
            
            conn.commit()
            
            return {"success": True, "cache_key": cache_key}
    
    except Exception as e:
        logger.error(f"Error setting cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cache/get/{cache_key}")
async def get_cache(cache_key: str):
    """Получить данные из кеша"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT data, expires_at FROM github_cache
                WHERE cache_key = ?
            ''', (cache_key,))
            
            row = cursor.fetchone()
            
            if not row:
                return {"found": False}
            
            # Проверка срока действия
            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at < datetime.utcnow():
                # Кеш истек
                cursor.execute('DELETE FROM github_cache WHERE cache_key = ?', (cache_key,))
                conn.commit()
                return {"found": False, "expired": True}
            
            return {
                "found": True,
                "data": row["data"],
                "cache_key": cache_key
            }
    
    except Exception as e:
        logger.error(f"Error getting cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/cache/clear")
async def clear_cache():
    """Очистить весь кеш"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM github_cache')
            conn.commit()
            deleted = cursor.rowcount
            
            return {
                "success": True,
                "deleted_records": deleted
            }
    
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)