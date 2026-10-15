# NeuralOps Auth Architecture Story

## Why Supabase?

NeuralOps needed a cloud identity provider that:
- Handles email/password, GitHub, Google OAuth out of the box
- Issues signed JWTs that any backend can verify independently
- Has a free tier suitable for early development
- Doesn't require us to build and maintain our own auth server

Supabase was chosen because it provides all of this plus edge functions for serverless logic. The key insight is that **Supabase only handles identity** — it never touches our data. Our Django backend verifies the JWT signature using Supabase's public JWKS endpoint, so Django always knows exactly who the user is without making any live call to Supabase after the initial login.

---

## Chapter 1 — The Device Registration Model (Abandoned)

### What it was

The original design was inspired by OAuth 2.0 Device Authorization Grant (RFC 8628) — the same pattern used by GitHub CLI, AWS CLI, Spotify on TV, and VS Code when signing into Copilot.

The flow:
1. Django generates a UUID `device_id` and stores it locally
2. Django calls a Supabase edge function (`device-request`) to register the device
3. Django opens the user's browser to `https://neuralops-nexus-auth.mapax.io/login?device_id=<uuid>`
4. User logs in on the portal
5. Portal calls Supabase edge function (`device-verify`) which marks the device as active
6. Django polls Supabase edge function (`device-poll`) every 3 seconds
7. When poll returns `active`, Django stores the user's identity locally
8. Session lasts 30 days

### What was built

- **neuralops-nexus-auth portal** — a React app deployed on Vercel at `https://neuralops-nexus-auth.mapax.io`
- **3 Supabase edge functions** — `device-request`, `device-verify`, `device-poll`
- **Django DeviceSession model** — stores device_id, status, user_id, email, session_expires_at
- **Celery task** — `poll_device_activation` polls Supabase every 3 seconds in background
- **2 Django endpoints** — `GET /api/v1/auth/init/` and `GET /api/v1/auth/status/`

### Why it was abandoned

The model made sense for a **purely local desktop app** with no web interface. But when we decided the React frontend would be hosted on Vercel (not served from the Django machine), the device registration concept broke down:

- The React app runs in the **user's browser**, not on the Django machine
- "Registering a device" means nothing when the UI is a public website
- Multiple users connecting from different machines made "one device session" meaningless
- The portal (`neuralops-nexus-auth.mapax.io`) became redundant — why have a separate login portal when the main app can handle login itself?

---

## Chapter 2 — The New Model (Current)

### The insight

NeuralOps is not a single-user local tool. It's a **self-hosted team workspace** — like Gitea, Outline, or Jellyfin. Multiple people connect to a shared Django server from their own browsers.

This changes everything:
- Authentication is **per user**, not per device
- The React app is hosted publicly (Vercel), Django runs on your machine/server
- Users connect their browser to whichever Django server they have access to

### The new flow

```
1. User opens neuralops.mapax.io (hosted on Vercel — public)
        ↓
2. Login with Supabase (email/password or GitHub OAuth)
   Supabase issues a JWT token
        ↓
3. Server selection screen — user picks a NeuralOps server from their saved list
   (servers are stored in localStorage — name + URL e.g. http://100.x.x.x:8003)
        ↓
4. React sends JWT to Django: GET /api/v1/auth/verify/
   Django verifies JWT signature using Supabase JWKS
   Django gets/creates local user record
   Returns 200 OK + user info
        ↓
5. React stores serverUrl in authStore
   All subsequent API calls go to that serverUrl with JWT in Authorization header
        ↓
6. /app — workspace opens
```

### Why this is better

| Concern | Old Model | New Model |
|---|---|---|
| Multi-user | One session per machine | One session per user |
| Auth complexity | 3 edge functions + Celery polling | One JWT verify endpoint |
| Portal dependency | Required separate portal site | Not needed |
| Security | Device trusted, not person | Person verified via Supabase JWT |
| Infrastructure | Redis + Celery required for auth | Redis + Celery only for AI tasks |

### Security model

- **Supabase** — proves who you are (identity layer)
- **Tailscale** — controls which machines can reach your Django server (network layer)
- **Django allowed users** — controls who is allowed on this specific server (authorization layer, coming soon)

The JWT is verified cryptographically by Django using Supabase's public key — no live call to Supabase needed after login. If someone intercepts the JWT, they still can't reach Django without being on your Tailscale network.

---

## Chapter 3 — What's Next

1. **Owner setup** — first user to connect becomes the server owner
2. **Invite system** — owner invites users by email, they get added to Django's allowed list
3. **Main app** — projects, channels, topics, chat
4. **AI agents** — agents participate in chat channels
5. **Knowledge base** — files and documents attached to projects

---

## Tech Decisions Log

| Decision | Reason |
|---|---|
| Supabase for identity | Free, battle-tested, JWT-based, no maintenance |
| React on Vercel | Static files, free hosting, always available, no dependency on Django machine being up |
| Django as backend | Already in the stack, Python ecosystem for AI, familiar |
| Celery + Redis | Background AI tasks, not auth (auth is now synchronous) |
| TanStack Start | Lovable's default, file-based routing, SSR capable |
| Tailscale for networking | Zero-config VPN, secure by default, works across networks |
| PostgreSQL | Production-grade, already in the stack |
| shadcn/ui | Consistent design system, accessible components |
