# Skill: list_files

## Description
Lists files in a directory to help with navigation and file discovery.

## Parameters
- `path` (string): The directory path to list. Defaults to current directory.

## Steps
1. **Step: exec**
   - `command`: `ls -F {{path}}`
   - **Output:** `file_list`

2. **Output**
   - **Value:** 
```
Contents of {{path}}:

{{file_list}}
```
