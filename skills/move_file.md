# Skill: move_file

## Description
Moves or renames a file safely using the `mv` command.

## Parameters
- `source` (string): The path to the source file.
- `destination` (string): The destination path or filename.

## Steps
1. **Step: exec**
   - `command`: `mv "{{source}}" "{{destination}}"`
   - **Output:** `move_result`

2. **Output**
   - **Value:** 
```
Move operation result:

{{move_result}}
Moved {{source}} to {{destination}}.
```
