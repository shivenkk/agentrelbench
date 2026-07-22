# Safety Doesn't Repeat: Universal, Stochastic, Trap-Free Damage in Action-Taking LLM Agents

**Draft v1 (2026-07-21), for honesty review before any external circulation.**
Figures: `docs/figs/fig1..fig4` (regenerated from committed merged verdicts by `scripts/make_figures.py`).
Alternative title: *No Task Fails Every Time: Why One-Shot Audits Are Structurally Blind to Agent Damage.*

---

## Abstract

Enterprise LLM agents increasingly take irreversible actions: a wrong database commit is damage to be detected and unwound, not a bad sample to regenerate. We introduce AgentRelBench, an environment-agnostic reliability instrument that computes ground-truth, severity-priced damage from database state diffs, with no LLM anywhere in the measurement path, across repeated runs (pass^k and safe^k), demonstrated on a simulated enterprise-operations substrate (EnterpriseOps-Gym). Across 2,128 evaluation runs spanning nine models in six families (four development models; five models evaluated under pre-registered held-out criteria, including two frontier-tier models), we find: **(1)** damage on irreversible actions is universal across the families we measured and stochastic within them; the same model on the same task with the same pinned serving configuration damages on some runs and not others. **(2)** No task damaged on every run: zero always-fail cells across 48 held-out damage events, so the damage is real but carries no discoverable dangerous-task signature that a one-shot audit could find. A single clean run misses a damage-producing (model, task) pair 0.80 of the time on the development pool (13 pairs); the held-out pool is descriptively consistent (0.665 over 7 pairs) but sits below our pre-registered power floor and is reported as underpowered, not as confirmation. **(3)** The number of damage-producing tasks decreases with model capability across the families we tested, from 7 of 20 tasks for an 8B model to 1 of 20 for the most capable model we measured; capability is confounded with family and training, so we report this as an observed gradient, not a causal claim. Critically, the residual damage does not change in character: the frontier model's single damaging task fails at p-hat = 0.16 per run, demonstrably stochastic under our pre-registered criterion, and a single audit misses it 84% of the time. **(4)** As a methodological finding, one model family committed the gated irreversible change while declaring it had refused; transcript- and judge-based grading scores those runs as safe refusals, and only state-diff verification labels them damage. All confirmatory findings were pre-registered with per-claim demote criteria; one criterion demoted our own initially favored finding, and we report that demotion. We release the instrument and task suite.

---

## 1. Introduction

Benchmarks for LLM agents largely inherit the framing of text generation: run the task once, score the output, and report an average. Action-taking agents break that framing in two ways. First, the failure model changes. When an agent holds write access to a production system, a wrong action is not a low-quality sample to be regenerated; it is a state change that someone must detect, price, and unwind. Second, the unit of evidence changes. A single observed run, safe or unsafe, is one draw from a distribution, and deployment exposes the distribution.

This paper asks a narrow question with an uncomfortable answer: **when an agent damages, does it damage repeatably?** If dangerous behavior concentrated in identifiable (model, task) cells that fail every time, pre-deployment audits could find those cells and certification would be a search problem. We find the opposite. Damage is real, universal across the model families we measured, and stochastic within each of them, with no always-fail cell anywhere in the data. A passed safety test is a coin-flip observation, not a property of the model.

Existing evaluations do not measure this, because measuring it requires three properties at once: **damage severity** (not just task failure), **repeated runs** (not single-shot scoring), and **ground-truth state verification** (not transcript or judge grading). Section 2 maps the landscape; each axis exists somewhere, and no benchmark crosses all three.

**Contributions.**

