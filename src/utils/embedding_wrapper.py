import os
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

# Default model to use for embeddings
# Using a simpler model that's more likely to be available
DEFAULT_MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'

class EmbeddingModel:
    """
    A wrapper for creating embeddings that avoids using sentence-transformers directly
    to work around the huggingface_hub cached_download issue
    """
    
    def __init__(self, model_name=DEFAULT_MODEL_NAME):
        """
        Initialize the embedding model
        
        Args:
            model_name: Name of the model to use
        """
        try:
            # Try to use sentence_transformers directly if available
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
            self.using_sentence_transformer = True
        except (ImportError, Exception) as e:
            print(f"Falling back to manual implementation due to: {str(e)}")
            # Fall back to manual implementation using transformers
            self.using_sentence_transformer = False
            # Load the tokenizer and model using transformers directly
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=False)
            self.model = AutoModel.from_pretrained(model_name, local_files_only=False)
            
            # Make sure the model is in evaluation mode
            self.model.eval()
        
    def _mean_pooling(self, model_output, attention_mask):
        """
        Mean pooling to get sentence embeddings
        """
        # First element of model_output contains all token embeddings
        token_embeddings = model_output[0]
        
        # Mask for padding tokens
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        
        # Sum token embeddings and divide by the expanded mask sum
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)
    
    def encode(self, sentences, batch_size=8):
        """
        Create embeddings for a list of sentences
        
        Args:
            sentences: List of sentences to encode
            batch_size: Batch size for encoding
        Returns:
            Numpy array of embeddings
        """
        # If we're using SentenceTransformer, use its encode method directly
        if hasattr(self, 'using_sentence_transformer') and self.using_sentence_transformer:
            return self.model.encode(sentences, convert_to_numpy=True)
            
        # Otherwise use our manual implementation with batching
        try:
            # Process sentences in batches to avoid memory issues
            all_embeddings = []
            
            for i in range(0, len(sentences), batch_size):
                batch = sentences[i:i+batch_size]
                
                # Tokenize the batch
                encoded_input = self.tokenizer(batch, padding=True, truncation=True, return_tensors='pt')
                
                # Get model output
                with torch.no_grad():
                    model_output = self.model(**encoded_input)
                
                # Perform mean pooling
                embeddings = self._mean_pooling(model_output, encoded_input['attention_mask'])
                
                # Normalize embeddings
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                
                all_embeddings.append(embeddings)
            
            # Concatenate all embeddings
            if len(all_embeddings) > 0:
                all_embeddings = torch.cat(all_embeddings, dim=0)
                return all_embeddings.numpy()
            else:
                return np.array([])
        except Exception as e:
            raise RuntimeError(f"Error creating embeddings: {str(e)}")

# Function to get an embedding model instance
def get_embedding_model(model_name=DEFAULT_MODEL_NAME):
    """
    Get an instance of the embedding model
    
    Args:
        model_name: Name of the model to use
    
    Returns:
        EmbeddingModel instance
    """
    return EmbeddingModel(model_name) 