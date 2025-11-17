from django.urls import path
from .views import CreatePurchaseView, YocoWebhookView, OrderStatusView
from .wallet_views import WalletView
from .views import TestMarkOrderPaidView
from .views import CreatePremiumView

urlpatterns = [
    path('coins/purchase', CreatePurchaseView.as_view(), name='coins_purchase'),
    path('premium/purchase', CreatePremiumView.as_view(), name='premium_purchase'),
    path('webhooks/yoco', YocoWebhookView.as_view(), name='yoco_webhook'),
    path('coins/order/<uuid:order_id>/status', OrderStatusView.as_view(), name='order_status'),
    path('wallet', WalletView.as_view(), name='wallet'),
    # Test-only endpoint
    path('test/mark_order_paid', TestMarkOrderPaidView.as_view(), name='test_mark_order_paid'),
]
