from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.db.models import Sum
import logging
import secrets

import requests
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from suntime import Sun

from .models import MediaFile, DevicePairing, UserProfile, Device, Mosque, PrayerTime, MosqueSlide

logger = logging.getLogger(__name__)


def purge_cloudflare_cache(url):
    zone_id = getattr(settings, 'CLOUDFLARE_ZONE_ID', '')
    token = getattr(settings, 'CLOUDFLARE_API_TOKEN', '')
    if not zone_id or not token:
        return
    try:
        response = requests.post(
            f'https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
            json={'files': [url]},
            timeout=10,
        )
        if not response.ok:
            logger.warning(f'Cloudflare purge failed for {url}: {response.status_code} {response.text}')
    except Exception as e:
        logger.warning(f'Cloudflare purge error for {url}: {e}')


def browser_label(user_agent):
    """Short human readable name for a browser, e.g. 'Chrome on macOS'"""
    ua = user_agent or ''
    browser = 'Browser'
    for name, token in (
        ('Edge', 'Edg/'),
        ('Opera', 'OPR/'),
        ('Samsung Internet', 'SamsungBrowser'),
        ('Firefox', 'Firefox/'),
        ('Chrome', 'Chrome/'),
        ('Safari', 'Safari/'),
    ):
        if token in ua:
            browser = name
            break

    platform = 'Unknown OS'
    for name, token in (
        ('Android', 'Android'),
        ('iOS', 'iPhone'),
        ('iPadOS', 'iPad'),
        ('Windows', 'Windows'),
        ('macOS', 'Mac OS X'),
        ('Linux', 'Linux'),
    ):
        if token in ua:
            platform = name
            break

    return f'{browser} on {platform}'


