"""Exercise graph-link output without importing the Flask/model runtime.

Compile the production class from its AST and replace only external services.
Run from the repository root with: python -B -m unittest discover -s tests -v
"""

import ast
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app_parse/file_processing/FaissRAG_Ollamachat_v2.py"
)
FILE_ID = "2112895930092118016"
OTHER_ID = "2112895930092118017"


def document(text="正文", **metadata):
    return SimpleNamespace(page_content=text, metadata=metadata)


class FakeVectorStore:
    def __init__(self, documents):
        self.documents = list(documents)
        self.docstore = SimpleNamespace(
            _dict={str(i): doc for i, doc in enumerate(self.documents)}
        )
        self.search_calls = []

    def merge_from(self, other):
        self.documents.extend(other.documents)
        self.docstore._dict = {
            str(i): doc for i, doc in enumerate(self.documents)
        }

    def similarity_search_with_score(self, query, k):
        self.search_calls.append((query, k))
        return [(doc, float(i)) for i, doc in enumerate(self.documents[:k])]


class KnowledgeSourceGraphLinksTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
        query_class = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "PDFQuerySystem"
        )
        self.listdir = Mock()
        self.load_local = Mock()
        self.save_chat = Mock()
        namespace = {
            "os": SimpleNamespace(path=os.path, listdir=self.listdir),
            "re": re,
            "FAISS": SimpleNamespace(load_local=self.load_local),
            "ChatMessage": SimpleNamespace(create_Chat=self.save_chat),
        }
        exec(compile(ast.Module(body=[query_class], type_ignores=[]),
                     str(SOURCE_PATH), "exec"), namespace)
        query_type = namespace["PDFQuerySystem"]
        self.query = query_type.__new__(query_type)
        self.query.embeddings = object()
        self.query.db = None
        self.query.messages = []
        self.query.final_input = ""
        self.query.ai_answer = []
        self.query.source_attributions = []
        self.query.question = ""
        self.query.session_id = "test-session"
        self.query.chain = SimpleNamespace(
            stream=Mock(return_value=iter([
                SimpleNamespace(content="回答"),
                SimpleNamespace(content="正文"),
            ]))
        )
        self.output = io.StringIO()
        self.stdout = redirect_stdout(self.output)
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)

    def load(self, indexes, source_name=None, index_name=None, db_path="indexes"):
        stores = {
            name: FakeVectorStore(documents)
            for name, documents in indexes.items()
        }
        self.listdir.return_value = [
            suffix for name in indexes for suffix in (name + ".faiss", name + ".pkl")
        ]
        self.load_local.side_effect = (
            lambda path, embeddings, index_name, **kwargs: stores[index_name]
        )
        self.query.load_database(db_path, source_name, index_name=index_name)
        self.assertIsNotNone(self.query.db, self.output.getvalue())
        return stores

    def answer(self, question="问题", use_vector_db=True, enable_thinking=True):
        self.query.set_final_input(question, use_vector_db, enable_thinking)
        streamed = "".join(self.query.generate())
        self.save_chat.assert_called_once_with("test-session", question, streamed)
        return streamed

    def test_standard_long_id_is_preserved_and_stream_matches_saved_answer(self):
        doc = document("装配规范 第1页：装配要求")
        self.load({FILE_ID: [doc]})
        answer = self.answer()
        self.assertEqual(
            answer,
            "回答正文\n\n知识来源：\n@graph: 装配规范.pdf|" + FILE_ID,
        )
        self.assertEqual(doc.metadata["file_id"], FILE_ID)
        self.assertIsInstance(doc.metadata["file_id"], str)
        self.assertEqual(self.query.db.search_calls, [("问题", 10)])
        self.query.chain.stream.assert_called_once_with({
            "input": self.query.final_input, "history": [],
        })

    def test_sim_set_directory_uses_child_ids_for_each_index(self):
        parent_id = "9999999999999999999"
        self.load(
            {FILE_ID: [document()], OTHER_ID: [document()]},
            source_name="仿真文件集",
            db_path="sim_indexes/" + parent_id,
        )
        answer = self.answer()
        self.assertIn("@graph: 仿真文件集|" + FILE_ID, answer)
        self.assertIn("@graph: 仿真文件集|" + OTHER_ID, answer)
        self.assertNotIn(parent_id, answer)
        self.assertEqual(self.load_local.call_count, 2)

    def test_explicit_sim_child_index_does_not_scan_parent_directory(self):
        self.load(
            {FILE_ID: [document()], OTHER_ID: [document()]},
            source_name="子文件.pdf", index_name=FILE_ID,
            db_path="sim_indexes/9999999999999999999",
        )
        answer = self.answer()
        self.listdir.assert_not_called()
        self.assertEqual(self.load_local.call_count, 1)
        self.assertIn("@graph: 子文件.pdf|" + FILE_ID, answer)
        self.assertNotIn(OTHER_ID, answer)

    def test_legacy_content_list_index_recovers_id_and_pdf_name(self):
        doc = document("装配规范_20250922100833A1 第2页：装配要求")
        self.load({FILE_ID + "_content_list": [doc]})
        answer = self.answer()
        self.assertIn("@graph: 装配规范.pdf|" + FILE_ID, answer)
        self.assertNotIn("_content_list", answer)

    def test_legacy_uuid_id_is_preserved(self):
        file_id = "0495d7a5-4df6-40cd-b76c-68fab57ef7b6"
        self.load({file_id: [document()]}, source_name="旧文件.pdf")
        self.assertIn("@graph: 旧文件.pdf|" + file_id, self.answer())

    def test_explicit_metadata_ids_override_index_ids_and_support_both_spellings(self):
        first_id = "2112895930092118100"
        second_id = "2112895930092118200"
        first = document(source="甲.pdf", file_id=int(first_id), fileId="ignored")
        second = document(source="乙.pdf", fileId=second_id)
        self.load({FILE_ID: [first], OTHER_ID: [second]}, source_name="父级名称")
        answer = self.answer()
        self.assertIn("@graph: 甲.pdf|" + first_id, answer)
        self.assertIn("@graph: 乙.pdf|" + second_id, answer)
        self.assertNotIn("ignored", answer)
        self.assertEqual(first.metadata["file_id"], first_id)
        self.assertIsInstance(first.metadata["file_id"], str)
        self.assertEqual(second.metadata["file_id"], second_id)

    def test_same_name_different_ids_stay_separate_and_same_id_chunks_deduplicate(self):
        self.load({
            FILE_ID: [document(source="同名.pdf"), document(source="同文件别名.pdf")],
            OTHER_ID: [document(source="同名.pdf")],
        })
        answer = self.answer()
        self.assertEqual(answer.count("@graph:"), 2)
        self.assertIn("@graph: 同名.pdf|" + FILE_ID, answer)
        self.assertIn("@graph: 同名.pdf|" + OTHER_ID, answer)
        self.assertNotIn("同文件别名", answer)
        self.assertEqual(self.query.source_attributions[0]["hits"], 2)
        self.assertEqual(self.query.source_attributions[0]["best_rank"], 1)

    def test_unknown_legacy_index_remains_plain_text(self):
        self.load({"old_named_index": [document()]}, source_name="旧来源.pdf")
        answer = self.answer()
        self.assertTrue(answer.endswith("\n\n知识来源：\n旧来源.pdf"))
        self.assertNotIn("@graph:", answer)
        self.assertNotIn("file_id", self.query.db.documents[0].metadata)

    def test_marker_sanitizes_display_text_and_rejects_id_delimiters(self):
        self.load({FILE_ID: [document(
            source="  表格|名称 \r\n第 二\t页.pdf  ", file_id="bad|id\nother",
        )]})
        answer = self.answer()
        self.assertEqual(answer.splitlines()[-1],
                         "@graph: 表格｜名称 第 二 页.pdf|" + FILE_ID)
        self.assertEqual(answer.count("|"), 1)
        self.assertNotIn("bad", answer)

    def test_only_top_ten_chunks_are_used_and_at_most_five_sources_are_shown(self):
        docs = [
            document("片段%02d" % i, source="文件%02d.pdf" % i,
                     file_id=str(int(FILE_ID) + i))
            for i in range(12)
        ]
        self.load({"legacy_collection": docs})
        answer = self.answer()
        self.assertEqual(self.query.db.search_calls, [("问题", 10)])
        self.assertEqual(len(self.query.source_attributions), 5)
        self.assertEqual(answer.count("@graph:"), 5)
        self.assertIn("片段09", self.query.final_input)
        self.assertNotIn("片段10", self.query.final_input)
        for i in range(5):
            self.assertIn("@graph: 文件%02d.pdf|%s" % (i, int(FILE_ID) + i), answer)

    def test_non_rag_request_clears_prior_sources(self):
        self.query.source_attributions = [{"source": "旧来源", "file_id": FILE_ID}]
        answer = self.answer(use_vector_db=False, enable_thinking=False)
        self.assertEqual(answer, "回答正文")
        self.assertEqual(self.query.source_attributions, [])
        self.assertEqual(self.query.final_input, "问题 /no_think")

    def test_no_hits_clear_prior_sources(self):
        self.load({FILE_ID: [document()]}, source_name="旧来源.pdf")
        self.query.set_final_input("上次问题", use_vector_db=True)
        self.assertTrue(self.query.source_attributions)
        self.query.db.documents = []
        answer = self.answer()
        self.assertEqual(answer, "回答正文")
        self.assertEqual(self.query.source_attributions, [])


if __name__ == "__main__":
    unittest.main()
