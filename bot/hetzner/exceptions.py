from dataclasses import dataclass


@dataclass
class HetznerError(Exception):
    message: str
    code: str | None = None
    status_code: int = 0


@dataclass
class HetznerRateLimitError(HetznerError):
    retry_after: float = 0.0


@dataclass
class HetznerAuthError(HetznerError):
    pass


@dataclass
class HetznerNotFoundError(HetznerError):
    pass
