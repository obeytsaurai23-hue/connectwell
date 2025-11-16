from rest_framework.throttling import SimpleRateThrottle


class SendPinRateThrottle(SimpleRateThrottle):
    scope = 'send_pin'

    def get_cache_key(self, request, view):
        # Rate-limit by IP and email (email as part of key when present)
        ident = self.get_ident(request)
        email = request.data.get('email') if request.data else None
        if email:
            return self.cache_format % {
                'scope': self.scope,
                'ident': f"{ident}:{email}".lower()
            }
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class VerifyPinRateThrottle(SimpleRateThrottle):
    scope = 'verify_pin'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        email = request.data.get('email') if request.data else None
        if email:
            return self.cache_format % {
                'scope': self.scope,
                'ident': f"{ident}:{email}".lower()
            }
        return self.cache_format % {'scope': self.scope, 'ident': ident}
