# Benji — Backend

Service cloud (FastAPI) : proxy STT/résumé, auth, facturation. Détient les clés
API ; les clients (macOS, iOS, …) ne les voient jamais.

Contrat exposé : [`../docs/api-contract.md`](../docs/api-contract.md).
Cadrage : [`../docs/cloud-architecture.md`](../docs/cloud-architecture.md).

## État

| Endpoint | État |
|---|---|
| `POST /v1/summary` (SSE) | **réel** — streame Claude (alias `haiku`/`sonnet`/`opus`) |
| `WS /v1/transcribe` | **réel** — session STT (Deepgram) → events du contrat + métering. `STT_BACKEND=fake` pour le dev hors-ligne. Validation Deepgram live à faire. |
| `POST /v1/auth/login` · `/refresh` | stub (jetons factices) |
| `GET /v1/me` · `/v1/history` | stub |

### Variables d'environnement

| Var | Rôle |
|---|---|
| `ANTHROPIC_API_KEY` | résumé Claude (`/v1/summary`) |
| `DEEPGRAM_API_KEY` | transcription Deepgram (`/v1/transcribe`) |
| `STT_BACKEND` | `deepgram` (défaut) ou `fake` (dev/test, sans réseau) |

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

1. Valider Deepgram en conditions réelles (clé + audio FR) et affiner le mapping
   des events (`app/stt/deepgram.py`).
2. Brancher le client macOS sur `/v1/transcribe` (provider STT distant côté app).
3. Vraie auth (JWT) + plans, en remplacement des stubs (`app/auth.py`).
4. Facturation (Stripe/Paddle) + persistance du métering et de l'historique.
