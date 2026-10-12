# Real WhatsApp: step-by-step setup (Windows)

This connects Sofi to **real WhatsApp** through Meta's **WhatsApp Cloud API** (spec [016](specs/016-whatsapp/spec.md)). At the end you send "Hola" from your own phone and Sofi answers there, with real buttons and lists. The conversation also shows up in the recruiter dashboard with a **WhatsApp** badge.

It is free: Meta gives every developer app a **test phone number**, which can message up to **5 phone numbers you verify**. Time needed: about 30 minutes the first time.

**How it fits together**

```
your phone ──WhatsApp──▶ Meta ──webhook (HTTPS)──▶ tunnel ──▶ your PC: API on :8000
your phone ◀──WhatsApp── Meta ◀──Graph API (HTTPS)───────────── your PC: API on :8000
```

Meta can only call a public HTTPS address, so a **tunnel** (Cloudflare Tunnel or ngrok) gives your local API one for the session.

---

## What you will collect

Write these down as you go. They end up in `.env` (step 7).

| What | Where it comes from | `.env` variable |
|---|---|---|
| Access token | Meta, step 3 | `WHATSAPP_TOKEN` |
| Phone number ID (of the test number) | Meta, step 3 | `WHATSAPP_PHONE_NUMBER_ID` |
| App secret | Meta, step 5 | `WHATSAPP_APP_SECRET` |
| Verify token | **you invent it**, step 6 | `WHATSAPP_VERIFY_TOKEN` |

---

## 1. Create a Meta developer account

1. Go to <https://developers.facebook.com/> and log in with your Facebook account.
2. If it is your first time, click **Get started** and follow the prompts (accept the terms, verify your phone or email). You end up on **My Apps**.

## 2. Create the app (type Business) and add WhatsApp

1. On **My Apps**, click **Create app**.
2. Give it a name, e.g. `Sazon Screening Dev`, and your contact email.
3. Meta asks for a **use case** or an **app type** (the wizard changes from time to time):
   - if you see use cases, pick **Other**, then app type **Business**;
   - if you see **Connect with customers through WhatsApp**, picking that is also fine (it adds WhatsApp for you).
4. If it asks for a **Business portfolio** (Business Manager account), choose yours or let it create one.
5. Click **Create app** and confirm your Facebook password if asked.
6. In the app dashboard, find **WhatsApp** in the product list and click **Set up**. (Skip if it is already in the left menu.)

## 3. Get the test number, its Phone number ID and a token

1. In the left menu: **WhatsApp > API Setup** (in some versions: **WhatsApp > Getting started**).
2. Under **Access token**, click **Generate access token** and copy it → `WHATSAPP_TOKEN`.
   **It expires after about 24 hours** (see "Permanent token" at the end for a long-lived one).
3. Under **Send and receive messages > From**, Meta has already selected a **test number** (something like `+1 555 …`). Right under it you see **Phone number ID**: a long number like `106540352242922`. Copy it → `WHATSAPP_PHONE_NUMBER_ID`.
   Careful: it is the *ID*, not the phone number itself.

## 4. Add and verify your own phone as a recipient

The test number only talks to numbers you have verified (max 5).

1. Same page, under **To**, open the dropdown and click **Manage phone number list** (or **Add phone number**).
2. Enter your mobile number with country code, e.g. `+34 600 000 000`.
3. WhatsApp sends you a **verification code**; type it in. Your number now appears in the **To** list.
4. Optional check: click **Send message**. You should receive Meta's "Hello World" message on WhatsApp. This proves the token, the number ID and your recipient are fine.

## 5. Copy the app secret

1. Left menu: **App settings > Basic**.
2. Next to **App secret**, click **Show**, confirm your password, copy it → `WHATSAPP_APP_SECRET`.

The API uses it to check that every webhook call really comes from Meta (header `X-Hub-Signature-256`). It is **not** the access token.

## 6. Choose a verify token

