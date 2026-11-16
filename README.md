# VoiceForge

A self-hosted voice cloning studio: a FastAPI backend wrapping Coqui's
open-source XTTS v2 model, plus a single-page frontend for recording or
uploading a reference sample and generating speech in that voice.

```
voiceforge/
├── backend/
│   ├── main.py            FastAPI app and REST endpoints
│   ├── voice_engine.py     Wraps the XTTS v2 model (lazy-loaded)
│   ├── requirements.txt
│   └── storage/            Created automatically: reference samples + outputs
├── frontend/
│   └── index.html          Open this in a browser once the backend is running
└── README.md
```

## 1. Before you start: consent

This tool can reproduce anyone's voice from a short sample. Only clone a
voice you own, or one you have clear, verifiable permission to use. Using
someone's voice without consent — to impersonate them, deceive someone, or
commit fraud — is illegal in most places and will get you banned from every
reputable hosted alternative too. If you're deploying this for other people
to use, build in a consent step (e.g. require the speaker to read a
randomized consent phrase that you check against the sample) before you let
it go further than your own machine.

## 2. Requirements

- Python 3.10 or 3.11 (XTTS's dependencies are not yet reliable on 3.12+)
- ~4 GB of free disk space for model weights
- A GPU is optional. CPU works but a 10-second clip can take 30-90+ seconds
  to generate. An NVIDIA GPU with CUDA will be dramatically faster.

## 3. Set up the backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Run it:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The first time you call `/api/synthesize`, Coqui will download the XTTS v2
weights (~1.8 GB) automatically and cache them under `~/.local/share/tts`.
That first request will be slow; after that the model stays loaded in
memory for the life of the process.

You'll also be asked to accept Coqui's model license (Coqui Public Model
License) on first run — this happens once, interactively, in the terminal.

Check it's alive:

```bash
curl http://localhost:8000/api/health
```

## 4. Open the frontend

### Just using it yourself, on this machine

`frontend/index.html` is a static file with no build step. With the backend
running on `localhost:8000`, just open the file directly in a browser
(double-click it, or `open frontend/index.html` / `xdg-open frontend/index.html`).
The frontend auto-detects the backend at `http://localhost:8000` — no config
needed.

### Letting other computers on your network use the microphone

Browsers only allow microphone access (`getUserMedia`) on a **secure
origin** — `https://`, or `http://localhost` on the exact machine running
the page. Someone opening your frontend from another PC over plain
`http://192.168.x.x` will have the mic silently blocked. To fix that, serve
both the frontend and backend over HTTPS with a local certificate:

```bash
# 1. From the project root, install the one extra dependency and generate a
#    cert covering localhost + your LAN IP:
pip install cryptography
python certs/make_certs.py

# 2. Start the backend with TLS (the command to copy is printed by step 1):
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --ssl-keyfile ../certs/dev.key --ssl-certfile ../certs/dev.crt

# 3. In another terminal, serve the frontend with TLS too:
cd frontend
python serve_https.py
```

Then, from any device on the same Wi-Fi/LAN, open:

```
https://<this-machine's-LAN-IP>:5173
```

The frontend picks up the backend automatically at the same hostname on
port 8000. Every browser will show a "this certificate isn't trusted"
warning the first time, since it's self-signed — that's expected; click
through ("Advanced" → "Proceed") to continue. This is fine for a home
network; don't ship a self-signed cert to the general public.

If the backend is on a different host/port than the frontend, override it
once per browser by opening `https://<frontend-host>:5173/?api=https://<backend-host>:8000`
— it's remembered after that.

### Going public (real domain, trusted certificate)

For a site anyone on the internet can open, put both services behind a
reverse proxy that handles TLS for you — e.g. [Caddy](https://caddyserver.com/)
gets you automatic, trusted HTTPS certificates (via Let's Encrypt) with a
3-line Caddyfile:

```
your-domain.com {
    reverse_proxy /api/* localhost:8000
    reverse_proxy /* localhost:5173
}
```

With a real certificate, the `?api=` override and self-signed warning go
away entirely — the browser trusts the origin automatically. Also narrow
`allow_origins` in `backend/main.py` from `"*"` to your actual domain
before exposing this publicly.

## 5. Using it

1. **Add a voice** — record ~10-15 seconds directly in the browser (mic
   access required) or upload an existing clip (wav/mp3/m4a/ogg/flac/webm).
   Clear speech with minimal background noise clones best.
2. **Select it** from the voice list on the left.
3. **Type text** on the right, pick a language, and hit *Generate speech*.
4. Press play — the waveform reacts live to the generated audio.

XTTS v2 supports 17 languages; the dropdown includes the most common ones.
You can add more by checking the `language` codes XTTS supports.

## 6. Notes on production use

- The current voice registry is a flat JSON file (`backend/storage/voices.json`)
  and local disk storage — fine for one person self-hosting this, not for a
  multi-tenant product. Swap in a real database and per-user storage buckets
  if you're building something others will use.
- `allow_origins=["*"]` in the CORS config is for local development only.
  Lock it down before exposing this publicly.
- There's no authentication on any endpoint. Put this behind a login or a
  reverse proxy with auth if it's reachable from the internet.
- Consider adding: rate limiting, a max-requests-per-voice quota, and a
  watermark or inaudible tag on generated audio so clips can be traced back
  to this tool (some jurisdictions are starting to require this for
  synthetic voice/media).

## 7. Deploying: Render (backend) + GitHub Pages (frontend)

This hosts the backend on Render and the frontend as a free static site on
GitHub Pages — no self-signed certs needed, since both get real HTTPS
automatically.

**Cost check first:** Render's free and $7/mo Starter plans both only give
512 MB RAM, which isn't enough to load XTTS v2 + PyTorch — the service will
crash on startup. You need the **Standard plan (2 GB RAM, ~$25/month at
time of writing)** at minimum. Confirm current pricing at
render.com/pricing before committing. CPU inference on that plan will still
take real time per request (there's no free/cheap GPU tier on Render); if
that's too slow, Hugging Face Spaces or a GPU host like RunPod/Modal are
worth comparing.

### 7a. Push the repo to GitHub

```bash
cd voiceforge
git init
git add .
git commit -m "Initial commit"
# create a new repo on github.com, then:
git remote add origin https://github.com/<you>/voiceforge.git
git push -u origin main
```

### 7b. Deploy the backend to Render

The repo includes `render.yaml`, so Render can set the service up for you:

1. In the Render dashboard: **New +** → **Blueprint** → select your repo.
2. Render reads `render.yaml` and proposes a `voiceforge-backend` web
   service on the **Standard** plan. Confirm and deploy.
3. First deploy will be slow (installing torch + TTS, then downloading the
   ~1.8 GB XTTS model on first request). Watch the build/deploy logs for
   errors.
4. Once live, note the public URL Render gives you, e.g.
   `https://voiceforge-backend.onrender.com`. Confirm it works:
   `curl https://voiceforge-backend.onrender.com/api/health`

No `render.yaml`? You can create the same service by hand: **New +** → **Web
Service** → your repo → set **Root Directory** to `backend`, **Build
Command** to `pip install -r requirements.txt`, **Start Command** to
`uvicorn main:app --host 0.0.0.0 --port $PORT`, and **Instance Type** to
Standard.

### 7c. Point the frontend at it

Open `frontend/index.html` and fill in the constant near the top of the
`<script>` block:

```js
const DEFAULT_PROD_API = 'https://voiceforge-backend.onrender.com';
```

Commit and push that change.

### 7d. Deploy the frontend to GitHub Pages

1. In your GitHub repo: **Settings** → **Pages**.
2. Under **Build and deployment**, set **Source** to "Deploy from a
   branch", branch `main`, folder `/frontend`.
3. Save. GitHub gives you a URL like `https://<you>.github.io/voiceforge/`
   within a minute or two.

### 7e. Allow that origin on the backend

Right now `backend/main.py` allows requests from any origin
(`allow_origins=["*"]`), so this will already work — but it's worth
tightening once you know your real frontend URL:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://<you>.github.io"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Commit, push, and Render will redeploy automatically.

### Persistence on Render

Without a persistent disk, Render's filesystem resets on every redeploy and
periodically on restarts — so cloned voices and the `voices.json` registry
will disappear. For anything beyond testing, either:
- attach a Render persistent disk (uncomment the `disk:` block in
  `render.yaml`, which adds to the monthly cost), or
- swap local-disk storage for real object storage (S3, Cloudflare R2, etc.)
  in `backend/main.py` — a bigger change, but the right one for a service
  other people will actually rely on.

## Swapping the model

`voice_engine.py` isolates all model-specific code. To use a different
engine (RVC, Tortoise, OpenVoice, a hosted API like ElevenLabs instead of a
local model), you only need to change `VoiceEngine.synthesize()` — the
FastAPI routes and the frontend don't need to know what's underneath.
