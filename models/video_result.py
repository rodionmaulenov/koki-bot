from dataclasses import dataclass


@dataclass
class VideoResult:
    approved: bool
    confidence: float
    reason: str
