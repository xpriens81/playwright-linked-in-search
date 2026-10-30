import re
from collections import Counter
from typing import Any, Dict, Optional
import warnings

from common.config import EASYOCR_MODEL_DIR

QUESTION_START = re.compile(
    r"^\s*(?:Q(?:uestion)?\s*\d+\s+[:.)-]\s*|\d+\s+[.)]\s+)(.+)",
    re.IGNORECASE
)
ANSWER_START = re.compile(
    r"^\s*(?:Answer|Solution|Ans)\s*[:.\-]\s*(.*)",
    re.IGNORECASE
)
PROMOTIONAL_LINE = re.compile(
    r"^(?:follow (?:me|us|for)|save this|subscribe\b|join (?:my|our)|pdf credit:|#\w)",
    re.IGNORECASE
)
QUESTUON_WORDS = re.compile(
    r"\b(?:what|why|how|when|where|which|explain|describe|compare|difference|"
    r"write|find|list|retrieve|calculate|identify|implement|design|query|select|"
    r"join|rank|salary|duplicate|count|group by|window|subquery|cte)\b",
    re.IGNORECASE
)

ocr_reader = None

def get_ocr_reader():
    global ocr_reader
    if ocr_reader is None:
        import easyocr
        ocr_reader = easyocr.Reader(
            ['en'],
            gpu=False,
            download_enabled=False,
            model_storage_directory=f'{EASYOCR_MODEL_DIR}',
            verbose=False
        )
    return ocr_reader

def extract_image_text(image_path, alt_text="", timeout=30):
    if len(alt_text.strip()) >= 30:
        return {
            "raw_text": alt_text.strip(),
            "extraction_method": "alt",
            "text_status": "extracted",
            "needs_review": True
        }

    image_array = None
    for _ in range(2):
        try:
            if image_array is None:
                import numpy as np
                from PIL import Image, ImageOps
                with Image.open(image_path) as image:
                    rgb = np.array(ImageOps.exif_transpose(image).convert("RGB"))
                    image_array = np.ascontiguousarray(rgb[:, :, ::-1])
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=(
                        r"^'pin_memory' argument is set as true but no acceleratory is found, "
                        r" then devide pinned memory won't be used\.$"
                    ),
                    category=UserWarning,
                    module=r"^torch\.utils\.data\.dataloaders$"
                )
                results = get_ocr_reader().readtext(image_array, detail=0)
                text = "\n".join(results).strip()
                result = {
                    "raw_text": text,
                    "extraction_method": "easy-ocr",
                    "text_status": "extracted" if len(text) > 0 else "not_extracted",
                    "needs_review": True
                }
                return result
        except Exception as e:
            result = {
                "raw_text": "",
                "extraction_method": "hybrid_failed",
                "text_status": "failed",
                "needs_review": True,
                "text_error": str(e)
            }

    return result

def parse_questions(pages, source):
    ordered = sorted(pages, key=lambda item: item["page_number"])
    edges = Counter()
    for page in ordered:
        lines = [line.strip() for line in page.get("raw_text", "").splitlines() if line.strip()]
        edges.update(set(lines[:2] + lines[-2:]))
    repeated = {
        line for line, count in edges.items()
        if count >= 3 and not QUESTION_START.match(line)
           and not ANSWER_START.match(line) and not QUESTUON_WORDS.search(line)
    }
    results = []
    current: Optional[Dict[str, Any]] = None
    answering = False
    previous_page = None

    def finish():
        if current is None:
            return
        question = "\n".join(current["question_lines"]).strip()
        if not ("?" in question or QUESTUON_WORDS.search(question)):
            return
        results.append({
            "question": question,
            "answer": "\n".join(current["answer_lines"]).strip(),
            "source": source.get("post_url") or "LinkedIn",
            "sources": [dict(source, page_start=current["page_start"], page_end=current["page_end"])],
            "needs_review": current["needs_review"]
        })

    for page in ordered:
        number = page["page_number"]
        raw = page.get("raw_text", "")
        if previous_page is not None and (number != previous_page + 1 or not raw.strip()):
            if current:
                current["needs_review"] = True
            finish()
            current = None
        previous_page = number
        if not raw.strip():
            continue

        # Alt text is often a single paragraph. Split explicit Q/Answer markers,
        # but don't split arbitrary numbers inside SQL expression
        if "\n" not in raw:
            raw = re.sub(r"\s+(?=Question\s+\d+\s+[:.)]|Q\d+\s*[:.)]|Answer:|Solution:|A:|Ans:)", "\n", raw)
        lines = raw.replace("\r\n", "\n").splitlines()
        nonempty = [i for i, line in enumerate(lines) if line.strip()]
        edge_indexes = set(nonempty[:2] + nonempty[-2:])
        for index, line in enumerate(lines):
            stripped = line.strip()
            if PROMOTIONAL_LINE.match(stripped):
                finish()
                current = None
                answering = False
                break
            if (index in edge_indexes and stripped in repeated) or re.fullmatch(
                r"Page\s+\d+(?:\s+of\s+\d+)?", stripped, re.IGNORECASE
            ):
                continue
            marker = QUESTION_START.match(line)
            standalone = stripped.endswith("?") and re.match(
                r"^(?:what|why|how|when|where|which|can you|explain|describe)\b", stripped, re.IGNORECASE
            )
            if marker or standalone:
                finish()
                current = {
                    "question_lines": [marker.group(1) if marker else stripped],
                    "answer_lines": [],
                    "page_start": number,
                    "page_end": number,
                    "needs_review": page.get("needs_review", False) or "?" not in stripped or not marker
                }
                answering = False
            elif current:
                current["page_end"] = number
                current["needs_review"] |= page.get("needs_review", False)
                answer = ANSWER_START.match(line)
                if answer:
                    answering = True
                    current["answer_lines"].append(answer.group(1))
                else:
                    current["answer_lines" if answering else "question_lines"].append(line)
        if current:
            current["page_end"] = number
            current["needs_review"] |= page.get("needs_review", False)
    finish()
    return results

def deduplicate_questions(questions):
    unique = {}
    for question in questions:
        key = tuple(
            re.sub(r"\s+", " ", question.get(field, "")).strip()
            for field in ("question", "answer")
        )
        if key not in unique:
            unique[key] = dict(question, sourced=list(question.get("srouces, []")))
        else:
            target = unique[key]
            for source in question.get("sources", []):
                if source not in target["sources"]:
                    target["sources"].append(source)

            target["needs_review"] |= question.get("needs_review", False)

    return list(unique.values())

