from django.db import models
from django.core.validators import FileExtensionValidator
from django.conf import settings

class MediaFile(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]

    title = models.CharField(max_length=255)
    content_type = models.CharField(max_length=10, choices=CONTENT_TYPE_CHOICES)
    
    # Use S3 storage if configured, otherwise use local filesystem
    storage_backend = settings.DEFAULT_FILE_STORAGE if hasattr(settings, 'DEFAULT_FILE_STORAGE') else None
    file = models.FileField(
        upload_to='uploads/',
        storage=storage_backend,
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
