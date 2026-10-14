"""Block until new role assignments work on every data plane the proof run uses.

Entra role assignments take a few minutes to reach Document Intelligence, Azure OpenAI and
Cosmos DB. Polling with a tiny request is faster and more reliable than a fixed sleep.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from azure.core.exceptions import HttpResponseError
from openai import APIStatusError
from PIL import Image

from revisa.config import Settings
from revisa.ocr import AzureReadEngine
from revisa.register import CosmosRegister
from revisa.runs import llm_client

TIMEOUT = 15 * 60
settings = Settings()


def document_intelligence() -> None:
    assert settings.azure_document_intelligence_endpoint
    AzureReadEngine(settings.azure_document_intelligence_endpoint).read(Image.new("RGB", (64, 64), "white"))


def openai() -> None:
    llm_client("azure", settings).chat.completions.create(
        model=settings.azure_openai_deployment, messages=[{"role": "user", "content": "ok"}], max_tokens=1
    )


def cosmos() -> None:
    assert settings.azure_cosmos_endpoint
    CosmosRegister.connect(settings.azure_cosmos_endpoint).entries("probe")


def wait(name: str, probe: Callable[[], None]) -> None:
    start = time.monotonic()
    while True:
        try:
            probe()
        except (HttpResponseError, APIStatusError) as error:
            if time.monotonic() - start > TIMEOUT:
                sys.exit(f"{name}: still denied after {TIMEOUT}s: {error}")
            print(f"{name}: not yet ({type(error).__name__}), retrying", flush=True)
            time.sleep(20)
        else:
            print(f"{name}: ready after {time.monotonic() - start:.0f}s", flush=True)
            return


for service, check in (
    ("Document Intelligence", document_intelligence),
    ("Azure OpenAI", openai),
    ("Cosmos DB", cosmos),
):
    wait(service, check)
