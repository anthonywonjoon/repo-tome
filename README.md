# RepoTome
 
Ask natural-language questions about any GitHub repository and get cited answers that point to the exact files and line numbers where the answer lives.
 
> "How does authentication work?" → *"Auth is handled in `src/middleware/auth.py` lines 42–78, where the JWT token is validated against..."*
 
Built with OpenAI embeddings, ChromaDB, and FastAPI. Designed as a portfolio project demonstrating production RAG patterns.
 
---
 
## What it does
 
- Clones any public GitHub repo by URL
- Parses and chunks source code intelligently by function and class boundaries (via tree-sitter)
- Embeds chunks using OpenAI `text-embedding-3-small` and stores them in a local vector database
- Accepts natural-language questions, retrieves the most relevant code chunks, and generates cited answers via GPT-4o-mini
- Exposes a REST API and a Next.js chat UI with inline source citations
---
 
## Tech stack
 
| Layer | Technology |
|---|---|
| Embeddings | OpenAI `text-embedding-3-small` |
| Vector DB | ChromaDB (local) → Qdrant (production) |
| LLM | Anthropic `claude-haiku-4-5` |
| Chunking | tree-sitter (AST-aware, by function/class) |
| Backend | FastAPI + Python 3.11 |
| Frontend | Next.js 14 |
| Deployment | Railway (backend) + Vercel (frontend) |
