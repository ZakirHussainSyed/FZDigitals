from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import logging

from .models import MediaFile

logger = logging.getLogger(__name__)


def index(request):
    return render(request, 'slideshow/index.html')


def tablet(request):
    return render(request, 'slideshow/tablet.html')


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
        files = MediaFile.objects.all()
        return JsonResponse(
            {
                'success': True,
                'files': [
                    {
                        'id': f.id,
                        'title': f.title,
                        'type': f.content_type,
                        'url': request.build_absolute_uri(f.file.url),
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
        logger.info(f"Received {len(uploaded)} files for upload")
        logger.info(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")
        logger.info(f"MEDIA_ROOT exists: {os.path.exists(settings.MEDIA_ROOT)}")
        
        created = []
        for uf in uploaded:
            if uf.content_type.startswith('image/'):
                ct = 'image'
            elif uf.content_type.startswith('video/'):
                ct = 'video'
            else:
                logger.warning(f"Skipping file with unsupported content type: {uf.content_type}")
                continue

            m = MediaFile.objects.create(
                title=uf.name,
                content_type=ct,
                file=uf,
            )
            logger.info(f"Created MediaFile: id={m.id}, title={m.title}, file={m.file.name}")
            logger.info(f"File path: {m.file.path}")
            logger.info(f"File exists: {os.path.exists(m.file.path)}")
            
            created.append(
                {
                    'id': m.id,
                    'title': m.title,
                    'type': m.content_type,
                    'url': request.build_absolute_uri(m.file.url),
                }
            )

        return JsonResponse({'success': True, 'files': created})
    except Exception as e:
        logger.error(f"Error in api_upload: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_delete(request, pk: int):
    try:
        obj = get_object_or_404(MediaFile, pk=pk)
        if obj.file:
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
        logger.info(f"Serving media: path={path}, MEDIA_ROOT={settings.MEDIA_ROOT}, full_path={full_path}")
        logger.info(f"File exists: {os.path.exists(full_path)}")
        
        # List files in media directory for debugging
        if os.path.exists(settings.MEDIA_ROOT):
            files = os.listdir(settings.MEDIA_ROOT)
            logger.info(f"Files in MEDIA_ROOT: {files}")
            if os.path.exists(os.path.join(settings.MEDIA_ROOT, 'uploads')):
                upload_files = os.listdir(os.path.join(settings.MEDIA_ROOT, 'uploads'))
                logger.info(f"Files in uploads: {upload_files}")
        
        if os.path.exists(full_path):
            return FileResponse(open(full_path, 'rb'))
        return HttpResponse('File not found', status=404)
    except Exception as e:
        logger.error(f"Error serving media: {str(e)}", exc_info=True)
        return HttpResponse('Error serving file', status=500)
