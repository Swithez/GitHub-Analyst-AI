"""
Общие модели данных для всех микросервисов
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class RepoInfo(BaseModel):
    """Базовая информация о репозитории"""
    full_name: str
    owner: str
    name: str
    description: Optional[str] = None
    language: Optional[str] = None
    stargazers_count: int = 0
    forks_count: int = 0
    subscribers_count: int = 0
    open_issues_count: int = 0
    watchers_count: int = 0
    size: int = 0
    default_branch: str = "main"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    pushed_at: Optional[str] = None
    html_url: Optional[str] = None
    topics: List[str] = []
    has_issues: bool = True
    has_projects: bool = True
    has_wiki: bool = True


class CommitStats(BaseModel):
    """Статистика коммитов"""
    total_commits: int = 0
    commits_by_author: Dict[str, int] = {}
    commits_by_day: Dict[str, int] = {}
    average_commits_per_day: float = 0.0
    most_active_day: Optional[str] = None
    most_active_author: Optional[str] = None


class ContributorInfo(BaseModel):
    """Информация о контрибьюторе"""
    login: str
    contributions: int
    avatar_url: Optional[str] = None
    html_url: Optional[str] = None


class IssueStats(BaseModel):
    """Статистика issue"""
    total_issues: int = 0
    open_issues: int = 0
    closed_issues: int = 0
    average_time_to_close: Optional[float] = None
    issues_by_label: Dict[str, int] = {}


class PullRequestStats(BaseModel):
    """Статистика pull request"""
    total_prs: int = 0
    open_prs: int = 0
    closed_prs: int = 0
    merged_prs: int = 0
    average_time_to_merge: Optional[float] = None


class LanguageStats(BaseModel):
    """Статистика языков программирования"""
    languages: Dict[str, int] = {}
    primary_language: Optional[str] = None
    total_bytes: int = 0


class ActivityStats(BaseModel):
    """Общая статистика активности"""
    repo_info: RepoInfo
    commit_stats: CommitStats
    contributors: List[ContributorInfo] = []
    total_contributors: int = 0
    issue_stats: Optional[IssueStats] = None
    pr_stats: Optional[PullRequestStats] = None
    language_stats: Optional[LanguageStats] = None
    analysis_period_days: int
    activity_index: float = 0.0
    start_date: str
    end_date: str


class AnalyticsRequest(BaseModel):
    """Запрос на аналитику"""
    owner: str
    repo_name: str
    start_date: str
    end_date: str
    days: int


class AnalyticsResponse(BaseModel):
    """Ответ с аналитикой"""
    activity_stats: ActivityStats
    ai_analysis: Optional[str] = None
    recommendations: List[str] = []
    insights: Dict[str, Any] = {}


class HistoryRecord(BaseModel):
    """Запись в истории запросов"""
    id: int
    owner: str
    repo_name: str
    total_commits: int
    total_contributors: int
    avg_commits_per_day: float
    analysis_period_days: int
    activity_index: float
    timestamp: str


class HealthCheck(BaseModel):
    """Проверка здоровья сервиса"""
    status: str
    service: str
    timestamp: str
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    """Ответ с ошибкой"""
    error: str
    details: Optional[str] = None
    status_code: int