"""
Web Client - веб-интерфейс для аналитики GitHub
Port: 8080
"""
import os
import logging
import hashlib
import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import requests

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="GitHub Analytics Web Client")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Настройка Jinja2 и кастомных фильтров ---
templates = Jinja2Templates(directory="templates")

def jinja2_hash_filter(value):
    """Превращает строку в числовой хэш для генерации цвета"""
    hash_object = hashlib.md5(str(value).encode('utf-8'))
    return int(hash_object.hexdigest(), 16)

def jinja2_rjust_filter(value, width, fillchar=' '):
    return str(value).rjust(width, fillchar)

templates.env.filters["hash"] = jinja2_hash_filter
templates.env.filters["rjust"] = jinja2_rjust_filter

# Конфигурация
API_GATEWAY_URL = os.getenv('API_GATEWAY_URL', 'http://localhost:8000')

def call_api(endpoint: str, method: str = "GET", json_data: dict = None):
    url = f"{API_GATEWAY_URL}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=120)
        elif method == "POST":
            response = requests.post(url, json=json_data, timeout=120)
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Репозиторий не найден")
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling {url}: {e}")
        raise HTTPException(status_code=502, detail=f"API unavailable")

@app.get("/")
async def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/repo/{owner}/{repo_name}", response_class=HTMLResponse)
async def repo_details_page(request: Request, owner: str, repo_name: str):
    try:
        repo_data = call_api(f"/api/repo/{owner}/{repo_name}")
        return templates.TemplateResponse(
            "repo_details.html",
            {
                "request": request,
                "repo_info": repo_data.get('repo_info', repo_data),
                "owner": owner, "repo_name": repo_name,
                "stats": None, "start_date": "", "end_date": ""
            }
        )
    except Exception as e:
        return templates.TemplateResponse("error.html", {"request": request, "error_msg": str(e)})

@app.post("/get_stats", response_class=HTMLResponse)
async def get_stats_post(
    request: Request,
    owner: str = Form(...),
    repo_name: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...)
):
    try:
        analysis_data = call_api(
            "/api/analyze",
            method="POST",
            json_data={
                "owner": owner,
                "repo_name": repo_name,
                "start_date": start_date + "T00:00:00Z",
                "end_date": end_date + "T23:59:59Z"
            }
        )
        
        # --- ЛОГИКА ПАРСИНГА AI JSON ---
        ai_raw = analysis_data.get('ai_analysis', '')
        ai_content = ""
        ai_summary = analysis_data.get('ai_summary', '')
        ai_insights = analysis_data.get('ai_insights', {})
        ai_recommendations = analysis_data.get('ai_recommendations', [])

        # Если AI прислал строку, которая похожа на JSON, парсим её
        if isinstance(ai_raw, str) and (ai_raw.strip().startswith('{') or "```json" in ai_raw):
            try:
                # Очистка от markdown оберток
                json_str = ai_raw
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                
                parsed_json = json.loads(json_str)
                ai_content = parsed_json.get('analysis', parsed_json.get('detailed_analysis', ''))
                ai_summary = parsed_json.get('summary', ai_summary)
                ai_insights = parsed_json.get('insights', ai_insights)
                ai_recommendations = parsed_json.get('recommendations', ai_recommendations)
            except Exception as e:
                logger.warning(f"Failed to parse AI JSON: {e}")
                ai_content = ai_raw # Оставляем как есть, если не JSON
        else:
            ai_content = ai_raw

        stats = {
            'totalCommits': analysis_data.get('commit_stats', {}).get('total_commits', 0),
            'totalContributors': analysis_data.get('total_contributors', 0),
            'avgCommitsPerDay': analysis_data.get('commit_stats', {}).get('average_commits_per_day', 0),
            'activityIndex': analysis_data.get('activity_index', 0),
            'analysis_period_days': analysis_data.get('analysis_period_days', 0),
            'mostActiveDay': analysis_data.get('commit_stats', {}).get('most_active_day'),
            'mostActiveAuthor': analysis_data.get('commit_stats', {}).get('most_active_author'),
            'totalIssues': analysis_data.get('issue_stats', {}).get('total_issues', 0),
            'openIssues': analysis_data.get('issue_stats', {}).get('open_issues', 0),
            'totalPRs': analysis_data.get('pr_stats', {}).get('total_prs', 0),
            'mergedPRs': analysis_data.get('pr_stats', {}).get('merged_prs', 0),
            
            # Обновленные поля после парсинга
            'ai_analysis': ai_content,
            'ai_summary': ai_summary,
            'ai_insights': ai_insights,
            'ai_recommendations': ai_recommendations,
            
            'languages': analysis_data.get('language_stats', {}).get('languages', {}),
            'top_contributors': analysis_data.get('contributors', [])[:10]
        }
        
        return templates.TemplateResponse(
            "repo_details.html",
            {
                "request": request,
                "repo_info": analysis_data.get('repo_info'),
                "owner": owner, "repo_name": repo_name,
                "stats": stats, "start_date": start_date, "end_date": end_date
            }
        )
    except Exception as e:
        logger.error(f"Error in get_stats_post: {e}", exc_info=True)
        return templates.TemplateResponse("error.html", {"request": request, "error_msg": str(e)})

@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, page: int = 1):
    try:
        history_data = call_api(f"/api/history?limit=20&offset={(page-1)*20}")
        return templates.TemplateResponse(
            "history.html",
            {
                "request": request,
                "statistics": history_data.get('history', []),
                "current_page": page,
                "total_pages": (history_data.get('total', 0) + 19) // 20
            }
        )
    except Exception:
        return templates.TemplateResponse("error.html", {"request": request, "error_msg": "Ошибка истории"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)