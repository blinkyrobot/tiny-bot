# Skill: create_file_with_summary

## Description

Reads a source file, generates a summary of its content, and writes the summary to a new destination file.

## Parameters

-   `source_file` (string): The path to the file to be read and summarized.
-   `destination_file` (string): The path where the summary will be saved.

## Steps

1.  **Step: read**
    -   `path`: `{{source_file}}`
    -   **Output:** `source_content`

2.  **LLM**
    -   **System Prompt:** You are a specialized summarization assistant.
    -   **Prompt:**
        ```
        Please provide a concise summary of the following content:

        {{source_content}}
        ```
    -   **Output:** `summary`

3.  **Step: write**
    -   `path`: `{{destination_file}}`
    -   `content`: `{{summary}}`
    -   **Output:** `write_result`

4.  **Output**
    -   **Value:** `Successfully created summary of {{source_file}} in {{destination_file}}.`
