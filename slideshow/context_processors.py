"""Per-host branding — takbir-al-ula.fzscreens.com serves the Takbir ul Ula
mosque brand, everything else stays FZ Screens."""

_TAKBIR = {
    'key': 'takbir',
    'name': 'Takbir ul Ula',
    'logo': '/static/slideshow/logo_takbir.png',
    'tagline': 'Never miss the jamaah — live iqamah times from your masjid, on every screen.',
}

BRANDS = {
    'takbir-al-ula': _TAKBIR,
    'qama': _TAKBIR,  # legacy subdomain → same brand
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
