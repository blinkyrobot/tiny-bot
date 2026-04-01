# Skill: update_journal

## Description
Appends a new Bayesian update block to an existing journal entry.

## Parameters
- `journal_topic` (string): The topic of the journal.
- `output_filename` (string): The target filename.
- `scout_report` (string): The research data to use.
- `current_entry` (string): The existing content of the journal.

## Steps

1. **LLM**
   - **System Prompt:** You are a Bayesian Probability Journal assistant. Generate an UPDATE block based ONLY on the provided scout report and the context of the current entry.
   - **Prompt:**
```
TOPIC: {{journal_topic}}
CURRENT ENTRY:
{{current_entry}}

SCOUT REPORT:
{{scout_report}}

Generate an update block using the template below. 
Use ONLY data from the SCOUT REPORT. Provide citations/URLs.

**UPDATE TEMPLATE:**
[YYYY-MM-DD]:
- **Trigger**: [Brief summary of the new data/event with citations]
- **Adjustment**: [How this changes the view on the Hypothesis, Prior P(H), or Lead Indicators]
- **Status**: [Maintain / Upgrade / Downgrade P(H)]
---
```
   - **Output:** `update_content`

2. **Tool: write**
   - `path`: `agents/bpj/journal/{{output_filename}}`
   - `content`: `{{update_content}}`
   - `append`: `True`

3. **Tool: exec**
   - `command`: `python3 agents/bpj/generate_dashboard.py`
