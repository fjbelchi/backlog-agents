"""
LiteLLM post-startup pricing verification.

Mounted into the container and invoked by the healthcheck to guarantee
that model pricing is correct before the container is marked healthy.

How it works:
  Calls the proxy's /model/info API and checks that each expected model
  has non-zero input_cost_per_token. Exits non-zero if any model has $0
  pricing, which keeps the container "unhealthy" and prevents traffic.

Why this exists:
  Cross-region inference profiles (e.g. us.anthropic.claude-sonnet-4-6)
  are not in LiteLLM's built-in pricing. Without the patched pricing file
  mounted at /app/model_prices_and_context_window.json, register_model()
  creates entries with input_cost_per_token=0 during startup. The dual
  mount in docker-compose.yml fixes this, and this script verifies it.
"""

import json
import sys
import urllib.request

PROXY_URL = "http://localhost:4000"

# Expected pricing per litellm_params.model (Bedrock cross-region)
EXPECTED_MODELS = {
    "bedrock/us.anthropic.claude-sonnet-4-6": 0.0000033,
    "bedrock/us.anthropic.claude-opus-4-6-v1": 0.0000055,
    "bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0": 0.0000011,
}


def main():
    try:
        req = urllib.request.Request(
            f"{PROXY_URL}/model/info",
            headers={"Authorization": f"Bearer {_get_master_key()}"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"FAIL: Cannot reach /model/info: {e}", file=sys.stderr)
        sys.exit(1)

    # Build map: litellm_params.model → input_cost_per_token from model_info
    model_pricing = {}
    for entry in data.get("data", []):
        litellm_model = entry.get("litellm_params", {}).get("model", "")
        icp = entry.get("model_info", {}).get("input_cost_per_token", 0)
        # Keep the highest price seen (multiple aliases may share the same backend)
        if litellm_model not in model_pricing or (icp or 0) > model_pricing[litellm_model]:
            model_pricing[litellm_model] = icp or 0

    ok = True
    for model, expected_icp in EXPECTED_MODELS.items():
        actual = model_pricing.get(model, 0)
        if actual == 0:
            print(f"FAIL: {model} has $0 pricing", file=sys.stderr)
            ok = False
        elif abs(actual - expected_icp) / expected_icp > 0.01:
            print(
                f"WARN: {model} pricing mismatch: expected {expected_icp}, got {actual}",
                file=sys.stderr,
            )

    if ok:
        sys.exit(0)
    else:
        print("Some models have $0 pricing — container stays unhealthy", file=sys.stderr)
        sys.exit(1)


def _get_master_key():
    """Read master key from env or fall back to default."""
    import os
    return os.environ.get("LITELLM_MASTER_KEY", "sk-litellm-changeme")


if __name__ == "__main__":
    main()
