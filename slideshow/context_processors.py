"""Per-host branding — takbir-al-ula.fzscreens.com serves the Takbir al Ula
mosque brand, everything else stays FZ Screens."""

_TAKBIR = {
    'key': 'takbir',
    'name': 'Takbir al Ula',
    'logo': '/static/slideshow/logo_takbir.png',
    # Logo artwork has no text — show the name beneath it.
    'wordmark': 'Takbir-al-Ula',
    'login_subtitle': 'Sign in to manage your masjid',
    'login_title': 'Sign In - Takbir al Ula',
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
    'wordmark': '',
    'login_subtitle': 'Sign in to manage your slideshows',
    'login_title': 'Sign In - FZ Screens',
    'tagline': 'Run and manage ads on multi screens remotely from anywhere.',
}


def brand(request):
    host = request.get_host().split(':')[0].lower().removeprefix('www.')
    # First label picks the brand — works for subdomains (takbir-al-ula.fzscreens.com)
    # and bare domains (takbir-al-ula.com); unknown labels → FZ Screens.
    subdomain = host.split('.')[0]
    b = BRANDS.get(subdomain, DEFAULT_BRAND)
    # Mosque accounts carry the Takbir brand on any host (dashboard etc.).
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        # getattr returns None when the OneToOne profile doesn't exist
        profile = getattr(user, 'userprofile', None)
        if profile is not None and profile.vertical == 'mosque':
            b = _TAKBIR
    return {'brand': b}
