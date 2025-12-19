"""
GitHub Service - сбор данных из GitHub API
Port: 8001
"""
import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="GitHub Service", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация
GITHUB_API_URL = "https://api.github.com"
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')

# Headers для GitHub API
headers = {
    'Accept': 'application/vnd.github.v3+json'
}
if GITHUB_TOKEN:
    headers['Authorization'] = f'token {GITHUB_TOKEN}'
    logger.info("GitHub token configured")
else:
    logger.warning("No GitHub token configured - API rate limits will be restricted")


class AnalysisRequest(BaseModel):
    owner: str
    repo_name: str
    start_date: str
    end_date: str


def make_github_request(endpoint: str, params: Dict = None) -> Any:
    """Выполнить запрос к GitHub API"""
    url = f"{GITHUB_API_URL}/{endpoint}"
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        # Логирование лимитов
        remaining = response.headers.get('X-RateLimit-Remaining')
        limit = response.headers.get('X-RateLimit-Limit')
        if remaining and limit:
            logger.info(f"GitHub API rate limit: {remaining}/{limit}")
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            raise HTTPException(status_code=404, detail="Repository not found")
        elif response.status_code == 403:
            raise HTTPException(status_code=403, detail="GitHub API rate limit exceeded")
        else:
            error_msg = response.json().get('message', f'HTTP {response.status_code}')
            raise HTTPException(status_code=response.status_code, detail=error_msg)
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "service": "github-service",
        "timestamp": datetime.utcnow().isoformat(),
        "github_token_configured": bool(GITHUB_TOKEN)
    }


