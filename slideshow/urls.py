from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.django_login, name='django_login'),
    path('signup/', views.signup, name='signup'),
    path('forget-password/', views.forget_password, name='forget-password'),
    path('forget-password/verify/', views.forget_password_verify, name='forget-password-verify'),
    path('<int:user_id>/', views.user_dashboard, name='user-dashboard'),
    path('tablet/', views.tablet, name='tablet'),
    path('tablet/<str:pairing_id>/', views.tablet_slideshow, name='tablet-slideshow'),
    path('manifest.webmanifest', views.manifest, name='manifest'),
    path('service-worker.js', views.service_worker, name='service-worker'),
    path('api/media/', views.api_media_list, name='api-media-list'),
    path('api/upload/', views.api_upload, name='api-upload'),
    path('api/media/<int:pk>/delete/', views.api_delete, name='api-delete'),
    path('api/pairing/', views.api_pairing_info, name='api-pairing-info'),
    path('api/pairing/<str:pairing_id>/', views.api_pairing_lookup, name='api-pairing-lookup'),
]
