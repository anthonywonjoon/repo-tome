import os
import shutil
from pathlib import Path

import chromadb
from git import Repo
from openai import OpenAI
from rich.console import Console
from rich.progress import track
from src.chunker import chunk_file

from src.config import (
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    REPOS_DIR,
    CHROMA_DIR
)

console = Console()
openai_client = OpenAI(api_key=OPENAI_API_KEY)

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs",
    ".java", ".cpp", ".c", ".h", ".rb", ".php", ".swift",
    ".kt", ".md",
}

SKIP_DIRS = {
    "node_modules", ".git", "venv", "__pycache__", ".next",
    "dist", "build", "vendor", ".mypy_cache", ".pytest_cache",
}

def clone_repo(repo_url: str) -> Path:
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    local_path = Path(REPOS_DIR) / repo_name

    if local_path.exists():
        console.print(f"Repo already cloned at {local_path}, skipping clone.")
        return local_path

    console.print(f"Cloning {repo_url}...")

    # Tell git never to prompt for credentials — fail immediately instead
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "echo"

    try:
        Repo.clone_from(
            repo_url,
            local_path,
            depth=1,
            kill_after_timeout=15,
            env=env,
        )
    except Exception as e:
        if local_path.exists():
            shutil.rmtree(local_path)

        err = str(e).lower()

        if any(word in err for word in ["authentication", "auth", "403", "401", "could not read", "repository not found", "terminal prompts disabled"]):
            raise ValueError(
                "Could not access this repository. It may be private — "
                "only public repositories are supported right now."
            )
        elif "timeout" in err or "timed out" in err or "kill_after_timeout" in err:
            raise ValueError(
                "Cloning timed out. The repo may be private or unreachable. "
                "Only public repositories are supported right now."
            )
        else:
            raise ValueError(f"Failed to clone repo: {str(e)}")

    console.print(f"Cloned to {local_path}")
    return local_path

def get_code_files(repo_path: Path) -> list[Path]:
    files = []
    for path in repo_path.rglob("*"):
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if path.is_file() and path.suffix in CODE_EXTENSIONS:
            files.append(path)
    return files

def embed_chunks(chunks: list[dict]) -> list[list[float]]:
    texts = [c["text"] for c in chunks]

    all_embeddings = []
    batch_size = 100

    for i in track(range(0, len(texts), batch_size), description="Embedding..."):
        batch = texts[i: i + batch_size]
        response = openai_client.embeddings.create(input=batch, model=EMBEDDING_MODEL)
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings

def store_in_chroma(repo_name: str, chunks: list[dict], embeddings: list[list[float]]):
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    collection = client.get_or_create_collection(name=repo_name)

    ids = [f"{repo_name}-chunk-{i}" for i in range(len(chunks))]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {
            "file": c["file"],
            "start_line": c["start_line"],
            "end_line": c["end_line"],
            "language": c["language"],
            "name": c.get("name") or ""
        }
        for c in chunks
    ]

    collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    console.print(f"Stored {len(chunks)} chunks in ChromaDB collection '{repo_name}'")

def ingest(repo_url: str):
    repo_path = clone_repo(repo_url)
    repo_name = repo_path.name

    console.print("Scanning files...")
    files = get_code_files(repo_path)
    console.print(f"Found {len(files)} source files")

    console.print(f"Chunking files...")
    all_chunks = []
    for file in files:
        all_chunks.extend(chunk_file(file, repo_path))
    all_chunks = [c for c in all_chunks if c["text"].strip()]
    console.print(f"Created {len(all_chunks)} chunks")

    embeddings = embed_chunks(all_chunks)
    store_in_chroma(repo_name, all_chunks, embeddings)

    console.print(f"Done: '{repo_name}' is ready to query")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        console.print("Usage: python -m src.ingest <github-url>")
        sys.exit(1)
    ingest(sys.argv[1])