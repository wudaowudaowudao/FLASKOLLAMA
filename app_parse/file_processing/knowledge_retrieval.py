"""Knowledge-base retrieval for upstream agent orchestration.

This module deliberately stops after vector retrieval.  The caller owns the
final prompt, tool calls, and answer generation.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable, List

from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import FAISS

from app_parse.DataManager.DB_Manager import FileSet, KnowledgeBase
from config import Config


class KnowledgeRetrievalError(RuntimeError):
    """Raised when a selected knowledge index cannot be loaded."""


def _source_name(identifier: str) -> str:
    knowledge_file = KnowledgeBase.query.filter_by(id=identifier).first()
    if knowledge_file and knowledge_file.name:
        return knowledge_file.name
    file_set = FileSet.query.filter_by(id=identifier).first()
    if file_set and file_set.name:
        return file_set.name
    return str(identifier)


def _annotate_sources(vector_store: Any, source: str) -> None:
    inferred_source = source
    if str(source).isdigit():
        for document in vector_store.docstore._dict.values():
            text = document.page_content or ""
            match = re.match(r"^(.+?)\s+第\d+页[：:]", text)
            if match:
                inferred_source = re.sub(r"_\d{14}A\d+$", "", match.group(1))
                if not os.path.splitext(inferred_source)[1]:
                    inferred_source += ".pdf"
                break
            part = re.search(r"本部分为Q/CSR 56的第([345])部分", text)
            if part:
                titles = {
                    "3": "装配建模",
                    "4": "模型投影工程图",
                    "5": "设计更改",
                }
                inferred_source = (
                    f"Q/CSR 56.{part.group(1)} 三维建模通用规则 "
                    f"第{part.group(1)}部分 {titles[part.group(1)]}.pdf"
                )
                break

    for document in vector_store.docstore._dict.values():
        document.metadata = dict(document.metadata or {})
        document.metadata.setdefault("source", inferred_source)


class KnowledgeRetriever:
    """Load selected FAISS indexes and return ranked document fragments."""

    def __init__(self) -> None:
        self.embeddings = OllamaEmbeddings(
            model="bge-m3:latest", base_url=Config.OLLAMA_BASE_URL
        )
        self.db = None

    def load_database(
        self,
        db_path: str | Path,
        source_name: str | None = None,
        index_name: str | None = None,
    ) -> None:
        path = Path(db_path)
        if not path.exists():
            raise KnowledgeRetrievalError(f"知识库索引不存在: {path}")

        if index_name:
            index_files = [Path(index_name).stem]
        else:
            index_files = [item.stem for item in path.glob("*.faiss")]
        if not index_files:
            raise KnowledgeRetrievalError(f"知识库索引为空: {path}")

        for index_file in index_files:
            vector_store = FAISS.load_local(
                str(path),
                self.embeddings,
                index_name=index_file,
                allow_dangerous_deserialization=True,
            )
            _annotate_sources(vector_store, source_name or index_file)
            if self.db is None:
                self.db = vector_store
            else:
                self.db.merge_from(vector_store)

    def retrieve(self, question: str, top_k: int = 8) -> List[dict[str, Any]]:
        if self.db is None:
            return []
        results = self.db.similarity_search_with_score(question, k=top_k)
        fragments: List[dict[str, Any]] = []
        for rank, (document, score) in enumerate(results, start=1):
            fragments.append(
                {
                    "rank": rank,
                    "content": document.page_content,
                    "source": (document.metadata or {}).get("source")
                    or "未标注来源",
                    "score": float(score),
                }
            )
        return fragments


def load_selected_databases(
    knowledge_ids: Iterable[str],
) -> KnowledgeRetriever:
    """Load the same file-set and simulated indexes used by legacy /chat."""

    retriever = KnowledgeRetriever()
    base_folder = Path(Config.PARSE_FILE_SETTINGS["BASE_FAISS_SAVE_FOLDER"])
    sim_folder = Path(Config.PARSE_FILE_SETTINGS["SIM_FAISS_SAVE_FOLDER"])

    for set_id in knowledge_ids:
        set_id = str(set_id)
        base_path = base_folder / set_id
        sim_path = sim_folder / set_id
        selected_path = base_path if base_path.exists() else sim_path
        file_ids = KnowledgeBase.get_all_file_set_ids(set_id)
        is_simulated = selected_path.exists() and selected_path == sim_path

        if selected_path.exists() and not (is_simulated and file_ids):
            retriever.load_database(selected_path, _source_name(set_id))

        for file_id in file_ids:
            file_id = str(file_id)
            if is_simulated:
                if selected_path.exists():
                    retriever.load_database(
                        selected_path, _source_name(file_id), index_name=file_id
                    )
                continue

            file_base_path = base_folder / file_id
            file_sim_path = sim_folder / file_id
            file_path = file_base_path if file_base_path.exists() else file_sim_path
            if file_path.exists():
                retriever.load_database(
                    file_path,
                    _source_name(file_id),
                    index_name=file_id if file_path == file_sim_path else None,
                )

    return retriever
