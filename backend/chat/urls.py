from django.urls import path
from .views import UnblurView
from .views import TestCreateSessionView, TestSessionDetailView, PurchaseFiltersView, NextActionView, AdWatchedView

urlpatterns = [
    path('sessions/<uuid:session_id>/unblur/', UnblurView.as_view(), name='unblur'),
    # Test-only helpers (DEBUG only)
    path('test/create_session', TestCreateSessionView.as_view(), name='test_create_session'),
    path('test/session/<uuid:session_id>/', TestSessionDetailView.as_view(), name='test_session_detail'),
    path('filters/purchase', PurchaseFiltersView.as_view(), name='purchase_filters'),
    path('sessions/<uuid:session_id>/next/', NextActionView.as_view(), name='session_next'),
    path('sessions/<uuid:session_id>/next/ad_watched/', AdWatchedView.as_view(), name='session_ad_watched'),
]
