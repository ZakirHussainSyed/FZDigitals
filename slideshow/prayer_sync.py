"""Fetch prayer times from a mosque's website.

Target sites (e.g. eastsidemosque.com) publish a monthly prayer schedule
PDF linked from the homepage (/images/namaz/YYYY_MM-MM.pdf). We locate the
PDF link, parse the timetable with pdfplumber, and upsert PrayerTime rows.

Only IQAMA times are imported — that is what the mosque TV displays.
Sunrise/sunset are computed from latitude/longitude, not taken from the
PDF. Rows the user edited manually (source='manual') are never overwritten
unless a sync is explicitly forced.
"""

import io
import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.utils import timezone
from suntime import Sun

from .models import PrayerTime

logger = logging.getLogger(__name__)

SYNC_INTERVAL = timedelta(hours=12)
PDF_LINK_RE = re.compile(r'href=["\']([^"\']*namaz/[^"\']+\.pdf)["\']', re.I)
TIME_RE = re.compile(r'^\d{1,2}:\d{2}$')
MONTHS = {m: i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'], 1)}

# Column indexes in the ICOE timetable (verified against 2026_09-10.pdf):
# Date|Hijri|Day|Fajr Azan/Iqama|Sunrise|Duhr Azan/Iqama|Asr Azan|
# Asr Hanafi Azan/Iqama|Maghrib Azan/Iqama|Isha Azan/Iqama
IQAMA_COLS = {'fajr': 4, 'dhuhr': 7, 'asr': 10, 'maghrib': 12, 'isha': 14}


def sunrise_time(latitude, longitude, d, tz):
    if latitude is None or longitude is None:
        return None
    try:
        sun = Sun(float(latitude), float(longitude))
        sr = sun.get_sunrise_time(d)
        if not sr.tzinfo:
            sr = sr.replace(tzinfo=ZoneInfo('UTC'))
        sr = sr.astimezone(tz)
        return sr.time()
    except Exception as e:
        logger.warning(f"Sunrise calc failed for {latitude},{longitude}: {e}")
        return None


def sunset_time(latitude, longitude, d, tz):
    if latitude is None or longitude is None:
        return None
    try:
        sun = Sun(float(latitude), float(longitude))
        ss = sun.get_sunset_time(d)
        if not ss.tzinfo:
            ss = ss.replace(tzinfo=ZoneInfo('UTC'))
        ss = ss.astimezone(tz)
        return ss.time()
    except Exception as e:
        logger.warning(f"Sunset calc failed for {latitude},{longitude}: {e}")
        return None


def _to_24h(t, pm):
    """'4:57' -> time(4,57); '1:10' PM -> time(13,10)."""
    h, m = map(int, t.split(':'))
    if pm and h != 12:
        h += 12
    if not pm and h == 12:
        h = 0
    return datetime.strptime(f'{h:02d}:{m:02d}', '%H:%M').time()


def find_schedule_pdf_url(website_url):
    """Locate the monthly prayer PDF link on the mosque homepage."""
    resp = requests.get(website_url, timeout=15, headers={'User-Agent': 'FZDigitals/1.0'})
    resp.raise_for_status()
    m = PDF_LINK_RE.search(resp.text)
    if not m:
        return None
    return urljoin(website_url, m.group(1))


def parse_prayer_pdf(pdf_bytes):
    """Parse the ICOE-style monthly timetable -> {date: {fajr: time, ...}}.

    Iqama cells are printed only when they change, so values are
    forward-filled down each column.
    """
    import pdfplumber  # heavy import; only needed during sync

    result = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table or not table[0]:
                    continue
                m = re.search(r'\((\w+)\s+(\d{4})\)', table[0][0] or '')
                if not m or m.group(1) not in MONTHS:
                    continue
                month, year = MONTHS[m.group(1)], int(m.group(2))
                last = {}
                for row in table[3:]:  # skip title + 2 header rows
                    if not row or not row[0] or not row[0].strip().isdigit():
                        continue
                    day = int(row[0])
                    entry = {}
                    for name, col in IQAMA_COLS.items():
                        v = (row[col] or '').strip() if col < len(row) else ''
                        if TIME_RE.match(v):
                            last[name] = v
                        if name in last:
                            entry[name] = _to_24h(last[name], pm=(name != 'fajr'))
                    if len(entry) == len(IQAMA_COLS):
                        try:
                            result[date(year, month, day)] = entry
                        except ValueError:
                            continue
    return result


def sync_mosque_prayer_times(mosque, force=False):
    """Fetch the mosque's prayer PDF and upsert PrayerTime rows.

    Returns (synced_count, error_or_none). Stamps prayer_synced_at on every
    attempt so failures don't retry on every page load.
    """
    mosque.prayer_synced_at = timezone.now()
    mosque.save(update_fields=['prayer_synced_at'])

    if not mosque.website_url:
        return 0, 'No website URL set'
    try:
        pdf_url = find_schedule_pdf_url(mosque.website_url)
        if not pdf_url:
            return 0, 'No prayer schedule PDF link found on the website'
        resp = requests.get(pdf_url, timeout=30, headers={'User-Agent': 'FZDigitals/1.0'})
        resp.raise_for_status()
        times = parse_prayer_pdf(resp.content)
        if not times:
            return 0, 'Could not parse prayer times from the PDF'
    except Exception as e:
        logger.warning(f'Prayer sync failed for mosque {mosque.id}: {e}')
        return 0, str(e)

    tz = ZoneInfo(mosque.timezone or getattr(settings, 'MOSQUE_TIMEZONE', 'UTC'))
    synced = 0
    for d, entry in times.items():
        defaults = {
            **entry,
            'sunset': sunset_time(mosque.latitude, mosque.longitude, d, tz),
            'source': 'pdf',
        }
        if force:
            PrayerTime.objects.update_or_create(mosque=mosque, date=d, defaults=defaults)
            synced += 1
        else:
            obj, created = PrayerTime.objects.get_or_create(
                mosque=mosque, date=d, defaults=defaults)
            if not created and obj.source == 'manual':
                continue  # never clobber a manual edit on lazy syncs
            if not created:
                for k, v in defaults.items():
                    setattr(obj, k, v)
                obj.save()
            synced += 1
    return synced, None


def maybe_sync_mosque(mosque):
    """Lazy sync: at most once per SYNC_INTERVAL, only when a website is set."""
    if not mosque or not mosque.website_url:
        return
    if mosque.prayer_synced_at and timezone.now() - mosque.prayer_synced_at < SYNC_INTERVAL:
        return
    sync_mosque_prayer_times(mosque)
