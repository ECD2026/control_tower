from dataclasses import dataclass
from typing import Awaitable, Callable, Literal


ExecutionMode = Literal["local", "jenkins"]
LogFn = Callable[[str], Awaitable[None]]
MetadataFn = Callable[[str | None, str | None], Awaitable[None]]


@dataclass
class ExecutionResult:
    status: str
    execution_mode: ExecutionMode
    external_ref: str | None = None
    external_url: str | None = None
