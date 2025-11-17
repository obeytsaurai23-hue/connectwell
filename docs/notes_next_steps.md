# Next Steps (implementation roadmap)

1. Implement backend skeleton
   - Django project with apps: accounts, payments, chat
   - Auth endpoints: send_pin, verify_pin, continue_anonymous
   - Wallet endpoints: wallet, coins/purchase, coins/spend
   - Yoco webhook handler
   - Minimal unit tests for PIN flow and wallet

2. Implement Channels consumer
   - WS connect auth, enqueue, match, signaling
   - Redis-based matchmaking queue and simple FIFO

3. Frontend prototype
   - Hook up login modal to auth endpoints
   - Basic WebRTC signaling through WS and peer connection

4. Safety pipeline
   - Snapshot capture and NSFW model pipeline (async worker)
   - Initial UI: blurred video until cleared or user unblurs

5. Ads integration
   - Use an ad provider that serves short rewarded video ads; control display after 3 Nexts

6. Monitoring & infra
   - Add prometheus/alerting, logging (structured)
   - Prepare production deployment guides (k8s/VMs, coturn sizing)

