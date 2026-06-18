# Benji — Architecture Cloud & Abonnement

> Document de cadrage. État : **proposition**, pas encore implémenté.
> Objectif : faire évoluer Benji d'une app macOS 100 % locale vers un produit
> multi-plateforme (macOS + mobile) avec une offre d'abonnement, **sans casser
> le mode local privé** qui reste le défaut sur desktop.

## 1. Vision

Aujourd'hui Benji **est** l'app macOS : tout le calcul (Whisper mlx, résumé
mlx-lm, diarisation) tourne sur le poste. Demain, on déplace le calcul lourd
**optionnel** côté serveur. Le centre de gravité devient le **backend** ; chaque
app (macOS, iOS, Android, web plus tard) n'est qu'un client.

```
        ┌── client macOS (PyQt6, existant)
Backend ─┼── client iOS (natif, SwiftUI)
(STT + IA + auth + billing)
        ├── client Android (natif, Compose)
        └── client web (plus tard)
```

Deux segments cohérents :

- **Desktop** : local par défaut (privé, gratuit), cloud en option (premium).
- **Mobile** : cloud par nature (pas de mlx) → c'est la cible d'abonnement.

## 2. Principe directeur : abstraction de providers

Le cœur technique est de rendre **interchangeables** les moteurs locaux et
cloud, derrière une interface stable. Deux abstractions symétriques dans
`benji/`.

### 2.1 `STTProvider`

```
class STTProvider(Protocol):
    def start(self) -> None: ...
    def feed(self, audio_chunk: bytes) -> None: ...        # mic → STT
    def events(self) -> Iterator[dict]: ...                # → display_queue
    def stop(self) -> None: ...
```

- `LocalSTTProvider` — l'actuel Whisper mlx + logique LocalAgreement-2
  (`transcriber.py`). **Défaut sur desktop.**
- `CloudSTTProvider` — streame l'audio vers le backend (WebSocket), reçoit les
  events `partial` / `final` / `speaker` et les pousse sur `transcribe_queue →
  display_queue`. **Court-circuite** LocalAgreement-2 (le cloud fournit ses
  propres partiels).

⚠️ La diarisation (`diarization.py`) : vérifier si le provider cloud la fait
côté serveur (Deepgram / AssemblyAI oui). Sinon, garder la diarisation locale ou
l'accepter dégradée en mode cloud.

### 2.2 `SummaryProvider`

```
class SummaryProvider(Protocol):
    def summarize(self, entries: list[dict],
                  on_token: Callable[[str], None] | None) -> str | None: ...
```

- `LocalSummaryProvider` — l'actuel mlx-lm `Qwen2.5-1.5B-4bit`
  (`summarizer.py`). **Défaut sur desktop.**
- `CloudSummaryProvider` — appelle le backend, qui relaie vers **Claude**
  (Anthropic). Streaming des tokens conservé (compatible `append_chunk` de
  l'UI).

Le `summary_worker.py` ne connaît que l'interface ; le choix du provider vient
de la config / des réglages.

### 2.3 Sélection du provider

Exposée à l'utilisateur (réglages) et stockée en config :

- Transcription : **Locale (privée)** / **Cloud (plus rapide, Mac peu puissants)**
- Résumés / IA : **Locale (privée)** / **Cloud (qualité premium)**

Local reste le défaut absolu sur desktop.

## 3. Backend

Le backend est le **produit**. Responsabilités :

1. **Auth** — comptes utilisateurs, sessions/tokens.
2. **Billing** — abonnements (Stripe / Paddle ; RevenueCat si Mac/App Store).
3. **Proxy providers** — détient les **clés API** (Anthropic, STT) ; jamais sur
   le client. Vérifie l'abonnement, relaie, et **compte la conso** (la STT se
   facture à la minute → métering obligatoire).
4. **Contrat d'API** — voir §4.

> ⚠️ **Ne jamais embarquer une clé API dans une app cliente** — elle serait
> extractible et exposerait toute la facturation. Toute requête cloud passe par
> le backend.

Stack suggérée : Python (FastAPI) pour réutiliser le savoir-faire et la logique
de prompts existante. WebSocket natif pour le streaming audio.

## 4. Contrat d'API (à figer en premier)

C'est **l'étape structurante** : une fois le contrat stable, n'importe quel
client s'y branche. La spécification normative complète vit dans un document
dédié : **[`api-contract.md`](./api-contract.md)** (v1).

