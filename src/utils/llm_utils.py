# =============================================================================
# llm_utils.py — Prebinary × UReap Integration
# =============================================================================
# Unified LLM interface used by all seven UReap feature modules.
#
# Module structure:
#   - Model registry       MODELS and MODEL_PROVIDERS constants that define
#                          all available models and their provider routing.
#   - Streaming functions  Per-provider streaming generators used by features
#                          that display output incrementally (RAG, Advisor AI,
#                          Student Wellness).
#   - Non-streaming        generate_llm_response() — used by features that
#                          need the full response before processing (Exam
#                          Grading, Exam Creation, Quiz Generator).
#   - Chat streaming       stream_llm() and stream_llm_chat() — the two public
#                          entry points for features. stream_llm() takes a
#                          single prompt string; stream_llm_chat() takes a full
#                          conversation history in OpenAI message format for
#                          multi-turn interactions.
#   - JSON extraction      strip_llm_json() — extracts a clean JSON object
#                          from raw LLM output regardless of provider formatting.
#
# Provider routing:
#   All public functions resolve the provider string from MODEL_PROVIDERS, then
#   delegate to a provider-specific implementation. API keys are read directly
#   from st.session_state at call time, populated at login by app.py.
# =============================================================================

import json
import requests
from typing import Dict, Generator, Any
import streamlit as st


# =============================================================================
# CONSTANTS
# =============================================================================

# Ollama local inference API endpoint. Used by stream_local_llm() and
# generate_llm_response() for the DeepSeek and Llama 3.2 local models.
OLLAMA_API_URL = "http://localhost:11434/api/generate"

# MODELS maps display names (shown in UI selectboxes) to internal model ID
# strings. Model IDs are stored in the pref_model_* columns in the users table
# and in each feature's session state key. Adding a new model requires a new
# entry here and a corresponding entry in MODEL_PROVIDERS below.
MODELS = {
    "DeepSeek (Thinking model)": "deepseek-r1:1.5B",
    "Llama 3.2 (by Meta)": "llama3.2",
    "Llama 3.3-70B (via Groq)": "llama-3.3-70b-groq",
    "Gemini 2.5 Flash (via Google)": "gemini-2.5-flash",
    "GPT-4o (via OpenAI)": "gpt-4o",
    "GPT-4o (via GitHub Models)": "gpt-4o-github",
}

# MODEL_PROVIDERS maps model ID strings to their provider routing key.
# The provider key is used by generate_llm_response(), stream_llm(), and
# stream_llm_chat() to dispatch to the correct API implementation.
# Valid provider values: "ollama", "groq", "gemini", "openai", "github".
MODEL_PROVIDERS = {
    "deepseek-r1:1.5B": "ollama",
    "llama3.2": "ollama",
    "llama-3.3-70b-groq": "groq",
    "gemini-2.5-flash": "gemini",
    "gpt-4o": "openai",
    "gpt-4o-github": "github",
}

