# Benji — Backend

Service cloud (FastAPI) : proxy STT/résumé, auth, facturation. Détient les clés
API ; les clients (macOS, iOS, …) ne les voient jamais.

Contrat exposé : [`../docs/api-contract.md`](../docs/api-contract.md).
Cadrage : [`../docs/cloud-architecture.md`](../docs/cloud-architecture.md).

## État

| Endpoint | État |
|---|---|
| `POST /v1/summary` (SSE) | **réel** — streame Claude (alias `haiku`/`sonnet`/`opus`) |
| `WS /v1/transcribe` | **squelette** — handshake + métering ok ; provider STT à brancher |
| `POST /v1/auth/login` · `/refresh` | stub (jetons factices) |
| `GET /v1/me` · `/v1/history` | stub |

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

1. Brancher un provider STT temps réel sur `/v1/transcribe` (Deepgram en tête)
   et émettre `segment_start`/`word`/`final_text`/`vad_status`.
2. Vraie auth (JWT) + plans, en remplacement des stubs (`app/auth.py`).
3. Facturation (Stripe/Paddle) + persistance du métering et de l'historique.
