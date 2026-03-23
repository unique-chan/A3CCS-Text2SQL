from __future__ import annotations

import os

# ---- MUST BE BEFORE ANY HF IMPORT ----
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ---- HARD KILL STDOUT/STDERR DURING MODEL LOAD ----
import contextlib
import sys

from transformers.utils import logging as hf_logging
hf_logging.set_verbosity_error()
hf_logging.disable_progress_bar()

import logging as py_logging
py_logging.getLogger("transformers").setLevel(py_logging.ERROR)
py_logging.getLogger("sentence_transformers").setLevel(py_logging.ERROR)
py_logging.getLogger("huggingface_hub").setLevel(py_logging.ERROR)

import ast
import hashlib
import json
import re
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


RAG_CACHE_VERSION = "v1"
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

@dataclass
class QueryTemplateDoc:
    name: str
    signature: str
    docstring: str
    source: str
    tags: List[str]
    text: str


@dataclass
class RetrievedQueryExample:
    name: str
    signature: str
    docstring: str
    source: str
    tags: List[str]
    score: float


@dataclass
class QueryRAGStore:
    bag_of_queries_path: str
    index_dir: str
    embedding_model_name: str
    docs: List[QueryTemplateDoc]
    encoder: Any
    index: Any

    def retrieve(self, question: str, top_k: int = 3, min_score: float = 0.05) -> List[RetrievedQueryExample]:
        question = (question or "").strip()
        if not question:
            return []

        np = _import_numpy()

        vector = self.encoder.encode(
            [question],
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype("float32")

        k = max(1, min(int(top_k), len(self.docs)))
        scores, indices = self.index.search(vector, k)

        out: List[RetrievedQueryExample] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.docs):
                continue
            score_value = float(score)
            if score_value < min_score:
                continue
            doc = self.docs[int(idx)]
            out.append(
                RetrievedQueryExample(
                    name=doc.name,
                    signature=doc.signature,
                    docstring=doc.docstring,
                    source=doc.source,
                    tags=list(doc.tags),
                    score=score_value,
                )
            )

        return out


def _import_embedding_libs():
    try:
        import faiss  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "RAG is enabled but faiss-cpu is not installed. Please run: pip install faiss-cpu"
        ) from e

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "RAG is enabled but sentence-transformers is not installed. Please run: pip install sentence-transformers"
        ) from e

    return faiss, SentenceTransformer


def _import_numpy():
    try:
        import numpy as np  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "RAG is enabled but numpy is not installed. Please run: pip install numpy"
        ) from e
    return np


