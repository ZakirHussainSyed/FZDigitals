class RenewRememberedSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.session.get('keep_signed_in'):
            request.session.modified = True
        return self.get_response(request)
