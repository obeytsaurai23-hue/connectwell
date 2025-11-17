from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import MatchSession
from accounts.models import WalletTransaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
from payments.models import Order
from pathlib import Path
from django.conf import settings
import os
import redis
from django.conf import settings as _settings
from pathlib import Path as _Path

# Redis key for active filters
FILTERS_KEY_PREFIX = 'connectwell:active_filters:'


class UnblurView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        user = request.user
        session = get_object_or_404(MatchSession, pk=session_id)
        # determine which side the user is (a or b)
        side = None
        if session.user_a and session.user_a == user:
            side = 'a'
        elif session.user_b and session.user_b == user:
            side = 'b'
        else:
            # maybe user connected anonymously; compare channels
            resp = {'detail': 'Not a participant or not linked user.'}
            return Response(resp, status=status.HTTP_403_FORBIDDEN)

        # check if already unblurred
        # If the session owner requires viewers to pay (`charge_viewers`), treat the video as still blurred
        # unless there's an existing WalletTransaction recording a prior unblur purchase for this session.
        def has_unblur_tx_for(user):
            if not user:
                return False
            q = WalletTransaction.objects.filter(
                user=user,
                reason__startswith=f'purchase:unblur:{session.id}',
            )
            return q.exists()

        if side == 'a':
            owner = session.user_a
            owner_charges = bool(owner and getattr(owner, 'charge_viewers', False))
            effective_unblur = session.user_a_unblurred and (not owner_charges or has_unblur_tx_for(owner))
        else:
            owner = session.user_b
            owner_charges = bool(owner and getattr(owner, 'charge_viewers', False))
            effective_unblur = session.user_b_unblurred and (not owner_charges or has_unblur_tx_for(owner))

        if effective_unblur:
            return Response({'detail': 'Already unblurred'}, status=status.HTTP_200_OK)

        price = session.unblur_price
        if user.coins < price:
            # attempt auto-buy if user enabled auto_buy_coins
            if user.auto_buy_coins:
                # create an order for the user's preferred pack
                pack_id = user.auto_buy_pack_id or 'starter'
                coins_conf_path = Path(settings.BASE_DIR).parent / 'coins_config.json'
                try:
                    conf = json.loads(coins_conf_path.read_text())
                except Exception:
                    conf = {}
                pack = conf.get('packs', {}).get(pack_id)
                if not pack:
                    resp = {'detail': 'Insufficient coins', 'needed': price}
                    return Response(resp, status=status.HTTP_402_PAYMENT_REQUIRED)
                amount = pack.get('price')
                order = Order.objects.create(user=user, pack_id=pack_id, amount=amount)
                checkout_url = f"https://yoco.example/checkout/{order.id}"
                # If environment requests auto-completion (testing/dev), mark paid and credit coins
                if os.environ.get('AUTO_COMPLETE_PURCHASES') == '1':
                    order.mark_paid(txid=f'auto-{order.id}')
                    # credit coins according to pack
                    coins = int(pack.get('coins', 0))
                    user.coins = (user.coins or 0) + coins
                    user.save()
                    WalletTransaction.objects.create(
                        user=user,
                        amount=coins,
                        reason=f'purchase:{pack_id}',
                        metadata={'order_id': str(order.id)},
                    )
                else:
                    # tell client to redirect to checkout
                    resp = {
                        'detail': 'Created order',
                        'order_id': str(order.id),
                        'checkout_url': checkout_url,
                    }
                    return Response(resp, status=status.HTTP_402_PAYMENT_REQUIRED)
                # re-check coins after auto-complete
                if user.coins < price:
                    resp = {'detail': 'Insufficient coins after purchase', 'needed': price}
                    return Response(resp, status=status.HTTP_402_PAYMENT_REQUIRED)
            else:
                resp = {'detail': 'Insufficient coins', 'needed': price}
                return Response(resp, status=status.HTTP_402_PAYMENT_REQUIRED)

        # charge user and mark unblurred
        with transaction.atomic():
            user.coins -= price
            user.save()
            WalletTransaction.objects.create(
                user=user,
                amount=-price,
                reason=f'purchase:unblur:{session.id}',
            )
            if side == 'a':
                session.user_a_unblurred = True
            else:
                session.user_b_unblurred = True
            session.save()

        # Notify both participants via channel layer that unblur occurred
        try:
            channel_layer = get_channel_layer()
            # Resolve latest channel for user_a and user_b from Redis reverse mapping
            try:
                url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
                r = redis.from_url(url)
                # prefer reverse mapping; fall back to stored session channel
                a_chan = None
                b_chan = None
                if session.user_a:
                    try:
                        a_chan = r.get(f'connectwell:user_channel:{session.user_a.id}')
                        if a_chan:
                            a_chan = a_chan.decode()
                    except Exception:
                        a_chan = None
                if not a_chan:
                    a_chan = session.user_a_channel
                if session.user_b:
                    try:
                        b_chan = r.get(f'connectwell:user_channel:{session.user_b.id}')
                        if b_chan:
                            b_chan = b_chan.decode()
                    except Exception:
                        b_chan = None
                if not b_chan:
                    b_chan = session.user_b_channel

                payload = {
                    'action': 'unblur',
                    'side': side,
                    'session_id': str(session.id),
                }
                if a_chan:
                    send_msg = {
                        'type': 'chat.message',
                        'text': json.dumps(payload),
                    }
                    async_to_sync(channel_layer.send)(a_chan, send_msg)
                if b_chan:
                    send_msg = {
                        'type': 'chat.message',
                        'text': json.dumps(payload),
                    }
                    async_to_sync(channel_layer.send)(b_chan, send_msg)
            except Exception:
                # fallback: send to stored channels
                fallback_payload = {
                    'action': 'unblur',
                    'side': side,
                    'session_id': str(session.id),
                }
                fallback_msg = {
                    'type': 'chat.message',
                    'text': json.dumps(fallback_payload),
                }
                async_to_sync(channel_layer.send)(session.user_a_channel, fallback_msg)
                async_to_sync(channel_layer.send)(session.user_b_channel, fallback_msg)
        except Exception:
            pass

        resp = {'detail': 'Unblurred', 'price': price}
        return Response(resp, status=status.HTTP_200_OK)


