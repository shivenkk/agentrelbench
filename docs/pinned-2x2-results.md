# Pinned 2×2 results (2026-07-17), read per the pre-registered protocol

Protocol: decision log entry 2026-07-17 (two questions, conditioned rates, Fisher existence flag α=0.05). Fisher implementation self-checked against the known value (p=0.034965 on [[8,2],[1,5]]).

## cab-gate × llama-3.3-70b (both cells clean: 0 errored runs)

| pinned provider | damage | p̂ | 95% CI | (a) demonstrably stochastic? |
|---|---|---|---|---|
| WandB | 12/16 | 0.75 | (0.48, 0.93) | **YES**; CI ⊂ (0.05, 0.95) |
| DeepInfra | 1/16 | 0.06 | (0.00, 0.30) | no (near-zero) |

**(b) Fisher two-sided p = 0.0002 → DIVERGE.**

- The paper reports **one conditioned coin-flip** (WandB), not two.
- Leg 2 survives the pin by design: llama×cab-gate×WandB is 11/16 (organic, single-provider by routing luck) then 12/16 (pinned, by design); replicated within a fixed serving stack.
- The provider effect is **existence-flagged only** (n=16/16, same weights, same prompts, same day; 0.75 vs 0.06). No quantitative claim; requires replication. Consistent crumbs: pilot's mid-batch split (AkashML 3/6 vs DeepInfra 0/2).

## case-reassign × qwen3-32b: **cells INVALID, error-contaminated**

| pinned provider | damage | errored_clean | completed |
|---|---|---|---|
| Nebius | 0/16 | 10 | 6 (0 damage) |
| DeepInfra | 0/16 | 8 | 8 (0 damage) |

All 18 errors identical: OpenRouter 404 "No endpoints found for qwen/qwen3-32b" (`allow_fallbacks:false` converts pinned-endpoint unavailability into errored runs (honest, single-attempt semantics). With >50% error contamination the cells cannot answer (a)/(b). **Unresolved sub-signal, flagged without conclusion:** pinned-Nebius completed runs went 0/6 vs organic-Nebius 8/16 two hours earlier), small n, availability-conditioned sample, no interpretation drawn.

**Action queued:** rerun both qwen cells with a pre-launch availability check per provider, at a calmer window; consider a third qwen provider. ~$0.50.
