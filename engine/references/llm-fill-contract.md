# llm_fill contract (any model)

Give the model `discovery.json` and this prompt. It works unchanged with any model that can emit JSON.

```
You are given discovery.json, a deterministic scan of one application. Do not change or restate any value as
different from the file. Write a JSON object with exactly these keys and no others:
{
  "narrative": {"text": "<=120 words, plain English summary of where the app stands", "cites": ["<fact id>", ...]},
  "resolutions": [{"ambiguity_id": "<id from llm_fill.ambiguities>", "answer": "<short answer>", "cites": ["<fact id>"]}]
}
Rules: every claim in the narrative must be supported by a fact you list in "cites" (ids look like
"tests.coverage_state" or a maturity criterion id). Treat status UNKNOWN or NOT_FOUND as exactly that;
never guess. If you cannot answer an ambiguity from the file, omit it.
```

Then: `python3 {skill_path}/scripts/validate.py merge-llm discovery.json fill.json`.
The merge rejects extra keys, unknown ambiguity ids and cites that are not real fact or criterion ids, stamps
`source: "llm"`, and leaves `run_meta.fingerprint` unchanged (it covers facts only). The UI shows the narrative
under "Notes", labelled as model-written; it never feeds the maturity score.
