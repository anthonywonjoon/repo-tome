import chromadb
from openai import OpenAI
import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.config import (
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    EMBEDDING_MODEL,
    LLM_MODEL,
    TOP_K,
    CHROMA_DIR
)

console = Console()
openai_client = OpenAI(api_key=OPENAI_API_KEY)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def embed_question(question: str) -> list[float]:
    response = openai_client.embeddings.create(input=question, model=EMBEDDING_MODEL)
    return response.data[0].embedding

def retrieve_chunks(repo_name: str, question_embedding: list[float]) -> list[dict]:
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(name=repo_name)

    results = collection.query(
        query_embeddings=[question_embedding],
        n_results=TOP_K,
        include=["documents", "metadatas", "distances"]
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        chunks.append({"text": doc, "metadata": meta, "distance": dist})

    return chunks

def build_prompt(question: str, chunks: list[dict]) -> str:
    context_blocks = []
    for i, chunk in enumerate(chunks):
        meta = chunk["metadata"]
        header = f"[Source {i+1}] {meta['file']} (lines {meta['start_line']}-{meta['end_line']})"
        context_blocks.append(f"{header}\n```{meta['language']}\n{chunk['text']}\n```")

    context = "\n\n".join(context_blocks)

    return f"""You are an expert code assistant. Answer the question below using ONLY the source code provided.
For every claim you make, cite the source file and line range using the format: [Source N, filename lines X–Y].
If the answer cannot be found in the provided sources, say so clearly.

{context}

Question: {question}

Answer:"""

def ask(repo_name: str, question: str):
    console.print(f"Searching '{repo_name}' for an answer...")

    question_embedding = embed_question(question)
    chunks = retrieve_chunks(repo_name, question_embedding)

    console.print(f"Retrieved {len(chunks)} relevant chunks")

    prompt = build_prompt(question, chunks)

    message = anthropic_client.messages.create(
        model=LLM_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    answer = message.content[0].text

    sources = [
        {
            "file": c["metadata"]["file"],
            "start_line": c["metadata"]["start_line"],
            "end_line": c["metadata"]["end_line"],
            "name": c["metadata"].get("name") or "",
        }
        for c in chunks
    ]

    console.print(Panel(Markdown(answer), title="Answer", border_style="green"))
    console.print("\nSources:")
    for i, s in enumerate(sources):
        label = f" ({s['name']})" if s["name"] else ""
        console.print(f" [{i+1}] {s['file']}{label} lines {s['start_line']}-{s['end_line']}")
    
    return answer, sources

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        console.print("[red]Usage: python -m src.query <repo-name> \"<question>\"[/red]")
        console.print("[red]Example: python -m src.query cli \"How does request authentication work?\"[/red]")
        sys.exit(1)

    repo_name = sys.argv[1]
    question = sys.argv[2]
    ask(repo_name, question)