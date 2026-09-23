"""Fetch prayer times from a mosque's website.

Extraction strategies, tried in order:
  1. Embedded widgets — MasjidNow and Mawaqit iframes are detected on the
     homepage and their data fetched directly.
  2. Schedule PDF — any PDF link whose URL or anchor text mentions prayer
     times is parsed with pdfplumber (ICOE-style monthly timetable).
  3. Page text — prayer names followed by times are scraped from the
     homepage, then from one linked "prayer times" page if needed.

Only IQAMA times are imported — that is what the mosque TV displays.
Sunrise/sunset are computed from latitude/longitude, not taken from the
site. Rows the user edited manually (source='manual') are never overwritten
unless a sync is explicitly forced.
"""

import io
import logging
import re
from datetime import date, datetime, timedelta
from html import unescape
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.utils import timezone
from suntime import Sun

from .models import PrayerTime

logger = logging.getLogger(__name__)

SYNC_INTERVAL = timedelta(hours=24)
UA = {'User-Agent': 'FZDigitals/1.0'}
TIME_RE = re.compile(r'^\d{1,2}:\d{2}$')
ANCHOR_RE = re.compile(r'href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
PRAYER_WORDS_RE = re.compile(r'prayer|sala[ah]?[ht]|namaz|iqamah?|timing|schedule', re.I)
MASJIDNOW_RE = re.compile(r'masjidnow\.com/(?:mosques|widgets)/(\d+)', re.I)
MAWAQIT_RE = re.compile(r'mawaqit\.net/(?:[a-z]{2}/)?m/([a-z0-9][a-z0-9\-]*)', re.I)
TIME_NEAR_RE = r'(\d{1,2}:\d{2})\s*(am|pm|a\.m\.|p\.m\.)?'
PRAYER_NAMES = {
    'fajr': r'fajr|fajar',
    'dhuhr': r'dhuhr|dhur|duhar|zuhr|zohar|dohr',
    'asr': r'asr|asar',
    'maghrib': r'maghrib|magrib',
    'isha': r'isha|ishaa|esha',
    'jummah': r"jummah|jumu'?ah|juma|friday",
    'jummah2': r"(?:2nd|second)\s+jumu'?ah|jumu'?ah\s*2|jummah\s*2",
    'jummah3': r"(?:3rd|third)\s+jumu'?ah|jumu'?ah\s*3|jummah\s*3",
}
NAME_TO_KEY = {
    'fajr': 'fajr', 'fajar': 'fajr',
    'dhuhr': 'dhuhr', 'dhur': 'dhuhr', 'duhar': 'dhuhr',
    'zuhr': 'dhuhr', 'zohar': 'dhuhr', 'dohr': 'dhuhr',
    'asr': 'asr', 'asar': 'asr',
    'maghrib': 'maghrib', 'magrib': 'maghrib',
    'isha': 'isha', 'ishaa': 'isha', 'esha': 'isha',
    'jummah': 'jummah', 'jumuah': 'jummah', 'juma': 'jummah',
    'jummah2': 'jummah2', 'jumuah2': 'jummah2', 'juma2': 'jummah2',
    'jummah3': 'jummah3', 'jumuah3': 'jummah3', 'juma3': 'jummah3',
}
# JS/JSON configs: fajr: "05:30", "dhuhr_iqama": '1:40 PM', etc.
JS_TIME_RE = re.compile(
    r'\b(fajr|fajar|dhuhr|dhur|zuhr|zohar|dohr|asr|asar|maghrib|magrib|isha|ishaa|esha|jummah|jumuah|juma)[_\s]?([23])?\b'
    r'([_\s]?(?:iqamah?|athan|adhan))?["\']?\s*[:=]\s*["\'](\d{1,2}:\d{2})\s*(am|pm|a\.m\.|p\.m\.)?',
    re.I)
REQUIRED_PRAYERS = ('fajr', 'dhuhr', 'asr', 'maghrib', 'isha')
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


def find_schedule_pdf_url(html, base_url):
    """Locate a prayer-schedule PDF link in page HTML — any .pdf whose URL
    or anchor text mentions prayer times."""
    for m in ANCHOR_RE.finditer(html):
        href, text = m.group(1), re.sub(r'<[^>]+>', '', m.group(2))
        if '.pdf' not in href.lower():
            continue
        if PRAYER_WORDS_RE.search(href) or PRAYER_WORDS_RE.search(text):
            return urljoin(base_url, href)
    return None


def _masjidnow_times(html):
    """MasjidNow widget embed -> today's iqama times."""
    m = MASJIDNOW_RE.search(html)
    if not m:
        return None
    try:
        resp = requests.get(f'https://masjidnow.com/mosques/{m.group(1)}',
                            timeout=15, headers=UA)
        resp.raise_for_status()
        times = _html_prayer_times(resp.text)
        return {None: times} if times else None
    except Exception as e:
        logger.warning(f'MasjidNow fetch failed: {e}')
        return None


def _mawaqit_times(html):
    """Mawaqit widget embed -> today's iqama times."""
    m = MAWAQIT_RE.search(html)
    if not m:
        return None
    try:
        resp = requests.get(f'https://mawaqit.net/en/m/{m.group(1)}',
                            timeout=15, headers=UA)
        resp.raise_for_status()
        tm = re.search(r'"times"\s*:\s*\[([^\]]+)\]', resp.text)
        if not tm:
            return None
        vals = re.findall(r'"(\d{1,2}:\d{2})"', tm.group(1))
        if len(vals) == 6:  # fajr, shuruk, dhuhr, asr, maghrib, isha
            vals = [vals[0], *vals[2:]]
        if len(vals) < 5:
            return None
        keys = ('fajr', 'dhuhr', 'asr', 'maghrib', 'isha')
        return {None: {k: datetime.strptime(v, '%H:%M').time() for k, v in zip(keys, vals)}}
    except Exception as e:
        logger.warning(f'Mawaqit fetch failed: {e}')
        return None


ATHANPLUS_RE = re.compile(
    r'timing\.athanplus\.com/masjid/widgets/embed[^"\'\s<>]*masjid_id=([A-Za-z0-9]+)')


def _athanplus_times(html):
    """Masjidal/AthanPlus embed widget (timing.athanplus.com).

    The widget is a day carousel — only the first (active) slide is today.
    Daily rows are 'Name adhan iqamah'; Jumuah rows put the time BEFORE
    the label ('1:15 PM Jumuah 1'), so they need their own pattern.
    """
    m = ATHANPLUS_RE.search(html)
    if not m:
        return None
    try:
        resp = requests.get(
            'https://timing.athanplus.com/masjid/widgets/embed'
            f'?theme=3&masjid_id={m.group(1)}', timeout=15, headers=UA)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f'AthanPlus fetch failed: {e}')
        return None
    slide = re.search(r'carousel-item active.*?(?=carousel-item|$)', resp.text, re.S)
    text = _page_text(slide.group(0) if slide else resp.text)
    result = _scrape_times(text)
    for jm in re.finditer(r'(\d{1,2}:\d{2})\s*(am|pm|a\.m\.|p\.m\.)?\s+Jumua?h\s*(\d)?',
                          text, re.I):
        key = 'jummah' if jm.group(3) in (None, '1') else f'jummah{jm.group(3)}'
        ap = (jm.group(2) or '').replace('.', '').lower()
        result[key] = _to_24h(jm.group(1), ap != 'am')
    return {None: result} if _validated(result) else None


