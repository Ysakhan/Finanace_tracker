"""
Middleware for FinRoll:
1. Anti-cache headers to prevent back-button viewing of protected pages after logout.
"""
from django.utils.cache import add_never_cache_headers


class NoCacheAfterLogoutMiddleware:
    """Adds HTTP headers to force browsers to revalidate protected pages on back button."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated or request.path.startswith('/logout/'):
            add_never_cache_headers(response)
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response


class UserFriendlyExceptionMiddleware:
    """Catches unhandled exceptions and presents human-readable error pages with solutions instead of raw code tracebacks."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        from django.shortcuts import render
        return render(request, '500.html', {
            'error_title': 'An Unexpected Error Occurred',
            'error_message': 'The system encountered an issue while processing your request. No technical code traceback will be shown.',
            'error_detail': str(exception),
            'status_code': 500,
        }, status=500)

