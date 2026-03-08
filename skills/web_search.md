# Skill: web_search

## Description

Perform a general web search and return a concise summary of the findings.

## Parameters

- `query` (string): The search query to look for on the web.

## Steps

1. **Skill: web_search_raw**
    - `query`: `{{query}}`
    - `site_filters`: ``
    - **Output:** `raw_search_json`

2. **LLM**
    - **System Prompt:** You are a helpful assistant that summarizes web search results into a concise list of news headlines and key details.
    - **Prompt:** 
```
Below are the search results for the query: "{{query}}".
Please extract and summarize the most relevant news headlines and key information from these results. 
If there are dates or timestamps, prioritize the most recent information.

SEARCH RESULTS (JSON):
{{raw_search_json}}

SUMMARY:
```
    - **Output:** `final_summary`

3. **Output**
    - **Value:** 
```
Summary of search results for "{{query}}":

{{final_summary}}
```
