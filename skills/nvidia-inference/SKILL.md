---
name: nvidia-inference
description: Configure NVIDIA inference API (inference-api.nvidia.com) as an AI model provider in openclaw. Use when setting up a new openclaw installation, adding NVIDIA models, rotating the NVIDIA API key, or troubleshooting model auth failures. Covers provider registration, available models, and auth profile setup.
---

# NVIDIA Inference API Setup

NVIDIA's inference API (`inference-api.nvidia.com`) is an OpenAI-compatible aggregator that provides access to Claude, Gemini, Llama, and other models under a single API key. It uses the OpenAI chat completions format (`/v1/chat/completions`), NOT Anthropic's messages format.

## Register NVIDIA as a custom provider in openclaw.json

Add the `models.providers.nvidia` block to `~/.openclaw/openclaw.json`:

```json
{
  "models": {
    "providers": {
      "nvidia": {
        "baseUrl": "https://inference-api.nvidia.com/v1",
        "apiKey": "<NVIDIA_API_KEY>",
        "models": [
          { "id": "azure/anthropic/claude-opus-4-6",       "name": "Claude Opus 4.6 (NVIDIA)" },
          { "id": "azure/anthropic/claude-opus-4-5",       "name": "Claude Opus 4.5 (NVIDIA)" },
          { "id": "azure/anthropic/claude-sonnet-4-6",     "name": "Claude Sonnet 4.6 (NVIDIA)" },
          { "id": "azure/anthropic/claude-sonnet-4-5",     "name": "Claude Sonnet 4.5 (NVIDIA)" },
          { "id": "azure/anthropic/claude-haiku-4-5",      "name": "Claude Haiku 4.5 (NVIDIA)" },
          { "id": "gcp/google/gemini-2.5-pro",             "name": "Gemini 2.5 Pro (NVIDIA)" },
          { "id": "gcp/google/gemini-2.5-flash",           "name": "Gemini 2.5 Flash (NVIDIA)" },
          { "id": "nvidia/meta/llama-3.3-70b-instruct",    "name": "Llama 3.3 70B (NVIDIA)" }
        ]
      }
    }
  }
}
```

Then restart the gateway:
```bash
openclaw gateway restart
```

## Set auth profile

Add to `~/.openclaw/agents/main/agent/auth-profiles.json`:

```json
{
  "version": 1,
  "profiles": {
    "nvidia:default": {
      "type": "api_key",
      "provider": "nvidia",
      "key": "<NVIDIA_API_KEY>"
    }
  }
}
```

## Switch models

```bash
openclaw models set nvidia/azure/anthropic/claude-sonnet-4-6
openclaw models set nvidia/azure/anthropic/claude-opus-4-6
openclaw models set nvidia/gcp/google/gemini-2.5-pro
openclaw models set nvidia/nvidia/meta/llama-3.3-70b-instruct
```

## Verify

```bash
openclaw models list           # should show nvidia model as default
openclaw agent --agent main --message "say hello"
```

## Notes

- Model IDs must use their full NVIDIA-prefixed form (e.g. `azure/anthropic/claude-opus-4-6`, not `claude-opus-4-6`)
- The API key format is `sk-...` (short, ~24 chars) — not the same format as Anthropic or OpenAI keys
- Keys issued by an org may restrict model access to `default-models` only — test with `curl` if unsure:
  ```bash
  curl -s https://inference-api.nvidia.com/v1/models \
    -H "Authorization: Bearer <key>" | python3 -m json.tool | grep '"id"'
  ```
- Do NOT set `ANTHROPIC_BASE_URL` to the NVIDIA endpoint — NVIDIA uses OpenAI format, not Anthropic format
