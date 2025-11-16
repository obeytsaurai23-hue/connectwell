import os
from django.conf import settings
from django.urls import path, include, re_path
from django.views.static import serve
from .views import healthz
from .metrics import metrics_view

urlpatterns = [
    path('api/v1/', include('accounts.urls')),
    path('api/v1/', include('payments.urls')),
    path('api/v1/', include('chat.urls')),
    path('healthz', healthz),
    path('metrics', metrics_view),
]

# DEV: serve the frontend static pages under /demo/ for local testing (only when DEBUG=True)
if settings.DEBUG:
    # BASE_DIR points at backend/, so frontend is one level up: ../frontend
    FRONTEND_ROOT = os.path.abspath(os.path.join(settings.BASE_DIR, '..', 'frontend'))
    urlpatterns += [
        # e.g. /demo/chat_demo.html -> serves backend/../frontend/chat_demo.html
        # serve /demo/ -> frontend/index.html
        re_path(r'^demo/?$', serve, {'path': 'index.html', 'document_root': FRONTEND_ROOT}),
        re_path(r'^demo/(?P<path>.*)$', serve, {'document_root': FRONTEND_ROOT, 'show_indexes': True}),
    ]
