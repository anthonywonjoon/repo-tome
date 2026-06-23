from dotenv import load_dotenv
import os

load_dotenv()

# API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTRHOPIC_API_KEY")

# Models
EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "claude-haiku-4-5"

# Chunking
CHUNK_SIZE = 40
CHUNK_OVERLAP = 5

# Retrieval
TOP_K = 5

REPOS_DIR = "repos"
CHROMA_DIR = ".chroma"