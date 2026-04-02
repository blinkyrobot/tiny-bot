# Skill: list_relevant_skills

## Description
Lists all available skills and identifies which ones are most relevant to the user's current need.

## Parameters
- `query` (string): A description of the task or need for which you are looking for a skill.

## Steps
1. **Step: exec**
   - `command`: `ls skills/*.md skills/*.py api/*.yaml agents/{{agent_key}}/skills/*.md 2>/dev/null`
   - **Output:** `skills_files`

2. **LLM**
   - **System Prompt:** You are a helpful assistant that identifies relevant skills and API manifests for a robot assistant.
   - **Prompt:**
```
The robot assistant needs to know which skills or API manifests are available to help with: "{{query}}"

Here are the available skill files and API manifests:
{{skills_files}}

Please provide a complete list of all these resources. For each resource, briefly describe what it likely does based on its filename and path (e.g., api/manifold.yaml provides access to prediction markets). Then, explicitly highlight which resources are the MOST relevant to the specific query "{{query}}".
```
   - **Output:** `recommendations`

3. **Output**
   - **Value:** 
```
Available Skills and Recommendations for "{{query}}":

{{recommendations}}
```
