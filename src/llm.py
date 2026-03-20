import json
import requests
from datetime import datetime
from utils import log_debug, log_message

GEMINI_TOTAL_TOKENS = 0
GEMINI_CACHED_TOKENS = 0

def get_gemini_usage():
    """Returns a formatted string of total Gemini token usage."""
    if GEMINI_TOTAL_TOKENS > 0 or GEMINI_CACHED_TOKENS > 0:
        return f"\n--- Gemini Session Usage --- \nTotal Tokens: {GEMINI_TOTAL_TOKENS}\nCached Tokens: {GEMINI_CACHED_TOKENS}\n----------------------------"
    return ""

def call_llm(model_config, messages, tools, supports_tools=True, debug=False, log_file=None):
    """Calls the appropriate LLM API."""
    global GEMINI_TOTAL_TOKENS, GEMINI_CACHED_TOKENS
    api_type = model_config.get('type')
    model, base_url, api_key = model_config.get('model'), model_config.get('base_url'), model_config.get('api_key')
    headers = {"Content-Type": "application/json"}

    if api_type == "openai_compatible":
        if api_key and api_key != 'not-required': headers['Authorization'] = f"Bearer {api_key}"
        
        # Convert messages to OpenAI format, ensuring tool_calls are handled if present from previous turns
        openai_messages = []
        for m in messages:
            om = {"role": m["role"], "content": m.get("content")}
            if m["role"] == "assistant" and m.get("tool_calls"):
                om["tool_calls"] = m["tool_calls"]
            if m["role"] == "tool":
                om["tool_call_id"] = m["tool_call_id"]
                om["name"] = m["name"]
            openai_messages.append(om)

        payload = {"messages": openai_messages, "model": model}
        if supports_tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        if debug:
            print(f"DEBUG (call_llm/openai): Payload sent: {json.dumps(payload, indent=2)}")
            log_debug(f"OpenAI Payload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(base_url, json=payload, headers=headers, timeout=120)
            if debug:
                print(f"DEBUG (call_llm/openai): Raw API response: {response.text}")
                log_debug(f"OpenAI Raw Response: {response.text}")
            response.raise_for_status()
            res_json = response.json()
            if debug and 'usage' in res_json:
                print(f"DEBUG (call_llm/openai): Usage: {json.dumps(res_json['usage'], indent=2)}")
            
            raw_msg = res_json.get('choices', [{}])[0].get('message', {"content": "Error: No message."})
            
            # Preserve all fields in the message object to ensure reasoning/thought fields are kept in history
            final_msg = {k: v for k, v in raw_msg.items() if v is not None}
                
            return final_msg
        except Exception as e:
            if debug: print(f"DEBUG (call_llm/openai): Exception caught: {e}")
            return {"content": f"Error connecting to {base_url}: {e}"}

    elif api_type == "google_gemini":
        gemini_contents, system_prompt = [], ""
        
        for msg in messages:
            role = msg.get('role')
            if role == 'system':
                system_prompt = msg['content']
                continue
            
            # Determine Gemini role
            gemini_role = 'model' if role == 'assistant' else ('user' if role == 'user' else 'function')
            
            # Extract parts from this message
            current_parts = []
            if "_gemini_parts" in msg:
                # Filter out empty text/thought parts which can crash Gemini
                for p in msg["_gemini_parts"]:
                    if 'text' in p and not p['text']: continue
                    if 'thought' in p and not p['thought']: continue
                    current_parts.append(p)
            elif role == 'user':
                if msg.get('content'):
                    current_parts = [{'text': msg['content']}]
            elif role == 'assistant':
                if msg.get('thought'):
                    current_parts.append({'thought': msg['thought']})
                if msg.get('content'):
                    current_parts.append({'text': msg['content']})
                if msg.get('tool_calls'):
                    for tc in msg['tool_calls']:
                        fc_internal = tc['function']
                        if hasattr(fc_internal, 'get') and '_gemini_fc' in fc_internal:
                            gemini_fc = fc_internal['_gemini_fc']
                        else:
                            gemini_fc = {
                                'name': fc_internal['name'],
                                'args': json.loads(fc_internal.get('arguments', '{}')) if fc_internal.get('arguments') else {}
                            }
                            for key, value in fc_internal.items():
                                if key not in ['name', 'arguments', '_gemini_fc']:
                                    gemini_fc[key] = value
                        current_parts.append({'functionCall': gemini_fc})
            elif role == 'tool':
                if msg.get('content') is not None:
                    current_parts = [{'functionResponse': {'name': msg['name'], 'response': {"content": msg['content']}}}]

            if not current_parts:
                continue

            # Grouping logic: if last turn has the same role, append parts to it
            if gemini_contents and gemini_contents[-1]['role'] == gemini_role:
                gemini_contents[-1]['parts'].extend(current_parts)
            else:
                gemini_contents.append({'role': gemini_role, 'parts': current_parts})
        
        # Final safety check: Gemini requires the first turn to be 'user'
        while gemini_contents and gemini_contents[0]['role'] != 'user':
            gemini_contents.pop(0)

        payload = {}
        if system_prompt:
            payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
        
        payload["contents"] = gemini_contents
        
        if tools and supports_tools:
            payload["tools"] = [{"function_declarations": [t['function'] for t in tools]}]
        
        if debug:
            print(f"DEBUG (call_llm/gemini): Payload sent to Google API.")
            log_debug(f"Gemini Payload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(f"{base_url}?key={api_key}", json=payload, headers=headers, timeout=120)
            if debug:
                print(f"DEBUG (call_llm/gemini): Raw API response: {response.text}")
                log_debug(f"Gemini Raw Response: {response.text}")
            response.raise_for_status()
            res_json = response.json()

            usage = res_json.get('usageMetadata') or res_json.get('usage_metadata')
            if usage:
                GEMINI_TOTAL_TOKENS += usage.get('totalTokenCount', 0)
                GEMINI_CACHED_TOKENS += usage.get('cachedContentTokenCount', 0)
                if debug:
                    print(f"DEBUG (call_llm/gemini): Usage Metadata: {json.dumps(usage, indent=2)}")
                    log_debug(f"Gemini Usage Metadata: {json.dumps(usage, indent=2)}")

            if not res_json.get('candidates') or not res_json['candidates'][0].get('content'):
                if debug: print(f"DEBUG (call_llm/gemini): No candidates or content in response: {json.dumps(res_json)}")
                # Check for finishReason which might indicate why content is missing (e.g. SAFETY)
                finish_reason = "Unknown"
                if res_json.get('candidates'):
                    finish_reason = res_json['candidates'][0].get('finishReason', 'Unknown')
                return {"content": f"API Error: No content returned. Finish Reason: {finish_reason}. Full response: {json.dumps(res_json)}"}
            
            candidate = res_json['candidates'][0]
            content_obj = candidate.get('content', {})
            response_parts = content_obj.get('parts', [])
            
            final_content = ""
            tool_calls = []
            thought = ""

            if not response_parts:
                if debug: print(f"DEBUG (call_llm/gemini): No 'parts' in candidate content: {json.dumps(res_json)}")
                # If it stopped normally but has no parts, it's just an empty response (maybe just thinking)
                finish_reason = candidate.get('finishReason', 'STOP')
                if finish_reason == 'STOP':
                    return {"role": "assistant", "content": "(The model produced no visible output. It may have reached a conclusion internally or is waiting for more context.)"}
                return {"content": f"API Error: No parts in response content. Finish Reason: {finish_reason}."}

            for part in response_parts:
                if 'text' in part and part['text']:
                    final_content += part['text']
                if 'thought' in part:
                    thought += part['thought']
                if 'functionCall' in part:
                    fc = part['functionCall']
                    f_data = {
                        "name": fc['name'],
                        "arguments": json.dumps(fc.get('args', {}))
                    }
                    # Preserve original for internal use
                    f_data['_gemini_fc'] = fc
                    
                    # Also keep them at top level for general compatibility
                    for key, value in fc.items():
                        if key not in ['name', 'args']:
                            f_data[key] = value

                    tool_calls.append({
                        "id": f"call_{datetime.now().timestamp()}_{len(tool_calls)}",
                        "type": "function",
                        "function": f_data
                    })
            
            final_message = {"role": "assistant"}
            if final_content:
                final_message["content"] = final_content
            if tool_calls:
                final_message["tool_calls"] = tool_calls
            if thought:
                final_message["thought"] = thought
            
            # Crucial: Store the raw parts to guarantee exact reconstruction in future turns
            final_message["_gemini_parts"] = response_parts
            
            if not final_content and not tool_calls and not thought:
                 if debug: print(f"DEBUG (call_llm/gemini): No text or function calls found in response: {json.dumps(res_json)}")
                 return {"role": "assistant", "content": "Error: No text or function calls in response."}

            return final_message

        except Exception as e:
            if debug: print(f"DEBUG (call_llm/gemini): Exception caught: {e}")
            return {"content": f"Error connecting to Google API: {e}"}
    if debug: print(f"DEBUG (call_llm): Unknown model type '{api_type}'")
    return {"content": f"Error: Unknown model type '{api_type}'."}
