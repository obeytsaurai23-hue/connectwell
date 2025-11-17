import json
from channels.generic.websocket import AsyncWebsocketConsumer
import redis.asyncio as aioredis
import os
from asgiref.sync import sync_to_async
from .models import MatchSession
from rest_framework_simplejwt.tokens import AccessToken
from accounts.models import User as AccountsUser
from accounts.models import WalletTransaction
from django.db import transaction
from pathlib import Path
# small tidy: removed unused imports (random, async_to_sync)

# Redis queue key prefix
QUEUE_KEY_PREFIX = 'connectwell:queue:'
FILTERS_KEY_PREFIX = 'connectwell:active_filters:'

# Load coin costs for paid filters (fallbacks if config missing)
_CFG_PATH = Path(__file__).resolve().parents[2] / 'coins_config.json'
try:
    with open(_CFG_PATH, 'r', encoding='utf-8') as _f:
        _CFG = json.load(_f)
except Exception:
    _CFG = {}

GENDER_FILTER_HOURS = int(_CFG.get('costs', {}).get('gender_filter_hour', 0))
LOCATION_FILTER_HOURS = int(_CFG.get('costs', {}).get('location_filter_hour', 0))
HD_VIDEO_COST = int(_CFG.get('costs', {}).get('hd_video_session', 0))
INSTANT_CONNECT_COST = int(_CFG.get('costs', {}).get('instant_connect', 0))


async def get_redis():
    url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    return aioredis.from_url(url)


