from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('tablet/', views.tablet, name='tablet'),
    path('manifest.webmanifest', views.manifest, name='manifest'),
    path('service-worker.js', views.service_worker, name='service-worker'),
    path('api/media/', views.api_media_list, name='api-media-list'),
    path('api/upload/', views.api_upload, name='api-upload'),
    path('api/media/<int:pk>/delete/', views.api_delete, name='api-delete'),
    path('media/uploads/<path:path>', views.serve_media, name='serve-media'),
]
