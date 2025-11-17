from django.utils import timezone
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import PinCode, User
from .serializers import UserSerializer
import random
from datetime import timedelta
from django.utils.crypto import get_random_string
from .throttles import SendPinRateThrottle, VerifyPinRateThrottle
from rest_framework import permissions


class PreferencesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        data = {
            'auto_unblur': user.auto_unblur,
            'auto_buy_coins': user.auto_buy_coins,
            'auto_buy_pack_id': user.auto_buy_pack_id,
            'charge_viewers': getattr(user, 'charge_viewers', False),
        }
        return Response(data)

    def patch(self, request):
        user = request.user
        body = request.data
        changed = False
        if 'auto_unblur' in body:
            user.auto_unblur = bool(body.get('auto_unblur'))
            changed = True
        if 'auto_buy_coins' in body:
            user.auto_buy_coins = bool(body.get('auto_buy_coins'))
            changed = True
        if 'auto_buy_pack_id' in body:
            user.auto_buy_pack_id = str(body.get('auto_buy_pack_id'))
            changed = True
        if 'charge_viewers' in body:
            user.charge_viewers = bool(body.get('charge_viewers'))
            changed = True
        if changed:
            user.save()
        return Response({'ok': True})


PIN_TTL_MINUTES = 10


class SendPinView(APIView):
    throttle_classes = [SendPinRateThrottle]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'ok': False, 'message': 'email required'}, status=status.HTTP_400_BAD_REQUEST)
        # Rate-limiting should be applied at view/infra level; omitted for skeleton
        pin = f"{random.randint(0, 9999):04d}"
        code_hash = make_password(pin)
        expires_at = timezone.now() + timedelta(minutes=PIN_TTL_MINUTES)
        PinCode.objects.create(email=email, code_hash=code_hash, expires_at=expires_at)
        # In production send an email asynchronously. Here we simply log or attempt to send if configured.
        try:
            send_mail(
                'Your Connectwell PIN',
                f'Your PIN is: {pin}',
                'noreply@connectwell.local',
                [email],
            )
        except Exception:
            # ignore email sending failures in skeleton
            pass
        return Response({'ok': True, 'message': 'If that email exists, a PIN was sent'})


class VerifyPinView(APIView):
    throttle_classes = [VerifyPinRateThrottle]

    def post(self, request):
        email = request.data.get('email')
        pin = request.data.get('pin')
        if not email or not pin:
            return Response({'ok': False, 'message': 'email and pin required'}, status=status.HTTP_400_BAD_REQUEST)
        latest = PinCode.objects.filter(email=email).order_by('-created_at').first()
        if not latest or latest.is_expired():
            return Response({'ok': False, 'message': 'PIN invalid or expired'}, status=status.HTTP_400_BAD_REQUEST)
        if latest.attempts >= 5:
            return Response({'ok': False, 'message': 'Too many attempts'}, status=status.HTTP_400_BAD_REQUEST)
        if not check_password(pin, latest.code_hash):
            latest.attempts += 1
            latest.save()
            return Response({'ok': False, 'message': 'PIN invalid'}, status=status.HTTP_400_BAD_REQUEST)
        # Success
        latest.delete()
        user, created = User.objects.get_or_create(email=email)
        user.is_verified = True
        user.save()
        # issue JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        data = UserSerializer(user).data
        data['access_token'] = access_token
        data['refresh_token'] = str(refresh)
        return Response({'ok': True, 'user': data})


class ContinueAnonymousView(APIView):
    def post(self, request):
        # create a short-lived anon token using random string (for demo)
        token = get_random_string(32)
        return Response({'token': token})


class TestCreateUserView(APIView):
    """Test-only endpoint to create a user and return a JWT for E2E tests.

    Enabled only when DEBUG=True to avoid exposing this in production.
    """
    def post(self, request):
        if not getattr(settings, 'DEBUG', False):
            return Response({'ok': False, 'message': 'Not available'}, status=status.HTTP_404_NOT_FOUND)
        email = request.data.get('email') or f'test+{get_random_string(8)}@example.local'
        coins = int(request.data.get('coins') or 0)
        auto_unblur = bool(request.data.get('auto_unblur', True))
        auto_buy_coins = bool(request.data.get('auto_buy_coins', False))
        auto_buy_pack_id = request.data.get('auto_buy_pack_id')
        charge_viewers = bool(request.data.get('charge_viewers', False))
        # profile fields (optional in tests, but ensure defaults exist)
        gender = request.data.get('gender') or 'other'
        birth_year = request.data.get('birth_year')
        location = request.data.get('location') or 'unknown'
        # Ensure we create a unique username to avoid UNIQUE constraint on username
        user = User.objects.filter(email=email).first()
        if not user:
            uname = f'user_{get_random_string(8)}'
            user = User(username=uname, email=email)
        user.coins = coins
        user.auto_unblur = auto_unblur
        user.auto_buy_coins = auto_buy_coins
        if auto_buy_pack_id:
            user.auto_buy_pack_id = auto_buy_pack_id
        user.charge_viewers = charge_viewers
        # apply profile defaults used by tests/helpers
        try:
            user.gender = gender
            if birth_year:
                user.birth_year = int(birth_year)
            user.location = location
        except Exception:
            pass
        user.is_verified = True
        # create unusable password for the test user
        user.set_unusable_password()
        user.save()
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        return Response({'ok': True, 'user': {'id': str(user.id), 'email': user.email}, 'access_token': access})
