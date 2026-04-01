def run(agent, parameters):
    query = parameters.get("query")
    site_filters = parameters.get("site_filters", "")
    is_technical = parameters.get("technical", False)
    
    if not query:
        return "Error: No query provided."

    # 1. Prepare query with filters
    full_query = query
    if site_filters:
        full_query = f"{query} {site_filters}"
    elif is_technical:
        full_query = f"{query} (site:x.com OR site:reddit.com OR site:github.com OR site:news.ycombinator.com)"

    # 2. Use the native tool to get raw results
    search_results = agent.dispatcher["web_search"](query=full_query)
    
    if "Error" in search_results:
        return search_results

    # 3. Use agent.ask for intelligence (Summarization)
    if is_technical:
        system_prompt = "You are a senior technical analyst providing 2026-era insights. Filter out low-signal 'SEO-optimized' fluff and focus on high-signal technical details."
    else:
        system_prompt = "You are a research assistant. Summarize the following web search results into a concise list of news headlines and key details."
        
    prompt = f"Below are the search results for the query: \"{full_query}\".\n\n{search_results}\n\nANALYSIS/SUMMARY:"
    
    summary = agent.ask(prompt, system_prompt=system_prompt)

    return f"Search Results for \"{query}\":\n\n{summary}"
