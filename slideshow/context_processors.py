"""Per-host branding — qama.fzscreens.com serves the Qama mosque brand,
everything else stays FZ Screens."""

BRANDS = {
    'qama': {
        'key': 'qama',
        'name': 'Qama',
        'logo': '/static/qama-logo.svg',
        'tagline': 'Never miss the jamaah — live iqamah times from your masjid, on every screen.',
    },
}

DEFAULT_BRAND = {
    'key': 'fzscreens',
    'name': 'FZ Screens',
    'logo': '/static/logo.png',
    'tagline': 'Run and manage ads on multi screens remotely from anywhere.',
}


def brand(request):
    host = request.get_host().split(':')[0].lower()
    subdomain = host.split('.')[0] if host.count('.') >= 2 else ''
    return {'brand': BRANDS.get(subdomain, DEFAULT_BRAND)}
