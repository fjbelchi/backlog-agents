# Backlog Toolkit Documentation

This documentation is the operational source of truth for the backlog toolkit.
It is designed for `cloud-first` usage with a LiteLLM self-hosted gateway.

## 🚀 Setup & Verification (Start Here)

### Essential Docs
- **[Final Summary](FINAL-SUMMARY.md)** ⭐ - Complete overview of everything
- **[Quick Reference](QUICK-REFERENCE.md)** - Daily commands and troubleshooting
- **[Service Verification](SERVICE-VERIFICATION.md)** - How to verify services are working

### Setup Guides
- **[AWS SSO Setup](AWS-SSO-SETUP.md)** - Using SSO credentials (recommended)
- **[AWS Credentials](AWS-CREDENTIALS.md)** - All credential configuration options
- **[Bedrock Permissions](BEDROCK-PERMISSIONS.md)** - ⚠️ **Important**: Permission issues & solutions
- **[Service Startup Guide](SERVICE-STARTUP-GUIDE.md)** - Managing LiteLLM and RAG services

### Monitoring & Debugging
- **[LiteLLM Prompts & Logging](LITELLM-PROMPTS-LOGGING.md)** - View prompts and monitor API calls
- **[Troubleshooting](TROUBLESHOOTING.md)** - Common issues and solutions

### Status & History
- **[Session Summary](SESSION-SUMMARY.md)** - Latest setup status and config

## Quick Links

- [Quickstart (Cloud-First)](tutorials/quickstart-cloud-only.md)
- [Token Optimization Playbook](tutorials/token-optimization-playbook.md)
- [Daily Operator Flow](tutorials/daily-flow.md)
- [System Overview](architecture/system-overview.md)
- [Skill Documentation](skills/README.md)
- [Technical Reference](reference/)
- [RAG Pipeline Reference](reference/rag-pipeline.md)
- [Runbooks](runbooks/)
- [Troubleshooting](troubleshooting/quick-diagnosis.md)
- [Documentation Standards](contributing/documentation-standards.md)

## Architecture Decisions

- [ADR-001: Orchestrator Entrypoint](architecture/adr/ADR-001-orchestrator-entrypoint.md)
- [ADR-002: Script-First, LLM-Second](architecture/adr/ADR-002-script-first-llm-second.md)
- [ADR-003: Model Routing Aliases](architecture/adr/ADR-003-model-routing-aliases.md)
- [ADR-004: Multi-Layer Caching & Batch](architecture/adr/ADR-004-multilayer-caching-and-batch.md)
- [ADR-005: RAG-Augmented Context](architecture/adr/ADR-005-rag-augmented-context.md)
- [ADR-006: Deterministic Init — Script vs Skill](architecture/adr/ADR-006-deterministic-init.md)

## Mandatory Policies

1. `backlog-orchestrator` is the recommended default entrypoint.
2. Deterministic scripts run before any LLM call.
3. Documentation updates are required for changes in `skills/`, `config/`, and `scripts/`.
4. All LLM calls must use model aliases (cheap/balanced/frontier), never raw model IDs.
5. Frontier model escalation requires documented reason.

## Validation

Run docs checks locally:

```bash
make validate    # or manually:
./scripts/docs/check-links.sh
./scripts/docs/check-doc-coverage.py
./scripts/docs/verify-snippets.sh
```
