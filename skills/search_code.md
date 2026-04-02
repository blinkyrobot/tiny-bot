# Skill: search_code

## Description
Searches the codebase for a specific pattern or keyword using grep.

## Parameters
- `query` (string): The pattern or keyword to search for.
- `path` (string): The directory or file path to search within. Defaults to current directory.

## Steps
1. **Step: exec**
   - `command`: `grep -rn -C 2 "{{query}}" {{path}}`
   - **Output:** `search_results`

2. **Output**
   - **Value:** 
```
Search results for "{{query}}" in {{path}}:

{{search_results}}
```
