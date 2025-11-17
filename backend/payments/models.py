from django.db import models
import uuid


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)
    pack_id = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=8, default='USD')
    yoco_transaction_id = models.CharField(max_length=128, null=True, blank=True)
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def mark_paid(self, txid=None):
        self.paid = True
        if txid:
            self.yoco_transaction_id = txid
        self.save()


class WebhookEvent(models.Model):
    # store unique webhook event ids to ensure idempotent processing
    event_id = models.CharField(max_length=255, unique=True)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"WebhookEvent {self.event_id}"
