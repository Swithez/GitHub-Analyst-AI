"""
API Gateway - центральная точка входа для всех запросов
Port: 8000
"""
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="API Gateway",
    version="1.0.0",
    description="Central API Gateway for GitHub Analytics Microservices"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# URLs сервисов
GITHUB_SERVICE_URL = os.getenv('GITHUB_SERVICE_URL', 'http://localhost:8001')
ANALYTICS_SERVICE_URL = os.getenv('ANALYTICS_SERVICE_URL', 'http://localhost:8002')
DATABASE_SERVICE_URL = os.getenv('DATABASE_SERVICE_URL', 'http://localhost:8003')

logger.info(f"GitHub Service: {GITHUB_SERVICE_URL}")
logger.info(f"Analytics Service: {ANALYTICS_SERVICE_URL}")
logger.info(f"Database Service: {DATABASE_SERVICE_URL}")


class AnalysisRequest(BaseModel):
    owner: str
    repo_name: str
    start_date: str
    end_date: str


def call_service(url: str, method: str = "GET", json_data: Dict = None, params: Dict = None) -> Dict:
    """Универсальный вызов микросервиса"""
    try:
        if method == "GET":
            response = requests.get(url, params=params, timeout=60)
        elif method == "POST":
            response = requests.post(url, json=json_data, timeout=60)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        # Обработка 404: если сервис вернул "не найдено", пробрасываем это как контролируемую ошибку
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Resource not found at {url}")
            
        response.raise_for_status()
        return response.json()
    
    except HTTPException:
        raise
    except requests.exceptions.Timeout:
        logger.error(f"Timeout calling {url}")
        raise HTTPException(status_code=504, detail=f"Service timeout: {url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling {url}: {e}")
        raise HTTPException(status_code=502, detail=f"Service unavailable: {url}")


@app.get("/health")
async def health_check():
    """Проверка здоровья API Gateway и всех сервисов"""
    services_status = {}
    
    # Проверка GitHub Service
    try:
        github_health = call_service(f"{GITHUB_SERVICE_URL}/health")
        services_status['github_service'] = 'healthy'
    except:
        services_status['github_service'] = 'unhealthy'
    
    # Проверка Analytics Service
    try:
        analytics_health = call_service(f"{ANALYTICS_SERVICE_URL}/health")
        services_status['analytics_service'] = 'healthy'
    except:
        services_status['analytics_service'] = 'unhealthy'
    
    # Проверка Database Service
    try:
        database_health = call_service(f"{DATABASE_SERVICE_URL}/health")
        services_status['database_service'] = 'healthy'
    except:
        services_status['database_service'] = 'unhealthy'
    
    all_healthy = all(status == 'healthy' for status in services_status.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": "api-gateway",
        "timestamp": datetime.utcnow().isoformat(),
        "services": services_status
    }


