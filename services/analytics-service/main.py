"""
Analytics Service - анализ данных через Mistral AI с улучшенным парсингом JSON
Port: 8002
"""
import os
import logging
import json
import re
from typing import Dict, Any, List
from datetime import datetime

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

app = FastAPI(title="Analytics Service", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY', '')
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-large-latest"

class AnalyticsRequest(BaseModel):
    repo_name: str
    owner: str
    activity_data: Dict[str, Any]

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "analytics-service",
        "timestamp": datetime.utcnow().isoformat(),
        "mistral_configured": bool(MISTRAL_API_KEY)
    }

@app.post("/analyze")
async def analyze_with_ai(request: AnalyticsRequest):
    if not MISTRAL_API_KEY:
        return {
            "success": False,
            "error": "Mistral API key not configured",
            "analysis": generate_fallback_analysis(request.activity_data),
            "recommendations": generate_fallback_recommendations(request.activity_data),
            "insights": {"strengths": [], "weaknesses": [], "trends": [], "health_score": "N/A"},
            "summary": "AI сервис не настроен"
        }
    
    try:
        logger.info(f"Starting AI analysis for {request.owner}/{request.repo_name}")
        activity_summary = prepare_activity_summary(request.activity_data)
        prompt = create_analysis_prompt(request.owner, request.repo_name, activity_summary)
        
        ai_response_text = call_mistral_api(prompt)
        analysis_result = parse_ai_response(ai_response_text)
        
        return {
            "success": True,
            "analysis": analysis_result['analysis'],
            "recommendations": analysis_result['recommendations'],
            "insights": analysis_result['insights'],
            "summary": analysis_result['summary']
        }
    
    except Exception as e:
        logger.error(f"Error during AI analysis: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "analysis": generate_fallback_analysis(request.activity_data),
            "recommendations": generate_fallback_recommendations(request.activity_data),
            "insights": {"strengths": [], "weaknesses": [], "trends": [], "health_score": "0"},
            "summary": "Ошибка при генерации аналитики"
        }

def prepare_activity_summary(data: Dict[str, Any]) -> str:
    repo_info = data.get('repo_info', {})
    commit_stats = data.get('commit_stats', {})
    
    summary = f"""
    Repo: {repo_info.get('full_name')} | Stars: {repo_info.get('stargazers_count')}
    Period: {data.get('analysis_period_days')} days | Total Commits: {commit_stats.get('total_commits')}
    Activity Index: {data.get('activity_index')}% | Authors: {data.get('total_contributors')}
    Languages: {json.dumps(data.get('language_stats', {}).get('languages', {}))}
    Issues O/C: {data.get('issue_stats', {}).get('open_issues')}/{data.get('issue_stats', {}).get('closed_issues')}
    PRs O/M: {data.get('pr_stats', {}).get('open_prs')}/{data.get('pr_stats', {}).get('merged_prs')}
    """
    return summary.strip()

def create_analysis_prompt(owner: str, repo_name: str, activity_summary: str) -> str:
    return f"""Ты - эксперт-аналитик Open Source проектов. Проанализируй данные репозитория {owner}/{repo_name}:
{activity_summary}

ЗАДАЧА: Сформируй глубокий технический отчет.
ТРЕБОВАНИЯ К ФОРМАТУ:
1. Ответ должен быть СТРОГО в формате JSON.
2. НИКАКОГО лишнего текста, пояснений или markdown-тегов ```json в ответе.
3. Все переносы строк внутри текстовых полей должны быть экранированы как \\n.

СТРУКТУРА JSON (отправь только её):
{{
    "summary": "Краткое резюме (2-3 предложения)",
    "analysis": "Детальный текст разбора (не менее 4 абзацев). Обсуди динамику коммитов, работу с Issues и PR, и стек технологий.",
    "insights": {{
        "strengths": ["список", "сильных", "сторон"],
        "weaknesses": ["список", "проблем"],
        "trends": ["направления", "развития"],
        "health_score": "число от 1 до 10"
    }},
    "recommendations": ["Конкретный совет 1", "Конкретный совет 2", "Конкретный совет 3"]
}}
"""

def call_mistral_api(prompt: str) -> str:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {MISTRAL_API_KEY}"}
    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": "You are a specialized JSON generator. Never include prose outside the JSON object."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2, # Снижаем для минимизации галлюцинаций в структуре
        "response_format": {"type": "json_object"} # Mistral поддерживает принудительный JSON режим
    }
    response = requests.post(MISTRAL_API_URL, headers=headers, json=payload, timeout=110)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

def parse_ai_response(text: str) -> Dict[str, Any]:
    # Дефолтная структура на случай сбоя
    default_res = {
        "summary": "Анализ завершен",
        "analysis": text,
        "insights": {"strengths": [], "weaknesses": [], "trends": [], "health_score": "5"},
        "recommendations": ["Продолжайте мониторинг репозитория"]
    }
    
    try:
        # 1. Очистка от markdown блоков
        clean_text = re.sub(r'```json|```', '', text).strip()
        
        # 2. Поиск JSON объекта
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if match:
            json_str = match.group(0)
            data = json.loads(json_str)
            
            # 3. Гарантируем наличие вложенных структур для фронтенда
            if "insights" not in data or not isinstance(data["insights"], dict):
                data["insights"] = default_res["insights"]
            if "recommendations" not in data or not isinstance(data["recommendations"], list):
                data["recommendations"] = default_res["recommendations"]
                
            return data
        
        return default_res
    except Exception as e:
        logger.error(f"Critical Parsing Error: {e}")
        return default_res

def generate_fallback_analysis(data: Dict[str, Any]) -> str:
    return f"Проект {data.get('repo_name')} показывает индекс активности {data.get('activity_index', 0)}%."

def generate_fallback_recommendations(data: Dict[str, Any]) -> List[str]:
    return ["Увеличьте частоту коммитов", "Закройте устаревшие Issues"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)