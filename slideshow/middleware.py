from django.shortcuts import redirect
from django.conf import settings
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
        ]
        
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Check if path is exempt
        if any(request.path.startswith(path) for path in exempt_paths):
            return self.get_response(request)
        
        # Check subscription status
        try:
            subscription = Subscription.objects.get(user=request.user)
            
            # Allow access if subscription is active or in trial
            if subscription.is_active():
                return self.get_response(request)
            
            # Redirect to subscription plans if not active
            if request.path != '/subscription-plans/':
                return redirect('/subscription-plans/')
        
        except Subscription.DoesNotExist:
            # Create trial subscription if doesn't exist
            Subscription.objects.create(user=request.user, status='trial')
            return self.get_response(request)
        
        return self.get_response(request)
