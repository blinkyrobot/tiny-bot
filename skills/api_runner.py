import requests
import json
import yaml
import os
import re

def run(agent, parameters):
    service_name = parameters.get("service")
    action_name = parameters.get("action")
    user_params = parameters.get("params", {})

    if not service_name or not action_name:
        return "Error: Both 'service' and 'action' parameters are required."

    # 1. Load the manifest
    tinybot_src = os.environ.get("TINYBOT_SRC", ".")
    manifest_path = os.path.join(tinybot_src, "api", f"{service_name}.yaml")
    
    if not os.path.exists(manifest_path):
        return f"Error: API manifest for service '{service_name}' not found at {manifest_path}."

    with open(manifest_path, "r") as f:
        manifest = yaml.safe_load(f)

    # 2. Find the endpoint
    endpoints = manifest.get("endpoints", {})
    if action_name not in endpoints:
        return f"Error: Action '{action_name}' not defined for service '{service_name}'. Available: {list(endpoints.keys())}"
    
    endpoint = endpoints[action_name]

    # 3. Resolve dynamic values (from user_params or secrets)
    def resolve(text):
        if not isinstance(text, str): return text
        
        # Priority 1: User parameters
        for k, v in user_params.items():
            text = text.replace(f"{{{{{k}}}}}", str(v))
        
        # Priority 2: Secrets from agent.config
        secrets = agent.config.get("secrets", {})
        for k, v in secrets.items():
            text = text.replace(f"{{{{{k}}}}}", str(v))
        
        return text

    # Handle resolution for dictionaries recursively
    def resolve_dict(d):
        if isinstance(d, dict):
            return {k: resolve_dict(v) for k, v in d.items()}
        elif isinstance(d, list):
            return [resolve_dict(x) for x in d]
        else:
            return resolve(d)

    base_url = manifest.get("base_url", "")
    path = resolve(endpoint.get("path", ""))
    method = endpoint.get("method", "GET").upper()
    params = resolve_dict(endpoint.get("params", {}))
    body = resolve_dict(endpoint.get("body", {}))
    
    full_url = f"{base_url}{path}"

    # 4. Handle Authentication and Extra Headers
    auth_config = manifest.get("auth", {})
    extra_headers = resolve_dict(manifest.get("extra_headers", {}))
    headers = {}
    
    if auth_config:
        auth_type = auth_config.get("type")
        if auth_type == "header":
            key_name = auth_config.get("key_name", "Authorization")
            value = resolve(auth_config.get("value_template", ""))
            if "(missing" not in value:
                headers[key_name] = value

    if extra_headers:
        headers.update(extra_headers)

    # 5. Execute the Request
    try:
        agent.log_trace(f"API Runner: {method} {full_url}")
        response = requests.request(
            method=method,
            url=full_url,
            params=params,
            json=body if method != "GET" else None,
            headers=headers,
            timeout=20
        )
        response.raise_for_status()
        
        # 6. Automatic Intelligence/Summarization (Optional)
        data = response.json()
        
        # If the data is large, use think() to summarize
        if len(json.dumps(data)) > 2000:
            task = f"Summarize the following API response from {service_name}/{action_name}. Highlight key information relevant to the user's intent."
            return agent.think(json.dumps(data), task)
        
        return data

    except Exception as e:
        return f"Error executing API call to {service_name}: {e}"