def index(request):
    """Root URL - shows landing page or redirects to user dashboard"""
    if request.user.is_authenticated:
        return redirect(f'/{request.user.id}/')
    return render(request, 'slideshow/home.html')


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
                try:
                    profile = user.userprofile
                    if profile.vertical == 'mosque':
                        return redirect('prayer-times')
                except UserProfile.DoesNotExist:
                    pass
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
                'security_questions': UserProfile.SECURITY_QUESTIONS,
            })

        if User.objects.filter(username=username).exists():
            return render(request, 'slideshow/signup.html', {
                'error': 'Username already exists',
                'security_questions': UserProfile.SECURITY_QUESTIONS,
            })

        if User.objects.filter(email=email).exists():
            return render(request, 'slideshow/signup.html', {
                'error': 'Email already exists',
                'security_questions': UserProfile.SECURITY_QUESTIONS,
            })

        user = User.objects.create_user(username=username, email=email, password=password)
        UserProfile.objects.create(
            user=user,
            security_question=security_question,
            security_answer=security_answer.lower(),
        )

        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect(f'/{user.id}/')

    return render(request, 'slideshow/signup.html', {
        'security_questions': UserProfile.SECURITY_QUESTIONS,
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

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        vertical = request.POST.get('vertical', 'bank')
        mosque_name = request.POST.get('mosque_name', '').strip()
        mosque_address = request.POST.get('mosque_address', '').strip()
        mosque_latitude = request.POST.get('mosque_latitude', '').strip()
        mosque_longitude = request.POST.get('mosque_longitude', '').strip()

        context = {
            'users': User.objects.all().order_by('-id'),
            'verticals': UserProfile.VERTICAL_CHOICES,
        }

        if not username or not email or not password:
            context['error'] = 'Username, email, and password are required.'
            return render(request, 'slideshow/user_management.html', context)

        if password != confirm_password:
            context['error'] = 'Passwords do not match.'
            return render(request, 'slideshow/user_management.html', context)

        if User.objects.filter(username=username).exists():
            context['error'] = 'Username already exists.'
            return render(request, 'slideshow/user_management.html', context)

        if User.objects.filter(email=email).exists():
            context['error'] = 'Email already exists.'
            return render(request, 'slideshow/user_management.html', context)

        user = User.objects.create_user(username=username, email=email, password=password)
        UserProfile.objects.create(
            user=user,
            vertical=vertical
        )

        if vertical == 'mosque':
            try:
                Mosque.objects.create(
                    user=user,
                    name=mosque_name or username,
                    address=mosque_address,
                    latitude=Decimal(mosque_latitude) if mosque_latitude else None,
                    longitude=Decimal(mosque_longitude) if mosque_longitude else None,
                )
            except Exception as e:
                logger.error(f"Mosque creation error: {str(e)}", exc_info=True)

        context['success'] = f'User {username} created successfully.'
        context['users'] = User.objects.all().order_by('-id')
        return render(request, 'slideshow/user_management.html', context)

    users = User.objects.all().order_by('-id')
    return render(request, 'slideshow/user_management.html', {
        'users': users,
        'verticals': UserProfile.VERTICAL_CHOICES,
    })


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
    
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    max_slideshows = profile.max_slideshows
    return render(request, 'slideshow/index.html', {
        'user': request.user,
        'max_slideshows': max_slideshows,
        'screens': range(1, max_slideshows + 1),
        'max_upload_size_mb': settings.MAX_UPLOAD_SIZE_MB,
    })


def tablet(request):
    """Tablet pairing page"""
    response = render(request, 'slideshow/tablet.html')
    response['Cache-Control'] = 'no-store, must-revalidate'
    return response


def tablet_slideshow(request, pairing_id):
    """Tablet slideshow after pairing"""
    response = render(request, 'slideshow/tablet.html', {'pairing_id': pairing_id})
    response['Cache-Control'] = 'no-store, must-revalidate'
    return response


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
    media_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', '')
    js = """const CACHE_NAME = 'fz-media-v1';
const MEDIA_DOMAIN = '%(media_domain)s';

function isMediaUrl(url) {
    try {
        return new URL(url).hostname === MEDIA_DOMAIN;
    } catch (e) {
        return false;
    }
}

function isSlideshowApi(url) {
    return url.includes('/api/device/') && url.includes('/slideshow/');
}

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'CACHE_MEDIA') {
        event.waitUntil(cacheMedia(event.data.urls));
    }
});

async function cacheMedia(urls) {
    const cache = await caches.open(CACHE_NAME);
    await Promise.all(urls.map(async (url) => {
        try {
            const req = new Request(url, {mode: 'no-cors'});
            const res = await fetch(req);
            if (res) {
                await cache.put(req, res);
            }
        } catch (err) {
            console.error('Cache media failed:', url, err);
        }
    }));
}

self.addEventListener('fetch', (event) => {
    const {request} = event;
    const url = request.url;

    if (request.method !== 'GET') {
        return;
    }

    if (isMediaUrl(url)) {
        event.respondWith(
            caches.match(request).then((cached) => {
                if (cached) return cached;
                return fetch(request).then((response) => {
                    const resClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(request, resClone).catch(() => {});
                    }).catch(() => {});
                    return response;
                });
            })
        );
    } else if (isSlideshowApi(url)) {
        event.respondWith(
            fetch(request).then((response) => {
                const resClone = response.clone();
                caches.open(CACHE_NAME).then((cache) => {
                    cache.put(request, resClone).catch(() => {});
                }).catch(() => {});
                return response;
            }).catch(() => {
                return caches.match(request);
            })
        );
    }
});
""" % {'media_domain': media_domain}
    return HttpResponse(js, content_type='application/javascript')


@login_required
@require_http_methods(["GET"])
def api_media_list(request):
    try:
        screen = request.GET.get('screen', 1)
        
        try:
            screen = int(screen)
            if screen < 1:
                screen = 1
        except ValueError:
            screen = 1
        
        # Respect the user's screen limit; superusers are unrestricted
        if not request.user.is_superuser:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            if screen > profile.max_slideshows:
                return JsonResponse({
                    'success': False,
                    'error': f'Screen number must be between 1 and {profile.max_slideshows}',
                }, status=400)
        
        files = MediaFile.objects.filter(user=request.user, screen=screen)
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


@login_required
@require_http_methods(["POST"])
def api_upload(request):
    try:
        uploaded = request.FILES.getlist('files')
        screen = request.POST.get('screen', 1)
        
        try:
            screen = int(screen)
        except ValueError:
            screen = 1
        
        is_super = request.user.is_superuser
        if not is_super:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            if screen < 1 or screen > profile.max_slideshows:
                return JsonResponse({
                    'success': False,
                    'error': f'Screen number must be between 1 and {profile.max_slideshows}',
                }, status=400)
        
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        
        if not is_super:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            used = MediaFile.objects.filter(user=request.user).aggregate(total=Sum('file_size'))['total'] or 0
            quota_bytes = profile.storage_quota_mb * 1024 * 1024
        else:
            used = 0
            quota_bytes = 0
        
        created = []
        for uf in uploaded:
            if uf.content_type.startswith('image/'):
                ct = 'image'
            elif uf.content_type.startswith('video/'):
                ct = 'video'
            else:
                return JsonResponse({
                    'success': False,
                    'error': f'{uf.name}: only Picture, GIF and Video formats are allowed',
                }, status=400)

            if not is_super and uf.size > max_bytes:
                return JsonResponse({
                    'success': False,
                    'error': f'{uf.name} is larger than {settings.MAX_UPLOAD_SIZE_MB} MB',
                }, status=400)
            
            if not is_super and used + uf.size > quota_bytes:
                return JsonResponse({
                    'success': False,
                    'error': f'Uploading {uf.name} would exceed your {profile.storage_quota_mb} MB storage quota',
                }, status=400)

            m = MediaFile.objects.create(
                user=request.user,
                screen=screen,
                title=uf.name,
                content_type=ct,
                file=uf,
                file_size=uf.size,
            )
            used += uf.size
            
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


@login_required
@require_http_methods(["POST"])
def api_delete(request, pk: int):
    obj = MediaFile.objects.filter(pk=pk, user=request.user).first()
    if obj is None:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    try:
        file_url = obj.file.url if obj.file and hasattr(obj.file, 'url') else ''
        obj.delete()
        if file_url:
            purge_cloudflare_cache(file_url)
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
        result = []
        for u in users:
            try:
                profile = u.userprofile
                vertical = profile.vertical
            except UserProfile.DoesNotExist:
                vertical = 'bank'
            result.append({
                'id': u.id,
                'email': u.email,
                'username': u.username,
                'is_active': u.is_active,
                'vertical': vertical,
                'date_joined': u.date_joined.isoformat() if u.date_joined else None,
            })
        return JsonResponse({'success': True, 'users': result})
    except Exception as e:
        logger.error(f"Error in api_users_list: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_user_profile(request):
    """Return the current user's profile including customer vertical"""
    try:
        profile, _ = UserProfile.objects.get_or_create(
            user=request.user,
            defaults={'vertical': 'bank'}
        )
        return JsonResponse({
            'success': True,
            'id': request.user.id,
            'email': request.user.email,
            'username': request.user.username,
            'vertical': profile.vertical,
            'number_of_screens': profile.number_of_screens,
            'max_slideshows': profile.max_slideshows,
            'storage_quota_mb': profile.storage_quota_mb,
        })
    except Exception as e:
        logger.error(f"Error in api_user_profile: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_mosques(request):
    """Return active mosques for the current user with today's prayer times"""
    try:
        mosques = Mosque.objects.filter(user=request.user, is_active=True)
        today = timezone.now().date()
        data = []
        for m in mosques:
            try:
                pt = m.prayer_times.get(date=today)
                prayer_times = {
                    'fajr': pt.fajr.strftime('%H:%M') if pt.fajr else None,
                    'dhuhr': pt.dhuhr.strftime('%H:%M') if pt.dhuhr else None,
                    'asr': pt.asr.strftime('%H:%M') if pt.asr else None,
                    'maghrib': pt.maghrib.strftime('%H:%M') if pt.maghrib else None,
                    'isha': pt.isha.strftime('%H:%M') if pt.isha else None,
                    'jummah': pt.jummah.strftime('%H:%M') if pt.jummah else None,
                }
            except PrayerTime.DoesNotExist:
                prayer_times = {}
            data.append({
                'id': m.id,
                'name': m.name,
                'address': m.address,
                'latitude': str(m.latitude) if m.latitude else None,
                'longitude': str(m.longitude) if m.longitude else None,
                'prayer_times': prayer_times,
            })
        return JsonResponse({'success': True, 'mosques': data})
    except Exception as e:
        logger.error(f"Error in api_mosques: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_mosque_slides(request, mosque_id):
    """Return active slides for a mosque"""
    try:
        mosque = get_object_or_404(Mosque, id=mosque_id, user=request.user)
        slides = mosque.slides.filter(is_active=True)
        return JsonResponse({
            'success': True,
            'mosque_id': mosque.id,
            'mosque_name': mosque.name,
            'files': [
                {
                    'id': s.id,
                    'title': s.title,
                    'url': s.file.url,
                    'order': s.order,
                }
                for s in slides
            ]
        })
    except Exception as e:
        logger.error(f"Error in api_mosque_slides: {str(e)}", exc_info=True)
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
        except ValueError:
            screen = 1
        
        if not request.user.is_superuser:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            if screen < 1 or screen > profile.max_slideshows:
                return JsonResponse({
                    'success': False,
                    'error': f'Screen number must be between 1 and {profile.max_slideshows}',
                }, status=400)
        
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
        pairing_id = pairing_id.upper()
        pairing = DevicePairing.objects.filter(pairing_id=pairing_id).first()

        if not pairing:
            # Pairing code no longer exists. If a linked Device still exists with no
            # assigned user, the user that owned the pairing was likely deleted.
            if Device.objects.filter(device_id=pairing_id, user__isnull=True).exists():
                return JsonResponse({
                    'success': False,
                    'user_deleted': True,
                    'contact_email': 'growwithfzdigitals@gmail.com',
                    'error': 'This pairing code is no longer active. Please contact growwithfzdigitals@gmail.com for service and a new pairing code.'
                }, status=404)
            raise Http404("Invalid pairing ID")

        # Identify each (pairing code, browser) pair as a distinct device.
        # This prevents the same browser opening two different pairing codes
        # from overwriting the same Device row.
        browser_id = (request.GET.get('browser_id') or '').strip().upper()[:100]
        device_key = f"{pairing_id.upper()}-{browser_id}" if browser_id else pairing_id.upper()
        device_name = browser_label(request.META.get('HTTP_USER_AGENT')) if browser_id else f'Paired Device ({device_key})'

        # Enforce plan limits (non-super users only)
        if not pairing.user.is_superuser:
            profile, _ = UserProfile.objects.get_or_create(user=pairing.user)

            # The pairing's screen must be within the allowed number of screens
            if pairing.screen > profile.max_slideshows:
                return JsonResponse({
                    'success': False,
                    'error': f'Pairing code is outside the allowed number of screens ({profile.max_slideshows})',
                }, status=403)

            # Global total active screens limit
            if profile.max_active_screens > 0:
                active_total = Device.objects.filter(user=pairing.user, is_active=True).count()
                if not Device.objects.filter(device_id=device_key).exists() and active_total >= profile.max_active_screens:
                    return JsonResponse({
                        'success': False,
                        'error': f'Active screen limit reached ({profile.max_active_screens})',
                    }, status=403)

            # Per-screen (per-slideshow) device limit
            if profile.max_screens_per_slideshow > 0:
                existing = Device.objects.filter(user=pairing.user, screen=pairing.screen).count()
                if not Device.objects.filter(device_id=device_key).exists() and existing >= profile.max_screens_per_slideshow:
                    return JsonResponse({
                        'success': False,
                        'error': f'Slideshow {pairing.screen} is limited to {profile.max_screens_per_slideshow} screens',
                    }, status=403)

        device, created = Device.objects.get_or_create(
            device_id=device_key,
            defaults={
                'name': device_name,
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
            if browser_id:
                device.name = device_name
            device.save()
        
        return JsonResponse({
            'success': True,
            'user_email': pairing.user.email,
            'screen': pairing.screen,
            'device_id': device.device_id,
            'device_token': device.token,
            'device_linked': True
        })
    except Exception as e:
        logger.error(f"Error in api_pairing_lookup: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Invalid pairing ID'}, status=404)


@login_required
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
    """Get slideshow for a specific device, authenticated by its pairing token"""
    try:
        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Device not found'}, status=404)

        token = request.GET.get('token') or request.headers.get('X-Device-Token', '')
        if not constant_time_compare(token, device.token):
            return JsonResponse({'success': False, 'error': 'Invalid device token'}, status=403)
        
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
                    'user_label': (d.user.email or d.user.username) if d.user else None,
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


@require_http_methods(["GET"])
def api_pairing_new(request):
    """Create an unclaimed browser device and return its QR-pairing info."""
    try:
        browser_id = (request.GET.get('browser_id') or '').strip().upper()[:100]
        if not browser_id or not browser_id.startswith('BR-') or len(browser_id) < 6:
            browser_id = 'BR-' + secrets.token_hex(4).upper()

        device_id = f'QR-{browser_id}'
        device, created = Device.objects.get_or_create(
            device_id=device_id,
            defaults={
                'name': 'Unclaimed display',
                'device_type': 'browser',
                'user': None,
                'screen': 1,
                'is_active': True,
            }
        )

        if not device.token:
            device.token = generate_device_token()
            device.save()

        response = JsonResponse({
            'success': True,
            'device_id': device.device_id,
            'token': device.token,
            'setup_url': request.build_absolute_uri(f'/setup/?device_id={device_id}&token={device.token}'),
        })
        response['Cache-Control'] = 'no-store, must-revalidate'
        return response
    except Exception as e:
        logger.error(f"Error in api_pairing_new: {str(e)}", exc_info=True)
        response = JsonResponse({'success': False, 'error': str(e)}, status=500)
        response['Cache-Control'] = 'no-store, must-revalidate'
        return response


@login_required
def setup_pairing(request):
    """Web page scanned from the QR code to assign an unclaimed device to a user."""
    device_id = (request.GET.get('device_id') or '').strip()
    token = (request.GET.get('token') or '').strip()

    if not device_id or not token:
        return render(request, 'slideshow/setup.html', {
            'error': 'Invalid setup link. Please scan the QR code again.'
        })

    device = Device.objects.filter(device_id=device_id, token=token).first()
    if not device:
        return render(request, 'slideshow/setup.html', {
            'error': 'Display not found or link expired.'
        })

    if device.user and device.user != request.user and not request.user.is_superuser:
        return render(request, 'slideshow/setup.html', {
            'error': 'This display is already linked to another account.'
        })

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    max_screens = profile.max_slideshows

    if request.method == 'POST':
        try:
            screen = int(request.POST.get('screen', 1))
            if screen < 1 or screen > max_screens:
                return render(request, 'slideshow/setup.html', {
                    'device_id': device_id,
                    'token': token,
                    'screens': range(1, max_screens + 1),
                    'error': f'Screen must be between 1 and {max_screens}',
                })

            name = request.POST.get('name', '').strip() or f'Display {screen}'

            device.user = request.user
            device.screen = screen
            device.name = name
            device.is_active = True
            device.save()

            return render(request, 'slideshow/setup.html', {
                'success': True,
                'name': name,
                'screen': screen,
            })
        except Exception as e:
            logger.error(f"Error in setup_pairing: {str(e)}", exc_info=True)
            return render(request, 'slideshow/setup.html', {
                'device_id': device_id,
                'token': token,
                'screens': range(1, max_screens + 1),
                'error': f'Something went wrong: {str(e)}',
            })

    return render(request, 'slideshow/setup.html', {
        'device_id': device_id,
        'token': token,
        'screens': range(1, max_screens + 1),
        'default_name': f'Display {device.screen}',
    })


@login_required
def my_screens(request):
    """List and manage the current user's screens/displays."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    max_screens = profile.max_slideshows
    error = None
    message = None

    if request.method == 'POST':
        action = request.POST.get('action')
        device_id = request.POST.get('device_id', '').strip()
        device = Device.objects.filter(device_id=device_id).first()

        if not device or (device.user != request.user and not request.user.is_superuser):
            error = 'Display not found.'
        elif action == 'update':
            try:
                screen = int(request.POST.get('screen', 1))
                if 1 <= screen <= max_screens:
                    device.screen = screen
                device.name = request.POST.get('name', '').strip() or device.name
                device.save()
                message = 'Display updated.'
            except ValueError:
                error = 'Invalid screen.'
        elif action == 'delete':
            device_id_str = device.device_id
            device.delete()
            message = f'Display {device_id_str} removed.'

    devices = Device.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'slideshow/screens.html', {
        'devices': devices,
        'screens': range(1, max_screens + 1),
        'max_screens': max_screens,
        'error': error,
        'message': message,
    })


@require_http_methods(["GET"])
def api_qr_svg(request):
    """Proxy a QR image for the tablet so the browser/TV never calls an external image host."""
    data = request.GET.get('data', '')
    if not data:
        return HttpResponse('', status=400)
    try:
        import requests
        providers = [
            f'https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={requests.utils.quote(data, safe="")}',
            f'https://chart.googleapis.com/chart?cht=qr&chs=300x300&chld=M|0&chl={requests.utils.quote(data, safe="")}',
        ]
        for url in providers:
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    content_type = r.headers.get('Content-Type', 'image/png')
                    if 'png' not in content_type.lower() and 'svg' not in content_type.lower():
                        content_type = 'image/png'
                    return HttpResponse(
                        r.content,
                        content_type=content_type,
                        headers={'Cache-Control': 'no-store'}
                    )
            except Exception as provider_err:
                logger.warning(f"QR provider failed {url}: {provider_err}")
                continue
        return JsonResponse({'success': False, 'error': 'QR generation unavailable'}, status=503)
    except Exception as e:
        logger.error(f"Error in api_qr_svg: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _format_prayer_time(t):
    if not t:
        return ''
    s = t.strftime('%I:%M %p')
    s = s.lstrip('0')
    return s.replace(' AM', 'am').replace(' PM', 'pm').replace('am', 'am').replace('pm', 'pm')


def _next_salah(prayer_time, now, tz):
    if not prayer_time:
        return {'name': None, 'time': ''}
    today_prayers = [
        ('Fajr', prayer_time.fajr),
        ('Dhuhr', prayer_time.dhuhr),
        ('Asr', prayer_time.asr),
        ('Maghrib', prayer_time.maghrib),
        ('Isha', prayer_time.isha),
    ]
    for name, t in today_prayers:
        if not t:
            continue
        dt = datetime.combine(prayer_time.date, t).replace(tzinfo=tz)
        if dt > now:
            return {'name': name, 'time': _format_prayer_time(t)}
    if prayer_time.fajr:
        return {'name': 'Fajr', 'time': _format_prayer_time(prayer_time.fajr)}
    return {'name': None, 'time': ''}


def _sunrise_time(latitude, longitude, d, tz):
    if latitude is None or longitude is None:
        return None
    try:
        sun = Sun(float(latitude), float(longitude))
        sr = sun.get_sunrise_time(d)
        if not sr.tzinfo:
            sr = sr.replace(tzinfo=ZoneInfo('UTC'))
        sr = sr.astimezone(tz)
        return sr.time()
    except Exception as e:
        logger.warning(f"Sunrise calc failed for {latitude},{longitude}: {e}")
        return None


def _sunset_time(latitude, longitude, d, tz):
    if latitude is None or longitude is None:
        return None
    try:
        sun = Sun(float(latitude), float(longitude))
        ss = sun.get_sunset_time(d)
        if not ss.tzinfo:
            ss = ss.replace(tzinfo=ZoneInfo('UTC'))
        ss = ss.astimezone(tz)
        return ss.time()
    except Exception as e:
        logger.warning(f"Sunset calc failed for {latitude},{longitude}: {e}")
        return None


@require_http_methods(["GET"])
def api_public_mosques(request):
    """Public list of mosques with today's prayer times, sunrise, and next salah."""
    try:
        today = timezone.now().date()
        tz = ZoneInfo(getattr(settings, 'MOSQUE_TIMEZONE', 'Asia/Kolkata'))
        now = datetime.now(tz)
        mosques = Mosque.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False)
        data = []
        for m in mosques:
            prayer_time = m.prayer_times.filter(date=today).first()
            timings = {}
            if prayer_time:
                timings = {
                    'fajr': _format_prayer_time(prayer_time.fajr),
                    'dhuhr': _format_prayer_time(prayer_time.dhuhr),
                    'asr': _format_prayer_time(prayer_time.asr),
                    'maghrib': _format_prayer_time(prayer_time.maghrib),
                    'isha': _format_prayer_time(prayer_time.isha),
                    'sunset': _format_prayer_time(prayer_time.sunset),
                    'jummah': _format_prayer_time(prayer_time.jummah),
                }
            timings['sunrise'] = _format_prayer_time(_sunrise_time(m.latitude, m.longitude, today, tz))
            next_salah = _next_salah(prayer_time, now, tz)
            data.append({
                'id': m.id,
                'name': m.name,
                'address': m.address,
                'latitude': float(m.latitude),
                'longitude': float(m.longitude),
                'next_salah': next_salah,
                'timings': timings,
            })
        return JsonResponse({'success': True, 'mosques': data})
    except Exception as e:
        logger.error(f"Error in api_public_mosques: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def mosque_map(request):
    """Public map page showing mosques with prayer times."""
    return render(request, 'slideshow/mosque_map.html', {
        'tile_url': getattr(settings, 'MAP_TILE_URL', 'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png'),
        'attribution': getattr(settings, 'MAP_ATTRIBUTION', '&copy; OpenStreetMap contributors'),
    })


@login_required
def prayer_times(request):
    """Mosque users can add or update today's prayer times."""
    if request.method == 'GET':
        try:
            profile = request.user.userprofile
            if profile.vertical != 'mosque':
                return redirect(f'/{request.user.id}/')
        except UserProfile.DoesNotExist:
            return redirect(f'/{request.user.id}/')

    mosque = Mosque.objects.filter(user=request.user).first()
    if not mosque:
        messages.error(request, 'No mosque is associated with your account.')
        return redirect(f'/{request.user.id}/')

    today = timezone.now().date()
    tz = ZoneInfo(getattr(settings, 'MOSQUE_TIMEZONE', 'Asia/Kolkata'))
    prayer_time, _ = PrayerTime.objects.get_or_create(
        mosque=mosque,
        date=today,
        defaults={
            'fajr': datetime.strptime('05:00', '%H:%M').time(),
            'dhuhr': datetime.strptime('13:00', '%H:%M').time(),
            'asr': datetime.strptime('16:00', '%H:%M').time(),
            'maghrib': datetime.strptime('18:30', '%H:%M').time(),
            'isha': datetime.strptime('20:00', '%H:%M').time(),
        }
    )

    # Default sunset based on the mosque's location.
    if prayer_time.sunset is None and mosque.latitude is not None and mosque.longitude is not None:
        try:
            computed_sunset = _sunset_time(mosque.latitude, mosque.longitude, today, tz)
            if computed_sunset:
                prayer_time.sunset = computed_sunset
                prayer_time.save(update_fields=['sunset'])
        except Exception as e:
            logger.warning(f"Sunset default failed: {e}")

    if request.method == 'POST':
        def _parse(field, optional=False):
            hour = request.POST.get(f'{field}_hour', '').strip()
            minute = request.POST.get(f'{field}_minute', '').strip()
            ampm = request.POST.get(f'{field}_ampm', '').strip()
            if not hour or not minute:
                if optional:
                    return None
                raise ValueError(f'{field.capitalize()} time is required')
            h = int(hour)
            m = int(minute)
            if ampm.upper() == 'PM' and h != 12:
                h += 12
            elif ampm.upper() == 'AM' and h == 12:
                h = 0
            return datetime.strptime(f'{h:02d}:{m:02d}', '%H:%M').time()

        try:
            for field in ['fajr', 'dhuhr', 'asr', 'maghrib', 'isha', 'sunset', 'jummah']:
                setattr(prayer_time, field, _parse(field))
            prayer_time.save()
            messages.success(request, 'Prayer times updated.')
            return redirect('prayer-times')
        except Exception as e:
            messages.error(request, f'Invalid prayer time: {e}')
            return redirect('prayer-times')

    prayer_fields = []
    for field, label in [
        ('fajr', 'Fajr'),
        ('dhuhr', 'Dhuhr'),
        ('asr', 'Asr'),
        ('sunset', 'Sunset'),
        ('maghrib', 'Maghrib'),
        ('isha', 'Isha'),
        ('jummah', 'Jummah'),
    ]:
        t = getattr(prayer_time, field)
        if t:
            hour = t.strftime('%I').lstrip('0')
            minute = t.strftime('%M')
            ampm = t.strftime('%p')
        else:
            hour = ''
            minute = ''
            ampm = 'AM'
        prayer_fields.append({'name': field, 'label': label, 'hour': hour, 'minute': minute, 'ampm': ampm})

    return render(request, 'slideshow/prayer_times.html', {
        'mosque': mosque,
        'prayer_time': prayer_time,
        'prayer_fields': prayer_fields,
        'today': today,
    })


@login_required
def mosque_tv(request):
    """Mosque TV view showing prayer times and the user's slideshow."""
    try:
        profile = request.user.userprofile
        if profile.vertical != 'mosque':
            return redirect(f'/{request.user.id}/')
    except UserProfile.DoesNotExist:
        return redirect(f'/{request.user.id}/')

    mosque = Mosque.objects.filter(user=request.user, is_active=True).first()
    if not mosque:
        messages.error(request, 'No mosque is associated with your account.')
        return redirect('prayer-times')

    today = timezone.now().date()
    tz = ZoneInfo(mosque.timezone or 'UTC')
    prayer_time, _ = PrayerTime.objects.get_or_create(
        mosque=mosque,
        date=today,
        defaults={
            'fajr': datetime.strptime('05:00', '%H:%M').time(),
            'dhuhr': datetime.strptime('13:00', '%H:%M').time(),
            'asr': datetime.strptime('16:00', '%H:%M').time(),
            'maghrib': datetime.strptime('18:30', '%H:%M').time(),
            'isha': datetime.strptime('20:00', '%H:%M').time(),
            'jummah': datetime.strptime('13:30', '%H:%M').time(),
            'sunset': _sunset_time(mosque.latitude, mosque.longitude, today, tz),
        }
    )

    timings = {
        'fajr': _format_prayer_time(prayer_time.fajr),
        'sunrise': _format_prayer_time(_sunrise_time(mosque.latitude, mosque.longitude, today, tz)),
        'dhuhr': _format_prayer_time(prayer_time.dhuhr),
        'asr': _format_prayer_time(prayer_time.asr),
        'sunset': _format_prayer_time(prayer_time.sunset),
        'maghrib': _format_prayer_time(prayer_time.maghrib),
        'isha': _format_prayer_time(prayer_time.isha),
        'jummah': _format_prayer_time(prayer_time.jummah),
    }
    now = timezone.now().astimezone(tz)
    next_salah = _next_salah(prayer_time, now, tz)

    media = MediaFile.objects.filter(user=request.user, screen=1).order_by('created_at')
    media_files = [
        {'id': m.id, 'url': m.file.url, 'type': m.content_type, 'title': m.title}
        for m in media
    ]

    return render(request, 'slideshow/mosque_tv.html', {
        'mosque': mosque,
        'timings': timings,
        'next_salah': next_salah,
        'media_files': media_files,
        'today': today,
    })
