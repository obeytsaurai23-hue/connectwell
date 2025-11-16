from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Order
from django.conf import settings
import json
from pathlib import Path
from accounts.models import WalletTransaction
import os
import hmac
import hashlib
from .models import WebhookEvent


class CreatePurchaseView(APIView):
    def post(self, request):
        pack_id = request.data.get('pack_id')
        if not pack_id:
            return Response({'ok': False, 'message': 'pack_id required'}, status=status.HTTP_400_BAD_REQUEST)
        # Lookup pack metadata from root-level coins_config.json
        coins_conf_path = Path(settings.BASE_DIR).parent / 'coins_config.json'
        try:
            conf = json.loads(coins_conf_path.read_text())
        except Exception:
            conf = {}
        pack = conf.get('packs', {}).get(pack_id)
        if not pack:
            return Response({'ok': False, 'message': 'unknown pack_id'}, status=status.HTTP_400_BAD_REQUEST)
        amount = pack.get('price')
        user = None
        if request.user and request.user.is_authenticated:
            user = request.user
        order = Order.objects.create(user=user, pack_id=pack_id, amount=amount)
        # In dev/demo mode we can use a local mock checkout page for end-to-end testing
        if os.environ.get('MOCK_CHECKOUT') == '1':
            checkout_url = f"/mock_checkout.html?order_id={order.id}"
        else:
            checkout_url = f"https://yoco.example/checkout/{order.id}"
        resp = {
            'ok': True,
            'checkout_url': checkout_url,
            'order_id': str(order.id),
        }
        return Response(resp)


class YocoWebhookView(APIView):
    # In production, verify the signature using Yoco webhook secret
    def post(self, request):
        # Optionally verify webhook signature header if YOCO_WEBHOOK_SECRET is set.
        # In production (DEBUG=False) the webhook secret must be configured.
        # Allow dynamic env override (tests set YOCO_WEBHOOK_SECRET in os.environ at runtime).
        secret = getattr(settings, 'YOCO_WEBHOOK_SECRET', None) or os.environ.get('YOCO_WEBHOOK_SECRET')
        # Allow tests to run without requiring a configured webhook secret. In production
        # (DEBUG=False and not TESTING) the secret must be set.
        if not secret and not getattr(settings, 'DEBUG', True) and not getattr(settings, 'TESTING', False):
            resp = {'ok': False, 'message': 'webhook secret not configured'}
            return Response(resp, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        raw_body = b''
        if secret:
            # Read the raw body from the underlying Django request BEFORE accessing DRF-parsed data
            # Accessing request.data may consume the stream and make request.body unavailable.
            try:
                raw_body = request._request.body
            except Exception:
                # Fallback to request.body; in some test/client setups this will work
                raw_body = request.body or b''
            sig_header = request.META.get('HTTP_X_YOCO_SIGNATURE') or request.META.get('HTTP_X_SIGNATURE')
            if not sig_header:
                return Response({'ok': False, 'message': 'missing signature'}, status=status.HTTP_400_BAD_REQUEST)
            mac = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
            # compare in constant time
            if not hmac.compare_digest(mac, sig_header):
                return Response({'ok': False, 'message': 'invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        # Now safe to use parsed data (DRF may have already parsed it above in some runtimes)
        try:
            event = request.data
        except Exception:
            # If DRF parsing isn't available, try to decode the raw body we read above
            try:
                event = json.loads(raw_body.decode() if isinstance(raw_body, (bytes, bytearray)) else raw_body)
            except Exception:
                event = {}

        # Example event: { "type": "payment_success", "order_id": "...", "tx_id": "..." }
        typ = event.get('type')
        if typ == 'payment_success':
            order_id = event.get('order_id')
            tx = event.get('tx_id')
            # guard by webhook event id if provided
            event_id = event.get('event_id') or tx
            if event_id:
                # if already processed, return OK
                if WebhookEvent.objects.filter(event_id=event_id).exists():
                    return Response({'ok': True})
            try:
                order = Order.objects.get(id=order_id)
                # Idempotency: if order already marked paid with same tx, skip processing
                if order.paid:
                    # already processed
                    return Response({'ok': True})
                # mark paid and process
                order.mark_paid(txid=tx)
                # credit coins to user if order attached
                if order.user:
                    # read coins mapping
                    coins_conf_path = Path(settings.BASE_DIR).parent / 'coins_config.json'
                    try:
                        conf = json.loads(coins_conf_path.read_text())
                    except Exception:
                        conf = {}
                    packs = conf.get('packs', {})
                    pack = packs.get(order.pack_id)
                    if pack:
                        coins = int(pack.get('coins', 0))
                        # ensure we don't double-credit by checking existing WalletTransaction for this order
                        existing = WalletTransaction.objects.filter(
                            user=order.user,
                            reason=f'purchase:{order.pack_id}',
                            metadata__order_id=str(order.id),
                        )
                        if not existing.exists():
                            order.user.coins = (order.user.coins or 0) + coins
                            order.user.save()
                            WalletTransaction.objects.create(
                                user=order.user,
                                amount=coins,
                                reason=f'purchase:{order.pack_id}',
                                metadata={'order_id': str(order.id)},
                            )
                # record webhook event id as processed
                if event_id:
                    WebhookEvent.objects.create(event_id=event_id)
                return Response({'ok': True})
            except Order.DoesNotExist:
                return Response({'ok': False, 'message': 'order not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'ok': False, 'message': 'unsupported event'}, status=status.HTTP_400_BAD_REQUEST)


class OrderStatusView(APIView):
    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
            checkout_url = f"https://yoco.example/checkout/{order.id}"
            resp = {
                'ok': True,
                'order_id': str(order.id),
                'paid': order.paid,
                'checkout_url': checkout_url,
            }
            return Response(resp)
        except Order.DoesNotExist:
            return Response({'ok': False, 'message': 'order not found'}, status=status.HTTP_404_NOT_FOUND)


class TestMarkOrderPaidView(APIView):
    """Test-only endpoint to mark an order paid and credit coins (DEBUG only).

    POST: { "order_id": "...", "tx_id": "..." }
    """
    def post(self, request):
        if not getattr(settings, 'DEBUG', False):
            return Response({'ok': False, 'message': 'Not available'}, status=status.HTTP_404_NOT_FOUND)
        order_id = request.data.get('order_id')
        tx = request.data.get('tx_id') or f'test-{order_id}'
        try:
            order = Order.objects.get(id=order_id)
            if order.paid:
                return Response({'ok': True, 'order_id': str(order.id), 'paid': True})
            order.mark_paid(txid=tx)
            # credit coins to user if present
            if order.user:
                coins_conf_path = Path(settings.BASE_DIR).parent / 'coins_config.json'
                try:
                    conf = json.loads(coins_conf_path.read_text())
                except Exception:
                    conf = {}
                pack = conf.get('packs', {}).get(order.pack_id)
                if pack:
                    coins = int(pack.get('coins', 0))
                    order.user.coins = (order.user.coins or 0) + coins
                    order.user.save()
                    WalletTransaction.objects.create(
                        user=order.user,
                        amount=coins,
                        reason=f'purchase:{order.pack_id}',
                        metadata={'order_id': str(order.id)},
                    )
            return Response({'ok': True, 'order_id': str(order.id), 'paid': True})
        except Order.DoesNotExist:
            return Response({'ok': False, 'message': 'order not found'}, status=status.HTTP_404_NOT_FOUND)
