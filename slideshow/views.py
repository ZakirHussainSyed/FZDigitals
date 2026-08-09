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
        result_files = []
        for f in files:
            # Handle both string (old data) and File object (new S3 data)
            if isinstance(f.file, str):
                # Old data - file is a string path
                url = f.file
            else:
                # New data - file is a File object
                url = f.file.url
            result_files.append({
                'id': f.id,
                'title': f.title,
                'type': f.content_type,
                'url': request.build_absolute_uri(url),
            })
        
        return JsonResponse(
            {
                'success': True,
                'files': result_files,
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
        print(f"DEFAULT_FILE_STORAGE: {settings.DEFAULT_FILE_STORAGE}")
        print(f"MEDIA_URL: {settings.MEDIA_URL}")
        print(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")
        
        created = []
        for uf in uploaded:
            if uf.content_type.startswith('image/'):
                ct = 'image'
            elif uf.content_type.startswith('video/'):
                ct = 'video'
            else:
                print(f"Skipping file with unsupported content type: {uf.content_type}")
                continue

            print(f"Creating MediaFile for: {uf.name}")
            m = MediaFile.objects.create(
                title=uf.name,
                content_type=ct,
                file=uf,
            )
            print(f"Created MediaFile: id={m.id}, title={m.title}, file={m.file.name}")
            print(f"File URL: {m.file.url}")
            print(f"File storage backend: {m.file.storage.__class__.__name__}")
            
            # Try to verify the file exists in storage
            try:
                exists = m.file.storage.exists(m.file.name)
                print(f"File exists in storage: {exists}")
            except Exception as e:
                print(f"Error checking file existence: {e}")
            
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
