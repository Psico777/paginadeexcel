"""
EMFOX OMS - Configuración Central
Carga variables de entorno y define settings globales del sistema.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json

# Resolve .env relative to this file's parent (backend/)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
    )

    # --- Gemini AI ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # --- Negocio ---
    cny_to_usd_rate: float = 7.2
    next_product_code: int = 10001

    # --- Database ---
    database_url: str = "sqlite:///./emfox_oms.db"

    # --- iLovePDF (Excel → PDF conversion) ---
    ilovepdf_public_key: str = ""
    ilovepdf_secret_key: str = ""

    # --- Ollama Local Vision (para smart crop sin gastar tokens) ---
    ollama_url: str = "http://localhost:11434"
    ollama_vision_model: str = "moondream"

    # --- Servidor ---
    upload_dir: str = "uploads"
    cors_origins: str = '["http://localhost:5173","http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.cors_origins)


settings = Settings()