Résumé : WebSocket `/v1/transcribe` (audio binaire montant + events
`segment_start` / `word` / `final_text` / `vad_status` descendants, alignés sur
le `display_queue` interne) ; REST `/v1/auth/*`, `/v1/me`, `/v1/history` ; SSE
`/v1/summary`. Auth Bearer (JWT + refresh), métering des secondes STT côté
serveur.

## 5. Providers cloud envisagés

### STT (temps réel — Claude ne fait PAS de STT)

| Service | Streaming live | FR | Note |
|---|---|---|---|
| **Deepgram** (Nova-3) | ✅ basse latence | bon | candidat n°1 pour le live |
| AssemblyAI | ✅ | bon | bonne qualité |
| OpenAI Realtime / `gpt-4o-transcribe` | ✅ | très bon | un peu plus cher |
| Groq (Whisper v3 turbo) | ⚠️ batch rapide | bon | pas de vrai streaming |

Contrainte à trancher : **hébergement EU / RGPD** (c'est de l'audio personnel).

### Résumé / IA (Claude)

| Modèle | $/1M in / out | ~Coût par résumé* |
|---|---|---|
| **Haiku 4.5** (`claude-haiku-4-5`) | $1 / $5 | ~0,008 $ |
| **Sonnet 4.6** (`claude-sonnet-4-6`) | $3 / $15 | ~0,022 $ |
| Opus 4.8 (`claude-opus-4-8`) | $5 / $25 | ~0,038 $ |

*Base ~5 000 tokens in / ~500 out. Pour du résumé, **Haiku 4.5 ou Sonnet 4.6**
sont le bon compromis.

## 6. Modèle de coût (à intégrer au prix d'abonnement)

- **Résumés** : négligeable (< 1 ct/résumé). N'impacte pas le pricing.
- **STT cloud** : **~0,20–0,36 $/heure d'audio** (à confirmer auprès du
  fournisseur). Un usage de 2 h/jour ≈ **10–20 $/mois de coût**. C'est le poste
  dimensionnant — le prix d'abonnement et/ou des quotas doivent le couvrir.

> Les chiffres STT sont des ordres de grandeur à **vérifier** sur les tarifs
> courants avant tout engagement.

## 7. Confidentialité

L'argument actuel = « tout reste sur le Mac ». Le cloud change ce contrat,
graduellement :

- **Résumés cloud** : seul le *texte* part.
- **STT cloud** : l'**audio brut** part en continu → saut le plus sensible.

Règles :

- Cloud **opt-in explicite**, jamais par défaut.
- Indiquer clairement *ce qui sort* du poste pour chaque mode.
- Tier gratuit desktop **strictement local**.
- Mobile = cloud assumé (segment distinct).

## 8. Mobile

- Le téléphone devient un **client mince** : micro + stream + affichage.
- Natif recommandé : **SwiftUI (iOS)**, **Kotlin/Compose (Android)** — pas de
  moteur à embarquer.
- 100 % local quasi impossible sur mobile → **mobile = tier cloud**.
- Réutilisable : **tout le backend**. Non réutilisable : UI PyQt6 + pipeline mlx
  (le client mobile est un nouveau projet, mais léger).

## 9. Feuille de route (incrémentale, chaque étape utilisable seule)

1. **Abstraction de providers** (STT + résumé) dans le code actuel.
   - Livrable immédiat : `CloudSummaryProvider` Claude activable avec une clé en
     `config.py`, pour **comparer la qualité** local vs Claude *sans backend*.
2. **Backend minimal** : auth + proxy providers + contrat WebSocket/REST.
3. **Brancher le client macOS** existant sur le backend (preuve du contrat).
4. **Billing** (Stripe/Paddle) + quotas/métering.
5. **Client iOS** une fois le contrat éprouvé.

## 10. Décisions ouvertes

- Fournisseur STT + hébergement EU/RGPD.
- ~~Modèle Claude par défaut pour les résumés~~ → **décidé : `claude-haiku-4-5`**
  (rapide, peu coûteux, suffisant pour du résumé). Configurable via `LLMConfig`.
- Stratégie de pricing (forfait vs quotas d'heures STT).
- Stack backend (FastAPI proposé).
- Diarisation : locale conservée ou déléguée au provider cloud.
