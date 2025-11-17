from django.http import JsonResponse


def healthz(request):
    """Simple health endpoint used by load balancers and process supervisors.

    Returns 200 when Django is up. Keep this extremely small and dependency-free.
    """
    return JsonResponse({'ok': True})
