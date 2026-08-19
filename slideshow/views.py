from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib import messages
import logging

from .models import MediaFile, DevicePairing, UserProfile

logger = logging.getLogger(__name__)


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
            login(request, user)
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
        login(request, user)
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
def user_dashboard(request, user_id):
    """User-specific upload page with device pairing"""
    if request.user.id != user_id:
        return redirect(f'/{request.user.id}/')
    return render(request, 'slideshow/index.html')


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
        if user_id:
            files = MediaFile.objects.filter(user_id=user_id)
        else:
            files = MediaFile.objects.all()
        return JsonResponse(
            {
                'success': True,
                'files': [
                    {
                        'id': f.id,
                        'title': f.title,
                        'type': f.content_type,
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
        print(f"=== UPLOAD DEBUG ===")
        print(f"Received {len(uploaded)} files for upload")
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
                title=uf.name,
                content_type=ct,
                file=uf,
            )
            print(f"Created MediaFile: id={m.id}, title={m.title}, file={m.file.name}, user={m.user}")
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
    """Get or create device pairing info for current user"""
    try:
        pairing, created = DevicePairing.objects.get_or_create(user=request.user)
        return JsonResponse({
            'success': True,
            'pairing_id': pairing.pairing_id,
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
            'user_id': pairing.user.id
        })
    except Exception as e:
        logger.error(f"Error in api_pairing_lookup: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Invalid pairing ID'}, status=404)
