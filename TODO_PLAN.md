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
   - Complete `Backtester/JarvisBT.py` beyond BTSignal class stub - add full backtesting engine.
   - Add `/api/backtest` route + Celery task for scheduled validations; export HTML/CSV summaries.
   - Walk-forward analysis and Monte Carlo simulation for robustness testing.

3. **AnalysisEngine Module (P0)**
   - Complete `AnalysisEngine/JarvisAnalysisEngine.py` implementation.
   - Expand SignalEvent, OrderEvent, FillEvent classes with full functionality.
   - Event-driven architecture for signal processing.
   - Integration with scanner and strategy engine.
   - Performance optimization for real-time signal generation.

4. **Broker Abstraction (P0)**
   - Define `services/broker/base.py` interface (place/modify/cancel/order status/positions/quotes).
   - Implement Zerodha adapter (paper + live) using settings; move `BrokerModules/Zerodha` demo into it.
   - Wire API orders and worker reconciliation through broker interface.
   - Add live price fetching capability (currently TODO in position_tracker.py#L515).
   - Implement broker position fetching for reconciliation (TODO in workers/tasks/position_monitoring.py#L310).

4. **Data Providers & Collection (P1)**
   - Create `data/providers/` interface (history/intraday/metadata).
   - Implement first provider (Quandl/AlphaVantage); refactor `DataCollector` scripts into Celery tasks using provider.
   - Complete stub implementations in `DataCollector/providers/` directory.
   - Add retry/backoff, rate-limit guards, and metadata logging.
   - Implement data archiving strategy (TODO in workers/tasks/system_maintenance.py#L129).
   - Data validation and quality checks before ingestion.

5. **Controller / Trade Orchestration (P1)**
   - Build `services/controller.py` to consume validated signals, run `RiskManager` + sizing, dispatch broker orders, and log audits.
   - Replace legacy `Controller` doc with this service.

6. **Watchlists & Alerts (P1)**
   - Add watchlist table + repository + API CRUD; integrate with signals/news tasks.
   - Expand notifications into `services/notifications` (email/SMS) using `config.notifications`; alert on circuit-breaker, SL/TP hits, reconciliation issues.
   - Implement emergency alerts for critical risk events (TODO in core/risk_manager.py#L572-L573).
   - Complete email/SMS sending implementations (TODO in core/position_monitor.py#L782).
   - Notification templates and preferences management.

7. **API Hardening (P1)**
   - Complete JWT auth/refresh; add role guards.
   - Tighten validation, pagination/filtering; rate-limit public routes; restrict CORS to known frontends.
   - Implement rate limiting (TODO in api/dependencies.py#L403).
   - Add daily drawdown tracking endpoint (TODO in api/routes/risk.py#L112).
   - Request throttling and abuse prevention.

8. **Strategies & Indicators (P2)**
   - Add intraday/sample strategies with tests; document plugin contract and dynamic loading from `strategies/`.
   - Complete strategy implementations beyond current EOD strategies.
   - Strategy versioning and A/B testing framework.

## Missing/Incomplete Features (Technical Debt)

### Critical TODOs in Existing Code
1. **Rate Limiting** (api/dependencies.py#L403)
   - Implement actual rate limiting for API endpoints
   - Add Redis-based rate limiting with configurable limits per user/endpoint

2. **Live Price Fetching** (core/position_tracker.py#L515)
   - Implement real-time price updates from broker
   - WebSocket integration for live data streaming

3. **Emergency Alerts** (core/risk_manager.py#L572-L573)
   - Critical risk breach notifications
   - Multi-channel alert delivery (SMS, Email, Push)

4. **Email/SMS Sending** (core/position_monitor.py#L782)
   - Complete notification implementation
   - Integration with SendGrid/Twilio or similar services

5. **Daily Drawdown Tracking** (api/routes/risk.py#L112)
   - Implement GET endpoint for daily drawdown metrics
   - Historical drawdown analysis and charting

6. **Broker Position Fetching** (workers/tasks/position_monitoring.py#L310)
   - Fetch actual positions from broker for reconciliation
   - Handle position discrepancies and auto-correction

7. **Data Archiving** (workers/tasks/system_maintenance.py#L129)
   - Implement archiving strategy for old data
   - Compression and cold storage for historical data

### Legacy Code Cleanup
- Refactor `Common/W2SMS2.py` and `Common/Way2SMSFreeSMS.py` into services/notifications
- Migrate legacy DB scripts (`DBLayer/` files) into Alembic migrations
- Consolidate scattered data collection scripts into unified provider system
- Remove deprecated test files (`Roughtests.py`, `roughtests2.py`)

9. **PositionManager Module (P1)**
   - Implement `services/position_manager/` for live position monitoring.
   - Add trailing stop-loss logic with auto-adjustment based on price movement.
   - Profit protection mechanisms (lock-in at X% profit, move SL to breakeven).
   - Real-time alerts for position health, drawdown warnings.
   - Integration with `core/position_tracker.py` and `core/stop_loss_manager.py`.

10. **PortfolioManager Module (P1)**
    - Implement `services/portfolio_manager/` for portfolio-level tracking.
    - Track portfolio-wide risk metrics, exposure, diversification.
    - Risk/reward ratio management across all positions.
    - Portfolio rebalancing suggestions and optimization.
    - Historical performance tracking and analytics.

11. **JarvisAI Module (P2)**
    - Implement `services/jarvis_ai/` for AI-powered strategy analysis.
    - Auto-generation of strategy ideas from market patterns.
    - Strategy backtesting automation with parameter optimization.
    - Machine learning models for signal prediction.
    - Strategy performance prediction and recommendation engine.

12. **NewsParser Module (P2)**
    - Implement `services/news_parser/` with plugin architecture.
    - RSS/API feed integration for financial news.
    - Sentiment analysis using NLP (VADER, FinBERT).
    - News-to-stock correlation and impact scoring.
    - Real-time news alerts for watchlist symbols.
    - Integration with watchlist manager for news-based watchlists.

13. **WatchlistManager Module (P1)**
    - Implement `services/watchlist_manager/` (beyond basic CRUD).
    - Support multiple watchlist types: EOD, Intraday, Potential, News-based, Investment.
    - Auto-population from scanner signals and news sentiment.
    - Watchlist scoring and ranking algorithms.
    - Symbol rotation based on performance/activity.
    - Export/import functionality for watchlists.

14. **AFDParser Module (P3)**
    - Implement `services/afd_parser/` for AmiBroker Formula Language (AFL) conversion.
    - Parse AFD files and extract strategy logic.
    - Convert AFL syntax to Python strategy implementations.
    - Validate converted strategies via backtesting.
    - Documentation for supported AFL functions and limitations.

15. **Web/App Surface (P2)**
    - Decide UI path (SPA or minimal dashboard) for metrics/watchlists/backtests.
    - Modern React/Vue dashboard with real-time updates via WebSockets.
    - Strategy management UI (create/edit/backtest/deploy).
    - Position monitoring dashboard with live P&L.
    - Portfolio analytics and risk visualization.
    - News feed integration with sentiment indicators.
    - Decommission legacy `Web/` once replacement exists.

16. **Documentation & Ops (P2)**
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
### Core Services
- `core/backtester.py`
- `services/broker/base.py`, `services/broker/zerodha.py`
- `services/controller.py`
- `services/position_manager/` (full module)
- `services/portfolio_manager/` (full module)
- `services/jarvis_ai/` (full module)
- `services/news_parser/` (full module)
- `services/watchlist_manager/` (full module)
- `services/afd_parser/` (full module)
- `services/notifications/` (email, SMS, push)

### Data & Providers
- `data/providers/base.py` (interface)
- `data/providers/quandl.py`
- `data/providers/alphavantage.py`
- `data/providers/nse.py`
- Complete implementations in `DataCollector/providers/`

### API & Models
- `/api/backtest`, `/api/watchlists`, `/api/portfolio`, `/api/news`
- Watchlist models/migrations + API routes
- Portfolio models/migrations
- News models/migrations

### Analysis Engine
- Complete `AnalysisEngine/JarvisAnalysisEngine.py`
- Event processing pipeline
- Signal generation framework

### Web UI (Modern)
- React/Vue SPA dashboard
- WebSocket integration for real-time updates
- Strategy management UI
- Portfolio visualization
- News sentiment dashboard

### Testing & CI/CD
- `docker-compose.test.yml`
- Integration tests for all new modules
- End-to-end workflow tests
- Performance benchmarks

### Documentation
- `ROADMAP.md`
- Architecture diagrams
- API documentation (Swagger/OpenAPI)
- Module-specific README files
- Deployment guides


## Definition of Done
- **P0**: Tests green; migrations in place; backtester + broker adapter work in paper mode; reconciliation task completes; CI passing; AnalysisEngine fully functional.
- **P1**: Controller workflow live; provider-driven ingestion; watchlists & alerts operational; auth hardened; PositionManager and PortfolioManager operational; all critical TODOs resolved.
- **P2**: JarvisAI & NewsParser operational; modern Web UI deployed; all strategies documented and tested; AFDParser available for legacy migrations.
- **P3**: Legacy code removed; full documentation complete; performance optimized; production monitoring in place.

## Module Status Tracking

### ✅ Complete
- Core foundation (FastAPI, Celery, SQLAlchemy)
- Position tracking and reconciliation
- Risk management and stop-loss
- Strategy engine basics
- Repository pattern and data models
- Docker deployment setup
- Basic API routes (positions, strategies, signals, risk)

### 🚧 In Progress
- Test coverage (unit/integration)
- Alembic migrations
- API authentication/authorization
- Worker task improvements

### ⏳ Not Started - High Priority (P0-P1)
- Backtester implementation
- Broker abstraction layer
- AnalysisEngine completion
- Controller/Orchestration service
- Data provider interfaces
- PositionManager module
- PortfolioManager module
- WatchlistManager module
- Notification service
- Live price fetching
- Broker position reconciliation

### ⏳ Not Started - Medium Priority (P2)
- JarvisAI module
- NewsParser module
- Modern Web UI
- Strategy library expansion
- Rate limiting
- Daily drawdown tracking
- Emergency alerts
- Data archiving

### ⏳ Not Started - Low Priority (P3)
- AFDParser module
- Legacy code cleanup
- Advanced analytics
- Performance optimization tools

## Implementation Sequence

### Phase 1: Foundation (Weeks 1-2)
1. Fix all test failures
2. Add Alembic migrations
3. Complete AnalysisEngine
4. Implement broker abstraction layer

### Phase 2: Core Trading (Weeks 3-4)
5. Implement Backtester
6. Build Controller/Orchestration
7. Complete data providers
8. PositionManager implementation

### Phase 3: Portfolio & Risk (Weeks 5-6)
9. PortfolioManager implementation
10. Advanced risk features (emergency alerts, live pricing)
11. Notification service
12. WatchlistManager implementation

### Phase 4: Intelligence (Weeks 7-8)
13. NewsParser module
14. JarvisAI module (phase 1)
15. API hardening and rate limiting
16. Broker reconciliation completion

### Phase 5: UI & UX (Weeks 9-10)
17. Modern Web UI development
18. Real-time WebSocket integration
19. Dashboard and visualizations
20. Mobile-responsive design

### Phase 6: Polish & Production (Weeks 11-12)
21. AFDParser (if needed)
22. Legacy code cleanup
23. Performance optimization
24. Documentation completion
25. Production deployment and monitoring

