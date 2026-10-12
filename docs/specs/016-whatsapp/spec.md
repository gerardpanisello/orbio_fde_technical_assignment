# Spec 016 — Real WhatsApp channel (Meta WhatsApp Cloud API) (compact)

**Status:** Approved (Gerard, 2026-10-13: "lo que consideres mejor" → Meta Cloud API with the free test number)
**Related:** ADR 0005 (channel = adapter), spec 001 (this is messaging), spec 008 (24 h window, templates), `docs/design/deployment.md`, `docs/design/ats-integration.md`.

## 1. Why
The brief says "this is messaging, not email". The web chat simulates WhatsApp; a real WhatsApp channel proves the agent works where Grupo Sazón's candidates actually are, and makes the live demo land ("text Sofi from your own phone").

## 2. Decision
Meta **WhatsApp Cloud API** (test phone number, up to 5 verified recipients, free) over Twilio Sandbox: native **reply buttons** (≤ 3) and **list messages** (≤ 10 rows) map 1:1 to our quick replies; no third party in the data path. Locally the webhook is exposed with a tunnel (ngrok / Cloudflare Tunnel). Twilio is the documented fallback.

## 3. Requirements
- FR-1 **Webhook** `GET /api/whatsapp/webhook` (Meta verification: `hub.mode`, `hub.verify_token`, `hub.challenge`) and `POST /api/whatsapp/webhook` (messages). Verify `X-Hub-Signature-256` with the app secret (HMAC-SHA256); reject invalid → 401. Respond 200 fast; process the message in the background (Meta retries on slow/failed responses).
- FR-2 **Idempotency:** Meta may deliver the same message twice → dedupe by WhatsApp message id (stored).
- FR-3 **Conversation by phone:** a candidate's phone number (wa_id) maps to their open conversation; a new number starts one (Sofi's greeting). `country_hint` from the prefix (+34 → ES, +52 → MX). Store the phone **hashed** for lookup + encrypted-at-rest is out of scope: store it in its own column, never in the transcript/record; opted-out numbers go to a do-not-contact set (spec 001 FR-7/FR-11) and are never messaged again.
- FR-4 **Inbound types:** text; interactive `button_reply` / `list_reply` → sent to the pipeline as the option label; audio/image/sticker → the pipeline's existing voice-note/media path ("¿me lo puedes escribir?"); others ignored with a log line.
- FR-5 **Outbound:** reply text; quick replies → reply buttons if ≤ 3 (titles ≤ 20 chars, truncated sensibly) else a list message (≤ 10 rows, titles ≤ 24 chars); links preview off. Mark the inbound message as read; show typing indicator if the API supports it. Send failures are retried (backoff) and logged with conversation id; never crash the turn.
- FR-6 **Channel on the conversation:** `conversations.channel` (`web` | `whatsapp`), visible in the dashboard (badge) and in analytics by channel. Re-engagement follow-ups (spec 008) for WhatsApp conversations are **sent through WhatsApp**; outside the 24 h window they must be a template message → use the pre-approved `hello_world` template in dev only if no custom template is configured, and log that a real approved template is needed (documented limitation).
- FR-7 **Config/env:** `WHATSAPP_ENABLED`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_API_VERSION`. Disabled by default; the app runs without them.
- FR-8 **Setup guide** `docs/whatsapp-setup.md`: step-by-step for Gerard (Meta for Developers app, test number, add recipient phone, temporary/permanent token, webhook URL via tunnel, subscribe to `messages`), plus how to run the tunnel on Windows and a troubleshooting section.

## 4. Acceptance criteria (all with a fake Graph API client, no network)
- AC-1 Webhook verification returns the challenge for the right token, 403 otherwise.
- AC-2 Invalid signature → 401; valid signature → 200 and the message is processed once even if delivered twice.
- AC-3 First message from a new number → conversation created with `channel=whatsapp`, `country_hint` from prefix, greeting sent with 2 reply buttons (Sí/No).
- AC-4 A button reply advances the conversation exactly like typing the label.
- AC-5 > 3 options → list message; ≤ 3 → buttons; titles truncated within limits.
- AC-6 Audio message → media reply, state unchanged.
- AC-7 Opt-out → number added to do-not-contact; later follow-ups/messages to it are suppressed; phone never appears in record/transcript/export.
- AC-8 Re-engagement step for a WhatsApp conversation is sent via the WhatsApp client (template when outside 24 h).
- AC-9 Graph API failure → logged, retried, turn not lost; dashboard shows the channel.

## 5. Tasks
- [x] T1 Settings + Graph API client (httpx, typed payload builders for text/buttons/list/template/read) + fake client for tests.
- [x] T2 DB: `conversations.channel`, phone column (lookup), processed WhatsApp message ids, do-not-contact; service: find-or-create by phone; outbound delivery hook used by turns and re-engagement.
- [x] T3 Webhook routes (verify, signature, background processing, dedupe) + inbound mapping (FR-4).
- [x] T4 Analytics/list: channel field + filter; frontend: channel badge + filter (small; coordinate — the voice agent also touches frontend, keep changes to `src/lib/status.ts`-like shared files minimal).
- [ ] T5 `docs/whatsapp-setup.md`, README/ROADMAP; live test with Gerard's credentials when available.
