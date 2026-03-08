# Skill: create_skill

## Description

Creates a new skill from a natural language description. This skill is used to generate the `.md` file for other skills.

## Parameters

-   `skill_name` (string): The name for the new skill (e.g., 'rename_file').
-   `skill_description_prompt` (string): A detailed natural language description of what the skill does, its parameters, and its steps.

## Steps

1.  **LLM**
    -   **System Prompt:** 
        ```
        You are an expert system that designs and creates skills for an AI agent. Your task is to convert a user's natural language description of a skill into a structured Markdown format. The user will provide a description, and you must generate a valid Markdown file that follows the schema precisely.

        ### SKILL MARKDOWN SCHEMA ###
        # Skill: [skill_name]

        ## Description

        [skill_description]

        ## Parameters

        - `param1` (string): [description]
        - `param2` (string): [description]

        ## Steps

        1. **Step: [tool_name]**
           - `arg1`: `{{param1}}`
           - **Output:** `output_key1`

        2. **LLM**
           - **System Prompt:** [system_prompt]
           - **Prompt:**
             ```
             [prompt]
             ```
           - **Output:** `output_key2`

        3. **Output**
            - **Value:** `[final_output_message]`
        ```
    -   **Prompt:**
        ```
        Based on the schema and example provided, please generate the Markdown for the following user request. ONLY output the raw Markdown, with no other text, explanation, or markdown formatting.

        USER REQUEST: {{skill_description_prompt}}
        ```
    -   **Output:** `new_skill_md_content`

2.  **Step: write**
    -   `path`: `skills/{{skill_name}}.md`
    -   `content`: `{{new_skill_md_content}}`
    -   **Output:** `write_result`

3.  **Output**
    -   **Value:** `Successfully created the new skill: '{{skill_name}}'. You can now use it by calling \`execute_skill(skill_name='{{skill_name}}', ...)\`.`
