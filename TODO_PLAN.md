# StockJarvis To‑Do Plan

## Goal
Deliver the refactored, production-ready StockJarvis: FastAPI + Celery + SQLAlchemy + broker adapters, with backtesting, data pipelines, and hardened risk controls.

## Priority Order
1. **Stabilize Foundation (P0)**
   - Run `pytest`; fix failures; add DB/Redis fixtures for CI.
   - Add Alembic migrations for `data/models.py` (stop relying on `create_tables()` in prod).
   - Unify structured logging/metrics across API and workers.

2. **Backtester & Validation (P0)**
   - Implement `core/backtester.py`: run strategies on historical data, write `BacktestResult`, set `Strategy.is_validated`.
   - Add `/api/backtest` route + Celery task for scheduled validations; export HTML/CSV summaries.

3. **Broker Abstraction (P0)**
   - Define `services/broker/base.py` interface (place/modify/cancel/order status/positions/quotes).
   - Implement Zerodha adapter (paper + live) using settings; move `BrokerModules/Zerodha` demo into it.
   - Wire API orders and worker reconciliation through broker interface.

4. **Data Providers & Collection (P1)**
   - Create `data/providers/` interface (history/intraday/metadata).
   - Implement first provider (Quandl/AlphaVantage); refactor `DataCollector` scripts into Celery tasks using provider.
   - Add retry/backoff, rate-limit guards, and metadata logging.

5. **Controller / Trade Orchestration (P1)**
   - Build `services/controller.py` to consume validated signals, run `RiskManager` + sizing, dispatch broker orders, and log audits.
   - Replace legacy `Controller` doc with this service.

6. **Watchlists & Alerts (P1)**
   - Add watchlist table + repository + API CRUD; integrate with signals/news tasks.
   - Expand notifications into `services/notifications` (email/SMS) using `config.notifications`; alert on circuit-breaker, SL/TP hits, reconciliation issues.

7. **API Hardening (P1)**
   - Complete JWT auth/refresh; add role guards.
   - Tighten validation, pagination/filtering; rate-limit public routes; restrict CORS to known frontends.

8. **Strategies & Indicators (P2)**
   - Add intraday/sample strategies with tests; document plugin contract and dynamic loading from `strategies/`.

9. **Web/App Surface (P2)**
   - Decide UI path (SPA or minimal dashboard) for metrics/watchlists/backtests.
   - Decommission legacy `Web/` once replacement exists.

10. **Documentation & Ops (P2)**
    - Refresh `README.md` quickstart; keep deep details in `README_REFACTOR.md`.
    - Add `ROADMAP.md`, architecture diagram, `docker-compose.test.yml` for CI; keep `.env.example` current.

## How to Execute (per workstream)
- **Backtester**: use repository to fetch price DF → run `strategy.generate_signal` over windows → compute metrics → persist `BacktestResult` and update `Strategy`; expose via API & Celery.
- **Broker Layer**: define dataclasses for Order/Position/Quote; adapter maps to SDK; inject via FastAPI dependency and worker factory; mock with `tests/mocks/broker_mock.py`.
- **Data Provider**: interface `get_history/get_intraday/get_symbols`; provider factory keyed by settings; Celery tasks ingest → normalize → `repository.add_prices_bulk`; validate data.
- **Controller**: consume new signals, call `RiskManager` + position sizer, place orders, persist orders/positions, emit alerts/audit events.
- **Watchlists**: schema (id, name, type, symbols, notes); API CRUD; tasks to refresh from signals/news; UI list.
- **Observability**: structured JSON logs, request/trace IDs, Prometheus metrics, health checks for DB/Redis/Celery/broker; alerts on circuit-breaker and reconciliation discrepancies.
- **Tests/CI**: compose up MySQL/Redis for tests; seed fixtures; run unit+integration with coverage gates.

## Risks / Dependencies
- Broker integration needs live creds → develop with paper mode + mocks.
- Provider rate limits → caching, backoff, quota guards.
- Backtester accuracy depends on clean price history → enforce ingestion validation.

## Artifacts to Create
- `core/backtester.py`
- `services/broker/base.py`, `services/broker/zerodha.py`
- `data/providers/*`
- `services/controller.py`
- `services/notifications/*`
- Watchlist models/migrations + API routes
- `/api/backtest`, `/api/watchlists`
- `ROADMAP.md`, `docker-compose.test.yml`

## Definition of Done
- **P0**: Tests green; migrations in place; backtester + broker adapter work in paper mode; reconciliation task completes; CI passing.
- **P1**: Controller workflow live; provider-driven ingestion; watchlists & alerts operational; auth hardened.
