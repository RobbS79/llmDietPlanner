"""
Utility functions for scrapers.
"""
import datetime as _dt
import re

from django.utils import timezone

# Matches a Czech/Slovak leaflet date token like "28. 5." or "28.5" (day. month.).
# nbsp between number and dot is normalized away before matching.
_DATE_TOKEN_RE = re.compile(r'(\d{1,2})\.\s*(\d{1,2})\.')


def _resolve_year(day: int, month: int, today: _dt.date):
    """
    Leaflet dates carry no year. Pick the year that places (day, month)
    nearest to `today` within a plausible leaflet window, so a "5. 1."
    scraped in late December resolves to next January, not last January.
    """
    for year in (today.year, today.year + 1, today.year - 1):
        try:
            candidate = _dt.date(year, month, day)
        except ValueError:
            continue  # e.g. 29. 2. on a non-leap year
        delta = (candidate - today).days
        if -45 <= delta <= 320:
            return candidate
    return None


def parse_validity_window(text: str, now=None):
    """
    Parse a leaflet validity window from Czech/Slovak header text.

    Handles both:
      - a full range  "...od čtvrtka, čt 28. 5. – ne 31. 5."  -> (from, until)
      - a single date "platí do neděle 31. 5."                -> (None, until)

    Returns a (valid_from, valid_until) tuple of timezone-aware datetimes
    (valid_from at 00:00:00, valid_until at end-of-day 23:59:59), with either
    element None when not derivable. Returns (None, None) when no date is found.
    `now` is injectable for testing; defaults to timezone.now().
    """
    if not text:
        return None, None

    if now is None:
        now = timezone.now()
    today = now.date()

    cleaned = text.replace('\xa0', ' ')
    tokens = _DATE_TOKEN_RE.findall(cleaned)
    if not tokens:
        return None, None

    dates = []
    for day_str, month_str in tokens:
        resolved = _resolve_year(int(day_str), int(month_str), today)
        if resolved is not None:
            dates.append(resolved)
    if not dates:
        return None, None

    if len(dates) >= 2:
        # Reading order is "od <from> do <until>"; guard against odd ordering.
        valid_from_date, valid_until_date = dates[0], dates[-1]
        if valid_until_date < valid_from_date:
            valid_from_date, valid_until_date = valid_until_date, valid_from_date
    else:
        valid_from_date, valid_until_date = None, dates[0]

    tz = timezone.get_current_timezone()

    def _aware(date_obj, time_obj):
        return timezone.make_aware(_dt.datetime.combine(date_obj, time_obj), tz)

    valid_from = _aware(valid_from_date, _dt.time(0, 0, 0)) if valid_from_date else None
    valid_until = _aware(valid_until_date, _dt.time(23, 59, 59)) if valid_until_date else None
    return valid_from, valid_until


def normalize_ingredient_name(name: str) -> str:
    """
    Normalize ingredient name for matching.
    
    Converts to lowercase and removes extra whitespace.
    Can be extended with more normalization logic (diacritics, etc.)
    
    Args:
        name: Original ingredient name
        
    Returns:
        Normalized ingredient name
    """
    if not name:
        return ""
    # Convert to lowercase and strip whitespace
    normalized = name.lower().strip()
    # Replace multiple spaces with single space
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized

