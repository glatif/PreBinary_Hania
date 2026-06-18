import requests
import json

OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"  

# Define a function named 'chat' that takes a 'prompt' (user input) as an argument
def chat(prompt):
    # Create a dictionary (key-value pairs) to hold the data we want to send to the API
    payload = {
        "model": MODEL_NAME,  # Specify the model we want to use (e.g., "llama3.2")
        "prompt": prompt,     # The user's input (question or message) to send to the AI
        "stream": True        # Enable streaming so we can get the response in parts
    }
    
    # Send a POST request to the API with the payload as JSON data
    # 'stream=True' means we want to receive the response in chunks as it is generated
    response = requests.post(OLLAMA_API_URL, json=payload, stream=True)

    # Loop through each line of the response as it is received
    for line in response.iter_lines():
        if line:  # Check if the line is not empty
            # Convert the line from JSON format into a Python dictionary
            data = json.loads(line)
            # Get the "response" part of the data and print it without a newline
            print(data.get("response", ""), end="", flush=True)
            # 'end=""' ensures the text is printed on the same line
            # 'flush=True' forces the output to appear immediately

if __name__ == "__main__":
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["exit", "quit"]:
            break
        print("Bot: ", end="")
        chat(user_input)
