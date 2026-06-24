from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import chromadb
import json
from pathlib import Path

from src.ingest import ingest
from src.query import ask
from src.config import CHROMA_DIR

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="repo-tome",
    description="Ask natural language questions about any public Github repository",
    version="0.1.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"]
)

def get_repo_url(repo_name: str) -> str | None:
    meta_path = Path(CHROMA_DIR) / f"{repo_name}.json"
    try:
        with open(meta_path) as f:
            return json.load(f).get("repo_url")
    except Exception:
        return None

indexing_status: dict[str, str] = {}

# Request/Response Models ---

class IngestRequest(BaseModel):
    repo_url: str

class QueryRequest(BaseModel):
    repo_name: str
    question: str

class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]

# Background Indexing Task ---

# Runs indexing in the background so it doesn't block the API
def run_ingest(repo_url: str, repo_name: str):
    try:
        indexing_status[repo_name] = "indexing"
        ingest(repo_url)
        indexing_status[repo_name] = "ready"
    except ValueError as e:
        indexing_status[repo_name] = f"error: {str(e)}"
    except Exception as e:
        indexing_status[repo_name] = f"error: Something went wrong while indexing — {str(e)}"

# Routes ---

@app.get("/")
def root():
    return {"message": "repo-tome API is running"}

@app.get("/health")
def health():
    return {"status": "ok"}

# Starts indexing the Github repo, runs in the background
@app.post("/ingest")
@limiter.limit("3/hour")
async def ingest_repo(request: Request, body: IngestRequest, background_tasks: BackgroundTasks):
    repo_name = body.repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    if indexing_status.get(repo_name) == "indexing":
        raise HTTPException(status_code=409, detail=f"'{repo_name}' is already being indexed")
    
    background_tasks.add_task(run_ingest, body.repo_url, repo_name)
    indexing_status[repo_name] = "indexing"

    return {"message": f"Indexing '{repo_name}' started", "repo_name": repo_name}

# Lists all already indexed repositories
@app.get("/repos")
def list_repos():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collections = client.list_collections()
    repos = []
    for col in collections:
        name = col.name
        status = indexing_status.get(name, "ready")
        repos.append({"name": name, "status": status, "chunks": col.count()})
    return {"repos": repos}

# Check the indexing status of a specific repo
@app.get("/repos/{repo_name}/status")
def repo_status(repo_name: str):
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collections = [c.name for c in client.list_collections()]

    if repo_name in collections:
        return {"repo_name": repo_name, "status": indexing_status.get(repo_name, "ready")}
    
    status = indexing_status.get(repo_name, "not_found")
    return {"repo_name": repo_name, "status": status}

# Remove a repo's index from the database
@app.delete("/repos/{repo_name}")
def delete_repo(repo_name: str):
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    try:
        client.delete_collection(repo_name)
        indexing_status.pop(repo_name, None)
        return {"message": f"'{repo_name}' index deleted"}
    except Exception:
        raise HTTPException(status_code=404, detail=f"'{repo_name}' not found")
    
# Ask a question about an indexed repo
@app.post("/query", response_model=QueryResponse)
@limiter.limit("20/hour;5/minute")
async def query_repo(request: Request, body: QueryRequest):
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collections = [c.name for c in client.list_collections()]

    if body.repo_name not in collections:
        raise HTTPException(status_code=404, detail=f"'{body.repo_name}' is not indexed yet")
    
    if indexing_status.get(body.repo_name) == "indexing":
        raise HTTPException(status_code=409, detail=f"'{body.repo_name}' is still indexing")
    
    answer, sources = ask(body.repo_name, body.question)
    repo_url = get_repo_url(body.repo_name)

    for source in sources:
        if repo_url:
            source["url"] = f"{repo_url}/blob/main/{source['file']}#L{source['start_line']}-L{source['end_line']}"
        else:
            source["url"] = None

    return {"answer": answer, "sources": sources}