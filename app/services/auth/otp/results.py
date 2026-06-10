from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ChallengeCreated:
    challenge_id: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class VerifyResult:
    phone: str
