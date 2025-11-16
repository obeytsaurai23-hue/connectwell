from django.urls import path
from .views import UnblurView
from .views import TestCreateSessionView, TestSessionDetailView

urlpatterns = [
    path('sessions/<uuid:session_id>/unblur/', UnblurView.as_view(), name='unblur'),
    # Test-only helpers (DEBUG only)
    path('test/create_session', TestCreateSessionView.as_view(), name='test_create_session'),
    path('test/session/<uuid:session_id>/', TestSessionDetailView.as_view(), name='test_session_detail'),
]
