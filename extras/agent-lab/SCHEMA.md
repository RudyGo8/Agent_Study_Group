# Agent Trajectory JSON Schema

A trajectory is a recording of one Agent run, used by the `<agent-trajectory>`
Web Component to replay the ReAct loop step by step in the browser.

The schema mirrors the `_emit(...)` calls in
[`chapter1/web-search-agent/agent.py`](../../chapter1/web-search-agent/agent.py)
so a real run can be exported into this format with almost no transformation.

## Top-level object

```jsonc
{
  "$schema": "../SCHEMA.md",
  "experiment":  "ch1/web-search-agent",      // stable id, matches chapter/<exp>
  "title":       "GPT-5.6 解「东盟 10 国首都最近距离」",
  "model":       "gpt-5.6-sol",
  "task":        "东盟 10 国首都之间，最近的一对首都距离多少？",
  "condition":   "full-context",              // ablation condition, optional
  "outcome":     "success",                   // success | failure | loop | timeout
  "tags":        ["deep-research", "code-interp"],
  "recorded_at": "2026-07-20T14:32:08Z",
  "steps":       [ /* see below */ ]
}
```

## Step types

Every step has `iteration` (1-based) and `type`. The remaining fields depend
on `type`. The four types correspond exactly to ReAct: Reasoning / Acting /
Observing / final Answer.

### `thought` — model's internal reasoning

```jsonc
{
  "iteration": 1,
  "type":      "thought",
  "content":   "需要先找出东盟 10 国首都的名称，再查每对首都的距离……"
}
```

`content` comes from the model's `reasoning_content` field (Kimi K3, GPT-5
Reasoning, Claude thinking, …). May be long — the UI collapses it.

### `action` — model called a tool

```jsonc
{
  "iteration": 1,
  "type":      "action",
  "tool":      "$web_search",
  "args":      { "query": "东盟 ASEAN 10 国首都 列表" }
}
```

`tool` is the tool name; `args` is the parsed argument object.

### `observation` — tool returned a result

```jsonc
{
  "iteration": 1,
  "type":      "observation",
  "tool":      "$web_search",
  "content":   "东盟 10 国首都：雅加达、曼谷、吉隆坡、新加坡、马尼拉……"
}
```

For long results (search hits, code output), the UI shows a truncated view
with a "show full" toggle.

### `answer` — final user-facing answer

```jsonc
{
  "iteration": 3,
  "type":      "answer",
  "content":   "最近的一对首都是雅加达—吉隆坡，约 1184 km。"
}
```

Only one `answer` step per trajectory; it ends the replay.

## Conventions

- **Iteration counter** is the LLM call index (1-based), not the step index.
  A single iteration may emit thought + action + observation (3 steps).
- **No PII / no API keys.** Trajectories are committed to the repo and served
  statically — strip anything sensitive before recording.
- **Keep it representative.** Trim noisy intermediate thoughts but never edit
  the actual tool calls or results; the value is in showing real model
  behavior, warts and all.
