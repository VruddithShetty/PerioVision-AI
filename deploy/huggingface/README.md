---
title: PerioVision API
emoji: 🦷
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

PerioVision AI backend (demo mode: in-memory database, signed models, synthetic demo patients).
The web app is deployed separately on Vercel and reaches this API through a `/api` rewrite.
Set `DEMO_EMAIL` and `DEMO_PASSWORD` as Space secrets to choose the demo login.
