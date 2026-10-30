from django.db import models, transaction
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
import threading
import uuid

class MediaFile(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    screen = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    title = models.CharField(max_length=255)
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPE_CHOICES)
    file = models.FileField(
        upload_to='uploads/',
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mov', 'avi']
            )
        ],
    )
    file_size = models.PositiveIntegerField(default=0, help_text='File size in bytes')
    position = models.PositiveIntegerField(
        default=0,
        help_text='Playlist order within (user, screen); lower plays first',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title

    class Meta:
        ordering = ['-created_at']


class DevicePairing(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    screen = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    pairing_id = models.CharField(max_length=12, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'screen']

    def save(self, *args, **kwargs):
        if not self.pairing_id:
            self.pairing_id = self.generate_pairing_id()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_pairing_id():
        return str(uuid.uuid4().hex[:8]).upper()

    def __str__(self) -> str:
        return f"{self.user.email} - Screen-{self.screen} - {self.pairing_id}"


class UserProfile(models.Model):
    SECURITY_QUESTIONS = [
        ('pet', 'What was the name of your first pet?'),
        ('school', 'What was the name of your first school?'),
        ('city', 'In which city were you born?'),
        ('mother', 'What is your mother\'s maiden name?'),
        ('job', 'What was your first job?'),
    ]

    VERTICAL_CHOICES = [
        ('bank', 'Bank'),
        ('mosque', 'Mosque'),
        ('restaurant', 'Restaurant'),
        ('hospital', 'Hospital'),
        ('retail', 'Retail'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    security_question = models.CharField(max_length=50, choices=SECURITY_QUESTIONS, blank=True, default='')
    security_answer = models.CharField(max_length=255, blank=True, default='')
    vertical = models.CharField(
        max_length=20,
        choices=VERTICAL_CHOICES,
        default='bank',
        help_text='Customer vertical that controls dashboard and display features',
    )
    number_of_screens = models.PositiveIntegerField(
        default=5,
        verbose_name='Number of screens',
        help_text='Upper limit of live screens this user is allowed.',
    )
    max_slideshows = models.PositiveIntegerField(
        default=5,
        verbose_name='Number of slideshows',
        help_text='Number of slideshows (screen slots) to display in the dashboard.',
    )
    max_screens_per_slideshow = models.PositiveIntegerField(
        default=0,
        editable=False,
        help_text='Max devices per slideshow; 0 = unlimited',
    )
    max_active_screens = models.PositiveIntegerField(
        default=50,
        editable=False,
        help_text='Total active screens across all slideshows; 0 = unlimited',
    )
    storage_quota_mb = models.PositiveIntegerField(default=100, help_text='Total upload quota in MB')

    def save(self, *args, **kwargs):
        # Number of screens drives the live/active screen limits.
        # Number of slideshows drives the dashboard screen slots and pairing codes.
        if self.number_of_screens is not None and self.number_of_screens > 0:
            self.max_screens_per_slideshow = self.number_of_screens
            self.max_active_screens = self.number_of_screens
        super().save(*args, **kwargs)
        if self.user_id and self.max_slideshows and self.max_slideshows > 0:
            for screen in range(1, self.max_slideshows + 1):
                DevicePairing.objects.get_or_create(user=self.user, screen=screen)
    
    def __str__(self):
        return f"{self.user.username} - Profile"


def generate_device_token():
    return uuid.uuid4().hex


class Device(models.Model):
    """Hardware device for USB displays"""
    DEVICE_TYPE_CHOICES = [
        ('browser', 'Browser'),
        ('usb', 'USB Device'),
    ]
    
    device_id = models.CharField(max_length=100, unique=True)  # Hardware ID or localStorage ID
    # Secret handed to the display when it pairs; required to read its slideshow
    token = models.CharField(max_length=64, unique=True, default=generate_device_token)
    name = models.CharField(max_length=200, blank=True)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPE_CHOICES, default='browser')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)  # Assigned user
    screen = models.IntegerField(default=1, validators=[MinValueValidator(1)])  # Assigned screen
    mosque = models.ForeignKey('Mosque', on_delete=models.SET_NULL, null=True, blank=True, related_name='devices')  # Assigned mosque for Mosque TV
    # Firebase Cloud Messaging registration token — set by the Android app
    # (Capacitor PushNotifications) via /api/device/<id>/fcm/. Used to push
    # a 'refresh' data message when this device's content changes.
    fcm_token = models.CharField(max_length=255, blank=True, default='')
    last_seen = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self) -> str:
        return f"{self.device_id} - {self.name or 'Unnamed'} ({self.device_type})"


class Mosque(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, default='')
    latitude = models.DecimalField(max_digits=16, decimal_places=12, blank=True, null=True)
    longitude = models.DecimalField(max_digits=16, decimal_places=12, blank=True, null=True)
    website_url = models.URLField(blank=True, default='')
    sync_enabled = models.BooleanField(
        default=False,
        help_text='When on, prayer times come from the website PDF; when off, manual entries are used.',
    )
    timezone = models.CharField(max_length=64, blank=True, default='')
    prayer_synced_at = models.DateTimeField(blank=True, null=True)
    jummah_section = models.CharField(
        max_length=100, blank=True,
        help_text="Keyword locating this mosque's Jumu'ah section on a shared "
                  "multi-location website (e.g. 'North' or '21 St'); blank = first Jumu'ah section",
    )
    sync_error = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Last website-sync failure message; empty when the last sync succeeded.',
    )
    sync_failures = models.PositiveSmallIntegerField(
        default=0,
        help_text='Consecutive sync failures since the last success; hourly '
                  'retries stop after 3 until the next daily sync window.',
    )
    sync_failing_since = models.DateTimeField(
        blank=True, null=True,
        help_text='When the current run of consecutive sync failures began; '
                  'null when the last sync succeeded.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def sync_failing_days(self):
        """Whole days the current failure streak has lasted (0 = not failing)."""
        if not self.sync_failing_since:
            return 0
        from django.utils import timezone
        return (timezone.now() - self.sync_failing_since).days

    def __str__(self):
        return self.name


class PrayerTime(models.Model):
    mosque = models.ForeignKey(Mosque, on_delete=models.CASCADE, related_name='prayer_times')
    date = models.DateField()
    fajr = models.TimeField()
    dhuhr = models.TimeField()
    asr = models.TimeField()
    maghrib = models.TimeField()
    isha = models.TimeField()
    sunset = models.TimeField(blank=True, null=True)
    jummah = models.TimeField(blank=True, null=True)
    jummah2 = models.TimeField(blank=True, null=True)
    jummah3 = models.TimeField(blank=True, null=True)
    maghrib_after_sunset = models.BooleanField(default=False)
    maghrib_sunset_minutes = models.PositiveSmallIntegerField(
        default=1,
        help_text='Minutes after sunset to set Maghrib (1-60) when '
                  'maghrib_after_sunset is on.',
    )
    source = models.CharField(
        max_length=10,
        default='default',
        help_text='default | pdf | manual — sync never overwrites manual rows',
    )

    class Meta:
        unique_together = ['mosque', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.mosque.name} - {self.date}"


class PrayerTimeOverride(models.Model):
    """User-owned manual overrides layered over synced PrayerTime rows.

    PrayerTime rows are system-owned (sync may rewrite any non-manual row).
    Override fields left NULL inherit the synced value; a non-NULL field
    wins for that prayer. Deleting a row fully reverts to website times.
    """
    mosque = models.ForeignKey(Mosque, on_delete=models.CASCADE, related_name='overrides')
    date = models.DateField()
    fajr = models.TimeField(blank=True, null=True)
    dhuhr = models.TimeField(blank=True, null=True)
    asr = models.TimeField(blank=True, null=True)
    maghrib = models.TimeField(blank=True, null=True)
    isha = models.TimeField(blank=True, null=True)
    sunset = models.TimeField(blank=True, null=True)
    jummah = models.TimeField(blank=True, null=True)
    jummah2 = models.TimeField(blank=True, null=True)
    jummah3 = models.TimeField(blank=True, null=True)
    maghrib_after_sunset = models.BooleanField(
        blank=True, null=True,
        help_text='NULL = inherit from synced row; set = override.',
    )
    maghrib_sunset_minutes = models.PositiveSmallIntegerField(
        blank=True, null=True,
        help_text='NULL = inherit from synced row; set = override.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['mosque', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.mosque.name} - {self.date} (override)"


class MosqueSlide(models.Model):
    mosque = models.ForeignKey(Mosque, on_delete=models.CASCADE, related_name='slides')
    title = models.CharField(max_length=255)
    file = models.FileField(
        upload_to='mosque_slides/',
        validators=[
            FileExtensionValidator(
                allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mov', 'avi']
            )
        ],
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title


@receiver(post_delete, sender=MediaFile)
def delete_media_file(sender, instance, **kwargs):
    """Delete the stored file when a MediaFile is deleted"""
    if instance.file:
        instance.file.delete(save=False)


@receiver(post_delete, sender=MosqueSlide)
def delete_mosque_slide_file(sender, instance, **kwargs):
    """Delete the stored mosque slide file when a MosqueSlide is deleted"""
    if instance.file:
        instance.file.delete(save=False)


# --- FCM push triggers ---------------------------------------------------
# Model signals cover every write path at once (dashboard views, admin,
# sync jobs) so a missed view can never leave a device stale. Sends run
# after commit, off the request thread — FCM latency never blocks a save.

def _fcm_push_for_devices(device_qs):
    """Fire-and-forget 'refresh' data push to every registered device in qs."""
    tokens = list(device_qs.exclude(fcm_token='').values_list('fcm_token', flat=True))
    if not tokens:
        return

    def _send():
        from .fcm import send_refresh
        dead = send_refresh(tokens)
        if dead:
            # Token died on Firebase's side — drop it so we stop retrying.
            Device.objects.filter(fcm_token__in=dead).update(fcm_token='')

    threading.Thread(target=_send, daemon=True).start()


@receiver(post_save, sender=MediaFile)
@receiver(post_delete, sender=MediaFile)
def media_changed_push(sender, instance, **kwargs):
    """A slide was uploaded/edited/reordered/deleted → ping that user's devices."""
    if not instance.user_id:
        return
    transaction.on_commit(lambda: _fcm_push_for_devices(
        Device.objects.filter(user=instance.user, screen=instance.screen)))


@receiver(post_save, sender=PrayerTime)
@receiver(post_delete, sender=PrayerTime)
@receiver(post_save, sender=PrayerTimeOverride)
@receiver(post_delete, sender=PrayerTimeOverride)
def prayer_changed_push(sender, instance, **kwargs):
    """Prayer timings changed → ping the mosque's TV devices."""
    mosque = getattr(instance, 'mosque', None)
    if mosque:
        transaction.on_commit(lambda: _fcm_push_for_devices(mosque.devices.all()))


@receiver(post_save, sender=MosqueSlide)
@receiver(post_delete, sender=MosqueSlide)
def mosque_slide_changed_push(sender, instance, **kwargs):
    """A mosque slide changed → ping the mosque's TV devices."""
    mosque = getattr(instance, 'mosque', None)
    if mosque:
        transaction.on_commit(lambda: _fcm_push_for_devices(mosque.devices.all()))
