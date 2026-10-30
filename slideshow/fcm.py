"""Firebase Cloud Messaging sender for device refresh pushes.

Setup (one-time):
  1. Firebase console → project → Service Accounts → generate private key.
  2. Render env var FIREBASE_CREDENTIALS = full contents of that JSON file
     (a file path works too if you prefer mounting it).
  3. Each app's google-services.json goes in <app>/android/app/.

Everything here is a graceful no-op until FIREBASE_CREDENTIALS is set —
the rest of the codebase can call send_refresh() unconditionally.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_app = None  # None = not attempted; False = attempted and unavailable


def _init():
    """Lazy firebase_admin init — returns True when ready to send."""
    global _app
    if _app is not None:
        return bool(_app)
    _app = False
    cred_val = os.environ.get('FIREBASE_CREDENTIALS', '').strip()
    if not cred_val:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials
        cred = (credentials.Certificate(json.loads(cred_val))
                if cred_val.startswith('{')
                else credentials.Certificate(cred_val))
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        _app = True
        logger.info('FCM sender initialised')
    except Exception:
        logger.exception('FCM init failed')
    return _app


def send_refresh(tokens):
    """Send a data-only 'refresh' message to the given FCM tokens.

    The apps listen for type=refresh in pushNotificationReceived and pull
    their slideshow — the push carries no content, just the nudge.
    Returns the list of dead tokens (unregistered) so callers can prune.
    """
    if not tokens or not _init():
        return []
    from firebase_admin import messaging
    dead = []
    msg = messaging.MulticastMessage(
        tokens=tokens,
        data={'type': 'refresh'},
        # High priority so dozing TV boxes wake for the data message.
        android=messaging.AndroidConfig(priority='high'),
    )
    try:
        resp = messaging.send_each_for_multicast(msg)
        for idx, r in enumerate(resp.responses):
            if not r.success and isinstance(
                    r.exception, messaging.UnregisteredError):
                dead.append(tokens[idx])
        if dead:
            logger.info('FCM: %d dead tokens pruned', len(dead))
    except Exception:
        logger.exception('FCM send failed')
    return dead