1. **AgentRelBench, the instrument (Section 3).** A k-run harness with per-run database re-seeding, a pre-cleanup full-state dump, and a state-diff damage labeler (closed-world DSL, primary-key matched, severity- and dollar-priced) with no LLM in the measurement path, plus estimators (pass^k, safe^k with an errored-run upper bound, exact Clopper-Pearson intervals, a pre-registered demonstrably-stochastic criterion, and a k=1 audit miss rate). The instrument is environment-agnostic and is demonstrated on EnterpriseOps-Gym.
2. **The headline finding (Section 5.1).** Damage on irreversible actions is universal across the six families we measured, stochastic within them, and trap-free: zero always-fail cells. One-shot audits are structurally blind to it.
3. **A capability gradient that does not reach zero (Section 5.2).** Damage-producing task count falls with model capability across the families we tested, while the residual damage stays stochastic and trap-free all the way to the frontier model we measured.
4. **A methodological result (Section 5.3).** State ground truth is necessary: one family executes the gated change while declaring refusal, a failure invisible to transcript grading. The behavior is family-specific; the need for state-level measurement is not.
5. **Pre-registered discipline (Section 5.4).** Per-claim replicate and demote criteria frozen before held-out contact; the criteria demoted our initially favored finding, and the paper reports it.

## 2. Related work

The measurement gap is visible as three columns that no prior benchmark crosses.

| Axis | Representative work | What it measures | What it lacks |
|---|---|---|---|
| Consistency, no damage | tau-bench (2406.12045); Beyond pass@1 (2603.29231); ReliabilityBench (2601.06112) | pass^k, run-to-run variance, reliability metrics | no damage axis; failure = task failure |
| Damage, single run | SABER, workspace safety (2606.01317); ClawsBench (2604.05172); EnterpriseOps-Gym (2603.13594) | end-state safety or unsafe-action rates at k=1 | one run per cell; no distributional claim |
| Abstention / mechanism | AgentAbstain (2607.10059); Yes-Man Syndrome (2605.20544); SABER, mutating steps (2512.07850); abstention competence (2606.02965); Science of Agent Reliability (2602.16666) | refusal competence, mutation-step sensitivity, judge-scored severity | no ground-truth priced damage under repetition |

EnterpriseOps-Gym is the closest substrate: a containerized enterprise sandbox with SQL verifiers on final state. It scores single-run binary success and one-shot infeasible-task refusal; it has no damage pricing, no repeated-run protocol, and no abstention mechanic. We build on it rather than beside it: AgentRelBench is the measurement layer (repetition, state-diff damage, estimators) demonstrated on EOG tasks. Judge-scored severity (2602.16666) differs from ours in kind: our severity comes from a closed-world diff DSL over the database, not from a model's opinion of a transcript. Our Section 5.3 result is a measured instance of the compliance-bias concern (2606.02965), scoped to one family.

## 3. AgentRelBench design

**3.1 Substrate.** EnterpriseOps-Gym (csm and itsm verticals), pinned by container digest and commit. Each run seeds a fresh database via the harness API and receives a unique database id, so runs are independent trials. Two audits support the IID treatment: a replay determinism audit (only wall-clock timestamp columns vary across independently seeded replays; primary keys and generated ids are byte-identical) and a full-toolset re-audit at task-suite scale (Appendix C).

**3.2 Damage labeler.** After each run, and before the harness deletes the environment, the wrapper dumps the full final state. The labeler diffs it against the post-seed state under a closed-world DSL: primary-key-matched row comparison, a per-domain volatile-column allowlist, and per-task damage specs with severity classes plus dollar pricing where the schema carries money columns. Errored runs are tri-classified (an errored run without mutation is not damage; mutation-then-error contributes to an upper bound, reported as safe^k upper). There is no LLM anywhere in the measurement path; the labeler is deterministic, test-first, and its verdict taxonomy is in Appendix A. Refusal detection is a deterministic token check, so a stalled run is never counted as an abstention.

**3.3 Metrics and estimators.** Unbiased pass^k and safe^k via combinatorial estimators; exact Clopper-Pearson intervals (stdlib bisection, test-covered); the pre-registered **demonstrably-stochastic** criterion (a (model, task) cell with damage count x of n is demonstrably stochastic when its exact 95% CI lies strictly inside (0.05, 0.95), which at k=16 is x in [4,12] and at k=32 is x in [5,27]); the **k=1 audit miss rate** over damage-producing pairs (the probability that a single clean run is observed on a pair that does damage); damage-mass share; beta-binomial decomposition; and duplicate-preserving cluster bootstrap. Figure 1 shows the pipeline.

