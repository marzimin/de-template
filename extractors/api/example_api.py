import os
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from extractors.base import BaseExtractor

log = structlog.get_logger()


class ExampleApiExtractor(BaseExtractor):
    """Concrete extractor for a REST API.

    Copy and adapt this class for each new API source:
    1. Set BASE_URL and any required headers
    2. Implement `extract` to call the endpoint(s) you need
    3. Return a flat list of dicts — one dict per record
    """

    BASE_URL = "https://api.example.com/v1"

    def __init__(self) -> None:
        self.api_key = os.environ["EXAMPLE_API_KEY"]
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}{path}"
        log.info("api_request", url=url, params=params)
        response = self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def extract(self) -> list[dict[str, Any]]:
        records = self._get("/items")
        log.info("extracted", count=len(records))
        return records
