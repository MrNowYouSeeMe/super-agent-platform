# SuperAgent Sentinel

Phase 2 adds a Redis-backed worker pipeline and PostgreSQL-persistent alert/case workflow to the Phase 1 contract-safe vertical slice.

## Implemented

- Separate API and analysis worker processes
- Redis queue and persistent analysis events
- PostgreSQL alerts and case events
- Legal workflow state transitions
- Assign, acknowledge, review, escalate, and resolve actions
- Optimistic workflow version checks
- Responsive workflow UI
- Health checks for API, PostgreSQL, and Redis
- Safe analytics and multilingual output from Phase 1

## Local services

- Frontend: http://127.0.0.1:5173
- API: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- PostgreSQL: 127.0.0.1:5432
- Redis: 127.0.0.1:6379

OpenAI remains disabled in this phase. It will be added only after the multilingual golden dataset and evaluation harness are ready.
