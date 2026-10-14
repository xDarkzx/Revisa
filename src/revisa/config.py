"""Settings from the environment (``REVISA_*``) or a ``.env`` file. No secrets: Azure access is
keyless (ADR 0005), so these are endpoints and names only."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REVISA_", env_file=".env", extra="ignore")

    ollama_url: str = "http://localhost:11434/v1"
    local_model: str = "qwen2.5-coder:14b-instruct-q4_K_M"

    azure_document_intelligence_endpoint: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str = "gpt-4.1-mini"
    azure_openai_api_version: str = "2024-10-21"
    azure_cosmos_endpoint: str | None = None

    # Seconds between Document Intelligence calls; the free tier allows about 20 a minute.
    azure_ocr_interval: float = 3.5