def _wayback_html(url):
    """Latest Wayback Machine snapshot of a page, archive URL rewriting
    unwrapped. Used only to discover widget/PDF links on WAF-challenged
    sites (e.g. Cloudflare) — archived prayer times would be stale."""
    try:
        avail = requests.get(f'https://archive.org/wayback/available?url={url}',
                             timeout=15, headers=UA).json()
        snap = avail.get('archived_snapshots', {}).get('closest', {})
        if not snap.get('available'):
            return None
        snap_url = re.sub(r'/web/(\d+)/', r'/web/\1id_/',
                          snap['url'].replace('http://', 'https://'))
        resp = requests.get(snap_url, timeout=20, headers=UA)
        resp.raise_for_status()
        return re.sub(r'https?://web\.archive\.org/web/\d+[a-z_]*/(https?://)',
                      r'\1', resp.text)
    except Exception as e:
        logger.warning(f'Wayback fallback failed ({url}): {e}')
        return None


FIREBASE_DB_RE = re.compile(r'databaseURL["\']?\s*:\s*["\'](https://[^"\']+)["\']')
FIREBASE_PRAYER_REF_RE = re.compile(
    r"ref\(\s*['\"]([^'\"]*prayer[^'\"]*?/)['\"]\s*\+\s*month", re.I)
