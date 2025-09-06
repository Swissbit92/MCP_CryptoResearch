from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class OhlcvUri:
    scheme: str = "ohlcv"
    location: str = "mem"  # mem|file|http
    path: str = "default"

    def __str__(self) -> str:
        return f"{self.scheme}://{self.location}/{self.path}"
