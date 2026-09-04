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
import logging

from .models import MediaFile, DevicePairing, UserProfile, Device

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
        
        try:
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                return redirect(f'/{user.id}/')
            else:
                return render(request, 'slideshow/login.html', {
                    'form': AuthenticationForm(),
                    'error': 'Invalid username or password'
                })
        except Exception as e:
            logger.error(f"Login error: {str(e)}", exc_info=True)
            return render(request, 'slideshow/login.html', {
                'form': AuthenticationForm(),
                'error': f'Login error: {str(e)}'
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
    
    return render(request, 'slideshow/index.html', {'user': request.user})


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


@login_required
@require_http_methods(["GET"])
def api_users_list(request):
    """Get list of all users for admin dashboard"""
    try:
        if not request.user.is_superuser:
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
        users = User.objects.all()
        return JsonResponse({
            'success': True,
            'users': [
                {
                    'id': u.id,
                    'email': u.email,
                    'username': u.username,
                    'is_active': u.is_active,
                    'date_joined': u.date_joined.isoformat() if u.date_joined else None,
                }
                for u in users
            ]
        })
    except Exception as e:
        logger.error(f"Error in api_users_list: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def device_management(request):
    """Device management page - only for superusers"""
    if not request.user.is_superuser:
        return redirect(f'/{request.user.id}/')
    return render(request, 'slideshow/device_management.html')


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
    """Lookup user by pairing ID for tablet connection and auto-create/link device"""
    try:
        pairing = get_object_or_404(DevicePairing, pairing_id=pairing_id.upper())
        
        # Auto-create or update device entry when pairing code is used
        # Use pairing_id as device_id for consistency
        device, created = Device.objects.get_or_create(
            device_id=pairing_id.upper(),
            defaults={
                'name': f'Paired Device ({pairing_id.upper()})',
                'device_type': 'browser',
                'user': pairing.user,
                'screen': pairing.screen,
                'is_active': True
            }
        )
        
        # If device already exists, update its assignment
        if not created:
            device.user = pairing.user
            device.screen = pairing.screen
            device.is_active = True
            device.save()
        
        return JsonResponse({
            'success': True,
            'user_email': pairing.user.email,
            'user_id': pairing.user.id,
            'screen': pairing.screen,
            'device_id': device.device_id,
            'device_linked': True
        })
    except Exception as e:
        logger.error(f"Error in api_pairing_lookup: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Invalid pairing ID'}, status=404)


@csrf_exempt
@require_http_methods(["POST"])
def api_device_register(request):
    """Register a device (browser or USB) for auto-assignment"""
    try:
        import json
        data = json.loads(request.body)
        device_id = data.get('device_id')
        device_type = data.get('device_type', 'browser')
        device_name = data.get('name', '')
        
        if not device_id:
            return JsonResponse({'success': False, 'error': 'device_id is required'}, status=400)
        
        device, created = Device.objects.get_or_create(
            device_id=device_id,
            defaults={
                'name': device_name,
                'device_type': device_type,
            }
        )
        
        # Update last_seen and name if changed
        device.last_seen = device.last_seen  # This will auto-update due to auto_now=True
        if device_name and device.name != device_name:
            device.name = device_name
            device.save()
        
        return JsonResponse({
            'success': True,
            'device_id': device.device_id,
            'name': device.name,
            'device_type': device.device_type,
            'assigned_user': device.user_id,
            'assigned_screen': device.screen if device.user else None,
            'created': created
        })
    except Exception as e:
        logger.error(f"Error in api_device_register: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def api_device_slideshow(request, device_id):
    """Get slideshow for a specific device"""
    try:
        device = get_object_or_404(Device, device_id=device_id)
        
        if not device.user:
            return JsonResponse({
                'success': False,
                'error': 'Device not assigned to any user',
                'device_id': device.device_id,
                'device_name': device.name
            }, status=404)
        
        files = MediaFile.objects.filter(user=device.user, screen=device.screen)
        return JsonResponse({
            'success': True,
            'device_id': device.device_id,
            'user_id': device.user.id,
            'screen': device.screen,
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
        })
    except Exception as e:
        logger.error(f"Error in api_device_slideshow: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_user_devices(request):
    """Get devices for the current user, optionally filtered by screen"""
    try:
        screen = request.GET.get('screen')
        devices = Device.objects.filter(user=request.user)
        
        if screen:
            try:
                screen = int(screen)
                if 1 <= screen <= 5:
                    devices = devices.filter(screen=screen)
            except ValueError:
                pass
        
        return JsonResponse({
            'success': True,
            'devices': [
                {
                    'id': d.id,
                    'device_id': d.device_id,
                    'name': d.name,
                    'device_type': d.device_type,
                    'screen': d.screen,
                    'last_seen': d.last_seen.isoformat() if d.last_seen else None,
                    'is_active': d.is_active,
                    'created_at': d.created_at.isoformat() if d.created_at else None,
                }
                for d in devices
            ]
        })
    except Exception as e:
        logger.error(f"Error in api_user_devices: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_devices_list(request):
    """Get list of all devices for admin dashboard"""
    try:
        if not request.user.is_superuser:
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
        devices = Device.objects.all()
        return JsonResponse({
            'success': True,
            'devices': [
                {
                    'id': d.id,
                    'device_id': d.device_id,
                    'name': d.name,
                    'device_type': d.device_type,
                    'user_id': d.user_id,
                    'user_email': d.user.email if d.user else None,
                    'user_name': d.user.username if d.user else None,
                    'screen': d.screen,
                    'last_seen': d.last_seen.isoformat() if d.last_seen else None,
                    'is_active': d.is_active,
                    'created_at': d.created_at.isoformat() if d.created_at else None,
                }
                for d in devices
            ]
        })
    except Exception as e:
        logger.error(f"Error in api_devices_list: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def api_device_assign(request, device_id):
    """Assign a device to a user and screen"""
    try:
        import json
        data = json.loads(request.body)
        user_id = data.get('user_id')
        screen = data.get('screen', 1)
        
        # Allow superusers to assign any device to any user
        # Allow regular users to assign devices only to themselves
        if not request.user.is_superuser and user_id != request.user.id:
            return JsonResponse({'success': False, 'error': 'Unauthorized - can only assign devices to yourself'}, status=403)
        
        try:
            screen = int(screen)
            if screen < 1 or screen > 5:
                screen = 1
        except ValueError:
            screen = 1
        
        device = get_object_or_404(Device, device_id=device_id)
        
        if user_id:
            user = get_object_or_404(User, id=user_id)
            device.user = user
            device.screen = screen
            device.save()
        else:
            device.user = None
            device.save()
        
        return JsonResponse({
            'success': True,
            'device_id': device.device_id,
            'user_id': device.user_id,
            'screen': device.screen
        })
    except Exception as e:
        logger.error(f"Error in api_device_assign: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["DELETE"])
def api_device_delete(request, device_id):
    """Delete a device (superuser only)"""
    try:
        if not request.user.is_superuser:
            return JsonResponse({'success': False, 'error': 'Unauthorized - superuser only'}, status=403)
        
        device = get_object_or_404(Device, device_id=device_id)
        device_id_str = device.device_id
        device.delete()
        
        return JsonResponse({
            'success': True,
            'device_id': device_id_str
        })
    except Exception as e:
        logger.error(f"Error in api_device_delete: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
