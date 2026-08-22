from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.django_login, name='django_login'),
    path('signup/', views.signup, name='signup'),
    path('forget-password/', views.forget_password, name='forget-password'),
    path('forget-password/verify/', views.forget_password_verify, name='forget-password-verify'),
    path('subscription-plans/', views.subscription_plans, name='subscription-plans'),
    path('create-checkout-session/', views.create_checkout_session, name='create-checkout-session'),
    path('billing-portal/', views.billing_portal, name='billing-portal'),
    path('stripe-webhook/', views.stripe_webhook, name='stripe-webhook'),
    path('user-management/', views.user_management, name='user-management'),
    path('delete-user/<int:user_id>/', views.delete_user, name='delete-user'),
    path('admin-reset-password/<int:user_id>/', views.admin_reset_password, name='admin-reset-password'),
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
