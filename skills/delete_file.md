# Skill: delete_file

## Description
Deletes a file safely using the `rm` command.

## Parameters
- `path` (string): The path to the file to be deleted.

## Steps
1. **Step: exec**
   - `command`: `rm "{{path}}"`
   - **Output:** `delete_result`

2. **Output**
   - **Value:** 
```
Delete operation result:

{{delete_result}}
Deleted file: {{path}}.
```
