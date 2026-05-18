from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    postgres_user: str = 'accounting'
    postgres_password: str = 'accounting_dev_pass'
    postgres_db: str = 'accounting_db'
    postgres_host: str = 'postgres'
    postgres_port: int = 5432

    ollama_url: str = 'http://host.docker.internal:11434'
    ollama_model: str = 'llama3.1:8b'

    upload_dir: str = '/app/uploads'

    model_config = SettingsConfigDict(env_file='.env', case_sensitive=False, extra='ignore')

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()