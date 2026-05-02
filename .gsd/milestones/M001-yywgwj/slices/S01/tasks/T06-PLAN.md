---
estimated_steps: 1
estimated_files: 2
skills_used: []
---

# T06: Deploy V2 database to staging

Deploy the V2-enriched database to metaforge-next.julianit.me via deploy/staging/deploy.sh. Verify the forge endpoint returns results with salience weighting visible in the response. Confirm health check passes and the staging site serves the updated data independently of production.

## Inputs

- `data-pipeline/output/lexicon_v2.db`

## Expected Output

- `Staging site serving V2-enriched data`
- `Health check passing`

## Verification

curl -s metaforge-next.julianit.me/forge/suggest?word=anger | jq '.suggestions[0].salience_sum' returns a non-zero value; curl -s metaforge-next.julianit.me/health returns 200