Invent any string without spaces, e.g. `sazon-verify-7f3k2`. You put it in `.env` **and** paste the same string in Meta in step 10. It is only used once, when Meta checks your webhook URL → `WHATSAPP_VERIFY_TOKEN`.

## 7. Put everything in `.env`

In the repo root, copy `.env.example` to `.env` if you have not yet, and add (with your values):

```dotenv
WHATSAPP_ENABLED=true
WHATSAPP_TOKEN=EAAG...your-long-token...
WHATSAPP_PHONE_NUMBER_ID=106540352242922
WHATSAPP_VERIFY_TOKEN=sazon-verify-7f3k2
WHATSAPP_APP_SECRET=0123456789abcdef0123456789abcdef
WHATSAPP_API_VERSION=v25.0
```

- With `WHATSAPP_ENABLED=true`, all four secrets are required: if one is missing, the API refuses to start and names it.
- `LLM_MODE=fake` (no Claude key) works too: Sofi then answers with the offline rules agent. For the real conversation quality set `LLM_MODE=anthropic` and `ANTHROPIC_API_KEY`.
- `.env` is gitignored. Never commit it.

## 8. Start the API

This feature adds database columns. The project creates tables at startup without migrations, so **delete the old local database once** before starting:

```powershell
cd "D:\FDE Orbio\backend"
Remove-Item .\sazon.db* -ErrorAction SilentlyContinue
uv run --env-file ../.env uvicorn sazon_screening.api.app:create_app --factory --port 8000
```

Leave this terminal open. You should see `Application startup complete` and one warning that the follow-up template `hello_world` is a placeholder (expected, see "Limitations").

Optional, in a second terminal, the dashboard: `cd "D:\FDE Orbio\frontend"; npm run dev` → <http://localhost:5173>.

## 9. Open a tunnel

Pick **one** of these. Open a **new** PowerShell terminal.

**Option A: Cloudflare Tunnel (no account needed)**

```powershell
winget install --id Cloudflare.cloudflared
# close and reopen PowerShell so the command is found, then:
cloudflared tunnel --url http://localhost:8000
```

It prints a line like `https://random-words-1234.trycloudflare.com`. That is your public URL.

**Option B: ngrok (free account needed)**

```powershell
winget install --id ngrok.ngrok
# sign up at https://dashboard.ngrok.com and copy your authtoken, then once:
ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>
ngrok http 8000
```

Use the `https://….ngrok-free.app` address shown under **Forwarding**.

Check it works: open `https://<your-tunnel>/api/health` in a browser. You should see `{"status":"ok",...}`.

Keep the tunnel terminal open. **A quick tunnel gets a new URL every time you restart it**: then repeat step 10 with the new URL.

## 10. Register the webhook in Meta

1. In the app: **WhatsApp > Configuration**.
2. Under **Webhook**, click **Edit**:
   - **Callback URL**: `https://<your-tunnel>/api/whatsapp/webhook`
     (e.g. `https://random-words-1234.trycloudflare.com/api/whatsapp/webhook`)
   - **Verify token**: the exact string from step 6.
3. Click **Verify and save**. Meta calls your API; it must answer with the challenge. In the API terminal you see `GET /api/whatsapp/webhook?... 200`.
4. Still under **Webhook**, next to **Webhook fields**, click **Manage** and **Subscribe** to the **`messages`** field. Without this, nothing arrives.

## 11. Say hello

