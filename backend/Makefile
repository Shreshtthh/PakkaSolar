.PHONY: local deploy seed-data upload-nasa logs build

# ── Local development (no AWS needed) ─────────────────────────────────────────
local:
	MOCK_MODE=true sam local start-api \
		--env-vars env.local.json \
		--port 3001

# ── Build (required before deploy) ────────────────────────────────────────────
build:
	sam build

# ── First deploy (interactive) ────────────────────────────────────────────────
deploy: build
	sam deploy --guided

# ── Subsequent deploys ────────────────────────────────────────────────────────
deploy-fast: build
	sam deploy

# ── Seed DynamoDB tables ───────────────────────────────────────────────────────
# Run AFTER first deploy (tables must exist)
seed-data:
	python scripts/seed_dynamo.py \
		--almm   scripts/seed_data/almm_panels.csv \
		--vendors scripts/seed_data/vendors_hp.csv \
		--region ap-south-1

# ── Upload NASA POWER cache to S3 ─────────────────────────────────────────────
# Run AFTER first deploy (bucket must exist)
upload-nasa:
	python scripts/fetch_nasa_power.py \
		--bucket $$(aws cloudformation describe-stacks \
			--stack-name pakkasolar \
			--query "Stacks[0].Outputs[?OutputKey=='MediaBucketName'].OutputValue" \
			--output text) \
		--region ap-south-1

# ── Tail Lambda logs ──────────────────────────────────────────────────────────
logs-webhook:
	sam logs -n WebhookHandler --stack-name pakkasolar --tail

logs-worker:
	sam logs -n AuditWorker --stack-name pakkasolar --tail

logs-status:
	sam logs -n StatusHandler --stack-name pakkasolar --tail

# ── Quick smoke test after deploy ─────────────────────────────────────────────
# Encodes sample_quotes/quote_pass.jpg and POSTs it to the deployed API
smoke-test:
	@API=$$(aws cloudformation describe-stacks \
		--stack-name pakkasolar \
		--query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
		--output text) && \
	IMG=$$(base64 -w 0 tests/sample_quotes/quote_pass.jpg) && \
	curl -s -X POST "$$API/audit" \
		-H "Content-Type: application/json" \
		-d "{\"image_b64\":\"$$IMG\",\"lang\":\"en\"}" | jq .
