# CLAUDE.md: guidance for Claude Code in this repo

## What this is
Monte Carlo Investment Lab: FastAPI backend (`backend/`) + React/TS frontend (`frontend/`). The math lives ONLY in `backend/app/engine/` (pure functions, unit-tested). The frontend presents results; it never re-implements financial math except trivial counting (e.g. goal probability from terminal values).

## Commands
- Backend tests: `cd backend && pytest -q` (uses synthetic data automatically via tests/conftest.py)
- Real-data QA: `python scripts/validate_real_data.py` (needs internet)
- API: `cd backend && uvicorn app.main:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev` · build/type-check: `npm run build`
- Refresh data: `python scripts/update_data.py`

## Rules
- Never fabricate market data. Missing data → error or labeled warning. Synthetic data only when `MC_DEV_SYNTHETIC=1`, and it must stay flagged in API responses and the UI.
- Return convention: monthly LOG returns inside the simulator; annual inputs are ARITHMETIC; convert with the lognormal identities in `simulate._custom_params`.
- Time-series ML: chronological walk-forward with embargo, never random splits; features must be backward-looking (there is a test for it).
- Backtests use only information available at each date.
- Every new engine function gets a test with an analytic or hand-computed expectation.
- Keep request/response shapes in `frontend/src/lib/api.ts` in sync with `backend/app/main.py`.

## Gotchas (learned the hard way in v1)
- `groupby.apply()` drops the group column in newer pandas → loop or use `transform`.
- `merge_asof` needs a global sort on the key.
- `pd.qcut` fails on sparse dates → `duplicates="drop"`.
- macOS Python SSL → `certifi`; Wikipedia needs a browser User-Agent.
- Scripts importing the backend: `sys.path.insert(0, <root>/backend)`.
- pandas 3: `DataFrame.stack()` has no `dropna` argument.

## Working style (owner preference)
After finishing each component, explain it with a visual analogy and a first-principles summary, then pause and ask the owner to paraphrase it before moving on.
