from django.db import models
from django.utils import timezone
import uuid


class MatchSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # optional foreign keys to verified users
    user_a = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='matches_as_a',
    )
    user_b = models.ForeignKey(
        'accounts.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='matches_as_b',
    )
    # channel identifiers used for signaling
    user_a_channel = models.CharField(max_length=255)
    user_b_channel = models.CharField(max_length=255)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_reason = models.CharField(max_length=128, null=True, blank=True)
    # video blur state: whether each side's video is unblurred (True) or blurred (False)
    # Default to True so remote video is visible unless the user opts to require payment
    user_a_unblurred = models.BooleanField(default=True)
    user_b_unblurred = models.BooleanField(default=True)
    # price (in coins) required to unblur the peer's video for the session
    unblur_price = models.IntegerField(default=5)

    def end(self, reason=None):
        self.ended_at = timezone.now()
        self.ended_reason = reason
        self.save()

    def mark_unblur(self, side: str):
        if side == 'a':
            self.user_a_unblurred = True
        elif side == 'b':
            self.user_b_unblurred = True
        self.save()
