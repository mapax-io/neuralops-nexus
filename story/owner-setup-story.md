# NeuralOps — Owner Setup Story

## The Problem

When someone installs NeuralOps on their own server, someone needs to be the owner.
The owner controls who can access the server, manages the workspace, and is the
first user to connect.

The question was: how do you securely establish who the owner is?

---

## What We Decided

A Django management command: `python manage.py create_owner`

The person who has SSH/terminal access to the server IS the rightful owner.
No API endpoint needed. No IP whitelist needed. If you can run commands on the
server, you own it.

---

## The Flow

```
1. Admin SSHes into the server
2. Runs: python manage.py create_owner
3. Command asks: do you have a NeuralOps account?
      → No  → go to https://neuralops-nexus.mapax.io/signup first
      → Yes → enter email + password
4. Command signs into Supabase with those credentials
5. Supabase returns a JWT token
6. Command verifies the JWT (same logic as auth/verify endpoint)
7. Creates Company (is_personal=True) + User + CompanyAccess(role=owner)
8. Done — owner can now log in via the React app
```

---

## Why Supabase credentials?

We require the person to sign in with their actual Supabase account because:
- Anyone with SSH access could otherwise claim ownership with just an email
- Supabase verifies the password — we don't store or see it
- The JWT proves they actually own that Supabase account
- Same JWT verification used everywhere else in the system

---

## The Company Model

For personal/self-hosted edition:
- One Company per server
- `is_personal = True`
- `owner` FK → the User who ran create_owner
- CompanyAccess entry with `role = owner`

For future SaaS/Enterprise:
- Many companies, same model
- `is_personal = False`
- Each company has its own owner and members

---

## What auth/verify now returns

When the React app connects to a server, `GET /api/v1/auth/verify/` now returns:

```json
{
  "ok": true,
  "email": "user@example.com",
  "user_id": "uuid",
  "is_new_user": false,
  "company_exists": true,
  "is_owner": true,
  "role": "owner",
  "company_name": "Noaman's Workspace"
}
```

The React app uses this to:
- `company_exists = false` → show "server not set up yet" message
- `is_owner = true` → show owner controls (invite users, settings)
- `role` → control what the user can see and do
- `403` → "You are not a member of this server. Ask the owner to invite you."

---

## Files Changed

| File | Change |
|---|---|
| `nucleus/models/governance.py` | Added `owner` FK to Company |
| `authn/services.py` | Updated `auth_verify` to return company + role info |
| `authn/schema.py` | Updated `AuthVerifyResponse` with company fields |
| `authn/management/commands/create_owner.py` | New management command |
| `nucleus/migrations/` | Migration for owner FK |
