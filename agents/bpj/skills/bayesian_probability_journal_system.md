# Skill: bayesian_probability_journal_system

## Description

A comprehensive Bayesian Probability Journal system that orchestrates a GOVERNOR and specialized sub-agents (ESSAYIST, FORECASTER, LIBRARIAN, SCOUT) to generate and manage journal entries.

## Parameters

- `journal_topic` (string): The topic for the journal entry.
- `output_filename` (string): The filename for the generated entry (e.g., 'my_journal.md').

## Steps

1. **Skill: spawn_subagent**
    - `task_description`: `Orchestrate BPJ for {{journal_topic}}`
    - `initial_prompt`: 
```
You are the GOVERNOR. Orchestrate the creation of a Bayesian Probability Journal entry for: {{journal_topic}}.
You must delegate to specialized sub-agents:
1. SCOUT: Research the topic and provide an "evidence packet".
2. FORECASTER: Generate 3-5 SMART, falsifiable hypotheses with initial probabilities.
3. ESSAYIST: Synthesize research and forecasts into a 1000-2000 word objective, academic essay.
4. LIBRARIAN: Save the final essay to '{{output_filename}}' and provide a 200-word summary.

Follow the SEARCH DISCIPLINE: ONE-AND-DONE, TARGETED, IGNORE NOISE, VERIFY.
```
    - `required_tools`: `["execute_skill", "read", "write", "exec"]`
    - **Output:** `final_report`

2. **Journal Maintenance**
    - **Update Protocol**: All journal updates must follow these mandatory rules:
        - **Append**: Always append updates to the end of the original journal entry file.
        - **Timestamp**: Use the shell command `date +%Y-%m-%d` to fetch the current date for the update timestamp.
        - **Format**: Use the following structure:
```markdown

---
### Updates & Revisions

**[YYYY-MM-DD]**: 
- **Trigger**: [Brief summary of the new data/event]
- **Adjustment**: [How this changes your view on the Hypothesis, Prior P(H), or Lead Indicators]
- **Status**: [Maintain/Upgrade/Downgrade P(H)]
```

3. **Output**
    - **Value:** 
```
### Bayesian Probability Journal System Result

{{final_report}}
```
