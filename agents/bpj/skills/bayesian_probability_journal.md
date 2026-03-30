# Skill : bayesian_probability_journal

## Description
Perform research, create or provide update on a bayesian probability journal topic.

## Parameters
- `journal_topic` (string): The main topic or hypothesis for the journal entry.
- `output_filename` (string): The filename for the generated or updated entry (e.g., `ai-risk-2026.md`).

## Steps

### Case 1: User asks for an update
1. **Step: read**
   - `path`: `agents/bpj/journal/{{output_filename}}`
   - **Output:** `current_entry`

2. **Step: spawn_subagent**
   - `task`: "Search/scout for the latest signals and data related to {{journal_topic}}."
   - **Output:** `scout_report`

3. **Step: write**
   - `path`: `agents/bpj/journal/{{output_filename}}`
   - `append`: `True`
   - `content`:
```
[YYYY-MM-DD]:Trigger: [Brief summary of the new data/event based on {{scout_report}}]
Adjustment: [How this changes the view on the Hypothesis, Prior P(H), or Lead Indicators]
Status: [Maintain / Upgrade / Downgrade P(H)]
```

### Case 2: User asks for a new entry
1. **Step: spawn_subagent**
   - `task`: "Search/scout for the latest signals and data related to {{journal_topic}} to initialize a new journal entry."
   - **Output:** `scout_report`

2. **Step: write**
   - `path`: `agents/bpj/journal/{{output_filename}}`
   - `append`: `False`
   - `content`:
```
| Journal Entry Field     | BPJ Entry: [{{journal_topic}}]              |
|-------------------------|---------------------------------------------|
| **Hypothesis (H)**      | [Detailed Hypothesis based on {{scout_report}}] |
| **Prior P(H)**          | [Probability estimate and justification]    |
| **Lead Indicator 1**    | [Indicator description]                     |
| **Lead Indicator 2**    | [Indicator description]                     |
| **Structural Isomorphism** | [Historical analogy/parallel]            |
| **The Bayesian Lever**  | [The critical event that updates P(H)]      |
| **Gated Complexity**    | [Non-obvious, second-order effects]         |
| **Alpha Move**          | [Actionable investment/strategy]            |
```

## Journal Maintenance (Mandatory Rules)
- **Always append** new updates to the end of the existing journal file — never overwrite (except when creating the new base file).
- **Timestamp**: Use the shell command `date +%Y-%m-%d` to get the current date.

## Dashboard Sync
After every journal entry creation or update, automatically run:
```bash
python3 agents/bpj/generate_dashboard.py
```
