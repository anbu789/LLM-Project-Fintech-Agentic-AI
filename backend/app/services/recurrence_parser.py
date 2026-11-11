"""
FinTech Agent — Recurrence and Schedule Parser
Parses natural language recurrence descriptions and cron expressions into validated
ScheduleSpec instances. Calculates next-run timestamps using real APScheduler triggers.
"""

from datetime import datetime, timezone
import re
from typing import List, Optional
import zoneinfo
from zoneinfo import ZoneInfo
from apscheduler.triggers.cron import CronTrigger

from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.schemas.schedule import ScheduleSpec

# Common day abbreviations mapping
DAY_MAP = {
    "mon": "mon", "monday": "mon",
    "tue": "tue", "tues": "tue", "tuesday": "tue",
    "wed": "wed", "wednesday": "wed",
    "thu": "thu", "thur": "thu", "thurs": "thu", "thursday": "thu",
    "fri": "fri", "friday": "fri",
    "sat": "sat", "saturday": "sat",
    "sun": "sun", "sunday": "sun",
}


def validate_iana_timezone(tz_name: Optional[str]) -> str:
    """Validates that a timezone string is a recognized IANA timezone identifier."""
    if not tz_name or not tz_name.strip():
        return settings.SCHEDULER_TIMEZONE or "Asia/Kolkata"
    cleaned = tz_name.strip()
    try:
        ZoneInfo(cleaned)
        return cleaned
    except Exception:
        raise ValueError(
            f"Invalid IANA timezone identifier '{cleaned}'. "
            f"Please specify a valid timezone such as 'Asia/Kolkata', 'UTC', or 'America/New_York'."
        )


def _parse_time_parts(text: str) -> tuple[int, int]:
    """Extracts hour (0-23) and minute (0-59) from time string."""
    # 1. Match "at <time>" e.g. "at 10:30 AM", "at 9am", "at 14:00"
    at_match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
    if at_match:
        hour = int(at_match.group(1))
        minute = int(at_match.group(2) or 0)
        meridiem = (at_match.group(3) or "").lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute

    # 2. Match explicit colon time e.g. "10:30", "18:45", "10:30am"
    colon_match = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", text, re.IGNORECASE)
    if colon_match:
        hour = int(colon_match.group(1))
        minute = int(colon_match.group(2))
        meridiem = (colon_match.group(3) or "").lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute

    # 3. Match explicit am/pm time e.g. "9am" or "5 pm"
    ampm_match = re.search(r"\b(\d{1,2})\s*(am|pm)\b", text, re.IGNORECASE)
    if ampm_match:
        hour = int(ampm_match.group(1))
        meridiem = ampm_match.group(2).lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23:
            return hour, 0

    return 9, 0  # default 9:00 AM


