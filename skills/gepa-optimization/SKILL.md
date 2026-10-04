---
name: gepa-optimization
description: Use for GEPA self-evolution runs and long dspy optimization.
---

# GEPA Self-Evolution Optimization

Run GEPA optimization to evolve Hermes skills or workflows. Long-running (20-60 min); requires careful credential and process management.

## Prerequisites

- Valid Nous API key (static key preferred for long runs)
- hermes-agent repo accessible (via HERMES_AGENT_REPO env or standard location)
- Python environment with dspy, litellm, and evolution dependencies installed

## Running GEPA Optimization

```bash
cd hermes-agent-self-evolution
python -m evolution.skills.evolve_skill --skill <skill-name> --iterations <n>
```

Or for a specific workflow:
```bash
python -m evolution.workflows.optimize_workflow --workflow <name> --iterations <n>
```

Run in background for long optimizations:
```bash
python -m evolution.skills.evolve_skill --skill github --iterations 10 > output/github/run.log 2>&1 &
```

## Credential Management (Critical for Long Runs)

**Pitfall:** OAuth agent_keys in `~/.hermes/profiles/local/auth.json` are periodically rotated by the Hermes runtime. A long-running GEPA process that started with a valid agent_key will begin failing with 401 AuthenticationError after rotation — even though short standalone calls still work.

**Solution:** Use a static API key for long-running processes. Set it via:

1. **Environment variable:** `export NOUS_API_KEY=sk-nous-...` (highest priority)
2. **Repo-local .env file:** Create `.env` in the evolution repo root with `NOUS_API_KEY=sk-nous-...` (gitignored)
3. **auth.json agent_key:** Last resort; rotates periodically

The `make_lm()` function in `evolution/core/config.py` handles the fallback chain automatically.

**Debugging auth failures:** If you see 401 errors mid-run, check which key is actually being used:
```bash
python -c "from evolution.core.config import _nous_credentials; k,_ = _nous_credentials(); print(k[:12])"
```
Compare against your expected key. Use SHA256 hashing to compare keys without exposing them.

## Monitoring Progress

GEPA logs iteration progress with fitness scores:
```
Iteration 1: Selected program 0 score: 0.65
Iteration 2: Selected program 0 score: 0.69
```

Scores should trend upward. Stagnant or declining scores indicate a problem.

**Pitfall:** Don't confuse eval scores with reflection success. Eval scores may look normal even when reflection calls are failing (dspy caches eval results from bootstrap). Check for "Per-task reflection failed" messages in the log.

## Common Errors

- **AuthenticationError (401):** Stale/rotated API key. Rotate to static key via .env.
- **Per-task reflection failed:** Usually auth-related; check key rotation.
- **Program selection stagnation:** Population may have converged; increase population_size or iterations.

## Post-Run

- Review the evolved skill/workflow in the output directory
- Run the full test suite to verify no regressions
- Consider creating a PR with the evolved changes

## Configuration

Key parameters in `evolution/core/config.py`:
- `optimizer_model`: Model for GEPA reflections (default: nous/openai/gpt-5-nano)
- `eval_model`: Model for LLM-as-judge scoring
- `population_size`: Number of programs in the population (default: 5)
- `iterations`: Number of optimization iterations (default: 10)