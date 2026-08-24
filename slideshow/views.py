from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
import stripe
import logging

from .models import MediaFile, DevicePairing, UserProfile, Subscription

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


def google_login_direct(request):
    """Direct Google login - redirects to Google OAuth URL without intermediate page"""
    from allauth.socialaccount.models import SocialApp
    from allauth.socialaccount.providers.google.provider import GoogleProvider
    import urllib.parse
    
    # Get the Google SocialApp
    try:
        app = SocialApp.objects.get(provider='google')
    except SocialApp.DoesNotExist:
        return redirect('/accounts/google/login/')
    
    # Get the provider
    provider = GoogleProvider(request)
    
    # Build the OAuth2 authorization URL manually
    callback_url = request.build_absolute_uri('/accounts/google/login/callback/')
    
    params = {
        'client_id': app.client_id,
        'redirect_uri': callback_url,
        'scope': 'profile email',
        'response_type': 'code',
        'access_type': 'offline',
    }
    
    auth_url = f'https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}'
    return redirect(auth_url)


def index(request):
    """Root URL - shows login page or redirects to user dashboard"""
    if request.user.is_authenticated:
        return redirect(f'/{request.user.id}/')
    return render(request, 'slideshow/login.html')


def django_login(request):
    """Django traditional login"""
    if request.user.is_authenticated:
        return redirect(f'/{request.user.id}/')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect(f'/{user.id}/')
        else:
            return render(request, 'slideshow/login.html', {
                'form': AuthenticationForm(),
                'error': 'Invalid username or password'
            })
    
    return render(request, 'slideshow/login.html', {'form': AuthenticationForm()})


def signup(request):
    """User registration with security question"""
    if request.user.is_authenticated:
        return redirect(f'/{request.user.id}/')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        security_question = request.POST.get('security_question')
        security_answer = request.POST.get('security_answer')
        
        if password != confirm_password:
            return render(request, 'slideshow/signup.html', {
                'error': 'Passwords do not match',
                'security_questions': UserProfile.SECURITY_QUESTIONS
            })
        
        if User.objects.filter(username=username).exists():
            return render(request, 'slideshow/signup.html', {
                'error': 'Username already exists',
                'security_questions': UserProfile.SECURITY_QUESTIONS
            })
        
        if User.objects.filter(email=email).exists():
            return render(request, 'slideshow/signup.html', {
                'error': 'Email already exists',
                'security_questions': UserProfile.SECURITY_QUESTIONS
            })
        
        user = User.objects.create_user(username=username, email=email, password=password)
        UserProfile.objects.create(
            user=user,
            security_question=security_question,
            security_answer=security_answer.lower()
        )
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect(f'/{user.id}/')
    
    return render(request, 'slideshow/signup.html', {
        'security_questions': UserProfile.SECURITY_QUESTIONS
    })


def forget_password(request):
    """Step 1: Enter username to reset password"""
    if request.user.is_authenticated:
        return redirect(f'/{request.user.id}/')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        try:
            user = User.objects.get(username=username)
            profile = UserProfile.objects.get(user=user)
            return render(request, 'slideshow/forget_password_verify.html', {
                'username': username,
                'security_question': profile.security_question,
                'security_question_text': dict(UserProfile.SECURITY_QUESTIONS).get(profile.security_question)
            })
        except User.DoesNotExist:
            return render(request, 'slideshow/forget_password.html', {
                'error': 'Username not found'
            })
        except UserProfile.DoesNotExist:
            return render(request, 'slideshow/forget_password.html', {
                'error': 'User profile not found. Please contact support.'
            })
    
    return render(request, 'slideshow/forget_password.html')


def forget_password_verify(request):
    """Step 2: Verify security answer and reset password"""
    if request.user.is_authenticated:
        return redirect(f'/{request.user.id}/')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        security_answer = request.POST.get('security_answer').lower()
        new_password = request.POST.get('new_password')
        
        try:
            user = User.objects.get(username=username)
            profile = UserProfile.objects.get(user=user)
            
            if profile.security_answer == security_answer:
                user.set_password(new_password)
                user.save()
                return render(request, 'slideshow/login.html', {
                    'success': 'Password reset successfully. Please login with your new password.'
                })
            else:
                return render(request, 'slideshow/forget_password_verify.html', {
                    'username': username,
                    'security_question': profile.security_question,
                    'security_question_text': dict(UserProfile.SECURITY_QUESTIONS).get(profile.security_question),
                    'error': 'Incorrect security answer'
                })
        except User.DoesNotExist:
            return render(request, 'slideshow/forget_password.html', {
                'error': 'Username not found'
            })
    
    return redirect('/forget-password/')