@app.get("/repo/{owner}/{repo_name}")
async def get_repo_info(owner: str, repo_name: str):
    """Получить базовую информацию о репозитории"""
    try:
        logger.info(f"Fetching repo info: {owner}/{repo_name}")
        repo_data = make_github_request(f"repos/{owner}/{repo_name}")
        
        return {
            "success": True,
            "repo_info": {
                "full_name": repo_data['full_name'],
                "owner": repo_data['owner']['login'],
                "name": repo_data['name'],
                "description": repo_data.get('description'),
                "language": repo_data.get('language'),
                "stargazers_count": repo_data.get('stargazers_count', 0),
                "forks_count": repo_data.get('forks_count', 0),
                "subscribers_count": repo_data.get('subscribers_count', 0),
                "open_issues_count": repo_data.get('open_issues_count', 0),
                "watchers_count": repo_data.get('watchers_count', 0),
                "size": repo_data.get('size', 0),
                "default_branch": repo_data.get('default_branch', 'main'),
                "created_at": repo_data.get('created_at'),
                "updated_at": repo_data.get('updated_at'),
                "pushed_at": repo_data.get('pushed_at'),
                "html_url": repo_data.get('html_url'),
                "topics": repo_data.get('topics', []),
                "has_issues": repo_data.get('has_issues', True),
                "has_projects": repo_data.get('has_projects', True),
                "has_wiki": repo_data.get('has_wiki', True),
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching repo info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze")
async def analyze_repository(request: AnalysisRequest):
    """
    Полный анализ репозитория:
    - Коммиты
    - Контрибьюторы
    - Issues
    - Pull Requests
    - Языки программирования
    """
    try:
        owner = request.owner
        repo_name = request.repo_name
        start_date = datetime.fromisoformat(request.start_date.replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(request.end_date.replace('Z', '+00:00'))
        days = (end_date - start_date).days + 1
        
        logger.info(f"Starting analysis: {owner}/{repo_name} ({days} days)")
        
        # 1. Базовая информация о репозитории
        repo_info_response = await get_repo_info(owner, repo_name)
        repo_info = repo_info_response['repo_info']
        
        # 2. Сбор коммитов
        logger.info("Fetching commits...")
        commits_data = fetch_commits(owner, repo_name, request.start_date)
        
        # 3. Получение контрибьюторов
        logger.info("Fetching contributors...")
        contributors_data = fetch_contributors(owner, repo_name)
        
        # 4. Статистика по issues
        logger.info("Fetching issues...")
        issues_data = fetch_issues(owner, repo_name, request.start_date)
        
        # 5. Статистика по pull requests
        logger.info("Fetching pull requests...")
        prs_data = fetch_pull_requests(owner, repo_name, request.start_date)
        
        # 6. Языки программирования
        logger.info("Fetching languages...")
        languages_data = fetch_languages(owner, repo_name)
        
        # 7. Расчет метрик
        avg_commits_per_day = commits_data['total_commits'] / days if days > 0 else 0
        
        # Индекс активности
        subscribers = repo_info['subscribers_count'] if repo_info['subscribers_count'] > 0 else 1
        activity_index = (commits_data['total_commits'] / subscribers) * 100
        
        result = {
            "success": True,
            "repo_info": repo_info,
            "commit_stats": {
                "total_commits": commits_data['total_commits'],
                "commits_by_author": commits_data['commits_by_author'],
                "commits_by_day": commits_data['commits_by_day'],
                "average_commits_per_day": round(avg_commits_per_day, 2),
                "most_active_day": commits_data.get('most_active_day'),
                "most_active_author": commits_data.get('most_active_author'),
            },
            "contributors": contributors_data['contributors'],
            "total_contributors": contributors_data['total_contributors'],
            "issue_stats": issues_data,
            "pr_stats": prs_data,
            "language_stats": languages_data,
            "analysis_period_days": days,
            "activity_index": round(activity_index, 2),
            "start_date": request.start_date,
            "end_date": request.end_date
        }
        
        logger.info(f"Analysis completed: {owner}/{repo_name}")
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


def fetch_commits(owner: str, repo_name: str, since_date: str) -> Dict:
    """Получить все коммиты за период"""
    total_commits = 0
    commits_by_author = defaultdict(int)
    commits_by_day = defaultdict(int)
    page = 1
    max_pages = 10  # Ограничение для защиты от больших репозиториев
    
    while page <= max_pages:
        commits = make_github_request(
            f"repos/{owner}/{repo_name}/commits",
            params={'since': since_date, 'per_page': 100, 'page': page}
        )
        
        if not commits:
            break
        
        for commit in commits:
            total_commits += 1
            
            # Автор
            author = commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
            commits_by_author[author] += 1
            
            # День
            date_str = commit.get('commit', {}).get('author', {}).get('date', '')
            if date_str:
                day = date_str.split('T')[0]
                commits_by_day[day] += 1
        
        if len(commits) < 100:
            break
        
        page += 1
    
    # Самый активный день и автор
    most_active_day = max(commits_by_day.items(), key=lambda x: x[1])[0] if commits_by_day else None
    most_active_author = max(commits_by_author.items(), key=lambda x: x[1])[0] if commits_by_author else None
    
    return {
        'total_commits': total_commits,
        'commits_by_author': dict(commits_by_author),
        'commits_by_day': dict(commits_by_day),
        'most_active_day': most_active_day,
        'most_active_author': most_active_author
    }


def fetch_contributors(owner: str, repo_name: str) -> Dict:
    """Получить список контрибьюторов"""
    contributors_list = make_github_request(f"repos/{owner}/{repo_name}/contributors")
    
    contributors = []
    for contributor in contributors_list[:50]:  # Топ 50 контрибьюторов
        contributors.append({
            'login': contributor.get('login'),
            'contributions': contributor.get('contributions', 0),
            'avatar_url': contributor.get('avatar_url'),
            'html_url': contributor.get('html_url')
        })
    
    return {
        'contributors': contributors,
        'total_contributors': len(contributors_list)
    }


def fetch_issues(owner: str, repo_name: str, since_date: str) -> Dict:
    """Получить статистику по issues"""
    try:
        issues = make_github_request(
            f"repos/{owner}/{repo_name}/issues",
            params={'state': 'all', 'since': since_date, 'per_page': 100}
        )
        
        total_issues = 0
        open_issues = 0
        closed_issues = 0
        issues_by_label = defaultdict(int)
        
        for issue in issues:
            # Пропускаем PR (они тоже возвращаются в /issues)
            if 'pull_request' in issue:
                continue
            
            total_issues += 1
            
            if issue['state'] == 'open':
                open_issues += 1
            else:
                closed_issues += 1
            
            # Метки
            for label in issue.get('labels', []):
                issues_by_label[label['name']] += 1
        
        return {
            'total_issues': total_issues,
            'open_issues': open_issues,
            'closed_issues': closed_issues,
            'issues_by_label': dict(issues_by_label)
        }
    
    except Exception as e:
        logger.warning(f"Could not fetch issues: {e}")
        return {
            'total_issues': 0,
            'open_issues': 0,
            'closed_issues': 0,
            'issues_by_label': {}
        }


def fetch_pull_requests(owner: str, repo_name: str, since_date: str) -> Dict:
    """Получить статистику по pull requests"""
    try:
        prs = make_github_request(
            f"repos/{owner}/{repo_name}/pulls",
            params={'state': 'all', 'per_page': 100}
        )
        
        total_prs = 0
        open_prs = 0
        closed_prs = 0
        merged_prs = 0
        
        for pr in prs:
            total_prs += 1
            
            if pr['state'] == 'open':
                open_prs += 1
            else:
                closed_prs += 1
                if pr.get('merged_at'):
                    merged_prs += 1
        
        return {
            'total_prs': total_prs,
            'open_prs': open_prs,
            'closed_prs': closed_prs,
            'merged_prs': merged_prs
        }
    
    except Exception as e:
        logger.warning(f"Could not fetch pull requests: {e}")
        return {
            'total_prs': 0,
            'open_prs': 0,
            'closed_prs': 0,
            'merged_prs': 0
        }


def fetch_languages(owner: str, repo_name: str) -> Dict:
    """Получить статистику по языкам программирования"""
    try:
        languages = make_github_request(f"repos/{owner}/{repo_name}/languages")
        
        if not languages:
            return {
                'languages': {},
                'primary_language': None,
                'total_bytes': 0
            }
        
        total_bytes = sum(languages.values())
        primary_language = max(languages.items(), key=lambda x: x[1])[0] if languages else None
        
        return {
            'languages': languages,
            'primary_language': primary_language,
            'total_bytes': total_bytes
        }
    
    except Exception as e:
        logger.warning(f"Could not fetch languages: {e}")
        return {
            'languages': {},
            'primary_language': None,
            'total_bytes': 0
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)