def stream_local_llm(prompt: str, model_name: str, api_url: str = OLLAMA_API_URL) -> Generator[str, None, None]:
    """
    Stream responses from a local LLM using Ollama API
    
    Args:
        prompt: The prompt to send to the model
        model_name: Name of the model to use
        api_url: Ollama API URL
        
    Yields:
        Text chunks from the model response
    """
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True
    }
    
    try:
        with requests.post(api_url, json=payload, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    json_data = json.loads(line.decode('utf-8'))
                    yield json_data["response"]
    except requests.exceptions.RequestException as e:
        yield f"Error: Failed to get response from local model. Details: {str(e)}"

def stream_groq_llm(prompt: str, api_key: str) -> Generator[str, None, None]:
    """
    Stream responses from Groq-hosted Llama models
    
    Args:
        prompt: The prompt to send to the model
        api_key: Groq API key
        
    Yields:
        Text chunks from the model response
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    model = "llama-3.3-70b-versatile"
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": True
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        with requests.post(url, json=payload, headers=headers, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    # Skip empty lines and "data: [DONE]" messages
                    line_str = line.decode('utf-8')
                    if not line_str or line_str == "data: [DONE]":
                        continue
                    
                    # Remove the "data: " prefix
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]
                    
                    try:
                        json_data = json.loads(line_str)
                        if "choices" in json_data and len(json_data["choices"]) > 0:
                            delta = json_data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                    except json.JSONDecodeError:
                        continue
    except requests.exceptions.RequestException as e:
        yield f"Error: Failed to get response from Groq. Details: {str(e)}"

def stream_openai_llm(prompt: str, api_key: str) -> Generator[str, None, None]:
    """
    Stream responses from OpenAI's GPT-4o API
    
    Args:
        prompt: The prompt to send to the model
        api_key: OpenAI API key
        
    Yields:
        Text chunks from the model response
    """
    url = "https://api.openai.com/v1/chat/completions"
    model = "gpt-4o"
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": True
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        with requests.post(url, json=payload, headers=headers, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    # Skip empty lines and "data: [DONE]" messages
                    line_str = line.decode('utf-8')
                    if not line_str or line_str == "data: [DONE]":
                        continue
                    
                    # Remove the "data: " prefix
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]
                    
                    try:
                        json_data = json.loads(line_str)
                        if "choices" in json_data and len(json_data["choices"]) > 0:
                            delta = json_data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                    except json.JSONDecodeError:
                        continue
    except requests.exceptions.RequestException as e:
        yield f"Error: Failed to get response from OpenAI. Details: {str(e)}"

def _transcribe_audio_openai_compatible(
    audio_bytes: bytes,
    filename: str,
    api_key: str,
    url: str,
    model: str,
    provider_label: str,
) -> str:
    """
    Transcribe audio via any OpenAI-compatible /audio/transcriptions endpoint.

    Groq and OpenAI both expose the same multipart request/response shape for
    Whisper transcription, so one implementation covers both — mirroring how
    _stream_openai_compatible_chat() already collapses this file's
    structurally identical chat providers into a single function.

    Returns:
        The transcript text, or an error string prefixed with 'Error:'.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": (filename, audio_bytes)}
    data = {"model": model}

    try:
        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        return response.json().get("text", "")
    except requests.exceptions.RequestException as e:
        return f"Error: Failed to transcribe audio via {provider_label}. Details: {str(e)}"


def transcribe_audio(audio_bytes: bytes, filename: str = "answer.wav") -> str:
    """
    Transcribe a spoken answer to text, used by the Oral Examination feature.

    Dispatches to whichever speech-to-text provider the current user has an
    API key for, preferring Groq (faster, cheaper) over OpenAI. Mirrors the
    'Error: ...' string convention used by generate_llm_response() and
    friends so callers can display the result directly without a separate
    error-handling path.

    Args:
        audio_bytes: Raw audio file bytes (WAV, as produced by st.audio_input).
        filename: Filename to forward to the transcription API.

    Returns:
        The transcript text, or an error string prefixed with 'Error:'.
    """
    if st.session_state.get("groq_api_key"):
        return _transcribe_audio_openai_compatible(
            audio_bytes, filename, st.session_state.groq_api_key,
            url="https://api.groq.com/openai/v1/audio/transcriptions",
            model="whisper-large-v3-turbo",
            provider_label="Groq",
        )
    if st.session_state.get("openai_api_key"):
        return _transcribe_audio_openai_compatible(
            audio_bytes, filename, st.session_state.openai_api_key,
            url="https://api.openai.com/v1/audio/transcriptions",
            model="whisper-1",
            provider_label="OpenAI",
        )
    return (
        "Error: No speech-to-text provider configured. Add a Groq or OpenAI "
        "API key in your profile settings."
    )


def strip_llm_json(raw: str) -> str:
    """
    Strip markdown code fences from an LLM response before JSON parsing.

    Some providers — notably Groq's Llama models — wrap JSON output in markdown
    code fences even when the prompt requests bare JSON:

        ```json
        { ... }
        ```

    Passing such a string directly to json.loads() raises a JSONDecodeError
    because the parser encounters a backtick rather than the opening brace.
    This function removes the fence lines so the caller receives a clean JSON
    string regardless of which provider produced the response.

    The function is safe to call unconditionally: if the response contains no
    fences the original string is returned unchanged, so providers that already
    return bare JSON (Gemini, OpenAI, Ollama) are unaffected.

    Usage:
        data = json.loads(strip_llm_json(raw_response))
    """
    import re as _re
    stripped = raw.strip()

    # DeepSeek (and some other thinking models) prefix their output with
    # <think>...</think> reasoning blocks even when format:json is requested.
    # These blocks may themselves contain { } characters that fool the brace
    # scanner below, so strip them before searching for the JSON object.
    stripped = _re.sub(r"<think>.*?</think>", "", stripped, flags=_re.DOTALL).strip()

    # Primary strategy: locate the outermost JSON object by finding the first
    # opening brace and its matching closing brace. This handles all provider
    # formatting variants in a single pass:
    #   - Bare JSON (no fences)
    #   - JSON wrapped in ```json ... ``` fences
    #   - Prose before or after the JSON block
    #   - Fences with trailing notes after the closing ```
    #
    # The brace-matching walk correctly handles nested objects so the entire
    # JSON structure is extracted regardless of depth.
    start = stripped.find("{")
    if start != -1:
        depth = 0
        end   = -1
        for i, ch in enumerate(stripped[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            return stripped[start:end + 1]

    # Fallback: if no valid brace pair was found, return the stripped string
    # as-is so the caller receives the original content for error reporting.
    return stripped


def generate_llm_response(
    prompt: str,
    model_name: str,
    api_url: str = OLLAMA_API_URL,
    force_json: bool = False,
) -> str:
    """
    Generate a complete (non-streaming) response from any supported LLM provider.

    Dispatches to the correct provider implementation based on MODEL_PROVIDERS.
    Used by features that require the full response before processing, such as
    Exam Grading, Exam Creation, and Quiz Generator.

    Args:
        prompt:     The prompt string to send to the model.
        model_name: A model ID string from llm_utils.MODELS values
                    (e.g. 'gemini-2.5-flash', 'llama3.2').
        api_url:    Ollama API URL. Only used when provider is 'ollama'.
        force_json: When True, instructs Ollama to constrain its output to
                    valid JSON. Set this only when the caller will parse the
                    response as JSON (e.g. the exam grading loop). Leave False
                    for plain-text responses such as question formatting or
                    generation — Ollama's json mode overrides the prompt's
                    format instructions and produces garbage JSON for text tasks.

    Returns:
        The full text response from the model, or an error string prefixed
        with 'Error:' if the request fails or a key is missing.
    """
    provider = MODEL_PROVIDERS.get(model_name, "ollama")

    if provider == "ollama":
        payload: Dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            # A fixed seed produces deterministic outputs for local models,
            # which simplifies debugging and manual testing of prompts.
            "seed": 1976,
        }
        if force_json:
            payload["format"] = "json"

        try:
            response = requests.post(api_url, json=payload)
            response.raise_for_status()
            return response.json()["response"]
        except requests.exceptions.RequestException as e:
            return f"Error: Failed to get response from local model. Details: {str(e)}"
            
    elif provider == "groq":
        # Use Groq API
        if not st.session_state.get("groq_api_key"):
            return "Error: Groq API key is missing. Please add your API key in your profile settings."
        
        return generate_groq_response(prompt, st.session_state.groq_api_key)
        
    elif provider == "gemini":
        # Use Gemini API
        if not st.session_state.get("gemini_api_key"):
            return "Error: Gemini API key is missing. Please add your API key in your profile settings."
        
        return generate_gemini_response(prompt, st.session_state.gemini_api_key)
    
    elif provider == "openai":
        # Use OpenAI API
        if not st.session_state.get("openai_api_key"):
            return "Error: OpenAI API key is missing. Please add your API key in your profile settings."
        
        return generate_openai_response(prompt, st.session_state.openai_api_key)
        
    elif provider == "github":
        # Use GitHub Models API
        if not st.session_state.get("github_token"):
            return "Error: GitHub token is missing. Please add your GitHub token in your profile settings."
        
        return generate_github_response(prompt, st.session_state.github_token)
    
    else:
        return f"Error: Unsupported model provider: {provider}"

def generate_groq_response(prompt: str, api_key: str) -> str:
    """
    Generate a complete response from Groq-hosted Llama models
    
    Args:
        prompt: The prompt to send to the model
        api_key: Groq API key
        
    Returns:
        Complete text response from the model
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    model = "llama-3.3-70b-versatile"
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return f"Error: Failed to get response from Groq. Details: {str(e)}"

def generate_openai_response(prompt: str, api_key: str) -> str:
    """
    Generate a complete response from OpenAI's GPT-4o API
    
    Args:
        prompt: The prompt to send to the model
        api_key: OpenAI API key
        
    Returns:
        Complete text response from the model
    """
    url = "https://api.openai.com/v1/chat/completions"
    model = "gpt-4o"
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return f"Error: Failed to get response from OpenAI. Details: {str(e)}"

def generate_gemini_response(prompt: str, api_key: str) -> str:
    """
    Generate a complete response from Google's Gemini API
    
    Args:
        prompt: The prompt to send to the model
        api_key: Google Gemini API key
        
    Returns:
        Complete text response from the model
    """
    model_id = "gemini-2.5-flash"
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    
    messages = [
        {
            "role": "user",
            "parts": [{"text": prompt}]
        }
    ]
    
    payload = {
        "contents": messages,
        "generationConfig": {
            "responseMimeType": "text/plain"
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except requests.exceptions.RequestException as e:
        return f"Error: Failed to get response from Gemini. Details: {str(e)}"

def stream_github_llm(prompt: str, api_key: str) -> Generator[str, None, None]:
    """
    Stream responses from GitHub Models GPT-4o API
    
    Args:
        prompt: The prompt to send to the model
        api_key: GitHub token
        
    Yields:
        Text chunks from the model response
    """
    url = "https://models.github.ai/inference/chat/completions"
    model = "openai/gpt-4o"
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 1,
        "max_tokens": 4096,
        "top_p": 1
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        with requests.post(url, json=payload, headers=headers, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    # Skip empty lines and "data: [DONE]" messages
                    line_str = line.decode('utf-8')
                    if not line_str or line_str == "data: [DONE]":
                        continue
                    
                    # Remove the "data: " prefix
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]
                    
                    try:
                        json_data = json.loads(line_str)
                        if "choices" in json_data and len(json_data["choices"]) > 0:
                            delta = json_data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                    except json.JSONDecodeError:
                        continue
    except requests.exceptions.RequestException as e:
        yield f"Error: Failed to get response from GitHub Models. Details: {str(e)}"

def generate_github_response(prompt: str, api_key: str) -> str:
    """
    Generate a complete response from GitHub Models GPT-4o API
    
    Args:
        prompt: The prompt to send to the model
        api_key: GitHub token
        
    Returns:
        Complete text response from the model
    """
    url = "https://models.github.ai/inference/chat/completions"
    model = "openai/gpt-4o"
    
    messages = [
        {"role": "user", "content": prompt}
    ]
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 1,
        "max_tokens": 4096,
        "top_p": 1
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return f"Error: Failed to get response from GitHub Models. Details: {str(e)}"

def stream_llm(prompt: str, model_name: str) -> Generator[str, None, None]:
    """
    Stream responses from the appropriate LLM based on the model name.
    Accepts a single prompt string. For multi-turn chat use stream_llm_chat().

    Args:
        prompt: The prompt to send to the model
        model_name: ID of the model to use (from llm_utils.MODELS values)

    Yields:
        Text chunks from the model response
    """
    provider = MODEL_PROVIDERS.get(model_name, "ollama")

    if provider == "ollama":
        yield from stream_local_llm(prompt, model_name)

    elif provider == "groq":
        if not st.session_state.get("groq_api_key"):
            yield "Error: Groq API key is missing. Please add your API key in your profile settings."
            return
        yield from stream_groq_llm(prompt, st.session_state.groq_api_key)

    elif provider == "gemini":
        if not st.session_state.get("gemini_api_key"):
            yield "Error: Gemini API key is missing. Please add your API key in your profile settings."
            return
        response = generate_gemini_response(prompt, st.session_state.gemini_api_key)
        yield response

    elif provider == "openai":
        if not st.session_state.get("openai_api_key"):
            yield "Error: OpenAI API key is missing. Please add your API key in your profile settings."
            return
        yield from stream_openai_llm(prompt, st.session_state.openai_api_key)

    elif provider == "github":
        if not st.session_state.get("github_token"):
            yield "Error: GitHub token is missing. Please add your GitHub token in your profile settings."
            return
        yield from stream_github_llm(prompt, st.session_state.github_token)

    else:
        yield f"Error: Unsupported model provider: {provider}"


def stream_llm_chat(messages: list, model_name: str) -> Generator[str, None, None]:
    """
    Stream a response from the appropriate LLM given a full conversation history.

    Unlike stream_llm(), which accepts a single prompt string, this function
    accepts a list of message dicts in the standard chat completions format:
        [{"role": "user" | "assistant" | "system", "content": str}, ...]

    This enables multi-turn conversations where the model has context from prior
    exchanges. Used by the RAG chat feature to pass conversation history alongside
    the retrieved document context on every query.

    Cloud providers (Groq, OpenAI, GitHub Models) accept the messages list
    directly via their chat completions APIs. Gemini uses a different role
    convention ("model" instead of "assistant") and content structure, so the
    list is translated before the request. Ollama uses the /api/chat endpoint
    which supports the messages format natively for both DeepSeek and Llama models.

    Args:
        messages: List of {"role": ..., "content": ...} dicts representing the
                  full conversation, with the most recent user message last.
        model_name: Model ID string from llm_utils.MODELS values.

    Yields:
        Text chunks from the model response.
    """
    provider = MODEL_PROVIDERS.get(model_name, "ollama")

    if provider == "ollama":
        yield from _stream_ollama_chat(messages, model_name)

    elif provider == "groq":
        if not st.session_state.get("groq_api_key"):
            yield "Error: Groq API key is missing. Please add your API key in your profile settings."
            return
        yield from _stream_openai_compatible_chat(
            messages=messages,
            model="llama-3.3-70b-versatile",
            url="https://api.groq.com/openai/v1/chat/completions",
            api_key=st.session_state.groq_api_key,
        )

    elif provider == "gemini":
        if not st.session_state.get("gemini_api_key"):
            yield "Error: Gemini API key is missing. Please add your API key in your profile settings."
            return
        yield from _stream_gemini_chat(messages, st.session_state.gemini_api_key)

    elif provider == "openai":
        if not st.session_state.get("openai_api_key"):
            yield "Error: OpenAI API key is missing. Please add your API key in your profile settings."
            return
        yield from _stream_openai_compatible_chat(
            messages=messages,
            model="gpt-4o",
            url="https://api.openai.com/v1/chat/completions",
            api_key=st.session_state.openai_api_key,
        )

    elif provider == "github":
        if not st.session_state.get("github_token"):
            yield "Error: GitHub token is missing. Please add your GitHub token in your profile settings."
            return
        yield from _stream_openai_compatible_chat(
            messages=messages,
            model="openai/gpt-4o",
            url="https://models.github.ai/inference/chat/completions",
            api_key=st.session_state.github_token,
            extra_payload={"temperature": 1, "top_p": 1, "max_tokens": 4096},
        )

    else:
        yield f"Error: Unsupported model provider: {provider}"


def _stream_openai_compatible_chat(
    messages: list,
    model: str,
    url: str,
    api_key: str,
    extra_payload: dict = None,
) -> Generator[str, None, None]:
    """
    Stream a chat response from any OpenAI-compatible API endpoint.

    Groq, OpenAI, and GitHub Models all use the same chat completions request
    and response format, so a single implementation covers all three. The
    extra_payload argument allows provider-specific fields (e.g. temperature
    for GitHub Models) to be merged into the request body without duplicating
    this function.

    Args:
        messages: Full conversation history in OpenAI message format.
        model: Model identifier string for the target provider.
        url: Chat completions endpoint URL.
        api_key: Bearer token for the provider.
        extra_payload: Optional dict of additional top-level payload fields.

    Yields:
        Text chunks from the streamed response.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    if extra_payload:
        payload.update(extra_payload)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with requests.post(url, json=payload, headers=headers, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8")
                    if not line_str or line_str == "data: [DONE]":
                        continue
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]
                    try:
                        json_data = json.loads(line_str)
                        if "choices" in json_data and json_data["choices"]:
                            delta = json_data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                    except json.JSONDecodeError:
                        continue
    except requests.exceptions.RequestException as e:
        yield f"Error: Request failed. Details: {str(e)}"


def _stream_gemini_chat(
    messages: list,
    api_key: str,
) -> Generator[str, None, None]:
    """
    Stream a chat response from the Gemini API given a messages list.

    Gemini uses a different schema from OpenAI: roles are "user" and "model"
    (not "assistant"), and content is wrapped in a "parts" list. System-role
    messages are prepended to the first user message as plain text since Gemini
    does not support a dedicated system role in this endpoint.

    Args:
        messages: Full conversation history in OpenAI message format.
        api_key: Google Gemini API key.

    Yields:
        The complete response text as a single chunk. Gemini's REST endpoint
        does not support streaming in the same way as OpenAI-compatible APIs,
        so the full response is returned at once.
    """
    model_id = "gemini-2.5-flash"
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_id}:generateContent?key={api_key}"
    )

    # Translate OpenAI message format to Gemini contents format.
    # System messages are injected as a prefix on the first user turn since
    # Gemini does not support a standalone system role in this API version.
    contents = []
    system_prefix = ""

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "system":
            system_prefix = content
            continue

        gemini_role = "model" if role == "assistant" else "user"

        # Prepend the system context to the first user message only.
        if gemini_role == "user" and system_prefix:
            content = f"{system_prefix}\n\n{content}"
            system_prefix = ""

        contents.append({
            "role": gemini_role,
            "parts": [{"text": content}],
        })

    payload = {
        "contents": contents,
        "generationConfig": {"responseMimeType": "text/plain"},
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        result = response.json()
        yield result["candidates"][0]["content"]["parts"][0]["text"]
    except requests.exceptions.RequestException as e:
        yield f"Error: Failed to get response from Gemini. Details: {str(e)}"


def _stream_ollama_chat(
    messages: list,
    model_name: str,
    api_url: str = "http://localhost:11434/api/chat",
) -> Generator[str, None, None]:
    """
    Stream a chat response from a local Ollama model using the /api/chat endpoint.

    Ollama's /api/chat endpoint supports the same role-based messages format as
    OpenAI, enabling proper multi-turn conversation context for local models.
    Both DeepSeek and Llama 3.2 support this endpoint.

    System-role messages are included as-is since Ollama's chat endpoint handles
    them natively.

    Args:
        messages: Full conversation history in OpenAI message format.
        model_name: Ollama model name (e.g. "deepseek-r1:1.5B", "llama3.2").
        api_url: Ollama chat API URL. Defaults to localhost.

    Yields:
        Text chunks from the streamed response.
    """
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
    }

    try:
        with requests.post(api_url, json=payload, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    json_data = json.loads(line.decode("utf-8"))
                    message = json_data.get("message", {})
                    if "content" in message:
                        yield message["content"]
    except requests.exceptions.RequestException as e:
        yield f"Error: Failed to get response from local model. Details: {str(e)}"