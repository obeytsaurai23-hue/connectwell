from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from accounts.models import WalletTransaction


class WalletView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        txs = WalletTransaction.objects.filter(user=user).order_by('-created_at')[:50]
        data = {
            'coins': user.coins,
            'transactions': [
                {
                    'amount': t.amount,
                    'reason': t.reason,
                    'metadata': t.metadata,
                    'created_at': t.created_at.isoformat(),
                } for t in txs
            ]
        }
        return Response(data)