class TestCreateSessionView(APIView):
    """Test-only endpoint to create a MatchSession quickly for E2E tests.

    Only enabled when DEBUG=True.
    """
    def post(self, request):
        if not getattr(_settings, 'DEBUG', False):
            return Response({'ok': False, 'message': 'Not available'}, status=status.HTTP_404_NOT_FOUND)
        user_a_id = request.data.get('user_a_id')
        user_b_id = request.data.get('user_b_id')
        from accounts.models import User as AccountsUser
        user_a = None
        user_b = None
        if user_a_id:
            try:
                user_a = AccountsUser.objects.get(id=user_a_id)
            except Exception:
                user_a = None
        if user_b_id:
            try:
                user_b = AccountsUser.objects.get(id=user_b_id)
            except Exception:
                user_b = None
        a_chan = request.data.get('user_a_channel') or f'chan-a-{getattr(user_a, "id", "anon")}'
        b_chan = request.data.get('user_b_channel') or f'chan-b-{getattr(user_b, "id", "anon")}'
        create_args = {
            'user_a': user_a,
            'user_b': user_b,
            'user_a_channel': a_chan,
            'user_b_channel': b_chan,
        }
        s = MatchSession.objects.create(**create_args)
        resp = {
            'ok': True,
            'session_id': str(s.id),
            'user_a_unblurred': s.user_a_unblurred,
            'user_b_unblurred': s.user_b_unblurred,
        }
        return Response(resp)


