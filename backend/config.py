from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    request_timeout: int = 120
    embedding_batch_size: int = 32

    chunk_size: int = 512
    chunk_overlap: int = 50
    similarity_threshold: float = 0.8
    bm25_top_k: int = 3
    vector_top_k: int = 3
    final_top_k: int = 5
    vector_min_score: float = 0.5

    max_context_tokens: int = 4000
    summary_keep_rounds: int = 3
    long_term_memory_top_k: int = 3

    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "team_knowledge"
    database_url: str = "sqlite+aiosqlite:///./app.db"
    redis_url: str = "redis://localhost:6379/0"
    session_memory_ttl_seconds: int = 604800

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