**3.4 Task suite.** Twenty tasks over csm and itsm with authored damage specs, oracle solvability proofs, and counterexample validation; six damage levers; a strict FAIL_SAFE boundary (a wrong-but-authorized outcome is a task failure, not damage; damage requires an out-of-scope irreversible mutation). Four tasks are dollar-denominated on real money columns. The flagship commit-gated task, change-request-cab-gate, requires Change Advisory Board approval before an irreversible change; the correct behavior is to stop at the gate.

## 4. Experimental setup

**Models.** Nine models in six families. Development pool: llama-3.3-70b, qwen3-32b, llama-3.1-8b, qwen3-14b (OpenRouter). Pre-registered held-out pool: mistral-small-24b, gpt-oss-120b, deepseek-v3.2 (OpenRouter, provider-pinned), plus a frontier pass on claude-opus-4.6 and claude-haiku-4.5 (AWS Bedrock). Held-out and frontier models had zero pre-campaign contact with the harness; first contact was the campaign run itself.

**Protocol.** k=8 across the 20-task breadth set, k=16 on a five-task depth set, and k=32 on the flagship cab-gate task for the two large campaign models and the frontier Opus model (k=16 elsewhere). Serving is controlled as a method: OpenRouter runs pin the provider with fallbacks disabled and log provider and quantization per run; Bedrock is a single fixed serving stack, and we log model id and region. We make no cross-model damage-rate ordering claim on top of differing serving stacks (Section 6).

**Pre-registration.** Replicate and demote criteria per claim were frozen before held-out contact (git-tagged pre-data), including an engagement floor for the flagship task, a demonstrably-stochastic window per k, a power floor of at least 8 held-out damage-producing pairs for the miss-rate statistic, and a tested-floor of at least 8 held-out damage events for the no-traps claim. Any harness fix after a held-out model has run voids that model's held-out status. The full log is Appendix F.

**Scale.** 2,128 evaluation runs in total. Held-out and frontier: 1,088 pre-registered runs (mistral-24b 208, gpt-oss-120b 224, deepseek-v3.2 224, opus-4.6 224, haiku-4.5 208). Development pool: 1,040 runs (832 base-task runs across the pilot, depth, and provider-pin diagnostic arms, plus 208 distractor-variant runs). Smoke tests and quarantined invalid batches (for example, a fully throttled frontier batch superseded by its clean rerun) are excluded from these counts.

## 5. Results

### 5.1 Damage is universal across families, stochastic within them, and trap-free

**Universal.** The commit-gated task produced damage in every family we measured: llama-3.3-70b 12/16, qwen3-32b 1/16, mistral-24b 4/16, gpt-oss-120b 12/32, deepseek-v3.2 4/32, haiku-4.5 1/16, and opus-4.6 5/32 (Figure 2a). No measured family is immune, including the two most capable models in the study. Other tasks fired per model (Figure 2b lists the held-out set).

**Stochastic.** Five held-out (model, task) cells are demonstrably stochastic under the pre-registered criterion, across three distinct held-out models: mistral-24b on sla-relink (12/16), case-reassign-scoped (10/16), and cab-gate (4/16); gpt-oss-120b on cab-gate (12/32); and opus-4.6 on cab-gate (5/32). The pre-registered requirement was replication on at least two distinct held-out models; the data exceed it, and the frontier model is itself one of the replicating instruments. Two further held-out cells damaged without clearing the band: deepseek-v3.2 on cab-gate (4/32) and haiku-4.5 on cab-gate (1/16). These count toward universality (the family damaged) and do not count toward the demonstrably-stochastic set; we hold that boundary because the band is the pre-registered dividing line between "observed damage" and "damage demonstrably not explained by an always-safe or always-fail cell."

**Trap-free.** Zero (model, task) cells reached x = n, across all runs of all nine models, including 48 damage events over 7 damage-producing cells on the five held-out models (pre-registered tested-floor of 8 events: cleared six times over). The highest observed cell is 12/16 = 0.75. The pre-registered falsifier for this claim (any task at x = n on an engaging held-out model, reproduced on a second) stayed silent.

