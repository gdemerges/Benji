# Benji — Backend

Service cloud (FastAPI) : proxy STT/résumé, auth, facturation. Détient les clés
API ; les clients (macOS, iOS, …) ne les voient jamais.

Contrat exposé : [`../docs/api-contract.md`](../docs/api-contract.md).
Cadrage : [`../docs/cloud-architecture.md`](../docs/cloud-architecture.md).

## État

| Endpoint | État |
|---|---|
| `POST /v1/auth/register` · `login` · `refresh` | **réel** — comptes SQLite, mot de passe PBKDF2, jetons JWT (HS256). Refresh **rotatif** (jti persisté, révocation + détection de réutilisation) et endpoints **rate-limités** par IP |
| `GET /v1/me` | **réel** — plan, droits (`free`/`pro`), quota STT depuis le métering |
| `POST /v1/summary` (SSE) | **réel** — streame Claude (alias `haiku`/`sonnet`/`opus`), gated `cloud_summary` |
| `WS /v1/transcribe` | **réel** — STT (Deepgram/Grok) + auth + **quota** + métering. `STT_BACKEND=fake` hors-ligne. Validation live à faire. |
| `POST /v1/billing/webhook` | **réel** — signature HMAC Stripe vérifiée, bascule de plan. Checkout/Stripe live = TODO |
| `GET /v1/history` | stub |

### Variables d'environnement

| Var | Rôle |
|---|---|
| `ANTHROPIC_API_KEY` | résumé Claude (`/v1/summary`) |
| `STT_BACKEND` | `deepgram` (défaut), `grok`, ou `fake` (dev/test, sans réseau) |
| `DEEPGRAM_API_KEY` | si `STT_BACKEND=deepgram` |
| `XAI_API_KEY` | si `STT_BACKEND=grok` |
| `JWT_SECRET` | secret de signature JWT (**obligatoire en prod**) |
| `BENJI_DB_PATH` | chemin SQLite (défaut `benji.db`) |
| `STRIPE_WEBHOOK_SECRET` | vérification des webhooks Stripe (sinon non vérifié, dev only) |
| `AUTH_RATE_LIMIT_MAX` | tentatives d'auth autorisées par fenêtre (défaut `10`) |
| `AUTH_RATE_LIMIT_WINDOW` | durée de la fenêtre de rate-limit en secondes (défaut `60`) |

## Lancer

```bash
cd backend
uv sync
export ANTHROPIC_API_KEY=sk-ant-...
uv run uvicorn app.main:app --reload
# http://127.0.0.1:8000/healthz   ·   docs : /docs
```

## Tester

```bash
cd backend
uv run pytest
```

Les tests sont hermétiques (Claude est mocké, aucun appel réseau).

## Prochaines étapes

1. Valider STT (Deepgram/Grok) en conditions réelles + flux temps réel app↔backend.
2. Intégration Stripe live : création de Checkout Sessions, portail client,
   produits/prix (le webhook + la bascule de plan sont déjà en place).
3. Persistance de l'historique (`/v1/history`) + sync multi-appareils.
4. Migration SQLite → Postgres pour le multi-instance (interface `Database` isolée).