@app.get("/api/repo/{owner}/{repo_name}")
async def get_repo_info(owner: str, repo_name: str):
    """
    Получить базовую информацию о репозитории
    """
    logger.info(f"API Gateway: Getting repo info for {owner}/{repo_name}")
    
    try:
        # Запрос к GitHub Service
        repo_data = call_service(f"{GITHUB_SERVICE_URL}/repo/{owner}/{repo_name}")
        
        return repo_data
    
    except HTTPException as e:
        # Пробрасываем 404 и другие HTTP ошибки
        raise e
    except Exception as e:
        logger.error(f"Error in get_repo_info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
async def analyze_repository(request: AnalysisRequest):
    """
    Полный анализ репозитория с AI-аналитикой
    """
    logger.info(f"API Gateway: Starting full analysis for {request.owner}/{request.repo_name}")
    
    try:
        # Шаг 1: Получение данных от GitHub Service
        logger.info("Step 1: Fetching GitHub data...")
        github_response = call_service(
            f"{GITHUB_SERVICE_URL}/analyze",
            method="POST",
            json_data={
                "owner": request.owner,
                "repo_name": request.repo_name,
                "start_date": request.start_date,
                "end_date": request.end_date
            }
        )
        
        # Если сервис вернул успех: False (но 200 OK), считаем это ошибкой данных
        if not github_response.get('success'):
            raise HTTPException(status_code=404, detail="GitHub data not found or analysis failed")
        
        activity_data = github_response
        
        # Шаг 2: AI-анализ через Analytics Service
        logger.info("Step 2: Generating AI analysis...")
        analytics_response = call_service(
            f"{ANALYTICS_SERVICE_URL}/analyze",
            method="POST",
            json_data={
                "repo_name": request.repo_name,
                "owner": request.owner,
                "activity_data": activity_data
            }
        )
        
        # Шаг 3: Сохранение в Database Service
        logger.info("Step 3: Saving to database...")
        commit_stats = activity_data.get('commit_stats', {})
        
        save_response = call_service(
            f"{DATABASE_SERVICE_URL}/stats/save",
            method="POST",
            json_data={
                "owner": request.owner,
                "repo_name": request.repo_name,
                "total_commits": commit_stats.get('total_commits', 0),
                "total_contributors": activity_data.get('total_contributors', 0),
                "avg_commits_per_day": commit_stats.get('average_commits_per_day', 0),
                "analysis_period_days": activity_data.get('analysis_period_days', 0),
                "activity_index": activity_data.get('activity_index', 0),
                "additional_data": {
                    "ai_analysis_available": analytics_response.get('success', False)
                }
            }
        )
        
        # Шаг 4: Формирование полного ответа
        logger.info("Step 4: Preparing response...")
        
        result = {
            "success": True,
            "repo_info": activity_data.get('repo_info'),
            "commit_stats": activity_data.get('commit_stats'),
            "contributors": activity_data.get('contributors'),
            "total_contributors": activity_data.get('total_contributors'),
            "issue_stats": activity_data.get('issue_stats'),
            "pr_stats": activity_data.get('pr_stats'),
            "language_stats": activity_data.get('language_stats'),
            "analysis_period_days": activity_data.get('analysis_period_days'),
            "activity_index": activity_data.get('activity_index'),
            "start_date": request.start_date,
            "end_date": request.end_date,
            "ai_analysis": analytics_response.get('analysis', ''),
            "ai_recommendations": analytics_response.get('recommendations', []),
            "ai_insights": analytics_response.get('insights', {}),
            "ai_summary": analytics_response.get('summary', ''),
            "database_record_id": save_response.get('record_id')
        }
        
        logger.info(f"API Gateway: Analysis completed for {request.owner}/{request.repo_name}")
        
        return result
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in analyze_repository: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
async def get_history(limit: int = 50, offset: int = 0):
    """
    Получить историю запросов
    """
    logger.info(f"API Gateway: Getting history (limit={limit}, offset={offset})")
    
    try:
        history_data = call_service(
            f"{DATABASE_SERVICE_URL}/stats/history",
            params={"limit": limit, "offset": offset}
        )
        
        return history_data
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in get_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history/{owner}/{repo_name}")
async def get_repo_history(owner: str, repo_name: str, limit: int = 10):
    """
    Получить историю для конкретного репозитория
    """
    logger.info(f"API Gateway: Getting history for {owner}/{repo_name}")
    
    try:
        history_data = call_service(
            f"{DATABASE_SERVICE_URL}/stats/repo/{owner}/{repo_name}",
            params={"limit": limit}
        )
        
        return history_data
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in get_repo_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/services/status")
async def get_services_status():
    """
    Получить статус всех микросервисов
    """
    status = {}
    
    services = {
        'github_service': f"{GITHUB_SERVICE_URL}/health",
        'analytics_service': f"{ANALYTICS_SERVICE_URL}/health",
        'database_service': f"{DATABASE_SERVICE_URL}/health"
    }
    
    for service_name, url in services.items():
        try:
            response = call_service(url)
            status[service_name] = {
                'status': 'online',
                'details': response
            }
        except Exception as e:
            status[service_name] = {
                'status': 'offline',
                'error': str(e)
            }
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "services": status
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)