@login_required
def subscription_plans(request):
    """Show subscription plans page"""
    subscription, created = Subscription.objects.get_or_create(
        user=request.user,
        defaults={'status': 'trial'}
    )
    
    plans = settings.SUBSCRIPTION_PLANS
    return render(request, 'slideshow/subscription_plans.html', {
        'plans': plans,
        'subscription': subscription,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY
    })


@login_required
def create_checkout_session(request):
    """Create Stripe checkout session"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    
    plan = request.POST.get('plan')
    if plan not in settings.SUBSCRIPTION_PLANS:
        return JsonResponse({'error': 'Invalid plan'}, status=400)
    
    try:
        subscription, created = Subscription.objects.get_or_create(
            user=request.user,
            defaults={'status': 'trial'}
        )
        
        # Get or create Stripe customer
        if not subscription.stripe_customer_id:
            customer = stripe.Customer.create(
                email=request.user.email,
                name=request.user.username,
            )
            subscription.stripe_customer_id = customer.id
            subscription.save()
        
        # Get price ID based on plan
        price_id_map = {
            'basic': settings.STRIPE_PRICE_ID_BASIC,
            'pro': settings.STRIPE_PRICE_ID_PRO,
            'enterprise': settings.STRIPE_PRICE_ID_ENTERPRISE
        }
        price_id = price_id_map.get(plan)
        
        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=subscription.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.build_absolute_uri(f'/{request.user.id}/?subscription=success'),
            cancel_url=request.build_absolute_uri('/subscription-plans/?subscription=cancelled'),
            subscription_data={
                'trial_period_days': settings.TRIAL_PERIOD_DAYS,
                'metadata': {
                    'user_id': request.user.id,
                    'plan': plan
                }
            }
        )
        
        return JsonResponse({'sessionId': checkout_session.id})
    
    except Exception as e:
        logger.error(f"Stripe checkout error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def billing_portal(request):
    """Redirect to Stripe customer portal"""
    try:
        subscription = Subscription.objects.get(user=request.user)
        
        if not subscription.stripe_customer_id:
            return redirect('/subscription-plans/')
        
        portal_session = stripe.billing_portal.Session.create(
            customer=subscription.stripe_customer_id,
            return_url=request.build_absolute_uri(f'/{request.user.id}/'),
        )
        
        return redirect(portal_session.url)
    
    except Exception as e:
        logger.error(f"Billing portal error: {str(e)}")
        return redirect('/subscription-plans/')


@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    """Handle Stripe webhooks"""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Webhook error: Invalid payload - {str(e)}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Webhook error: Invalid signature - {str(e)}")
        return HttpResponse(status=400)
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_completed(session)
    elif event['type'] == 'customer.subscription.created':
        subscription = event['data']['object']
        handle_subscription_created(subscription)
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        handle_subscription_updated(subscription)
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        handle_subscription_deleted(subscription)
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        handle_payment_succeeded(invoice)
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        handle_payment_failed(invoice)
    
    return HttpResponse(status=200)


def handle_checkout_completed(session):
    """Handle successful checkout"""
    try:
        user_id = session.get('metadata', {}).get('user_id')
        plan = session.get('metadata', {}).get('plan')
        
        if user_id:
            user = User.objects.get(id=user_id)
            subscription = Subscription.objects.get(user=user)
            subscription.stripe_customer_id = session.get('customer')
            subscription.save()
    except Exception as e:
        logger.error(f"Checkout completion error: {str(e)}")


def handle_subscription_created(stripe_subscription):
    """Handle subscription creation"""
    try:
        customer_id = stripe_subscription.get('customer')
        subscription = Subscription.objects.get(stripe_customer_id=customer_id)
        
        subscription.stripe_subscription_id = stripe_subscription.get('id')
        subscription.stripe_price_id = stripe_subscription.get('items', {}).get('data', [{}])[0].get('price', {}).get('id')
        subscription.status = 'trial' if stripe_subscription.get('trial_end') else 'active'
        subscription.current_period_start = stripe_subscription.get('current_period_start')
        subscription.current_period_end = stripe_subscription.get('current_period_end')
        
        if stripe_subscription.get('trial_end'):
            from django.utils import timezone
            subscription.trial_start = timezone.now()
            subscription.trial_end = stripe_subscription.get('trial_end')
        
        subscription.save()
    except Exception as e:
        logger.error(f"Subscription creation error: {str(e)}")


def handle_subscription_updated(stripe_subscription):
    """Handle subscription updates"""
    try:
        customer_id = stripe_subscription.get('customer')
        subscription = Subscription.objects.get(stripe_customer_id=customer_id)
        
        subscription.status = stripe_subscription.get('status')
        subscription.current_period_start = stripe_subscription.get('current_period_start')
        subscription.current_period_end = stripe_subscription.get('current_period_end')
        subscription.cancel_at_period_end = stripe_subscription.get('cancel_at_period_end', False)
        subscription.save()
    except Exception as e:
        logger.error(f"Subscription update error: {str(e)}")


def handle_subscription_deleted(stripe_subscription):
    """Handle subscription cancellation"""
    try:
        customer_id = stripe_subscription.get('customer')
        subscription = Subscription.objects.get(stripe_customer_id=customer_id)
        subscription.status = 'cancelled'
        subscription.save()
    except Exception as e:
        logger.error(f"Subscription deletion error: {str(e)}")


def handle_payment_succeeded(invoice):
    """Handle successful payment"""
    try:
        customer_id = invoice.get('customer')
        subscription = Subscription.objects.get(stripe_customer_id=customer_id)
        subscription.status = 'active'
        subscription.save()
    except Exception as e:
        logger.error(f"Payment success error: {str(e)}")


def handle_payment_failed(invoice):
    """Handle failed payment"""
    try:
        customer_id = invoice.get('customer')
        subscription = Subscription.objects.get(stripe_customer_id=customer_id)
        subscription.status = 'past_due'
        subscription.save()
    except Exception as e:
        logger.error(f"Payment failure error: {str(e)}")


@login_required
def user_management(request):
    """User management page - only for superusers"""
    if not request.user.is_superuser:
        return redirect(f'/{request.user.id}/')
    
    users = User.objects.all().order_by('-id')
    return render(request, 'slideshow/user_management.html', {'users': users})


@login_required
def delete_user(request, user_id):
    """Delete a user - only for superusers"""
    if not request.user.is_superuser:
        return redirect(f'/{request.user.id}/')
    
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            if user == request.user:
                return render(request, 'slideshow/user_management.html', {
                    'users': User.objects.all().order_by('-id'),
                    'error': 'Cannot delete your own account'
                })
            user.delete()
            return render(request, 'slideshow/user_management.html', {
                'users': User.objects.all().order_by('-id'),
                'success': f'User {user.username} deleted successfully'
            })
        except User.DoesNotExist:
            return render(request, 'slideshow/user_management.html', {
                'users': User.objects.all().order_by('-id'),
                'error': 'User not found'
            })
    
    return redirect('/user-management/')


@login_required
def admin_reset_password(request, user_id):
    """Admin password reset - only for superusers"""
    if not request.user.is_superuser:
        return redirect(f'/{request.user.id}/')
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        try:
            user = User.objects.get(id=user_id)
            user.set_password(new_password)
            user.save()
            return render(request, 'slideshow/user_management.html', {
                'users': User.objects.all().order_by('-id'),
                'success': f'Password reset successfully for {user.username}'
            })
        except User.DoesNotExist:
            return render(request, 'slideshow/user_management.html', {
                'users': User.objects.all().order_by('-id'),
                'error': 'User not found'
            })
    
    return redirect('/user-management/')


@login_required
def user_dashboard(request, user_id):
    """User-specific upload page with device pairing"""
    if request.user.id != user_id:
        return redirect(f'/{request.user.id}/')
    
    subscription, created = Subscription.objects.get_or_create(
        user=request.user,
        defaults={'status': 'trial'}
    )
    
    return render(request, 'slideshow/index.html', {'subscription': subscription})


def tablet(request):
    """Tablet pairing page"""
    return render(request, 'slideshow/tablet.html')


def tablet_slideshow(request, pairing_id):
    """Tablet slideshow after pairing"""
    return render(request, 'slideshow/tablet.html', {'pairing_id': pairing_id})


def manifest(request):
    content = {
        'name': 'Slideshow',
        'short_name': 'Slideshow',
        'start_url': '/tablet/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#000000',
        'theme_color': '#000000',
        'icons': [
            {
                'src': '/static/slideshow/icon.svg',
                'sizes': 'any',
                'type': 'image/svg+xml',
                'purpose': 'any maskable',
            }
        ],
    }
    return JsonResponse(content)


def service_worker(request):
    js = """self.addEventListener('install', (event) => {\n  self.skipWaiting();\n});\n\nself.addEventListener('activate', (event) => {\n  event.waitUntil(self.clients.claim());\n});\n"""
    return HttpResponse(js, content_type='application/javascript')


@require_http_methods(["GET"])
def api_media_list(request):
    try:
        user_id = request.GET.get('user_id')
        screen = request.GET.get('screen', 1)
        
        try:
            screen = int(screen)
            if screen < 1 or screen > 5:
                screen = 1
        except ValueError:
            screen = 1
        
        if user_id:
            # For tablet pairing - allow filtering by user_id and screen
            files = MediaFile.objects.filter(user_id=user_id, screen=screen)
        elif request.user.is_authenticated:
            # For dashboard - use authenticated user and screen
            files = MediaFile.objects.filter(user=request.user, screen=screen)
        else:
            # No user specified and not authenticated
            files = MediaFile.objects.none()
        return JsonResponse(
            {
                'success': True,
                'files': [
                    {
                        'id': f.id,
                        'title': f.title,
                        'type': f.content_type,
                        'screen': f.screen,
                        'url': request.build_absolute_uri(f.file.url) if hasattr(f.file, 'url') else request.build_absolute_uri(f'/media/{f.file}'),
                    }
                    for f in files
                ],
            }
        )
    except Exception as e:
        logger.error(f"Error in api_media_list: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_upload(request):
    try:
        from django.conf import settings
        import os
        
        uploaded = request.FILES.getlist('files')
        screen = request.POST.get('screen', 1)
        
        try:
            screen = int(screen)
            if screen < 1 or screen > 5:
                screen = 1
        except ValueError:
            screen = 1
        
        print(f"=== UPLOAD DEBUG ===")
        print(f"Received {len(uploaded)} files for upload to screen {screen}")
        print(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")
        print(f"MEDIA_ROOT exists: {os.path.exists(settings.MEDIA_ROOT)}")
        
        created = []
        for uf in uploaded:
            if uf.content_type.startswith('image/'):
                ct = 'image'
            elif uf.content_type.startswith('video/'):
                ct = 'video'
            else:
                print(f"Skipping file with unsupported content type: {uf.content_type}")
                continue

            m = MediaFile.objects.create(
                user=request.user if request.user.is_authenticated else None,
                screen=screen,
                title=uf.name,
                content_type=ct,
                file=uf,
            )
            print(f"Created MediaFile: id={m.id}, title={m.title}, file={m.file.name}, user={m.user}, screen={m.screen}")
            print(f"File URL: {m.file.url}")
            
            created.append(
                {
                    'id': m.id,
                    'title': m.title,
                    'type': m.content_type,
                    'url': request.build_absolute_uri(m.file.url),
                }
            )

        print(f"=== UPLOAD COMPLETE ===")
        return JsonResponse({'success': True, 'files': created})
    except Exception as e:
        print(f"=== UPLOAD ERROR ===")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_delete(request, pk: int):
    try:
        obj = get_object_or_404(MediaFile, pk=pk)
        if obj.file and hasattr(obj.file, 'delete'):
            obj.file.delete(save=False)
        obj.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error in api_delete: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def serve_media(request, path):
    """Serve media files directly - needed for Render deployment"""
    try:
        from django.conf import settings
        import os
        full_path = os.path.join(settings.MEDIA_ROOT, path)
        print(f"=== MEDIA SERVE DEBUG ===")
        print(f"Serving media: path={path}, MEDIA_ROOT={settings.MEDIA_ROOT}, full_path={full_path}")
        print(f"File exists: {os.path.exists(full_path)}")
        
        # List files in media directory for debugging
        if os.path.exists(settings.MEDIA_ROOT):
            files = os.listdir(settings.MEDIA_ROOT)
            print(f"Files in MEDIA_ROOT: {files}")
            if os.path.exists(os.path.join(settings.MEDIA_ROOT, 'uploads')):
                upload_files = os.listdir(os.path.join(settings.MEDIA_ROOT, 'uploads'))
                print(f"Files in uploads: {upload_files}")
        
        if os.path.exists(full_path):
            return FileResponse(open(full_path, 'rb'))
        return HttpResponse('File not found', status=404)
    except Exception as e:
        print(f"=== MEDIA SERVE ERROR ===")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return HttpResponse('Error serving file', status=500)


@login_required
@require_http_methods(["GET"])
def api_pairing_info(request):
    """Get or create device pairing info for current user and specific screen"""
    try:
        screen = request.GET.get('screen', 1)
        try:
            screen = int(screen)
            if screen < 1 or screen > 5:
                screen = 1
        except ValueError:
            screen = 1
        
        pairing, created = DevicePairing.objects.get_or_create(
            user=request.user,
            screen=screen
        )
        return JsonResponse({
            'success': True,
            'pairing_id': pairing.pairing_id,
            'screen': pairing.screen,
            'created': created
        })
    except Exception as e:
        logger.error(f"Error in api_pairing_info: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_pairing_lookup(request, pairing_id):
    """Lookup user by pairing ID for tablet connection"""
    try:
        pairing = get_object_or_404(DevicePairing, pairing_id=pairing_id.upper())
        return JsonResponse({
            'success': True,
            'user_email': pairing.user.email,
            'user_id': pairing.user.id,
            'screen': pairing.screen
        })
    except Exception as e:
        logger.error(f"Error in api_pairing_lookup: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Invalid pairing ID'}, status=404)
