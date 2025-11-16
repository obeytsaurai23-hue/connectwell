"""Django models sketch for Connectwell.

Small, test-friendly models used by the demo and tests.
Keep formatting minimal and PEP8-compliant.
"""

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email=None, password=None, **extra):
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_unusable_password()
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    email = models.EmailField(unique=True, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    coins = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    objects = UserManager()


class PinCode(models.Model):
    email = models.EmailField()
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)


class WalletTransaction(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE)
    amount = models.IntegerField()  # positive for credit, negative for debit (coins)
    reason = models.CharField(max_length=64)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Subscription(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE)
    yoco_subscription_id = models.CharField(max_length=128)
    plan = models.CharField(max_length=64)
    active = models.BooleanField(default=True)
    started_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)


class MatchSession(models.Model):
    user_a = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='session_a')
    user_b = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='session_b')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_reason = models.CharField(max_length=64, null=True, blank=True)
