from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_secret_key: str = "dev-secret-change-me"
    openai_api_key: str = ""
    openai_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    openai_user_agent: str = "agent/8.0"
    chat_model: str = "glm-4.5-air"
    pr_agent_control_model: str = "glm-4.5-air"
    pr_agent_generation_model: str = "glm-4.5-air"
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = "embedding-3"
    request_timeout: int = 180
    llm_retry_attempts: int = 3
    embedding_batch_size: int = 32

    chunk_size: int = 512
    chunk_overlap: int = 50
    similarity_threshold: float = 0.8
    bm25_top_k: int = 6
    vector_top_k: int = 6
    final_top_k: int = 8
    vector_min_score: float = 0.5
    rag_neighbor_window: int = 1

    max_context_tokens: int = 32000
    summary_keep_rounds: int = 3
    long_term_memory_top_k: int = 3

    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "team_knowledge"
    database_url: str = "sqlite+aiosqlite:///./app.db"
    redis_url: str = "redis://localhost:6379/0"
    session_memory_ttl_seconds: int = 604800
    github_api_base_url: str = "https://api.github.com"
    github_diff_max_files: int = 20
    github_diff_max_chars: int = 24000
    pr_context_planner_diff_chars: int = 5000
    pr_context_stage_diff_chars: int = 12000
    pr_context_stage_summary_chars: int = 2200
    pr_context_tool_history_chars: int = 1200
    pr_context_knowledge_chars: int = 1800
    pr_context_changed_files_limit: int = 12
    pr_context_degraded_diff_chars: int = 6000
    pr_context_degraded_summary_chars: int = 1200
    pr_recovery_github_attempts: int = 2
    pr_alert_webhook_url: str = ""
    pr_alert_provider: str = "generic"
    pr_alert_timeout: int = 10
    pr_alert_dedupe_window_minutes: int = 120
    github_mcp_enabled: bool = False
    github_mcp_url: str = "https://api.githubcopilot.com/mcp/"
    github_mcp_timeout: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
