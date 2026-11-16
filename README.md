# MultiOne spare-parts catalog

This project pulls a machine's spare-parts catalog from manufacturer dealer portals and returns it in one shared shape.

Each manufacturer stores the same idea differently: a serial number, a model, exploded-view drawings (assemblies), and the parts on those drawings. The portals are MultiOne, Peruzzo, and Weidemann. This service logs into each portal with dealer credentials, looks the machine up by serial, and maps the result into a single JSON document so a downstream app does not have to know which portal the data came from.

## What you get back

A machine looks like this, regardless of manufacturer:

- **manufacturer** — `MULTIONE`, `PERUZZO`, or `WEIDEMANN`
- **serial_number**
- **model** — external id, model number, and model name
- **assemblies** — each exploded-view drawing, with a name, the serial range it applies to, a drawing URL, and the parts on that drawing
- **parts** — reference number on the drawing, part number, description, quantity, and manufacturer-specific extras (price, unit, preferred/alternative/disabled flags, notes)

Drawing URLs are not the same kind of link on every portal:

| Manufacturer | Drawing URL |
| --- | --- |
| MultiOne | A public URL on the dealer site |
| Peruzzo | A temporary URL; `expires_at` is taken from the link |
| Weidemann | A metadata URL that still needs an authenticated follow-up to resolve the image and click coordinates |

## How each portal is read

**MultiOne** (`b2b.multione-csf.com`). Logs in through the HTML form, pages through the dealer's serial list, finds the serial, then loads that serial's spare-parts drawings and components.

**Peruzzo** (`peruzzo.theasp.cloud` / `sparepartsapi.theasp.cloud`). Logs in for a bearer token, pages through the dealer's machines, finds the serial (`matricola`), loads the boards grouped by serial range, then loads the parts on each board.

**Weidemann** (`shop.weidemann-online.com`). Login goes through Wacker Neuson (Gigya), so a real browser (Playwright) signs in, cookies are copied into a `requests` session, and an OAuth token is read from that session. The serial page yields a material number; that yields a spare-parts list and a bill-of-materials tree. The tree is walked for assemblies and parts. If more than one spare-parts list comes back, retrieval stops — picking among them is not decided yet. Drawing image and coordinate files are resolved only when a drawing is actually requested.

## API

`multione_api.py` is the app that is meant to be served. It mounts the MultiOne routes and the Peruzzo router.

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/ping` | Health check |
| GET | `/multione/login-test` | Confirms MultiOne login |
| GET | `/multione/serials-test` | Counts serials visible to the dealer account |
| GET | `/multione/machine/{serial}` | Normalized MultiOne machine. Unknown serials return `found: false` |
| GET | `/peruzzo/machine/{serial}` | Normalized Peruzzo machine. Unknown serials return 404 |

`weidemann_api.py` exposes `GET /weidemann/machine/{serial}` on its own FastAPI app. That router is not mounted on `multione_api.py` yet.

Credentials come from the environment:

- `MULTIONE_USERNAME`, `MULTIONE_PASSWORD`
- `PERUZZO_USERNAME`, `PERUZZO_PASSWORD`
- `WEIDEMANN_USERNAME`, `WEIDEMANN_PASSWORD`

## Scripts

`multione_test.py`, `peruzzo_test.py`, and `weidemann_login_test.py` do the same retrieval from the command line. They prompt for a username, password, and serial, print a short summary, and (for MultiOne and Peruzzo) write `multione_{serial}.json` or `peruzzo_{serial}.json`. `normalizers.py` is shared by the API and the scripts.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

export MULTIONE_USERNAME=...
export MULTIONE_PASSWORD=...
export PERUZZO_USERNAME=...
export PERUZZO_PASSWORD=...

uvicorn multione_api:app --reload
```

Weidemann, on its own app:

```bash
export WEIDEMANN_USERNAME=...
export WEIDEMANN_PASSWORD=...

uvicorn weidemann_api:app --reload
```

Weidemann login launches a visible Chromium window (`headless=False`).
