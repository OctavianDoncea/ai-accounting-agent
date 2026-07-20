import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database — prefer DATABASE_URL if set (Neon, Render, etc.);
    # fall back to individual vars for local Docker Compose.
    database_url_override: str | None = None  # env var: DATABASE_URL

    postgres_user: str = 'accounting'
    postgres_password: str = 'accounting_dev_pass'
    postgres_db: str = 'accounting_db'
    postgres_host: str = 'postgres'
    postgres_port: int = 5432

    # LLM provider: "ollama" (local) or "groq" (cloud, free tier)
    llm_provider: str = 'ollama'

    # Ollama (local development)
    ollama_url: str = 'http://host.docker.internal:11434'
    ollama_model: str = 'llama3.1:8b'

    # Groq (deployed / cloud)
    groq_api_key: str = ''
    groq_model: str = 'llama-3.3-70b-versatile'

    # App
    upload_dir: str = '/app/uploads'

    model_config = SettingsConfigDict(
        env_file='.env',
        case_sensitive=False,
        extra='ignore',
        env_prefix='',
    )

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            url = self.database_url_override
            # Neon/Render sometimes give "postgres://" which SQLAlchemy 2.0 rejects
            if url.startswith('postgres://'):
                url = url.replace('postgres://', 'postgresql://', 1)
            # Ensure we use psycopg2 driver
            if url.startswith('postgresql://'):
                url = url.replace('postgresql://', 'postgresql+psycopg2://', 1)
            elif url.startswith('postgresql+psycopg2://'):
                pass  # already correct
            return url
        return (
            f'postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}'
            f'@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}'
        )


settings = Settings()

# Pick up DATABASE_URL explicitly (Neon/Render provide this env var name)
if os.environ.get('DATABASE_URL') and not settings.database_url_override:
    settings.database_url_override = os.environ['DATABASE_URL']
