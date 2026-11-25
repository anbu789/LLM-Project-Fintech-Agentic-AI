"""
FinTech Agent — Recurrence and Schedule Parser
Parses natural language recurrence descriptions and cron expressions into validated
ScheduleSpec instances. Calculates next-run timestamps using real APScheduler triggers.
"""

from datetime import datetime, timedelta, timezone
import re
from typing import List, Optional
import zoneinfo
from zoneinfo import ZoneInfo
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

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

# Common timezone abbreviation to IANA mapping
TIMEZONE_ABBR_MAP = {
    "ist": "Asia/Kolkata",
    "utc": "UTC",
    "gmt": "UTC",
    "est": "America/New_York",
    "edt": "America/New_York",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "bst": "Europe/London",
    "cet": "Europe/Paris",
    "cest": "Europe/Paris",
    "sgt": "Asia/Singapore",
    "jst": "Asia/Tokyo",
    "aest": "Australia/Sydney",
}


def validate_iana_timezone(tz_name: Optional[str]) -> str:
    """Validates that a timezone string is a recognized IANA timezone identifier."""
    if not tz_name or not tz_name.strip():
        return settings.SCHEDULER_TIMEZONE or "Asia/Kolkata"
    cleaned = tz_name.strip()
    if cleaned.lower() in TIMEZONE_ABBR_MAP:
        return TIMEZONE_ABBR_MAP[cleaned.lower()]
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
    # 1. Match "at <time>" e.g. "at 10:30 AM", "at 9am", "at 14:00", "at 10.39 PM"
    at_match = re.search(r"\bat\s+(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
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

    # 2. Match explicit colon or dot time e.g. "10:30", "18:45", "10:30am", "10.39 PM"
    colon_match = re.search(r"\b(\d{1,2})[:.](\d{2})\s*(am|pm)?\b", text, re.IGNORECASE)
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


def _parse_max_executions(text: str) -> Optional[int]:
    """Extracts finite execution count limit if specified (e.g. '2 times', 'twice', 'stop after 2nd run')."""
    lower = text.lower()

    # 1. Stop after the N-th execution / run
    stop_match = re.search(
        r"\bstop after (?:the\s+)?(first|second|third|fourth|fifth|\d+)(?:st|nd|rd|th)?\s+(?:execution|run)s?\b",
        lower,
    )
    if stop_match:
        val = stop_match.group(1)
        word_map = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
        if val in word_map:
            return word_map[val]
        if val.isdigit():
            return int(val)

    # 2. Match "run X times", "X times", "exactly X times"
    times_match = re.search(
        r"\b(?:run\s+)?(?:exactly\s+)?(\d+|one|two|three|four|five)\s+times?\b",
        lower,
    )
    if times_match:
        val = times_match.group(1)
        word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        if val in word_map:
            return word_map[val]
        if val.isdigit():
            return int(val)

    # 3. Match "twice", "thrice"
    if re.search(r"\b(?:exactly\s+)?twice\b", lower):
        return 2
    if re.search(r"\b(?:exactly\s+)?thrice\b", lower):
        return 3

    # 4. Match "once", "one-time", "one time", "single execution"
    if re.search(r"\b(?:once|one-time|one time|single execution)\b", lower):
        return 1

    # 5. Match "limit to X executions", "max X executions"
    limit_match = re.search(
        r"\b(?:max|maximum|limit\s+to)\s+(?:of\s+)?(\d+)\s+(?:execution|run)s?\b",
        lower,
    )
    if limit_match:
        return int(limit_match.group(1))

    return None


def _parse_start_datetime(
    text: str,
    tz_name: str,
    base_time: Optional[datetime] = None,
) -> Optional[datetime]:
    """Extracts start datetime from natural language text, localized to tz_name."""
    tz = ZoneInfo(tz_name)
    now_in_tz = (base_time or datetime.now(timezone.utc)).astimezone(tz)
    lower = text.lower()

    # Look for start indicator patterns e.g. "starting today at 10:39 PM", "starts at 10:30"
    start_match = re.search(
        r"\b(?:start(?:ing|s)?|begin(?:ning|s)?|from)\s+(?:on\s+|date\s+|at\s+)?([a-z0-9\s:.-]+)",
        lower,
    )

    target_date = now_in_tz.date()
    has_date_spec = False

    iso_date_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if iso_date_match:
        target_date = datetime(
            int(iso_date_match.group(1)),
            int(iso_date_match.group(2)),
            int(iso_date_match.group(3)),
            tzinfo=tz,
        ).date()
        has_date_spec = True
    elif "tomorrow" in lower:
        target_date = target_date + timedelta(days=1)
        has_date_spec = True
    elif "today" in lower:
        has_date_spec = True

    # If start clause exists, parse time from it
    if start_match:
        start_clause = start_match.group(1)
        clause_cut = re.split(r"[,;]|\bwith\b|\band\b|\bto\s+run\b|\bstop\b", start_clause)[0]
        hour, minute = _parse_time_parts(clause_cut)
        has_explicit_time = bool(
            re.search(r"\b\d{1,2}[:.]\d{2}\b", clause_cut)
            or re.search(r"\b\d{1,2}\s*(?:am|pm)\b", clause_cut)
            or re.search(r"\bat\s+\d{1,2}\b", clause_cut)
        )
    else:
        hour, minute = _parse_time_parts(lower)
        has_explicit_time = bool(
            re.search(r"\b\d{1,2}[:.]\d{2}\b", lower)
            or re.search(r"\b\d{1,2}\s*(?:am|pm)\b", lower)
            or re.search(r"\bat\s+\d{1,2}\b", lower)
        )

    # Return datetime if explicit start clause, date keyword, or single run with explicit time
    is_one_time = bool(re.search(r"\b(?:once|one-time|one time)\b", lower))
    if start_match or has_date_spec or (is_one_time and has_explicit_time):
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            0,
            0,
            tzinfo=tz,
        )

    return None


