import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch
import numpy as np

from common.config import EASYOCR_MODEL_DIR

from flow.document_text_extractor import deduplicate_questions, extract_image_text, parse_questions
from flow.output_generator import generate_markdown, save_markdown

class ParsingTests(unittest.TestCase):
    def test_question_and_answer_continue_across_pages(self):
        pages = [
            {"page_number": 1, "raw_text": "Q1: Find the second highest salary?\nAnswer:\nSELECT salary\nFROM employees"},
            {"page_number": 2, "raw_text": "ORDER BY salary DESC;\nQ2: What is a JOIN?\nAnswer: Combines rows."}
        ]
        questions = parse_questions(pages, {"document_id": "doc"})
        self.assertEqual(len(questions), 2)
        self.assertIn("FROM employees\nORDER BY salary DESC;", questions[0]["answer"])
        self.assertEqual(questions[0]["sources"][0]["page_end"], 2)

    def test_gap_does_not_merge_unrelated_text(self):
        pages = [
            {"page_number": 1, "raw_text": "1. What is SQL?\nAnswer: A language."},
            {"page_number": 3, "raw_text": "Unrelated continuation\n2. Explain joins?"}
        ]
        questions = parse_questions(pages, {})
        self.assertEqual(len(questions), 2)
        self.assertNotIn("Unrelated", questions[0]["answer"])
        self.assertTrue(questions[0]["needs_review"])

class OCRTests(unittest.TestCase):
    def setup(self):
        from PIL import Image
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.paths = [Path(folder.name) / f"page-{number}.png" for number in (1, 2)]
        for path in self.paths:
            Image.new("RGB", (24, 24), "white").save(path)
        self.easyocr = Mock()
        self.reader = self.easyocr.Reader.return_value
        modules = patch.dict("sys.modules", {"easyocr": self.easyocr})
        modules.start()
        self.addCleanup(modules.stop)
        shared = patch("flow.document_text_extractor.ocr_reader", None)
        shared.start()
        self.addCleanup(shared.stop)

    def test_one_reader_for_multiple_saved_images_without_success_retry(self):
        self.setup()
        self.easyocr.Reader.assert_not_called()
        self.reader.readtext.return_value = ["Q1: What is SQL?"]
        for path in self.paths:
            self.assertEqual(extract_image_text(path)["text_status"], "extracted")
        self.easyocr.Reader.assert_called_once_with(
            ["en"],
            gpu=False,
            download_enabled=False,
            model_storage_directory=rf"{EASYOCR_MODEL_DIR}",
            verbose=False
        )
        self.assertEqual(self.reader.readtext.call_count, 2)
        for args, kwargs in self.reader.readtext.call_args_list:
            self.assertEqual(args[0].shape, (24, 24, 3))
            self.assertTrue((args[0] == 255).all())
            self.assertEqual(kwargs, {"detail": 0})

if __name__ == "main":
    unittest.main()
