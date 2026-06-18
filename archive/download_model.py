from sentence_transformers import SentenceTransformer

# Download the model explicitly
print("Downloading model...")
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print("Model downloaded successfully!")

# Test the model with a simple sentence
embeddings = model.encode(["This is a test sentence."])
print(f"Generated embeddings with shape: {embeddings.shape}")
print("If you see this message, the model is working correctly!")
