import streamlit as st
import requests
import json

def stream_ollama_response(prompt):
    """
    Generator function to stream responses from the Ollama API.
    
    Args:
        prompt (str): The user's input message.
    
    Yields:
        str: Parts of the model's response as they arrive.
    """
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "deepseek-r1:1.5B",
        "prompt": prompt,
        "stream": True
    }
    
    # Send POST request with streaming enabled
    with requests.post(url, json=payload, stream=True) as response:
        response.raise_for_status()  # Raise an exception for HTTP errors
        for line in response.iter_lines():
            if line:  # Skip empty lines
                json_data = json.loads(line.decode('utf-8'))
                yield json_data["response"]

# Streamlit UI setup
st.title("Ollama Streamlit App")

# Input box for user's message
prompt = st.text_input("Enter your message:", placeholder="Type your message here...")

# Button to trigger generation
if st.button("Generate"):
    if prompt.strip():  # Check if prompt is not empty
        try:
            # Stream the response in real time
            generator = stream_ollama_response(prompt)
            st.write_stream(generator)
        except requests.exceptions.ConnectionError:
            st.error("Failed to connect to the Ollama server. Please ensure 'ollama serve' is running.")
        except requests.exceptions.RequestException as e:
            st.error(f"An error occurred: {str(e)}")
    else:
        st.warning("Please enter a message to generate a response.")