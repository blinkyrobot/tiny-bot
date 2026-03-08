# Skill: list_relevant_skills

## Description
Lists all available skills and identifies which ones are most relevant to the user's current need.

## Parameters
- `query` (string): A description of the task or need for which you are looking for a skill.

## Steps
1. **Step: exec**
   - `command`: `ls skills/*.md agents/{{agent_key}}/skills/*.md 2>/dev/null`
   - **Output:** `skills_files`

2. **LLM**
   - **System Prompt:** You are a helpful assistant that identifies relevant skills for a robot assistant.
   - **Prompt:**
```
The robot assistant needs to know which skills are available to help with: "{{query}}"

Here are the available skill files in the 'skills/' directory:
{{skills_files}}

Please provide a complete list of all these skills. For each skill, briefly describe what it likely does based on its filename. Then, explicitly highlight which skill(s) are the MOST relevant to the specific query "{{query}}".
```
   - **Output:** `recommendations`

3. **Output**
   - **Value:** 
```
Available Skills and Recommendations for "{{query}}":

{{recommendations}}
```