FIREBASE_JUMMAH_REF_RE = re.compile(r"ref\(\s*['\"]([^'\"]*jummah[^'\"]*?)['\"]\s*\)", re.I)
FIREBASE_CONFIG_SRC_RE = re.compile(r'src=["\']([^"\']*firebase[^"\']*\.js[^"\']*)["\']', re.I)


def _parse_ampm(s):
    """'6:00 PM' -> time; None when unparseable."""
    m = re.match(r'(\d{1,2}:\d{2})\s*(am|pm|a\.m\.|p\.m\.)?', s.strip(), re.I)
    if not m:
        return None
    ap = (m.group(2) or '').replace('.', '').lower()
    return _to_24h(m.group(1), ap != 'am')


def _firebase_times(html, base_url, today):
    """Mosque PWA backed by Firebase RTDB (e.g. ICOR's iant app).

    The site renders times client-side from firebase.database() refs; the
    RTDB REST endpoint serves the same data when rules allow public read.
    Plain keys are iqamah, '*Begin' keys are adhan.
    """
    ref_m = FIREBASE_PRAYER_REF_RE.search(html)
    if not ref_m:
        return None
    db_m = FIREBASE_DB_RE.search(html)
    db_url = db_m.group(1) if db_m else None
    if not db_url:
        src_m = FIREBASE_CONFIG_SRC_RE.search(html)
        if src_m:
            try:
                cfg = requests.get(urljoin(base_url, src_m.group(1)),
                                   timeout=15, headers=UA)
                db_m = FIREBASE_DB_RE.search(cfg.text)
                db_url = db_m.group(1) if db_m else None
            except Exception as e:
                logger.warning(f'Firebase config fetch failed: {e}')
    if not db_url:
        return None
    db_url = db_url.rstrip('/')

    today = today or timezone.now().date()
    try:
        data = requests.get(
            f'{db_url}/{ref_m.group(1)}{today.strftime("%B")}.json',
            timeout=15, headers=UA).json()
    except Exception as e:
        logger.warning(f'Firebase prayer fetch failed: {e}')
        return None
    entries = data.values() if isinstance(data, dict) else (data or [])
    row = next((e for e in entries
                if isinstance(e, dict) and str(e.get('day')) == str(today.day)), None)
    if not row:
        return None
    result = {}
    for key in REQUIRED_PRAYERS:
        t = _parse_ampm(str(row.get(key) or ''))
        if t:
            result[key] = t

    jref_m = FIREBASE_JUMMAH_REF_RE.search(html)
    if jref_m:
        try:
            jdata = requests.get(f'{db_url}/{jref_m.group(1).rstrip("/")}.json',
                                 timeout=15, headers=UA).json()
            jrows = jdata.values() if isinstance(jdata, dict) else (jdata or [])
            active = sorted(
                (j for j in jrows if isinstance(j, dict)
                 and str(j.get('status', '1')) not in ('0', '', 'None')),
                key=lambda j: j.get('ID') or 0)
            for i, j in enumerate(active[:3]):
                t = _parse_ampm(str(j.get('Jummah_Time') or ''))
                if t:
                    result['jummah' if i == 0 else f'jummah{i + 1}'] = t
        except Exception as e:
            logger.warning(f'Firebase jummah fetch failed: {e}')

    return {None: result} if _validated(result) else None


def _page_text(html):
    """Visible text of a page — tags/scripts stripped, whitespace collapsed."""
    text = unescape(re.sub(r'<[^>]+>', ' ',
              re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)))
    return re.sub(r'\s+', ' ', text)


