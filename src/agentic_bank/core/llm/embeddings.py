import os
from typing import List
import numpy as np
from openai import AzureOpenAI

def embed_texts(texts: List[str]) -> np.ndarray:
    model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
   
    client = AzureOpenAI(
        api_version=os.getenv("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-12-01-preview"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=api_key
    )
   
    resp = client.embeddings.create(
        input=texts,
        model=model
        
        
        
    )
  
    vecs = [d.embedding for d in resp.data]
   
    return np.array(vecs, dtype=np.float32)

def cosine_sim_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
    return a_norm @ b_norm.T


