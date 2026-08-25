from django.shortcuts import redirect
from django.conf import settings
from django.contrib import messages
from .models import Subscription


class SubscriptionMiddleware:
    """Middleware to check subscription status"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Allow unauthenticated users and specific paths
        exempt_paths = [
            '/',
            '/login/',
            '/signup/',
            '/forget-password/',
            '/forget-password/verify/',
            '/subscription-plans/',
            '/api/pairing/',
            '/api/pairing/',
            '/tablet/',
            '/accounts/',
            '/user-management/',
            '/delete-user/',
            '/admin-reset-password/',
        ]
        
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Check if path is exempt
        if any(request.path.startswith(path) for path in exempt_paths):
            return self.get_response(request)
        
        # Check subscription status
        try:
            subscription = Subscription.objects.get(user=request.user)
            
            # Check if trial has expired
            if subscription.is_trial() and subscription.days_remaining() <= 0:
                subscription.status = 'cancelled'
                subscription.save()
                messages.warning(request, 'Your trial has expired. Please subscribe to continue using the service.')
                return redirect('/subscription-plans/')
            
            # Check if payment has failed
            if subscription.status == 'past_due':
                messages.error(request, 'Payment failed. Please update your payment method to continue using the service.')
                return redirect('/subscription-plans/')
            
            # Check if subscription is cancelled
            if subscription.status == 'cancelled':
                messages.warning(request, 'Your subscription has been cancelled. Please subscribe to continue using the service.')
                return redirect('/subscription-plans/')
            
            # Allow access if subscription is active or in trial
            if subscription.is_active():
                # Check if trial is ending soon (3 days or less)
                if subscription.is_trial() and subscription.days_remaining() <= 3:
                    messages.info(request, f'Your trial ends in {subscription.days_remaining()} day(s). Subscribe now to avoid interruption.')
                return self.get_response(request)
            
            # Redirect to subscription plans if not active
            if request.path != '/subscription-plans/':
                return redirect('/subscription-plans/')
        
        except Subscription.DoesNotExist:
            # Create trial subscription if doesn't exist
            Subscription.objects.create(user=request.user, status='trial')
            return self.get_response(request)
        
        return self.get_response(request)
