# Repository Guidelines

## Project Structure & Module Organization

The Python backend, CLI, MCP server, research workflows, and backtesting code live in `agent/`; tests are in `agent/tests/`. The Vite/React application is in `frontend/`, with page tests alongside code in `frontend/src/**/__tests__/`. The Electron client is in `desktop/electron/`. Public documentation is under `wiki/`; static assets live in `assets/`.

## Build, Test, and Development Commands

Use Python 3.11–3.13. Install backend development dependencies with `pip install -e ".[dev]"`. Run the normal backend suite with:

```bash
pytest --ignore=agent/tests/e2e_backtest --ignore=agent/tests/test_e2e_harness_v2.py --tb=short -q
```

Run focused tests for changed modules, e.g. `pytest agent/tests/factors/test_alpha_purity.py -q`. For the web app, run `cd frontend && npm ci && npm run test:run` and `npm run build`. `scripts/dev up` starts the local backend (port 8899) and frontend (port 5899); use `scripts/dev stop` when finished. Electron checks run from `desktop/electron/`, e.g. `npm run test:locales`.

## Coding Style & Naming Conventions

Python uses four-space indentation, type annotations on public APIs, and Google-style docstrings. Format changed Python files with Black and lint them with Ruff; Ruff targets Python 3.11 and uses a 120-character line limit. Prefer `snake_case` modules, functions, and test names; classes use `PascalCase`. Keep changes focused—do not combine unrelated formatting cleanup with functional edits. TypeScript/React follows the existing component and page naming conventions (`RunDetail.tsx`, `agentToolTimeline.ts`).

## Testing Guidelines

Pytest discovers tests under `agent/tests`; mark fast isolated tests with `unit` and network-dependent coverage with `integration`. Put regression tests next to the affected backend area, named `test_<behavior>.py`. For alpha-factor changes, run both `test_alpha_purity.py` and `test_lookahead.py`; factors must preserve shape, missing values, and avoid look-ahead bias. Frontend tests use Vitest and Testing Library.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit-style subjects such as `feat(skills): add weekly-first trendline drawing guide` and `fix: register breakout and episodic pivot skills`. Use an imperative, scoped subject when useful. Community commits require DCO sign-off: `git commit -s -m "feat(area): description"`. PRs should state the goal, affected areas, test commands and results, scope exclusions, and any broker, MCP, network, credential, or deployment risk. Include screenshots for visible UI changes.

## Security & Safety

Never commit secrets, `.env` files, OAuth caches, broker exports, or private trading data. Do not run live-order, deployment, or externally reachable server flows as routine validation. Changes to broker order gates, mandates, kill switches, or audit logs require focused safety tests and a documented rollback path.