PAIR_PRIORITY_LUA = '''
-- Attempt priority matching across a premium queue (KEYS[1]) and a normal queue (KEYS[2]).
-- Prefer premium-premium, then premium-normal, then normal-normal. Returns up to two items.
local pkey = KEYS[1]
local nkey = KEYS[2]
local p_len = redis.call('LLEN', pkey)
local n_len = redis.call('LLEN', nkey)
if p_len >= 2 then
    local a = redis.call('LPOP', pkey)
    local b = redis.call('LPOP', pkey)
    return {a, b}
end
if p_len == 1 and n_len >= 1 then
    local a = redis.call('LPOP', pkey)
    local b = redis.call('LPOP', nkey)
    return {a, b}
end
if n_len >= 2 then
    local a = redis.call('LPOP', nkey)
    local b = redis.call('LPOP', nkey)
    return {a, b}
end
return {}
'''


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Validate token from query string (access_token) if provided
        _token = None
        qs = self.scope.get('query_string', b'')
        if qs:
            try:
                qs_decoded = qs.decode()
                # support both token= and access_token= query keys
                if 'token=' in qs_decoded:
                    _token = qs_decoded.split('token=')[-1].split('&')[0]
                elif 'access_token=' in qs_decoded:
                    _token = qs_decoded.split('access_token=')[-1].split('&')[0]
            except Exception:
                _token = None

        self.user = None
        if _token:
            try:
                claims = AccessToken(_token)
                user_id = claims.get('user_id')
                if user_id:
                    try:
                        self.user = await sync_to_async(AccountsUser.objects.get)(pk=user_id)
                    except AccountsUser.DoesNotExist:
                        self.user = None
            except Exception:
                # invalid token -> reject
                await self.close(code=4001)
                return

        await self.accept()

        # store mapping channel -> user_id in Redis for later resolution
        try:
            r = await get_redis()
            if self.user:
                # set a per-channel key with TTL so mappings expire if client disappears
                await r.set(f'connectwell:channel_user:{self.channel_name}', str(self.user.id), ex=300)
                await r.hset('connectwell:channel_user', self.channel_name, str(self.user.id))
                # also set a reverse mapping user->channel for quick lookup
                await r.set(f'connectwell:user_channel:{self.user.id}', self.channel_name, ex=300)
        except Exception:
            pass

    async def disconnect(self, close_code):
        # Remove entry from Redis queue if present
        r = await get_redis()
        # remove any occurrence of this channel from all mode queues
        for mode in ('video', 'text'):
            try:
                await r.lrem(QUEUE_KEY_PREFIX + mode, 0, self.channel_name)
            except Exception:
                pass
        # remove channel->user mapping
        try:
            await r.hdel('connectwell:channel_user', self.channel_name)
            await r.delete(f'connectwell:channel_user:{self.channel_name}')
            # remove reverse mapping if it points to this channel
            try:
                val = await r.get(f'connectwell:user_channel:{self.user.id}') if self.user else None
                if val and val.decode() == self.channel_name:
                    await r.delete(f'connectwell:user_channel:{self.user.id}')
            except Exception:
                pass
        except Exception:
            pass

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or '{}')
        except Exception:
            return
        action = data.get('action')
        if action == 'enqueue':
            await self.handle_enqueue(data)
        elif action == 'signal':
            peer = data.get('peer')
            payload = data.get('payload')
            if peer and payload:
                signal_payload = {
                    'action': 'signal',
                    'from': self.channel_name,
                    'payload': payload,
                }
                await self.channel_layer.send(peer, {
                    'type': 'chat.message',
                    'text': json.dumps(signal_payload),
                })
        elif action == 'next':
            await self.send(json.dumps({'action': 'next_ack'}))
        elif action == 'heartbeat':
            # refresh TTL on channel->user mapping
            try:
                r = await get_redis()
                await r.expire(f'connectwell:channel_user:{self.channel_name}', 300)
            except Exception:
                pass

    async def handle_enqueue(self, data):
        mode = data.get('mode', 'video')
        # optional filters requested by this enqueuer (premium-only unless paid)
        requested_filters = data.get('filters') or {}
        # optional self-declared profile (to be used by peers when filtering)
        self_profile = data.get('profile') or {}
        r = await get_redis()
        key = QUEUE_KEY_PREFIX + mode
        premium_key = key + ':premium'
        # Persist any temporary profile the user sends with a short TTL so peers can inspect it during matching
        if self_profile:
            try:
                await r.hset('connectwell:profile', self.channel_name, json.dumps(self_profile))
                # expire the mapping after 5 minutes (profiles in quick-mode are ephemeral)
                await r.expire('connectwell:profile', 300)
            except Exception:
                pass

        # Before queueing, ensure that the participant provided required profile fields (gender, age >=18, location)

        # Try to compute age from provided profile.age or birth_year
        def _compute_age_from_profile(p):
            try:
                if p.get('age') is not None:
                    return int(p.get('age'))
                if p.get('birth_year') is not None:
                    from datetime import datetime
                    return datetime.utcnow().year - int(p.get('birth_year'))
            except Exception:
                return None
            return None

        # prefer self_profile, fall back to user persistent profile if available
        profile_to_check = {}
        if self_profile:
            profile_to_check.update(self_profile)
        elif self.user:
            try:
                profile_to_check.update({
                    'gender': getattr(self.user, 'gender', None),
                    'age': None,
                    'birth_year': getattr(self.user, 'birth_year', None),
                    'location': getattr(self.user, 'location', None),
                })
                age = _compute_age_from_profile(profile_to_check)
                if age:
                    profile_to_check['age'] = age
            except Exception:
                profile_to_check = {}

        # validate required fields
        age_val = _compute_age_from_profile(profile_to_check) or profile_to_check.get('age')
        gender_val = profile_to_check.get('gender')
        location_val = profile_to_check.get('location')
        try:
            if age_val is None or int(age_val) < 18:
                payload = {
                    'action': 'error',
                    'message': 'You must provide your age and be 18+ to use matchmaking.',
                }
                await self.send(json.dumps(payload))
                return
        except Exception:
            payload = {
                'action': 'error',
                'message': 'Invalid age value; please provide a valid number.',
            }
            await self.send(json.dumps(payload))
            return
        if not gender_val:
            payload = {
                'action': 'error',
                'message': 'Please provide your gender in profile before matchmaking.',
            }
            await self.send(json.dumps(payload))
            return
        if not location_val:
            payload = {
                'action': 'error',
                'message': 'Please allow location detection or enter your location before matchmaking.',
            }
            await self.send(json.dumps(payload))
            return

        # If the user requested filters, enforce premium-only or paid filters here.
        if requested_filters:
            # If the user is not authenticated or not premium, deny unless they explicitly paid.
            try:
                is_premium = bool(self.user and getattr(self.user, 'is_premium', False))
            except Exception:
                is_premium = False

            if not is_premium:
                # Determine coin cost for requested filters (gender and/or location)
                cost_hours = 0
                if requested_filters.get('gender'):
                    cost_hours += GENDER_FILTER_HOURS
                if requested_filters.get('location'):
                    cost_hours += LOCATION_FILTER_HOURS
                # single-session features
                hd_requested = bool(requested_filters.get('hd'))
                instant_requested = bool(requested_filters.get('instant_connect'))
                coin_cost = 0
                # hourly costs converted to coins (1 coin per hour by convention)
                coin_cost += cost_hours
                if hd_requested:
                    coin_cost += HD_VIDEO_COST
                if instant_requested:
                    coin_cost += INSTANT_CONNECT_COST
                if coin_cost > 0:
                    # require the user to have enough coins; if not, inform client (via queued reply)
                    if not self.user or (getattr(self.user, 'coins', 0) < coin_cost):
                        payload = {
                            'action': 'queued',
                            'message': 'filters require premium or purchase',
                            'required_coins': coin_cost,
                        }
                        await self.send(json.dumps(payload))
                        return
                    # charge coins and record transaction, then persist the requested
                    # filter in Redis for `cost_hours` hours

                    def charge_for_filters():
                        with transaction.atomic():
                            self.user.coins -= coin_cost
                            self.user.save()
                            WalletTransaction.objects.create(
                                user=self.user,
                                amount=-coin_cost,
                                reason='purchase:filters',
                                metadata={'filters': requested_filters},
                            )
                    try:
                        await sync_to_async(charge_for_filters)()
                        # store filters keyed by channel with TTL
                        if cost_hours > 0:
                            ttl = max(1, cost_hours) * 3600
                        else:
                            # single-session features -> keep for 1 hour
                            ttl = 3600
                        filter_key = FILTERS_KEY_PREFIX + self.channel_name
                        await r.set(filter_key, json.dumps(requested_filters), ex=ttl)
                    except Exception:
                        payload = {'action': 'queued', 'message': 'filter payment failed'}
                        await self.send(json.dumps(payload))
                        return
                else:
                    # no coin cost configured and not premium -> deny
                    payload = {'action': 'queued', 'message': 'filters require premium account'}
                    await self.send(json.dumps(payload))
                    return

        # Push this channel into the appropriate queue (premium users get a priority queue)
        try:
            is_premium = bool(self.user and getattr(self.user, 'is_premium', False))
        except Exception:
            is_premium = False
        if is_premium:
            await r.rpush(premium_key, self.channel_name)
        else:
            await r.rpush(key, self.channel_name)

        try:
            # Atomically attempt priority matching: prefer premium queue
            res = await r.eval(PAIR_PRIORITY_LUA, 2, premium_key, key)
            # decode redis bytes to strings in a short loop to avoid long comprehensions
            popped = []
            for p in res:
                if isinstance(p, (bytes, bytearray)):
                    try:
                        popped.append(p.decode())
                    except Exception:
                        popped.append(p)
                else:
                    popped.append(p)
            if len(popped) < 2:
                # push back any popped items that aren't self
                for p in popped:
                    if p != self.channel_name:
                        await r.lpush(key, p)
                payload = {'action': 'queued'}
                await self.send(json.dumps(payload))
                return
            # determine peer which is not self
            if popped[0] == self.channel_name:
                peer_channel = popped[1]
            elif popped[1] == self.channel_name:
                peer_channel = popped[0]
            else:
                # we popped two other channels; requeue them and notify queued
                for p in popped:
                    await r.lpush(key, p)
                payload = {'action': 'queued'}
                await self.send(json.dumps(payload))
                return

            # Before creating a session, load profiles and active filters for both channels and ensure compatibility
            try:
                peer_profile_raw = await r.hget('connectwell:profile', peer_channel)
                self_profile_raw = await r.hget('connectwell:profile', self.channel_name)
                if peer_profile_raw:
                    try:
                        peer_profile = json.loads(peer_profile_raw.decode())
                    except Exception:
                        peer_profile = {}
                else:
                    peer_profile = {}

                if self_profile_raw:
                    try:
                        self_profile_current = json.loads(self_profile_raw.decode())
                    except Exception:
                        self_profile_current = self_profile
                else:
                    self_profile_current = self_profile
            except Exception:
                peer_profile = {}
                self_profile_current = self_profile

            try:
                peer_filters_raw = await r.get(FILTERS_KEY_PREFIX + peer_channel)
                self_filters_raw = await r.get(FILTERS_KEY_PREFIX + self.channel_name)
                # if peer has no channel-scoped filters, check user-scoped filters (persistent for premium)
                if not peer_filters_raw:
                    try:
                        # resolve peer user id and check user-scoped key
                        peer_user_id = await r.hget('connectwell:channel_user', peer_channel)
                        if peer_user_id:
                            if isinstance(peer_user_id, (bytes, bytearray)):
                                try:
                                    peer_user_id = peer_user_id.decode()
                                except Exception:
                                    pass
                            key = FILTERS_KEY_PREFIX + f'user:{peer_user_id}'
                            peer_filters_raw = await r.get(key)
                    except Exception:
                        pass
                if not self_filters_raw:
                    try:
                        self_user_id = await r.hget('connectwell:channel_user', self.channel_name)
                        if self_user_id:
                            if isinstance(self_user_id, (bytes, bytearray)):
                                try:
                                    self_user_id = self_user_id.decode()
                                except Exception:
                                    pass
                            key = FILTERS_KEY_PREFIX + f'user:{self_user_id}'
                            self_filters_raw = await r.get(key)
                    except Exception:
                        pass
                # decode filter values safely
                if peer_filters_raw:
                    try:
                        peer_filters = json.loads(peer_filters_raw.decode())
                    except Exception:
                        peer_filters = {}
                else:
                    peer_filters = {}
                if self_filters_raw:
                    try:
                        self_filters = json.loads(self_filters_raw.decode())
                    except Exception:
                        self_filters = requested_filters
                else:
                    self_filters = requested_filters
            except Exception:
                peer_filters = {}
                self_filters = requested_filters

            def _matches(profile, flt):
                if not flt:
                    return True
                # gender
                g = flt.get('gender')
                if g and g != 'any':
                    if profile.get('gender') != g:
                        return False
                # age range
                amin = flt.get('age_min')
                amax = flt.get('age_max')
                if amin is not None or amax is not None:
                    try:
                        age = int(profile.get('age')) if profile.get('age') is not None else None
                    except Exception:
                        age = None
                    if age is None:
                        return False
                    if amin is not None and age < int(amin):
                        return False
                    if amax is not None and age > int(amax):
                        return False
                # location (simple equality)
                loc = flt.get('location')
                if loc:
                    if profile.get('location') != loc:
                        return False
                return True

            # ensure both sides' requested filters (if any) are compatible with the other's profile

            if self_filters and not _matches(peer_profile, self_filters):
                # peer doesn't satisfy our filters -> requeue and tell us we're still queued
                await r.lpush(key, peer_channel)
                payload = {
                    'action': 'queued',
                    'message': 'no match for requested filters yet',
                }
                await self.send(json.dumps(payload))
                return
            if peer_filters and not _matches(self_profile_current, peer_filters):
                # we don't satisfy peer's filters -> requeue and notify queued
                await r.lpush(key, peer_channel)
                payload = {
                    'action': 'queued',
                    'message': 'no match (peer filters)',
                }
                await self.send(json.dumps(payload))
                return

            # create MatchSession with optional user references
            user_a = self.user if self.user else None
            # we don't have peer user mapping by channel here; leave user_b None
            create_args = {
                'user_a': user_a,
                'user_b': None,
                'user_a_channel': self.channel_name,
                'user_b_channel': peer_channel,
            }
            session = await sync_to_async(MatchSession.objects.create)(**create_args)

            # Determine initial unblur state based on whether the session owners require viewers to pay.
            # By default a user's video is visible unless that user has `charge_viewers=True`.
            try:
                r = await get_redis()
                # try to resolve both user ids from channel mapping
                user_a_id = await r.hget('connectwell:channel_user', self.channel_name)
                user_b_id = await r.hget('connectwell:channel_user', peer_channel)
                user_a_obj = None
                user_b_obj = None
                if user_a_id:
                    user_a_id = user_a_id.decode() if isinstance(user_a_id, (bytes, bytearray)) else user_a_id
                    try:
                        user_a_obj = await sync_to_async(AccountsUser.objects.get)(pk=user_a_id)
                    except AccountsUser.DoesNotExist:
                        user_a_obj = None
                if user_b_id:
                    user_b_id = user_b_id.decode() if isinstance(user_b_id, (bytes, bytearray)) else user_b_id
                    try:
                        user_b_obj = await sync_to_async(AccountsUser.objects.get)(pk=user_b_id)
                    except AccountsUser.DoesNotExist:
                        user_b_obj = None

                # By default unblurred unless the owner requires viewers to pay
                a_unblurred = not (user_a_obj and getattr(user_a_obj, 'charge_viewers', False))
                b_unblurred = not (user_b_obj and getattr(user_b_obj, 'charge_viewers', False))

                # persist initial state
                def _persist_state():
                    MatchSession.objects.filter(pk=session.pk).update(
                        user_a_unblurred=a_unblurred,
                        user_b_unblurred=b_unblurred,
                    )

                await sync_to_async(_persist_state)()

                # If owner requires viewers to pay (so owner side is blurred),
                # attempt auto-unblur by charging the viewer
                # If viewer has auto_unblur enabled and enough coins, charge and unblur immediately.
                if not a_unblurred and user_b_obj:
                    if user_b_obj.auto_unblur and user_b_obj.coins >= session.unblur_price:
                        def charge_and_unblur_a():
                            with transaction.atomic():
                                user_b_obj.coins -= session.unblur_price
                                user_b_obj.save()
                                WalletTransaction.objects.create(
                                    user=user_b_obj,
                                    amount=-session.unblur_price,
                                    reason=f'purchase:unblur:{session.id}',
                                )
                                s = MatchSession.objects.get(pk=session.pk)
                                s.user_a_unblurred = True
                                s.save()
                        await sync_to_async(charge_and_unblur_a)()
                        # notify both peers that the a side was unblurred
                        try:
                            payload = {
                                'action': 'unblur',
                                'side': 'a',
                                'session_id': str(session.id),
                            }
                            send_msg = {
                                'type': 'chat.message',
                                'text': json.dumps(payload),
                            }
                            await self.channel_layer.send(self.channel_name, send_msg)
                            await self.channel_layer.send(peer_channel, send_msg)
                        except Exception:
                            pass

                if not b_unblurred and user_a_obj:
                    if user_a_obj.auto_unblur and user_a_obj.coins >= session.unblur_price:
                        def charge_and_unblur_b():
                            with transaction.atomic():
                                user_a_obj.coins -= session.unblur_price
                                user_a_obj.save()
                                WalletTransaction.objects.create(
                                    user=user_a_obj,
                                    amount=-session.unblur_price,
                                    reason=f'purchase:unblur:{session.id}',
                                )
                                s = MatchSession.objects.get(pk=session.pk)
                                s.user_b_unblurred = True
                                s.save()
                        await sync_to_async(charge_and_unblur_b)()
                        # notify both peers that the b side was unblurred
                        try:
                            payload = {
                                'action': 'unblur',
                                'side': 'b',
                                'session_id': str(session.id),
                            }
                            send_msg = {
                                'type': 'chat.message',
                                'text': json.dumps(payload),
                            }
                            await self.channel_layer.send(self.channel_name, send_msg)
                            await self.channel_layer.send(peer_channel, send_msg)
                        except Exception:
                            pass
            except Exception:
                pass

            # notify both peers
            # include premium flag in the payload so clients can enable premium UX (HD, no-ads, etc.)
            try:
                peer_is_premium = bool(user_b_obj and getattr(user_b_obj, 'is_premium', False))
            except Exception:
                peer_is_premium = False
            try:
                self_is_premium = bool(user_a_obj and getattr(user_a_obj, 'is_premium', False))
            except Exception:
                self_is_premium = False

            match_payload_peer = {
                'action': 'match_found',
                'you': peer_channel,
                'peer': self.channel_name,
                'session_id': str(session.id),
                'peer_is_premium': self_is_premium,
            }
            match_payload_self = {
                'action': 'match_found',
                'you': self.channel_name,
                'peer': peer_channel,
                'session_id': str(session.id),
                'peer_is_premium': peer_is_premium,
            }
            peer_text = json.dumps(match_payload_peer)
            self_text = json.dumps(match_payload_self)
            send_peer_msg = {
                'type': 'chat.message',
                'text': peer_text,
            }
            send_self_msg = {
                'type': 'chat.message',
                'text': self_text,
            }
            await self.channel_layer.send(peer_channel, send_peer_msg)
            await self.channel_layer.send(self.channel_name, send_self_msg)
        except Exception:
            payload = {'action': 'queued'}
            await self.send(json.dumps(payload))

    async def chat_message(self, event):
        await self.send(event['text'])
