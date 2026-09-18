# Benji — Backend

> ## 🔓 Dégelé partiellement (2026-09-18)
>
> Suspendu le 2026-08-19 (voir historique git pour le détail de cette
> décision), repris pour porter l'offre payante cross-OS du modèle freemium
> (achat unique local sur Mac reste le défaut ; Windows/Linux passent par un
> moteur local plus léger **ou** ce backend, cf. `CLAUDE.md` racine et
> `benji/stt/CLAUDE.md`). Le service tourne à nouveau en développement/test —
> auth, quotas, métering, Checkout/webhook Stripe (déjà codés, cf. tableau
> ci-dessous) sont utilisables avec des clés **test/sandbox**.
>
> **Toujours hors scope**, décision de Guillaume à reprendre explicitement
> avant d'y toucher :
> - ❌ passage Stripe en **live** (clés de production, compte vérifié) — reste
>   une action sur le dashboard Stripe, pas un chantier de code
> - ❌ persistance `/v1/history` (sync multi-appareils)
> - ❌ migration SQLite → Postgres
> - ❌ clients mobiles

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
| `POST /v1/billing/checkout` · `portal` · `webhook` | **réel** — Checkout Session, portail client, signature HMAC vérifiée, bascule de plan. Sans clé configurée → repli stub (dev/CI). Passage en **live** = clés de production sur le dashboard Stripe, pas du code manquant |
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
2. Passage Stripe en live : produits/prix + clés de production sur le dashboard
   Stripe (le code — Checkout, portail, webhook, bascule de plan — est déjà en
   place, cf. tableau ci-dessus). **Reste gelé**, décision explicite requise.
3. Persistance de l'historique (`/v1/history`) + sync multi-appareils. **Reste gelé.**
4. Migration SQLite → Postgres pour le multi-instance (interface `Database` isolée).
   **Reste gelé.**

**Condition de reprise des points gelés** : des utilisateurs payants existent et
demandent la synchronisation entre appareils.