def parse_recurrence(text: str, timezone_name: Optional[str] = None) -> ScheduleSpec:
    """Parses natural language recurrence descriptions or cron strings into ScheduleSpec.

    Supported patterns:
      - Standard 5-field cron: '0 9 * * 1', '30 8 * * *'
      - Daily: 'every day at 9am', 'daily at 08:30', 'every day at 6:00 PM'
      - Weekly: 'every monday at 9am', 'every friday at 6:00 pm', 'weekly on monday at 10:00'
      - Monthly: 'first day of every month at 9am', 'every month on the 15th at 10am'
    """
    cleaned = text.strip()
    tz = validate_iana_timezone(timezone_name)

    # 1. Check for standard 5-field cron expression (digits, asterisks, commas, hyphens, slashes)
    cron_parts = cleaned.split()
    is_cron_candidate = (
        len(cron_parts) == 5
        and not any(p.lower() in ("every", "at", "on", "am", "pm", "day", "month", "week") for p in cron_parts)
    )
    if is_cron_candidate:
        try:
            # Validate via APScheduler CronTrigger
            CronTrigger.from_crontab(cleaned, timezone=ZoneInfo(tz))
            return ScheduleSpec(
                frequency="cron",
                recurrence_expression=cleaned,
                timezone=tz,
                cron_expression=cleaned,
            )
        except Exception as e:
            raise ValueError(f"Invalid 5-field cron expression '{cleaned}': {e}")

    lower = cleaned.lower()

    # 2. Daily patterns
    if any(k in lower for k in ("every day", "daily", "each day")):
        time_part = re.sub(r"(every day|daily|each day|at)\s*", "", lower).strip()
        hour, minute = _parse_time_parts(time_part or lower)
        return ScheduleSpec(
            frequency="daily",
            recurrence_expression=f"Every day at {hour:02d}:{minute:02d}",
            timezone=tz,
            hour=hour,
            minute=minute,
            cron_expression=f"{minute} {hour} * * *",
        )

    # 3. Weekly patterns (enforce word boundaries so 'mon' does not match 'month')
    for day_word, day_abbr in DAY_MAP.items():
        if re.search(rf"\b(every|on)\s+{day_word}\b", lower):
            hour, minute = _parse_time_parts(lower)
            day_name_cap = day_word.capitalize()
            return ScheduleSpec(
                frequency="weekly",
                recurrence_expression=f"Every {day_name_cap} at {hour:02d}:{minute:02d}",
                timezone=tz,
                hour=hour,
                minute=minute,
                day_of_week=[day_abbr],
                cron_expression=f"{minute} {hour} * * {day_abbr}",
            )

    # 4. Monthly patterns
    monthly_match = re.search(r"(?:monthly\s+on\s+the|monthly\s+on|on\s+the)\s+(\d{1,2})(?:st|nd|rd|th)?", lower)
    if monthly_match or "first day of" in lower or "1st of" in lower or "first of every month" in lower:
        dom = 1
        if monthly_match:
            dom = int(monthly_match.group(1))
        if not (1 <= dom <= 31):
            raise ValueError(f"Day of month must be between 1 and 31, got {dom}.")
        hour, minute = _parse_time_parts(lower)
        return ScheduleSpec(
            frequency="monthly",
            recurrence_expression=f"Monthly on the {dom} at {hour:02d}:{minute:02d}",
            timezone=tz,
            hour=hour,
            minute=minute,
            day_of_month=dom,
            cron_expression=f"{minute} {hour} {dom} * *",
        )

    dom_match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+)?of\s+(?:every\s+)?month", lower)
    if dom_match:
        dom = int(dom_match.group(1))
        if not (1 <= dom <= 31):
            raise ValueError(f"Day of month must be between 1 and 31, got {dom}.")
        hour, minute = _parse_time_parts(lower)
        return ScheduleSpec(
            frequency="monthly",
            recurrence_expression=f"Every month on the {dom} at {hour:02d}:{minute:02d}",
            timezone=tz,
            hour=hour,
            minute=minute,
            day_of_month=dom,
            cron_expression=f"{minute} {hour} {dom} * *",
        )

    raise ValueError(
        f"Could not extract recurrence pattern from expression: '{cleaned}'. "
        "Supported formats include: 'every day at 9am', 'every monday at 9am', 'first day of every month at 9am', or standard 5-field cron."
    )


def calculate_next_run_times(
    spec: ScheduleSpec,
    count: int = 3,
    base_time: Optional[datetime] = None,
) -> List[str]:
    """Calculates the next N run timestamps using real APScheduler triggers."""
    tz = ZoneInfo(spec.timezone)
    now = (base_time or datetime.now(timezone.utc)).astimezone(tz)

    if spec.frequency == "cron" and spec.cron_expression:
        trigger = CronTrigger.from_crontab(spec.cron_expression, timezone=tz)
    elif spec.frequency == "daily":
        trigger = CronTrigger(hour=spec.hour, minute=spec.minute, timezone=tz)
    elif spec.frequency == "weekly":
        dow = ",".join(spec.day_of_week or ["mon"])
        trigger = CronTrigger(day_of_week=dow, hour=spec.hour, minute=spec.minute, timezone=tz)
    elif spec.frequency == "monthly":
        trigger = CronTrigger(day=spec.day_of_month or 1, hour=spec.hour, minute=spec.minute, timezone=tz)
    else:
        # Fallback to hourly or daily trigger
        trigger = CronTrigger(hour=spec.hour or 9, minute=spec.minute or 0, timezone=tz)

    run_times: List[str] = []
    current_time = now

    for _ in range(count):
        next_fire = trigger.get_next_fire_time(current_time, current_time)
        if not next_fire:
            break
        # Convert to UTC ISO string
        utc_dt = next_fire.astimezone(timezone.utc)
        run_times.append(utc_dt.isoformat())
        current_time = next_fire

    return run_times
