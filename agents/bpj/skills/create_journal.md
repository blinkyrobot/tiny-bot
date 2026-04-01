# Skill: create_journal

## Description
Initializes a new Bayesian Probability Journal entry with a structured table.

## Parameters
- `journal_topic` (string): The topic of the journal.
- `output_filename` (string): The target filename.
- `scout_report` (string): The research data to use.

## Steps

1. **LLM**
   - **System Prompt:** You are a Bayesian Probability Journal assistant. Generate a NEW journal entry based ONLY on the provided scout report.
   - **Prompt:**
```
TOPIC: {{journal_topic}}
SCOUT REPORT:
{{scout_report}}

Generate a NEW journal entry using the template below. 
Use ONLY data from the SCOUT REPORT. Provide citations/URLs.

**NEW ENTRY TEMPLATE:**
| Journal Entry Field     | BPJ Entry: [{{journal_topic}}]              |
|-------------------------|---------------------------------------------|
| **Hypothesis (H)**      | [Detailed Hypothesis based on scout report] |
| **Prior P(H)**          | [Probability estimate and justification]    |
| **Lead Indicator 1**    | [Indicator description]                     |
| **Lead Indicator 2**    | [Indicator description]                     |
| **Structural Isomorphism** | [Historical analogy/parallel]            |
| **The Bayesian Lever**  | [The critical event that updates P(H)]      |
| **Gated Complexity**    | [Non-obvious, second-order effects]         |
| **Alpha Move**          | [Actionable investment/strategy]            |
```
   - **Output:** `final_content`

2. **Tool: write**
   - `path`: `agents/bpj/journal/{{output_filename}}`
   - `content`: `{{final_content}}`
   - `append`: `False`

3. **Tool: exec**
   - `command`: `python3 agents/bpj/generate_dashboard.py`