From your phone (the number you verified in step 4), open WhatsApp and send **"Hola"** to the test number (it is in the chat where Meta's "Hello World" arrived).

Within a few seconds:
- your message gets blue ticks and "typing…" appears;
- Sofi greets you with two buttons, **Sí** / **No**. Tap one and keep going: questions with up to 3 options come as buttons, longer ones as a list ("Ver opciones");
- a voice note gets "I can't listen to audio yet, could you write it?";
- in the dashboard (<http://localhost:5173>, "Soy recruiter") your conversation has a green **WhatsApp** badge, and the **Canal** filter shows only WhatsApp candidates.

In the API terminal, log lines identify you only by a hash like `wa:3f9a1c2b7d`, never by your number.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Meta: "The callback URL or verify token couldn't be validated"; API log shows **403** on `GET /api/whatsapp/webhook` | The verify token in Meta and `WHATSAPP_VERIFY_TOKEN` differ (spaces, a typo) | Copy the same string in both; restart the API if you changed `.env`. |
| Same Meta error, API log shows **404** | The API runs without WhatsApp: `WHATSAPP_ENABLED` is not `true`, or the API was started without `--env-file ../.env` | Fix `.env` and restart with the command from step 8. |
| Same Meta error, nothing in the API log | The tunnel is down or its URL changed | Restart the tunnel, check `https://<tunnel>/api/health`, paste the new URL in step 10. |
| API log shows **401** on `POST /api/whatsapp/webhook` | Wrong `WHATSAPP_APP_SECRET` (it must be the **app secret** from App settings > Basic, not the token) | Fix it and restart the API. |
| Webhook verified, but nothing happens when you write | Not subscribed to the **`messages`** field; or you wrote from a number other than the verified one; or the tunnel URL changed | Step 10.4; write from the verified phone; re-check the callback URL. |
| Messages arrive (log shows `POST ... 200`) but Sofi never answers; log shows `send failed ... HTTP 401: 190 ...` | The **access token expired** (temporary tokens last about 24 h) | Generate a new one (step 3.2), update `WHATSAPP_TOKEN`, restart the API. For long sessions, use a permanent token (below). |
| Log shows `send failed ... 131030 Recipient phone number not in allowed list` | The number Sofi replies to is not in the test number's recipient list | Add it in step 4. For a Mexican number, add it exactly as WhatsApp reports it (Mexico numbers may appear as `521…`). |
| Log shows `131047` or "re-engagement message" | Free text sent more than 24 h after the candidate's last message: WhatsApp only allows templates there | Expected for late reminders: they go as the configured template (see Limitations). |
| API refuses to start: `WHATSAPP_ENABLED=true needs WHATSAPP_...` | A secret is missing in `.env` | Add it. |
| Errors like `no such column: conversations.channel` in the API log | Old `sazon.db` from before this feature (tables are not migrated) | Stop the API, delete `backend/sazon.db*`, start again. |

---

## Permanent token (optional)

The temporary token expires after about a day. For longer demos: **Meta Business Suite > Business settings > Users > System users > Add** (role Admin) → **Add assets**: your app, full control → **Generate new token**: select your app, permissions `whatsapp_business_messaging` and `whatsapp_business_management`, expiration **Never**. Put it in `WHATSAPP_TOKEN`.

## Limitations (dev setup)

- **Follow-ups after 24 h use `hello_world`.** WhatsApp only allows approved **templates** more than 24 h after the candidate's last message. Until Grupo Sazón has its own approved reminder template, `config/whatsapp.yaml` points to Meta's `hello_world` (English, generic), marked `placeholder: true`, and every such send logs a warning. To fix: create and get approved a template in **WhatsApp Manager > Message templates** (e.g. Spanish, category Utility), then set its `name` and `language` (e.g. `es_ES`) in `config/whatsapp.yaml` and `placeholder: false`.
  To see reminders quickly in a demo: `REENGAGEMENT_TIME_SCALE=60` in `.env` (one hour of schedule per minute; the 24 h window becomes 24 minutes).
- **Test number:** only up to 5 verified recipients, and Meta shows it as a test business. Production needs a real number on a verified business.
- **Opt-out is final on that number.** A candidate who opts out ("dame de baja") is put on a do-not-contact list; later messages from that number are ignored.
- **One process.** Webhook messages are processed in the API process right after Meta gets its 200. If the API stops at that moment, that one message gets no answer (the candidate can write again). Production would use a queue.
