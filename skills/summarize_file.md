# Skill: summarize_file

## Description

Reads a file and generates a concise summary of its content.

## Parameters

-   `file_path` (string): The path to the file to be summarized.

## Steps

1.  **Step: read**
    -   `path`: `{{file_path}}`
    -   **Output:** `file_content`

2.  **LLM**
    -   **System Prompt:** You are a specialized summarization assistant.
    -   **Prompt:**
        ```
        Please provide a concise summary of the following content:

        {{file_content}}
        ```
    -   **Output:** `summary`

3.  **Output**
    -   **Value:** `{{summary}}`