class PurchaseFiltersView(APIView):
    """Allow authenticated users to purchase time-limited filters (gender/location).

    Request JSON: { filters: { gender: 'female', location: 'lat,lon' }, hours: 1 }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data or {}
        filters = data.get('filters') or {}
        hours = int(data.get('hours') or 1)

        # load costs from coins_config.json
        try:
            cfg_path = _Path(settings.BASE_DIR).parent / 'coins_config.json'
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            cfg = {}
        costs = cfg.get('costs', {})

        coin_cost = 0
        if filters.get('gender'):
            coin_cost += int(costs.get('gender_filter_hour', 0)) * hours
        if filters.get('location'):
            coin_cost += int(costs.get('location_filter_hour', 0)) * hours
        # single-session features
        if filters.get('hd'):
            coin_cost += int(costs.get('hd_video_session', 0))
        if filters.get('instant_connect'):
            coin_cost += int(costs.get('instant_connect', 0))
        # allow premium users to enable filters without charging; persist permanently for their account
        is_premium = bool(getattr(user, 'is_premium', False))
        if coin_cost <= 0 and not is_premium:
            return Response({'detail': 'No cost configured for requested filters'}, status=status.HTTP_400_BAD_REQUEST)

        if not is_premium:
            if (user.coins or 0) < coin_cost:
                resp = {'detail': 'Insufficient coins', 'required_coins': coin_cost}
                return Response(resp, status=status.HTTP_402_PAYMENT_REQUIRED)

            # charge user
            with transaction.atomic():
                user.coins = (user.coins or 0) - coin_cost
                user.save()
                WalletTransaction.objects.create(
                    user=user,
                    amount=-coin_cost,
                    reason='purchase:filters',
                    metadata={'filters': filters, 'hours': hours},
                )
        else:
            # premium users: record a WalletTransaction for auditing (amount 0) and persist permanently
            WalletTransaction.objects.create(
                user=user,
                amount=0,
                reason='grant:premium:filters',
                metadata={'filters': filters, 'hours': hours},
            )

        # persist to Redis for the computed TTL
        if any([filters.get('gender'), filters.get('location')]):
            ttl = max(1, hours) * 3600
        else:
            # single-session features -> keep for 1 hour
            ttl = 3600
        try:
            url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            r = redis.from_url(url)
            # attempt to store under user's current channel if available
            chan = None
            try:
                chan = r.get(f'connectwell:user_channel:{user.id}')
                if chan:
                    chan = chan.decode() if isinstance(chan, (bytes, bytearray)) else chan
            except Exception:
                chan = None
            key_set = []
            if chan:
                # if premium, persist without expiry; otherwise set TTL
                if is_premium:
                    r.set(FILTERS_KEY_PREFIX + chan, json.dumps(filters))
                else:
                    r.set(FILTERS_KEY_PREFIX + chan, json.dumps(filters), ex=ttl)
                key_set.append(FILTERS_KEY_PREFIX + chan)
            # always set a user-scoped key as well (persistent for premium)
            if is_premium:
                r.set(FILTERS_KEY_PREFIX + f'user:{user.id}', json.dumps(filters))
            else:
                r.set(FILTERS_KEY_PREFIX + f'user:{user.id}', json.dumps(filters), ex=ttl)
            key_set.append(FILTERS_KEY_PREFIX + f'user:{user.id}')
        except Exception:
            # don't fail the purchase if Redis is temporarily unavailable
            key_set = []

        return Response({'detail': 'filters purchased', 'coins_charged': coin_cost, 'keys_set': key_set})


class TestSessionDetailView(APIView):
    def get(self, request, session_id):
        if not getattr(_settings, 'DEBUG', False):
            return Response({'ok': False, 'message': 'Not available'}, status=status.HTTP_404_NOT_FOUND)

        try:
            s = MatchSession.objects.get(id=session_id)
            resp = {
                'ok': True,
                'session_id': str(s.id),
                'user_a_unblurred': s.user_a_unblurred,
                'user_b_unblurred': s.user_b_unblurred,
                'unblur_price': s.unblur_price,
            }
            return Response(resp)
        except MatchSession.DoesNotExist:
            return Response({'ok': False, 'message': 'not found'}, status=status.HTTP_404_NOT_FOUND)


class NextActionView(APIView):
    """Record a 'next' (skip) action for a session and enforce ad requirement after threshold.

    POST /api/v1/sessions/<session_id>/next/
    Requesting user must be one of the session participants.
    Returns { action: 'next_ack' } or { action: 'ad_required', 'count': n }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        user = request.user
        try:
            s = MatchSession.objects.get(id=session_id)
        except MatchSession.DoesNotExist:
            return Response({'detail': 'not found'}, status=status.HTTP_404_NOT_FOUND)

        # determine side
        side = None
        if s.user_a and s.user_a == user:
            side = 'a'
        elif s.user_b and s.user_b == user:
            side = 'b'
        else:
            return Response({'detail': 'not a participant'}, status=status.HTTP_403_FORBIDDEN)

        # increment counter in Redis
        try:
            url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            r = redis.from_url(url)
            key = f'connectwell:session_next:{session_id}:{side}'
            count = r.incr(key)
            # set a TTL for the counter tied to session life (1 day)
            r.expire(key, 86400)
        except Exception:
            # if Redis unavailable, fallback to allowing next
            return Response({'action': 'next_ack'})

        # enforce ad after 3 for non-premium users
        try:
            is_premium = bool(user and getattr(user, 'is_premium', False))
        except Exception:
            is_premium = False

        if not is_premium and int(count) >= 3:
            return Response({'action': 'ad_required', 'count': int(count)})

        return Response({'action': 'next_ack', 'count': int(count)})


class AdWatchedView(APIView):
    """Notify server that an ad was watched for this session/side so counters can be reset."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        user = request.user
        try:
            s = MatchSession.objects.get(id=session_id)
        except MatchSession.DoesNotExist:
            return Response({'detail': 'not found'}, status=status.HTTP_404_NOT_FOUND)

        # determine side
        side = None
        if s.user_a and s.user_a == user:
            side = 'a'
        elif s.user_b and s.user_b == user:
            side = 'b'
        else:
            return Response({'detail': 'not a participant'}, status=status.HTTP_403_FORBIDDEN)

        try:
            url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            r = redis.from_url(url)
            key = f'connectwell:session_next:{session_id}:{side}'
            r.delete(key)
        except Exception:
            pass

        return Response({'detail': 'ok'})
