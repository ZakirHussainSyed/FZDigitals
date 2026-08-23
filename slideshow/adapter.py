from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_email, user_field
from allauth.utils import import_callable
from django.conf import settings


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_auto_signup_allowed(self, request, sociallogin):
        return True
    
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        
        # Generate username from email if not set
        if not user.username:
            email = user_email(user)
            if email:
                username = email.split('@')[0]
                # Make username unique
                base_username = username
                counter = 1
                while user.__class__.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                user.username = username
                user.save()
        
        return user
    
    def pre_social_login(self, request, sociallogin):
        # If a user already exists with the same email, link the social account
        from allauth.socialaccount.models import SocialAccount
        from django.contrib.auth.models import User
        
        email = sociallogin.account.extra_data.get('email')
        if email:
            try:
                user = User.objects.get(email=email)
                sociallogin.user = user
                # Link the social account to the existing user
                sociallogin.account.user = user
                sociallogin.account.save()
            except User.DoesNotExist:
                pass
