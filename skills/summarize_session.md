# Skill: summarize_session

## Description

Reads a session transcript from the `transcripts` directory, generates a concise summary, and appends it to the agent's dedicated memory file.

## Parameters

-   `session_transcript_path` (string): The path to the session transcript file (under the `transcripts` directory) to be summarized.
-   `destination_memory_path` (string): The path to the agent's memory file where the summary will be appended.

## Steps

1.  **Step: read**
    -   `path`: `{{session_transcript_path}}`
    -   **Output:** `transcript_content`

2.  **LLM**
    -   **System Prompt:** You are a specialized summarization assistant. Your task is to summarize provided text.
    -   **Prompt:**
```
Please provide a concise summary of the following session transcript. Focus on key decisions made, actions taken by the assistant, and important information discussed. The summary should be concise and well-structured, capturing the essence of the session's objectives and outcomes. Do NOT include phrases like 'Based on the content...' or 'The transcript shows...'. Just provide the summary directly.

--- SESSION TRANSCRIPT ---
{{transcript_content}}
--- END SESSION TRANSCRIPT ---
```
    -   **Output:** `generated_summary`

3.  **Step: write**
    -   `path`: `{{destination_memory_path}}`
    -   `append`: `True`
    -   `content`: 
```
## Session Summary ({{timestamp}})

{{generated_summary}}
---
```
    -   **Output:** `write_result`

4.  **Output**
    -   **Value:** `Skill 'summarize_session' executed successfully. Session summarized and appended to {{destination_memory_path}}.`
