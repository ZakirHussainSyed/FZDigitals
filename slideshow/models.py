from django.db import models
from django.core.validators import FileExtensionValidator
from django.contrib.auth.models import User
import uuid

class MediaFile(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title

    class Meta:
        ordering = ['-created_at']


class DevicePairing(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    pairing_id = models.CharField(max_length=12, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.pairing_id:
            self.pairing_id = self.generate_pairing_id()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_pairing_id():
        return str(uuid.uuid4().hex[:8]).upper()

    def __str__(self) -> str:
        return f"{self.user.email} - {self.pairing_id}"
