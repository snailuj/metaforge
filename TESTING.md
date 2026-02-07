# Testing

## TypeScript (Frontend)

```bash
cd web
npm test              # Run tests
npm run test:coverage # Run tests with coverage report
```

Coverage HTML report: `web/coverage/index.html`

## Go (Backend)

```bash
go test ./...                          # Run tests
go test -coverprofile=coverage.out ./... # Run tests with coverage
go tool cover -html=coverage.out -o coverage.html  # Generate HTML report
```

Coverage HTML report: `coverage.html`
