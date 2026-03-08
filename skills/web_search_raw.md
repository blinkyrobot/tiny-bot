# Skill: web_search_raw

## Description

Perform a web search using the Brave Search API via curl and return the raw JSON results. Optionally filter by specific sites.

## Parameters

- `query` (string): The search query to look for on the web.
- `site_filters` (string): Optional space-separated site filters (e.g., "site:x.com OR site:reddit.com").

## Steps

1. **Tool: exec**
    - `command`: `grep -A 2 '"search":' config.json | grep '"apiKey":' | cut -d'"' -f4`
    - `simple`: `true`
    - **Output:** `brave_api_key`

2. **Tool: exec**
    - `command`: `curl -s -G "https://api.search.brave.com/res/v1/web/search" --data-urlencode "q={{query}} {{site_filters}}" -H "Accept: application/json" -H "X-Subscription-Token: {{brave_api_key}}"`
    - `simple`: `true`
    - **Output:** `raw_search_json`

3. **Output**
    - **Value:** `{{raw_search_json}}`
