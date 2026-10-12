from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

@dataclass(frozen=True)
class Context:
    reference_date: date | None = None     # e.g. date(2026, 10, 13)
    timezone: str | None = None            # e.g. "Asia/Kolkata"

    def __post_init__(self):
        if self.timezone is not None:
            ZoneInfo(self.timezone)        # raises if the timezone name is invalid
