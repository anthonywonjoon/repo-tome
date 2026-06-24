from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import chromadb

from src.ingest import ingest
from src.query import ask
from src.config import CHROMA_DIR

app = FastAPI(
    title="repo-tome",
    description="Ask natural language questions about any public Github repository",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"]
)

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
def ingest_repo(request: IngestRequest, background_tasks: BackgroundTasks):
    repo_name = request.repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    if indexing_status.get(repo_name) == "indexing":
        raise HTTPException(status_code=409, detail=f"'{repo_name}' is already being indexed")
    
    background_tasks.add_task(run_ingest, request.repo_url, repo_name)
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
def query_repo(request: QueryRequest):
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collections = [c.name for c in client.list_collections()]

    if request.repo_name not in collections:
        raise HTTPException(status_code=404, detail=f"'{request.repo_name}' is not indexed yet")
    
    if indexing_status.get(request.repo_name) == "indexing":
        raise HTTPException(status_code=409, detail=f"'{request.repo_name}' is still indexing")
    
    answer, sources = ask(request.repo_name, request.question)
    return QueryResponse(answer=answer, sources=sources)