def _scrape_times(text, jummah_section=None):
    """Pull every prayer name + time out of page text.

    When two times follow a prayer name (athan then iqama) the last is
    used — iqama is what the TV displays. Jumu'ah is the exception: the
    first time (khutbah start) is shown, e.g. 'First Jumu'ah 1:30 2:00'
    displays 1:30.

    jummah_section: on multi-location sites (e.g. ICOE Main vs North) the
    Jumu'ah blocks repeat per location — this keyword selects the section
    whose heading contains it; blank uses the first Jumu'ah on the page.
    """
    jummah_text = text
    if jummah_section:
        # The keyword may appear earlier on the page (nav, footer) — use the
        # occurrence closest to a following Jumu'ah mention (its section
        # heading sits right above the Jumu'ah rows).
        best_start, best_dist = None, None
        for sec in re.finditer(re.escape(jummah_section), text, re.I):
            jm = re.search(r"jummah|jumu'?ah|juma|friday", text[sec.end():], re.I)
            if jm and (best_dist is None or jm.start() < best_dist):
                best_start, best_dist = sec.start(), jm.start()
        if best_start is not None:
            jummah_text = text[best_start:best_start + 800]
    result = {}
    for key, names in PRAYER_NAMES.items():
        haystack = jummah_text if key.startswith('jummah') else text
        m = re.search(
            rf'\b(?:{names})\b[^0-9]{{0,60}}?{TIME_NEAR_RE}(?:[^0-9]{{0,30}}?{TIME_NEAR_RE})?',
            haystack, re.I)
        if not m:
            continue
        pairs = [(m.group(i), m.group(i + 1)) for i in (1, 3) if m.group(i)]
        if not pairs:
            continue
        t, ap = pairs[0] if key.startswith('jummah') else pairs[-1]
        if t.lstrip('0') == ':00':  # '0:00'/'00:00' = no prayer scheduled
            continue
        ap = (ap or '').replace('.', '').lower()
        pm = (ap == 'pm') if ap else key != 'fajr'
        result[key] = _to_24h(t, pm)
    return result


def _html_prayer_times(html, jummah_section=None):
    """Scrape prayer names + times out of arbitrary page HTML.
    Returns None unless all five daily prayers are found."""
    return _validated(_scrape_times(_page_text(html), jummah_section))


def _jummah_times(html, jummah_section=None):
    """Jumu'ah times only — supplements sources (schedule PDFs) that carry
    daily prayers but no Friday rows."""
    scraped = _scrape_times(_page_text(html), jummah_section)
    return {k: v for k, v in scraped.items() if k.startswith('jummah')}


def _js_prayer_times(html):
    """Prayer times embedded in a JS/JSON config on the page.

    Catches widget data like {"fajr":"05:30","fajr_iqama":"06:15"} that
    never appears in the rendered text. Iqama-labelled keys win over plain
    or athan-labelled ones.
    """
    found = {}
    for m in JS_TIME_RE.finditer(html):
        key = NAME_TO_KEY.get(m.group(1).lower())
        if not key:
            continue
        if key == 'jummah' and m.group(2):
            key = f'jummah{m.group(2)}'
        label = (m.group(3) or '').lower()
        t, ap = m.group(4), (m.group(5) or '').replace('.', '').lower()
        if t.lstrip('0') == ':00':  # '0:00'/'00:00' = no prayer scheduled
            continue
        pm = (ap == 'pm') if ap else key != 'fajr'
        slot = 'iqama' if 'iqama' in label else ('athan' if label else 'plain')
        found.setdefault(key, {})[slot] = _to_24h(t, pm)
    result = {}
    for key, slots in found.items():
        if key.startswith('jummah'):  # khutbah start, not iqama
            result[key] = slots.get('athan') or slots.get('plain') or slots.get('iqama')
        else:
            result[key] = slots.get('iqama') or slots.get('plain') or slots.get('athan')
    return _validated(result)


def _validated(result):
    """Accept only complete, non-degenerate results — five identical times
    means the scraper latched onto one unrelated clock on the page."""
    if not all(k in result for k in REQUIRED_PRAYERS):
        return None
    if len({result[k] for k in REQUIRED_PRAYERS}) == 1:
        return None
    # '0:00' placeholders (e.g. a location with no second Jumu'ah) aren't times
    for k in ('jummah', 'jummah2', 'jummah3'):
        t = result.get(k)
        if t and t.hour == 0 and t.minute == 0:
            del result[k]
    return result


def _find_prayer_pages(html, base_url):
    """Links whose text or URL mentions prayer times — one level deep."""
    seen, pages = set(), []
    for m in ANCHOR_RE.finditer(html):
        href, text = m.group(1), re.sub(r'<[^>]+>', '', m.group(2))
        if '.pdf' in href.lower():
            continue
        if PRAYER_WORDS_RE.search(text) or re.search(r'prayer|sala[ah]?[ht]|namaz|iqamah?', href, re.I):
            url = urljoin(base_url, href)
            if url not in seen:
                seen.add(url)
                pages.append(url)
    return pages


