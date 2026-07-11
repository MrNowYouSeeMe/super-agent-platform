# Observability and Distributed Tracing

SuperAgent Sentinel uses structured JSON logs, request correlation, OpenTelemetry traces, and Jaeger for local trace visualization.

## Trace path

`Frontend -> FastAPI -> Redis queue -> worker -> PostgreSQL`

The API injects W3C Trace Context into the Redis job record. The worker extracts the context and creates a consumer span in the same distributed trace.

## Safe telemetry policy

Allowed trace attributes include route, latency, analysis ID, scenario, language, classification, confidence, and alert ID.

Never record full request payloads, prompts, responses, credentials, tokens, PINs, OTPs, private keys, or personal transaction content.

## Local dashboard

Jaeger UI: `http://127.0.0.1:16686`

Services:
- `superagent-api`
- `superagent-worker`

Jaeger all-in-one uses in-memory storage for local development, so traces are removed when the Jaeger container restarts.
