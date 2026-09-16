from django.db import models
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.contrib.auth.models import User
from django.db.models.signals import post_delete
from django.dispatch import receiver
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
    max_slideshows = models.PositiveIntegerField(
        default=5,
        verbose_name='Number of slideshows',
        help_text='Number of slideshows this user is allowed.',
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
        # A single "Number of screens" input drives all screen limits
        # and pre-creates the pairing codes for screens 1..n.
        if self.max_slideshows is not None and self.max_slideshows > 0:
            self.max_screens_per_slideshow = self.max_slideshows
            self.max_active_screens = self.max_slideshows
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
    latitude = models.DecimalField(max_digits=12, decimal_places=8, blank=True, null=True)
    longitude = models.DecimalField(max_digits=12, decimal_places=8, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

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
    jummah = models.TimeField(blank=True, null=True)

    class Meta:
        unique_together = ['mosque', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.mosque.name} - {self.date}"


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
