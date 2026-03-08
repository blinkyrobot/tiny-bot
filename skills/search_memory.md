# Skill: search_memory

## Description

Search the agent's persistent memory file for a specific keyword or pattern to retrieve historical context.

## Parameters

- `query` (string): The keyword or regex pattern to search for in the memory.
- `path` (string): The path to the memory file (e.g., agents/chat/memory.md).

## Steps

1. **Step: exec**
    - `command`: `grep -i -C 2 "{{query}}" {{path}}`
    - **Output:** `search_results`

2. **Output**
    - **Value:** 
```
Search results for "{{query}}" in {{path}}:

{{search_results}}
```