def build_or_load_query_rag(
    bag_of_queries_path: str,
    index_dir: str,
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> QueryRAGStore:
    faiss, SentenceTransformer = _import_embedding_libs()
    np = _import_numpy()

    bag_path = Path(bag_of_queries_path)
    if not bag_path.exists():
        raise FileNotFoundError(f"bag_of_queries.py not found: {bag_of_queries_path}")

    docs = extract_query_template_docs(bag_path)
    if not docs:
        raise RuntimeError(f"No public query template functions found in {bag_of_queries_path}")

    cache_dir = Path(index_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = compute_bag_fingerprint(bag_path, embedding_model_name)
    meta_path = cache_dir / "meta.json"
    docs_path = cache_dir / "docs.json"
    index_path = cache_dir / "index.faiss"

    encoder = SentenceTransformer(embedding_model_name)

    if meta_path.exists() and docs_path.exists() and index_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("fingerprint") == fingerprint:
                raw_docs = json.loads(docs_path.read_text(encoding="utf-8"))
                loaded_docs = [QueryTemplateDoc(**item) for item in raw_docs]
                index = faiss.read_index(str(index_path))
                return QueryRAGStore(
                    bag_of_queries_path=str(bag_path),
                    index_dir=str(cache_dir),
                    embedding_model_name=embedding_model_name,
                    docs=loaded_docs,
                    encoder=encoder,
                    index=index,
                )
        except Exception:
            pass

    texts = [doc.text for doc in docs]
    embeddings = encoder.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32")

    if embeddings.ndim != 2 or embeddings.shape[0] != len(docs):
        raise RuntimeError("Failed to build query RAG embeddings with expected shape.")

    index = faiss.IndexFlatIP(int(embeddings.shape[1]))
    index.add(embeddings)

    docs_path.write_text(
        json.dumps([asdict(doc) for doc in docs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    faiss.write_index(index, str(index_path))
    meta_path.write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "embedding_model_name": embedding_model_name,
                "bag_of_queries_path": str(bag_path),
                "doc_count": len(docs),
                "cache_version": RAG_CACHE_VERSION,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return QueryRAGStore(
        bag_of_queries_path=str(bag_path),
        index_dir=str(cache_dir),
        embedding_model_name=embedding_model_name,
        docs=docs,
        encoder=encoder,
        index=index,
    )


def compute_bag_fingerprint(bag_path: Path, embedding_model_name: str) -> str:
    payload = {
        "cache_version": RAG_CACHE_VERSION,
        "embedding_model_name": embedding_model_name,
        "bag_sha256": hashlib.sha256(bag_path.read_bytes()).hexdigest(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def extract_query_template_docs(bag_path: Path) -> List[QueryTemplateDoc]:
    source_text = bag_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)

    docs: List[QueryTemplateDoc] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue

        raw_source = ast.get_source_segment(source_text, node) or ""
        function_source = textwrap.dedent(raw_source).strip()
        docstring = (ast.get_docstring(node) or "").strip()
        signature = build_function_signature(node)
        tags = extract_tags(node.name, docstring, function_source)
        text = build_doc_text(node.name, signature, docstring, function_source, tags)

        docs.append(
            QueryTemplateDoc(
                name=node.name,
                signature=signature,
                docstring=docstring,
                source=function_source,
                tags=tags,
                text=text,
            )
        )

    return docs


def build_function_signature(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""

    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    positional_defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)

    parts: List[str] = []
    for arg, default in zip(positional, positional_defaults):
        parts.append(_format_arg(arg, default))

    if args.vararg is not None:
        parts.append("*" + _format_arg(args.vararg, None))
    elif args.kwonlyargs:
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        parts.append(_format_arg(arg, default))

    if args.kwarg is not None:
        parts.append("**" + _format_arg(args.kwarg, None))

    returns = ""
    if getattr(node, "returns", None) is not None:
        returns = f" -> {_safe_unparse(node.returns)}"

    return f"{node.name}({', '.join(parts)}){returns}"


def _format_arg(arg: ast.arg, default: Optional[ast.AST]) -> str:
    text = arg.arg
    if arg.annotation is not None:
        text += f": {_safe_unparse(arg.annotation)}"
    if default is not None:
        text += f" = {_safe_unparse(default)}"
    return text


def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def extract_tags(name: str, docstring: str, source: str, max_tags: int = 16) -> List[str]:
    bag = f"{name} {name.replace('_', ' ')} {docstring} {source}"
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", bag.lower())

    stopwords = {
        "return",
        "returns",
        "specified",
        "latest",
        "within",
        "fixed",
        "with",
        "none",
        "true",
        "false",
        "limit",
        "from",
        "where",
        "select",
        "group",
        "order",
        "count",
        "datetime",
        "string",
        "build",
        "shared",
        "sql",
        "run",
        "get",
        "the",
        "and",
        "for",
        "def",
        "str",
        "int",
        "float",
        "bool",
        "clause",
        "_run",
    }

    ranked: List[str] = []
    seen = set()
    for token in tokens:
        if token in stopwords:
            continue
        if len(token) < 3:
            continue
        if token not in seen:
            ranked.append(token)
            seen.add(token)
        if len(ranked) >= max_tags:
            break

    return ranked


def build_doc_text(name: str, signature: str, docstring: str, source: str, tags: List[str]) -> str:
    return (
        f"name: {name}\n"
        f"signature: {signature}\n"
        f"docstring: {docstring or '(empty)'}\n"
        f"tags: {', '.join(tags) if tags else '(none)'}\n"
        "python_query_template:\n"
        f"{source}"
    )


def format_retrieved_examples(examples: List[RetrievedQueryExample]) -> str:
    if not examples:
        return "(no retrieved query templates)"

    blocks: List[str] = []
    for i, ex in enumerate(examples, start=1):
        header = [
            f"[QUERY_TEMPLATE_{i}]",
            f"name: {ex.name}",
            f"similarity: {ex.score:.4f}",
            f"signature: {ex.signature}",
            f"docstring: {ex.docstring or '(empty)'}",
        ]
        if ex.tags:
            header.append(f"tags: {', '.join(ex.tags)}")
        header.append("python_query_template:")
        blocks.append("\n".join(header) + f"\n```python\n{ex.source}\n```")

    return "\n\n".join(blocks)
