from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from worldpulse.models import Item


class BaseCollector(ABC):
    def __init__(self, config: dict[str, Any], http_client: httpx.AsyncClient) -> None:
        self._config = config
        self._http = http_client

    @abstractmethod
    async def collect(self) -> list[Item]: ...
