# Testing

## TypeScript (Frontend)

```bash
cd web
npm test              # Run tests
npm run test:coverage # Run tests with coverage report
```

Coverage HTML report: `web/coverage/index.html`

## Python (Data Pipeline)

```bash
cd data-pipeline && python -m pytest scripts/ -v
```

Tests validate imported data integrity against `data-pipeline/output/lexicon_v2.db`.
The database must be built (or restored via `scripts/restore_db.sh`) before running tests.

## Go (Backend)

```bash
go test ./...                          # Run tests
go test -coverprofile=coverage.out ./... # Run tests with coverage
go tool cover -html=coverage.out -o coverage.html  # Generate HTML report
```

Coverage HTML report: `coverage.html`
