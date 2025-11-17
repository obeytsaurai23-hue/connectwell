from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
import uuid


class User(AbstractUser):
    # Extend Django's AbstractUser to add coins and verification flags
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Keep email optional for the skeleton; AbstractUser provides username fields
    email = models.EmailField(unique=True, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    coins = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    # Auto-unblur preferences: enabled by default; user may toggle off
    auto_unblur = models.BooleanField(default=True)
    # If True, the system will attempt to auto-purchase coins (create an order) when needed
    auto_buy_coins = models.BooleanField(default=True)
    # Which pack to auto-buy when coins run out
    auto_buy_pack_id = models.CharField(max_length=64, default='starter')
    # If True, this user requires viewers to pay to unblur their video by default
    charge_viewers = models.BooleanField(default=False)
    # Profile fields used for premium filtering
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer_not', 'Prefer not to say'),
    ]
    gender = models.CharField(max_length=32, choices=GENDER_CHOICES, null=True, blank=True)
    # birth_year stored for simple age calculation; nullable for existing users
    birth_year = models.IntegerField(null=True, blank=True)
    # simple location string (city/country). Frontend will attempt to set this via Geolocation.
    location = models.CharField(max_length=256, null=True, blank=True)
    # If set, the datetime when premium access expires; null means no expiry (not premium)
    premium_expires_at = models.DateTimeField(null=True, blank=True)


class PinCode(models.Model):
    email = models.EmailField()
    code_hash = models.CharField(max_length=256)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)

    def is_expired(self):
        return timezone.now() > self.expires_at


class WalletTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.IntegerField()
    reason = models.CharField(max_length=128)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
