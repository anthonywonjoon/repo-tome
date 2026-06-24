from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as tstypescript
import tree_sitter_go as tsgo
import tree_sitter_rust as tsrust
import tree_sitter_java as tsjava

from src.config import CHUNK_SIZE

LANGUAGE_MAP = {
    ".py":   Language(tspython.language(), "python"),
    ".js":   Language(tsjavascript.language(), "javascript"),
    ".jsx":  Language(tsjavascript.language(), "javascript"),
    ".ts":   Language(tstypescript.language_typescript(), "typescript"),
    ".tsx":  Language(tstypescript.language_tsx(), "tsx"),
    ".go":   Language(tsgo.language(), "go"),
    ".rs":   Language(tsrust.language(), "rust"),
    ".java": Language(tsjava.language(), "java"),
}

CHUNK_NODE_TYPES = {
    # Python
    "function_definition", "class_definition",
    # JavaScript / TypeScript
    "function_declaration", "class_declaration",
    "method_definition", "arrow_function",
    "export_statement",
    # Go
    "function_declaration", "method_declaration", "type_declaration",
    # Rust
    "function_item", "impl_item", "struct_item", "enum_item",
    # Java
    "class_declaration", "method_declaration", "interface_declaration"
}

def _fallback_chunks(content: str, file_path: Path, repo_path: Path) -> list[dict]:
    lines = content.splitlines()
    chunks = []
    for start in range(0, len(lines), CHUNK_SIZE):
        end = min(start + CHUNK_SIZE, len(lines))
        chunks.append({
            "text": "\n".join(lines[start:end]),
            "file": str(file_path.relative_to(repo_path)),
            "start_line": start + 1,
            "end_line": end,
            "language": file_path.suffix.lstrip("."),
            "name": None
        })
    return chunks

def _node_name(node) -> str | None:
    for child in node.children:
        if child.type == "identifier":
            return child.text.decode("utf-8")
    return None
    
def chunk_file(file_path: Path, repo_path: Path) -> list[dict]:
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    
    if not content.strip():
        return []
    
    suffix = file_path.suffix
    relative_path = str(file_path.relative_to(repo_path))
    language = suffix.lstrip(".")

    if suffix not in LANGUAGE_MAP:
        return _fallback_chunks(content, file_path, repo_path)
    
    parser = Parser()
    parser.set_language(LANGUAGE_MAP[suffix])
    tree = parser.parse(content.encode("utf-8"))

    chunks = []
    lines = content.splitlines()
    
    def visit(node):
        if node.type in CHUNK_NODE_TYPES:
            start_line = node.start_point[0]
            end_line = node.end_point[0]

            chunk_lines = lines[start_line : end_line + 1]

            if len(chunk_lines) > CHUNK_SIZE * 2:
                for i in range(0, len(chunk_lines), CHUNK_SIZE):
                    sub = chunk_lines[i : i + CHUNK_SIZE]
                    chunks.append({
                        "text": "\n".join(sub),
                        "file": relative_path,
                        "start_line": start_line + i + 1,
                        "end_line": start_line + i + len(sub),
                        "language": language,
                        "name": _node_name(node)
                    })
            else:
                chunks.append({
                    "text": "\n".join(chunk_lines),
                    "file": relative_path,
                    "start_line": start_line + 1,
                    "end_line": end_line + 1,
                    "language": language,
                    "name": _node_name(node)
                })

            return
        
        for child in node.children:
            visit(child)

    visit(tree.root_node)

    if not chunks:
        return _fallback_chunks(content, file_path, repo_path)
    
    return chunks