def _parse_end_datetime(
    text: str,
    tz_name: str,
    base_time: Optional[datetime] = None,
) -> Optional[datetime]:
    """Extracts optional end datetime from natural language text, localized to tz_name."""
    tz = ZoneInfo(tz_name)
    now_in_tz = (base_time or datetime.now(timezone.utc)).astimezone(tz)
    lower = text.lower()

    end_match = re.search(
        r"\b(?:until|ending|ends?|stop(?:ping)?\s+at|through)\s+(?:on\s+|date\s+|at\s+)?([a-z0-9\s:.-]+)",
        lower,
    )
    if not end_match:
        return None

    end_clause = end_match.group(1)
    clause_cut = re.split(r"[,;]|\bwith\b|\band\b", end_clause)[0]

    target_date = now_in_tz.date()
    iso_date_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", clause_cut)
    if iso_date_match:
        target_date = datetime(
            int(iso_date_match.group(1)),
            int(iso_date_match.group(2)),
            int(iso_date_match.group(3)),
            tzinfo=tz,
        ).date()
    elif "tomorrow" in clause_cut:
        target_date = target_date + timedelta(days=1)

    hour, minute = _parse_time_parts(clause_cut)
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        0,
        0,
        tzinfo=tz,
    )


def parse_recurrence(text: str, timezone_name: Optional[str] = None) -> ScheduleSpec:
    """Parses natural language recurrence descriptions or cron strings into ScheduleSpec.

    Supported patterns:
      - Standard 5-field cron: '0 9 * * 1', '30 8 * * *'
      - One-time scheduled jobs: 'run once at 10:30 PM', 'schedule once today at 5pm'
      - Minute intervals: 'every 2 minutes', '2-minute interval', 'interval of 2 minutes'
      - Hour intervals: 'every 2 hours', 'every hour', 'hourly'
      - Weekdays: 'every weekday at 9am', 'weekdays at 8:30'
      - Daily: 'every day at 9am', 'daily at 08:30', 'every day at 6:00 PM'
      - Weekly: 'every monday at 9am', 'every friday at 6:00 pm', 'weekly on monday at 10:00'
      - Monthly: 'first day of every month at 9am', 'every month on the 15th at 10am'
      - Finite/Execution-limited schedules: 'run 2 times with a 2-minute interval', 'stop after 2nd execution'
    """
    cleaned = text.strip()

    # 1. Check for standard 5-field cron expression first (digits, asterisks, commas, hyphens, slashes)
    cron_parts = cleaned.split()
    is_cron_candidate = (
        len(cron_parts) == 5
        and not any(p.lower() in ("every", "at", "on", "am", "pm", "day", "month", "week") for p in cron_parts)
    )
    if is_cron_candidate:
        tz = validate_iana_timezone(timezone_name)
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

    # Strip markdown bold/code syntax (e.g. **bold**, __bold__, `code`)
    cleaned_no_md = re.sub(r"\*\*|__|`", "", cleaned)

    # Detect timezone abbreviation from text if timezone_name is empty or default
    tz_to_use = timezone_name
    if not tz_to_use or tz_to_use == settings.SCHEDULER_TIMEZONE:
        tz_match = re.search(r"\b(IST|UTC|GMT|EST|EDT|CST|CDT|PST|PDT|BST|CET|CEST|SGT|JST|AEST)\b", cleaned_no_md)
        if tz_match:
            abbr = tz_match.group(1).lower()
            if abbr in TIMEZONE_ABBR_MAP:
                tz_to_use = TIMEZONE_ABBR_MAP[abbr]

    tz = validate_iana_timezone(tz_to_use)
    lower = cleaned_no_md.lower()

    # Extract optional finite execution bounds, start datetime, and end datetime
    max_executions = _parse_max_executions(cleaned_no_md)
    start_dt = _parse_start_datetime(cleaned_no_md, tz)
    start_at = start_dt.astimezone(timezone.utc) if start_dt else None
    end_dt = _parse_end_datetime(cleaned_no_md, tz)
    end_at = end_dt.astimezone(timezone.utc) if end_dt else None

    # 2. Minute interval patterns (e.g., 'every 2 minutes', '2-minute interval', 'interval of 2 minutes', 'every 5 mins')
    min_match = (
        re.search(r"\bevery\s+(\d+)?\s*(?:minute|min)s?\b", lower)
        or re.search(r"\b(?:interval|intervals)\s+of\s+(\d+)\s*(?:minute|min)s?\b", lower)
        or re.search(r"\b(\d+)[ -](?:minute|min)s?\s*(?:interval|intervals)?\b", lower)
        or re.search(r"\b(?:at|with)\s+(?:an?\s+)?(\d+)[ -](?:minute|min)s?\b", lower)
    )
    if min_match or "every minute" in lower or "each minute" in lower:
        mins = 1
        if min_match:
            for g in min_match.groups():
                if g:
                    mins = int(g)
                    break
        if mins <= 0 or mins > 59:
            raise ValueError(f"Minute interval must be between 1 and 59, got {mins}.")
        cron_expr = f"*/{mins} * * * *" if mins > 1 else "* * * * *"

        if max_executions or start_dt or "interval" in lower:
            freq = "interval"
            desc_parts = []
            if max_executions:
                desc_parts.append(f"Run {max_executions} times at {mins}-minute intervals")
            else:
                desc_parts.append(f"Every {mins} minute" if mins == 1 else f"Every {mins} minutes")
            if start_dt:
                desc_parts.append(f"starting at {start_dt.strftime('%H:%M')} ({tz})")
            desc = " ".join(desc_parts)
            return ScheduleSpec(
                frequency=freq,
                recurrence_expression=desc,
                timezone=tz,
                cron_expression=cron_expr,
                interval_minutes=mins,
                max_executions=max_executions,
                start_at=start_at,
                end_at=end_at,
            )
        else:
            return ScheduleSpec(
                frequency="cron",
                recurrence_expression=f"Every {mins} minute" if mins == 1 else f"Every {mins} minutes",
                timezone=tz,
                cron_expression=cron_expr,
                interval_minutes=mins,
                max_executions=max_executions,
                start_at=start_at,
                end_at=end_at,
            )

    # 3. Hour interval patterns (e.g., 'every 2 hours', 'every hour', 'hourly', 'every 1 hr')
    hr_match = (
        re.search(r"\bevery\s+(\d+)?\s*(?:hour|hr)s?\b", lower)
        or re.search(r"\b(?:interval|intervals)\s+of\s+(\d+)\s*(?:hour|hr)s?\b", lower)
        or re.search(r"\b(\d+)[ -](?:hour|hr)s?\s*(?:interval|intervals)?\b", lower)
        or re.search(r"\b(?:at|with)\s+(?:an?\s+)?(\d+)[ -](?:hour|hr)s?\b", lower)
    )
    if hr_match or "every hour" in lower or "each hour" in lower or "hourly" in lower:
        hrs = 1
        if hr_match:
            for g in hr_match.groups():
                if g:
                    hrs = int(g)
                    break
        if hrs <= 0 or hrs > 23:
            raise ValueError(f"Hour interval must be between 1 and 23, got {hrs}.")
        cron_expr = f"0 */{hrs} * * *" if hrs > 1 else "0 * * * *"
        return ScheduleSpec(
            frequency="cron",
            recurrence_expression=f"Every {hrs} hour" if hrs == 1 else f"Every {hrs} hours",
            timezone=tz,
            cron_expression=cron_expr,
            interval_minutes=hrs * 60,
            max_executions=max_executions,
            start_at=start_at,
            end_at=end_at,
        )

    # 4. One-time scheduled jobs (e.g. 'run once at 10:30 PM', 'schedule once today at 5pm')
    is_once_explicit = bool(re.search(r"\b(?:once|one-time|one time|single execution)\b", lower))
    if max_executions == 1 or is_once_explicit:
        hour, minute = (start_dt.hour, start_dt.minute) if start_dt else _parse_time_parts(lower)
        desc = f"Run once at {hour:02d}:{minute:02d} ({tz})"
        return ScheduleSpec(
            frequency="once",
            recurrence_expression=desc,
            timezone=tz,
            hour=hour,
            minute=minute,
            max_executions=1,
            start_at=start_at,
            end_at=end_at,
        )

    # 5. Weekday patterns (Monday through Friday)
    if any(k in lower for k in ("every weekday", "weekdays", "each weekday", "every business day", "business days")):
        hour, minute = _parse_time_parts(lower)
        return ScheduleSpec(
            frequency="weekly",
            recurrence_expression=f"Every weekday at {hour:02d}:{minute:02d}",
            timezone=tz,
            hour=hour,
            minute=minute,
            day_of_week=["mon", "tue", "wed", "thu", "fri"],
            cron_expression=f"{minute} {hour} * * mon-fri",
            max_executions=max_executions,
            start_at=start_at,
            end_at=end_at,
        )

    # 6. Daily patterns
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
            max_executions=max_executions,
            start_at=start_at,
            end_at=end_at,
        )

    # 7. Weekly patterns (enforce word boundaries so 'mon' does not match 'month')
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
                max_executions=max_executions,
                start_at=start_at,
                end_at=end_at,
            )

    # 8. Monthly patterns
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
            max_executions=max_executions,
            start_at=start_at,
            end_at=end_at,
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
            max_executions=max_executions,
            start_at=start_at,
            end_at=end_at,
        )

    # 9. Explicit time scheduling without explicit 'daily' (e.g., 'schedule at 9am', 'run at 10:30 PM')
    if any(k in lower for k in ("schedule", "recurring", "run")) and re.search(r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", lower):
        hour, minute = _parse_time_parts(lower)
        return ScheduleSpec(
            frequency="daily",
            recurrence_expression=f"Every day at {hour:02d}:{minute:02d}",
            timezone=tz,
            hour=hour,
            minute=minute,
            cron_expression=f"{minute} {hour} * * *",
            max_executions=max_executions,
            start_at=start_at,
            end_at=end_at,
        )

    raise ValueError(
        f"Could not extract recurrence pattern from expression: '{cleaned}'. "
        "Supported formats include: 'every day at 9am', 'every monday at 9am', 'run once at 10:30 PM', 'with a 2-minute interval', or standard 5-field cron."
    )


def calculate_next_run_times(
    spec: ScheduleSpec,
    count: int = 3,
    base_time: Optional[datetime] = None,
) -> List[str]:
    """Calculates the next N run timestamps using real APScheduler triggers or interval projections."""
    tz = ZoneInfo(spec.timezone)
    now = (base_time or datetime.now(timezone.utc)).astimezone(tz)

    max_exec = spec.max_executions
    effective_count = min(count, max_exec) if max_exec else count
    if effective_count <= 0:
        return []

    # 1. One-time scheduled execution
    if spec.frequency == "once":
        if spec.start_at:
            run_dt = spec.start_at.astimezone(timezone.utc)
        else:
            local_dt = datetime(now.year, now.month, now.day, spec.hour or 9, spec.minute or 0, tzinfo=tz)
            if local_dt < now:
                local_dt += timedelta(days=1)
            run_dt = local_dt.astimezone(timezone.utc)
        return [run_dt.isoformat()]

    # 2. Fixed interval execution (minutes)
    if (spec.frequency == "interval" or spec.interval_minutes) and (spec.start_at or spec.max_executions or spec.frequency == "interval"):
        mins = spec.interval_minutes or 1
        run_times: List[str] = []

        if spec.start_at:
            first_run = spec.start_at.astimezone(tz)
        else:
            first_run = now

        current_run = first_run
        for _ in range(effective_count):
            if spec.end_at and current_run > spec.end_at.astimezone(tz):
                break
            utc_dt = current_run.astimezone(timezone.utc)
            run_times.append(utc_dt.isoformat())
            current_run = current_run + timedelta(minutes=mins)

        return run_times

    # 3. Recurring schedules (cron, daily, weekly, monthly) using APScheduler triggers
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

    for _ in range(effective_count):
        next_fire = trigger.get_next_fire_time(current_time, current_time)
        if not next_fire:
            break
        if spec.end_at and next_fire > spec.end_at.astimezone(tz):
            break
        # Convert to UTC ISO string
        utc_dt = next_fire.astimezone(timezone.utc)
        run_times.append(utc_dt.isoformat())
        current_time = next_fire

    return run_times
