# Choose the AI model per task, and adopt one only when it passes the False Exclusion benchmark

The app has three AI tasks with very different volume and risk: AI Suggestions (one per Citation opened, the bulk of calls), Full-Text Suggestions (few, long inputs, and they also propose Extraction Values) and Search Terms (rare).
Today all three share one setting, `ANTHROPIC_MODEL` (default `claude-haiku-4-5`, `backend/src/asr_backend/settings.py`).
We decided that the model is chosen per task, and that a task moves to a different model, including another vendor's or an open-weight one, only when that model matches or beats the current one on a benchmark led by False Exclusion rate and costs less, or brings a property we need (below).
Cost per call alone never justifies a switch, because a False Exclusion is the error a systematic review can least afford: an excluded Citation is rarely looked at again.

## The benchmark

- Inputs: the SYNERGY labeled reviews (the same data as the ranking spike, #114), plus reviews the product owner has adjudicated, kept as a holdout that is never used for prompt tuning.
- Run every candidate with the same prompt and tool schema the app sends for that task.
- Report, per task and model: False Exclusion rate (with denominator), overall agreement with the reference, parse failures, cost per 1,000 Citations from provider-reported usage (#113), and latency.
- Full-Text Suggestions are also scored on Extraction Values (missing or unsupported values per field), since that task does more than decide.
- A domain reviewer sets the acceptable False Exclusion threshold before any scoring, as roadmap #88 requires.

## Properties that can justify a switch besides cost

- **Reproducibility.** Hosted models are retired on the vendor's schedule, so a review screened today cannot be re-run with the same model later. A pinned open-weight model can, which matters for methods reporting.
- **Data residency.** An institution may require that abstracts and PDFs never leave infrastructure it approves.
- **Vendor risk.** Price changes, outages or policy changes at a single provider.

## Considered Options

- **One model for every task** (today's setup): simplest, but it forces the high-volume, low-risk task and the low-volume, high-risk task onto the same cost/quality point.
- **Always the cheapest capable model**: rejected because "capable" was undefined; without a False Exclusion benchmark a cheaper model can quietly drop relevant studies.
- **A multi-provider abstraction library now** (for example LangChain): rejected for now. There are three call sites (`ai_suggestion.py` for AI and Full-Text Suggestions, `search_terms.py` for Search Terms), so moving one task to a new provider is a contained change, and a generic layer would add dependencies and hide provider-specific structured-output behavior that the tool schemas rely on.
- **Self-hosting an open-weight model on our own GPUs**: rejected at current scale; an always-on GPU costs more per month than the whole AI bill. Open-weight models served pay-per-token by a hosting provider remain a candidate under this ADR.

## Consequences

- `ANTHROPIC_MODEL` stays a single setting until the first task actually adopts a different model; that change splits it into one setting per task. No per-task configuration is built speculatively.
- Every persisted AI result records the model that wrote it (#68) and, once #113 lands, its token usage, so models can be compared on real traffic as well as on the benchmark.
- Changing models is not only a string change. The current code forces a specific tool call (`tool_choice={"type": "tool", ...}`), which newer Claude models and some other providers reject, so each switch includes adapting the structured-output call for that task and re-running its tests.
- A Review Project screened partly before and partly after a switch has AI Suggestions from two models. That is acceptable because AI Suggestions are advisory and each one names its model; it should be visible wherever AI accuracy is reported.
- The in-house ranking from #114, if it ships, is not covered here: it is not a language model and never proposes a Screening Decision.