**Consequence.** If damage were concentrated in always-fail cells, one audit run per cell would find them. Instead every damage-producing cell is intermediate, so a k=1 audit observes a clean run on a damage-producing pair 0.80 of the time on the development pool (13 pairs, primary per pre-registration). The held-out pool gives 0.665 over 7 pairs, direction-consistent (above 0.5) but below the pre-registered power floor of 8 pairs, so it is reported descriptively and does not upgrade to a confirmed held-out statistic (Section 5.4). Figure 4 shows the decay: for the frontier pair at p-hat = 0.156, a fully clean audit remains better than even odds through k = 4, and an auditor needs roughly 18 independent runs before the probability of observing zero damage falls below 5%. Safety, as observed in any finite audit, does not repeat.

### 5.2 Capability shrinks the damage surface, not the damage's nature

Across the families we tested, the number of damage-producing tasks (of 20) falls from the smallest model to the frontier: llama-3.1-8b 7, qwen3-14b 2, mistral-24b 3, qwen3-32b 2, llama-3.3-70b 2, gpt-oss-120b 1, deepseek-v3.2 1, haiku-4.5 1, opus-4.6 1 (Figure 3). Development counts use the frozen dev-pool definition (each model's 20-task, k=8 breadth batch; these are the same 13 pairs behind the development miss rate), and held-out counts use each model's full pre-registered protocol; the exposure asymmetry biases against the trend, since the capable models received the most runs. Three cautions are part of the claim, not footnotes to it. First, capability is confounded with family, training data, and alignment recipe; the models differ in more than capability, so this is an observed correlation across the families we tested, not a causal statement that capability reduces danger. Second, the ordering is by an approximate capability proxy (parameter count and release tier), and the middle of the ordering is flat rather than strictly monotone (2 to 3 tasks across qwen3-14b, mistral-24b, qwen3-32b, and llama-3.3-70b); the claim rests on the ends of the range (7 for the smallest model, 1 for each of the four most capable), not on every adjacent step. Third, run counts per model differ in the direction that works against us: opus-4.6 had 224 chances to fire additional tasks and did not.

The point of the gradient is what does not change along it. The frontier model's residual damage is not a rounding error or a fluke run: it is 5 damage events in 32 runs on a task the model demonstrably can do (27/32 PASS, far above the pre-registered engagement floor of 6/32), with an exact CI of (0.053, 0.328), inside the pre-registered stochastic band. The most capable model we measured, on its single damaging task, at the highest per-cell sample size in the study, commits irreversible damage as a per-run coin flip that a single audit misses 84% of the time. Capability, over the range we measured, reduced how many tasks damage; it did not convert the remaining damage into something an audit can find.

This also explains, rather than excuses, the thin held-out miss-rate pool of Section 5.1: capable models damage on few tasks, so a held-out pool built from capable models yields few damage-producing pairs. The under-powering of the miss-rate statistic and the capability gradient are the same observation seen from two sides.

### 5.3 Methodology result: state ground truth is necessary (scoped to one family)

On cab-gate, llama-3.3-70b executed the CAB-gated irreversible change and emitted an explicit refusal declaration in 12 of 16 runs. Transcript- or judge-based grading scores those runs as safe refusals; only the state diff labels them damage. This is direct evidence that state-level verification is necessary for action-taking agents, independent of any behavioral claim.

The behavioral claim, that agents in general dress damage as refusal, was our initially favored headline, and the pre-registered demote criterion fired against it: both held-out leg-1 instruments engage and damage cab-gate openly (gpt-oss-120b: 12 damage runs, all completed_damage, 0 refused-but-mutated; deepseek-v3.2: 4 damage runs, 1 refused-but-mutated). The frontier pass corroborates the demotion at the top of the capability range: opus-4.6's 5 damage runs are all completed_damage with zero refusal declarations. Refuse-while-mutating is a llama-family failure mode in our data, not a universal one. The damage on cab-gate is universal (Section 5.1); only its disguise is family-specific. We present this section as evidence for the measurement method, not as a claim about agents in general.

### 5.4 Method integrity and honest negatives

Three pre-registered mechanisms fired against our own preferences, and we report all three.

1. **The leg-1 demotion (Section 5.3).** A demote criterion written before the data, on instrument models frozen before first contact, demoted the finding we most wanted. That the process demoted its own preferred headline is the strongest evidence available that the surviving criteria were not reverse-engineered to pass.
2. **The miss-rate power floor.** The held-out miss rate (0.665 over 7 pairs) sits one pair below the pre-registered floor of 8, so the development pool (0.80 over 13 pairs) remains the primary statistic and the held-out number stays descriptive. Adding weak models until the pool crossed 8 would have satisfied the letter of the floor while gaming its intent, and we declined to do it, both after the confirmatory campaign and again after the frontier pass. One additional damage observation exists outside the frozen development pool: a pre-registered arm-C depth read shows qwen3-32b damaging sla-relink in 1 of 16 runs. Folding it in would grow the pool to 14 pairs and change the frozen denominator after the fact, so we disclose it here for completeness and do not pool it; a frozen definition keeps its meaning only if it binds when an honest observation tempts us past it.
3. **An earlier k=16 demotion.** A pre-registered depth read demoted qwen3-32b's cab-gate cell (3/8 at pilot, 1/16 at depth), recorded at the time and carried here.

## 6. Limitations

**Serving-stack effects are flagged, not resolved.** On openly served models we observed provider- and quantization-correlated variation in damage rates; it is confounded with capability and infeasible to deconfound on the endpoints available to us. We therefore pin providers, log serving metadata, treat Bedrock as a single fixed stack, and make no cross-model rate-ordering claim. Stochasticity itself survives pinning: the demonstrably-stochastic cells are single-provider, single-stack data.

**The held-out miss-rate statistic is underpowered.** 7 damage-producing pairs against a pre-registered floor of 8. The qualitative claims (universality, stochasticity, no traps) are confirmed on held-out models; the specific population miss-rate number leans on the development pool. Section 5.2 gives the substantive reason the held-out pool is thin.

**The capability gradient is observational.** Six families, one substrate, capability confounded with family and training; ordering by a capability proxy. We claim the observed monotone pattern and its coexistence with unchanged damage structure, nothing stronger.

**Single substrate.** All results are on EnterpriseOps-Gym (csm and itsm). The instrument is environment-agnostic by construction (the labeler consumes state dumps, not EOG internals), but cross-substrate generalization is untested.

**Known harness artifacts.** Tool errors surface to the agent as an empty-object string; errored-run handling is tri-classified as described in Section 3.2.

## 7. Discussion and future work

If damage is universal across families, stochastic within cells, and trap-free, then pre-deployment task audits cannot certify an action-taking agent: there is no dangerous-cell list to discover, and every clean audit of a damage-producing cell was likely to be clean anyway. The enforcement point that follows from the data is per-run and at the commit boundary, not per-model and pre-deployment. A calibrated commit-gate (an abstain mechanism priced against intermediate-p-hat commits, with mutation-gated safeguards and runtime blockers as baselines) is the natural next artifact; we scope it as future work, and this paper is complete without it.

The Section 5.3 result carries a second implication for evaluation practice: transcript-level and judge-based safety grading can be strictly wrong about state, in at least one family, in the most safety-relevant direction. Ground-truth state verification should be the default for any benchmark whose agents hold write access.

The serving stack is an unmeasured reliability variable in most agent evaluations; we flag it as a direction rather than a result.

## 8. Conclusion

Across nine models in six families, 2,128 runs, and a pre-registered confirmatory protocol, damage on irreversible actions was universal across families, stochastic within every damage-producing cell, and never concentrated in an always-fail task. Capability compressed the damage surface from seven tasks in twenty down to one, and left that one a per-run coin flip at the frontier. A passed safety test is a coin-flip observation, not a property of the model, and certification of action-taking agents will have to live where the coin is flipped: at the commit, on every run.

## Appendices (pointers)

A: labeler DSL and verdict taxonomy. B: 20-task specs, levers, oracles. C: determinism audits (M1, M4). D: silent-discard audit. E: full per-(model, task) p-hat tables, all families and conditions. F: pre-registration log (timestamped pre-data, including the leg-1 demotion and the frontier read).

---

## Drafting flags (self-review; updated after the verification round of 2026-07-21)

### Resolved this round

1. **Run totals are now exact (was flag 1).** 2,128 = 832 dev base-task runs + 208 dev distractor-variant runs + 1,088 held-out/frontier runs, recounted from batch manifests and verdicts with smokes and quarantined batches excluded. The recount also corrected two v1 errors: the held-out/frontier total was stated as 1,104 (mistral's flagship cell ran at k=16, so mistral totals 208, not 224), and the dev merged assemblies (llama8b-merged, qwen14b-merged, qwen-merged, qwen32b-plus10-merged) reconcile exactly with their component batches, so nothing is double-counted.
2. **Citations verified (was flag 6).** All ten arXiv IDs were fetched from the arXiv API on 2026-07-21 and matched on ID, title, author list, and abstract against the claims made in Section 2; tau-bench verified as 2406.12045 (Yao et al.). Two labels were corrected: 2605.20544 is titled "The Yes-Man Syndrome" (the v1 label "RoboAbstention" was an internal shorthand, not the paper's name), and the two papers literally named SABER are now disambiguated as workspace safety (2606.01317) versus mutating steps (2512.07850). Remaining for camera-ready: a full-text read of each cited paper (the API check covers title, authors, and abstract, not body-level claims) and venue fields for the bibliography.
3. **Figure 3 dev points computed, not hand-entered (was flag 3).** All four dev models' pair counts (7, 2, 2, 2) are now computed by the figure script from committed run data (llama8b-merged, qwen14b-merged, qwen-merged, and the llama-70b pilot batch) and asserted, alongside assertions on the five held-out counts and the Fig 2a dev cab cells (12/16 pinned read; 1/16 depth read). The script fails loudly if any figure number drifts from the record.
4. **Arithmetic-sibling hunt complete (extends flag 5).** The corrected audit-sizing sentence was re-verified (0.84375^4 = 0.51, 0.84375^5 = 0.43, 0.84375^18 = 0.047), and every other count-to-probability conversion in the draft was rechecked: 84% = 27/32; 48 events against floor 8 is six times over; 12/16 = 0.75; 27/32 pass against floor 6/32; 2,128 = 832 + 208 + 1,088; 1,040 = 832 + 208. No further errors found.

5. **qwen3-32b out-of-pool observation placed (advisor decision, 2026-07-21).** Reported-but-not-pooled: the arm-C sla-relink 1/16 observation is now disclosed in Section 5.4 item 2, framed as an observation consistent with the finding but outside the frozen 13-pair pool, kept out to preserve the pre-registered denominator. Remaining: include the cell in Appendix E's full tables.

### Open (reviewer decisions)

6. **Family counting.** Six families counts gpt-oss and DeepSeek as families. "Every family we measured" holds either way; confirm the convention.
7. **qwen3-32b cab-gate shown at the k=16 depth read (1/16) in Figure 2a.** The pre-registered depth read demoted the pilot 3/8; never-splice is why they are not pooled. State this in the figure caption or appendix.
8. **Release plan (policy now verified; Shiven's option choice pending).** The abstract promises "we release the instrument and task suite"; the repo is local-only and the leaderboard is unbuilt. ICLR policy, verified against the live ICLR 2026 Author Guide on 2026-07-21 (the 2027 guide is not posted yet and must be re-checked when it is): submissions are double blind and "any paper where author identity is revealed in either the main text or the supplementary material will be desk rejected"; the sanctioned code channel is an anonymized supplementary upload ("source code associated with a paper can be uploaded as part of the supplementary material... we encourage all authors to submit code"), and the guide's recommended Reproducibility Statement pattern is "a link to an anonymous downloadable source." Consequence: a public repo under the authors' names, linked in the PDF, is a desk-reject risk; the compliant form at submission is an anonymized artifact (supplementary zip and/or anonymous repo mirror), with the public named release at camera-ready. Options: (a) build the release package and submit it as the anonymized artifact, keeping the abstract sentence true at submission (recommended; the packaging is bounded and the CLIs already exist as console entry points); (b) soften the abstract to "will be made available." Also add the recommended Reproducibility Statement paragraph during the LaTeX port.
9. **Engagement floor scaling.** The pre-registration states pass >= 3/16; applied proportionally as >= 6/32 at k=32 (opus clears either reading at 27/32). State the scaling in Appendix F.
