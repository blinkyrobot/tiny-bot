# Skill: web_search_technical

## Description

Perform a web search for technical queries and return a high-signal summary with 2026-era insights.

## Parameters

- `query` (string): The search query to look for on the web.

## Steps

1. **Skill: web_search_raw**
    - `query`: `{{query}}`
    - `site_filters`: `(site:x.com OR site:reddit.com OR site:github.com OR site:news.ycombinator.com)`
    - **Output:** `search_results`

2. **LLM**
    - **System Prompt:** You are a senior technical analyst providing 2026-era insights. You prioritize high-signal sources like GitHub, X (Twitter), Reddit, and Hacker News. Your summaries are dense, technical, and focused on current trends, architectural shifts, and practical data.
    - **Prompt:** 
```
Below are raw search results for the technical query: "{{query}}".
Filter out low-signal "SEO-optimized" fluff and focus on insights from X, Reddit, GitHub, and HN.
Synthesize the results into a high-density technical summary. 
Look for 2026-era developments, including recent model improvements, API changes, and emerging patterns.

SEARCH RESULTS (JSON):
{{search_results}}

TECHNICAL ANALYSIS:
```
    - **Output:** `technical_analysis`

3. **Output**
    - **Value:** 
```
Technical Analysis for "{{query}}":

{{technical_analysis}}
```