def fetch_prayer_times(website_url, jummah_section=None, for_date=None):
    """Try every known strategy to get prayer times from a mosque site.

    Returns {date: {fajr: time, ...}} for schedule PDFs, or {None: {...}}
    for single-day sources (widgets, page text) — the caller maps None to
    today in the mosque's timezone.
    """
    try:
        resp = requests.get(website_url, timeout=15, headers=UA)
        resp.raise_for_status()
        html = resp.text
        # Resolve relative links against the FINAL url — the entered domain
        # may redirect (e.g. .com -> .org) and sub-path redirects drop the path.
        base_url = resp.url
    except requests.HTTPError:
        # WAF-challenged site (e.g. Cloudflare managed challenge) — pull the
        # latest archived copy to discover widget/PDF links; the widget hosts
        # themselves aren't challenged and serve live times.
        html = _wayback_html(website_url)
        if not html:
            raise
        base_url = website_url

    for fetcher in (_masjidnow_times, _mawaqit_times, _athanplus_times):
        times = fetcher(html)
        if times:
            return times

    times = _firebase_times(html, base_url, for_date)
    if times:
        return times

    pdf_url = find_schedule_pdf_url(html, base_url)
    if pdf_url:
        try:
            presp = requests.get(pdf_url, timeout=30, headers=UA)
            presp.raise_for_status()
            times = parse_prayer_pdf(presp.content)
            if times:
                # Schedule PDFs rarely carry Jumu'ah — merge it from the page
                jummah = _jummah_times(html, jummah_section)
                for entry in times.values():
                    for k, v in jummah.items():
                        entry.setdefault(k, v)
                return times
        except Exception as e:
            logger.warning(f'Prayer PDF fetch failed ({pdf_url}): {e}')

    times = _js_prayer_times(html) or _html_prayer_times(html, jummah_section)
    if times:
        return {None: times}

    for link in _find_prayer_pages(html, base_url)[:3]:
        try:
            r2 = requests.get(link, timeout=15, headers=UA)
            r2.raise_for_status()
            times = _js_prayer_times(r2.text) or _html_prayer_times(r2.text, jummah_section)
            if times:
                return {None: times}
        except Exception as e:
            logger.warning(f'Prayer page fetch failed ({link}): {e}')
    return None


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
    attempt so failures don't retry on every page load, and records the
    outcome on mosque.sync_error so failures are visible to the user.
    """
    mosque.prayer_synced_at = timezone.now()
    mosque.save(update_fields=['prayer_synced_at'])

    synced, err = _sync(mosque, force)
    err = err or ''
    if err != mosque.sync_error:
        mosque.sync_error = err
        mosque.save(update_fields=['sync_error'])
    return synced, err or None


def _sync(mosque, force):
    if not mosque.website_url:
        return 0, 'No website URL set'
    tz = ZoneInfo(mosque.timezone or getattr(settings, 'MOSQUE_TIMEZONE', 'UTC'))
    today = timezone.now().astimezone(tz).date()
    try:
        times = fetch_prayer_times(mosque.website_url, mosque.jummah_section or None, today)
        if not times:
            return 0, 'Could not find prayer times on the website'
    except Exception as e:
        logger.warning(f'Prayer sync failed for mosque {mosque.id}: {e}')
        return 0, str(e)

    synced = 0
    for d, entry in times.items():
        d = d or today  # single-day sources (widgets, page text) key on None
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
    """Lazy daily sync in the mosque's local 12-1 AM window.

    The mosque TV reloads shortly after midnight, which lands the request
    inside the window. A 24h-staleness fallback covers nights when no
    page load happens, so a day is never skipped entirely.
    """
    if not mosque or not mosque.sync_enabled or not mosque.website_url:
        return
    last = mosque.prayer_synced_at
    if last:
        tz = ZoneInfo(mosque.timezone or getattr(settings, 'MOSQUE_TIMEZONE', 'UTC'))
        now = timezone.now()
        now_local = now.astimezone(tz)
        in_midnight_window = (
            now_local.hour == 0
            and last.astimezone(tz).date() < now_local.date()
        )
        stale = now - last >= SYNC_INTERVAL
        if not (in_midnight_window or stale):
            return
    sync_mosque_prayer_times(mosque)
