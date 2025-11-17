from django.urls import path
from .views import SendPinView, VerifyPinView, ContinueAnonymousView
from .views import PreferencesView
from .views import TestCreateUserView

urlpatterns = [
    path('auth/send_pin', SendPinView.as_view(), name='send_pin'),
    path('auth/verify_pin', VerifyPinView.as_view(), name='verify_pin'),
    path('auth/continue_anonymous', ContinueAnonymousView.as_view(), name='continue_anonymous'),
    path('auth/preferences', PreferencesView.as_view(), name='preferences'),
    # Test-only endpoint (DEBUG only)
    path('test/create_user', TestCreateUserView.as_view(), name='test_create_user'),
]
