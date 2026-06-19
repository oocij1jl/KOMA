import subprocess
import sys
import unittest
import tempfile
from typing import cast
from pathlib import Path
from unittest.mock import patch

from backend.schemas.llm import LLMInputPayload
from backend.schemas.llm_output import FieldEvidence, GenerateResult
from backend.schemas.lookup import BiblioSchema, EvidenceSchema
from backend.services.marc_generator import build_prompt, select_generation_tags
import backend.services.rag_loader as rag_loader
from backend.services.rag_loader import load_rules


def vegetarian_payload() -> LLMInputPayload:
    return LLMInputPayload(
        isbn="9788936434595",
        biblio=BiblioSchema(
            found=True,
            isbn_ea="9788936434595",
            isbn_add_code="03810",
            price="₩15000",
            title="채식주의자",
            author="한강 지음",
            publisher="창비",
            publish_year="2022",
            field_sources={"title": "nl.go.kr", "publisher": "data4library.kr"},
        ),
        evidence=EvidenceSchema.model_validate(
            {
                "keywords": [
                    {"word": "채식주의", "weight": 0.91},
                    {"word": "한국소설", "weight": 0.88},
                    {"word": "폭력", "weight": 0.72},
                ],
                "description": "채식주의를 선택한 인물을 둘러싼 가족과 사회의 폭력을 다룬 한국 장편소설.",
                "co_loan_books": [
                    {"bookname": "소년이 온다", "isbn13": "9788936434120", "authors": "한강"}
                ],
                "title": "채식주의자",
                "author": "한강 지음",
                "kdc_from_api": "813.7",
                "ddc_from_api": "",
                "translation_signals": {"detected": False, "hints": []},
                "available": {
                    "keywords": True,
                    "description": True,
                    "co_loan_books": True,
                    "translation_signals": True,
                },
            }
        ),
    )


class PromptBuildTests(unittest.TestCase):
    def test_load_rules_returns_653_jsonl_content(self) -> None:
        rules = load_rules(["653"])

        self.assertIn("653", rules)
        self.assertIn("653 필드는", rules["653"])
        self.assertIn("비통제 색인어", rules["653"])

    def test_load_rules_skips_missing_tag_without_error(self) -> None:
        self.assertEqual(load_rules(["020"]), {})

    def test_load_rules_rejects_path_like_tags(self) -> None:
        self.assertEqual(load_rules(["../653", "653/../../020", "/653", "abc"]), {})

    def test_load_rules_skips_malformed_jsonl_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            chunks_dir = Path(temp_dir)
            malformed_jsonl = "\n".join(
                [
                    '{"title":"valid","section":"generation","content":"정상 규칙"}',
                    "{not valid json}",
                    "",
                ]
            )
            _ = (chunks_dir / "kormarc-999.jsonl").write_text(malformed_jsonl, encoding="utf-8")

            with patch.object(rag_loader, "RAG_CHUNKS_DIR", chunks_dir):
                rules = load_rules(["999"])

        self.assertIn("999", rules)
        self.assertIn("정상 규칙", rules["999"])

    def test_select_generation_tags_excludes_650(self) -> None:
        tags = select_generation_tags(vegetarian_payload())

        self.assertNotIn("650", tags)
        self.assertIn("653", tags)

    def test_build_prompt_contains_required_materials(self) -> None:
        payload = vegetarian_payload()
        prompt = build_prompt(payload)

        self.assertIn("채식주의자", prompt)
        self.assertIn("채식주의", prompt)
        for constraint in payload.constraints:
            self.assertIn(constraint, prompt)
        self.assertIn("FIELD_EVIDENCE_MAP", prompt)
        self.assertIn("각 필드에 사용 가능한 evidence 소스", prompt)
        self.assertIn("RAG RULES", prompt)
        self.assertIn("653 필드는", prompt)
        self.assertIn("indicator1", prompt)
        self.assertIn("indicator2", prompt)
        self.assertNotIn('"ind1"', prompt)
        self.assertNotIn('"ind2"', prompt)
        self.assertIn('"653": [', prompt)
        self.assertIn('"650": []', prompt)
        self.assertNotIn("rag_notes", prompt)
        self.assertNotIn("skip_allowed", prompt)
        self.assertIn("650은 skipped_by_default", prompt)
        self.assertIn("통제 주제명은 표목표 대조 필요: 653으로 대체", prompt)

    def test_output_schema_uses_from_alias(self) -> None:
        evidence = FieldEvidence.model_validate(
            {
                "from": ["keywords"],
                "keywords_used": ["채식주의(0.91)"],
                "reasoning": "키워드 근거",
            }
        )

        self.assertEqual(evidence.from_, ["keywords"])
        self.assertEqual(evidence.model_dump(by_alias=True)["from"], ["keywords"])
        _ = GenerateResult.model_validate(
            {
                "fields": [
                    {
                        "tag": "653",
                        "indicator1": " ",
                        "indicator2": " ",
                        "subfields": [{"code": "a", "value": "채식주의"}],
                        "source": "ai_inference",
                        "review_required": True,
                        "confidence": "medium",
                        "evidence": evidence.model_dump(by_alias=True),
                    }
                ],
                "skipped_fields": [{"tag": "650", "reason": "통제 주제명은 표목표 대조 필요: 653으로 대체"}],
                "warnings": ["653 색인어는 키워드 기반 추론 — 반드시 검수"],
            }
        )

        with self.assertRaises(ValueError):
            _ = GenerateResult.model_validate(
                {
                    "fields": [
                        {
                            "tag": "653",
                            "indicator1": " ",
                            "indicator2": " ",
                            "subfields": [{"code": "a", "value": "채식주의"}],
                            "source": "ai_inference",
                            "review_required": True,
                            "confidence": "medium",
                        }
                    ],
                    "skipped_fields": [],
                    "warnings": [],
                }
            )

        with self.assertRaises(ValueError):
            _ = GenerateResult.model_validate(
                {
                    "fields": [
                        {
                            "tag": "653",
                            "indicator1": " ",
                            "indicator2": " ",
                            "subfields": [],
                            "source": "api",
                            "review_required": False,
                            "confidence": "high",
                        }
                    ],
                    "skipped_fields": [],
                    "warnings": [],
                }
            )

    def test_output_schema_json_schema_has_marc_constraints(self) -> None:
        schema = cast(dict[str, object], GenerateResult.model_json_schema())
        schema_defs = cast(dict[str, dict[str, object]], schema["$defs"])
        generated_field = schema_defs["GeneratedField"]
        skipped_field = schema_defs["SkippedField"]
        subfield_item = schema_defs["SubfieldItem"]
        generated_field_properties = cast(dict[str, dict[str, object]], generated_field["properties"])
        skipped_field_properties = cast(dict[str, dict[str, object]], skipped_field["properties"])
        subfield_item_properties = cast(dict[str, dict[str, object]], subfield_item["properties"])

        self.assertEqual(generated_field_properties["tag"]["pattern"], r"^\d{3}$")
        self.assertEqual(list(generated_field_properties)[:2], ["tag", "source"])
        self.assertEqual(generated_field_properties["indicator1"]["minLength"], 1)
        self.assertEqual(generated_field_properties["indicator1"]["maxLength"], 1)
        self.assertEqual(generated_field_properties["indicator2"]["minLength"], 1)
        self.assertEqual(generated_field_properties["indicator2"]["maxLength"], 1)
        self.assertEqual(generated_field_properties["subfields"]["minItems"], 1)
        self.assertEqual(skipped_field_properties["tag"]["pattern"], r"^\d{3}$")
        self.assertEqual(subfield_item_properties["code"]["pattern"], r"^[a-z0-9]$")
        self.assertIn("allOf", generated_field)

    def test_new_prompt_layer_contains_no_llm_call_code(self) -> None:
        suspicious_fragments = [
            "Open" + "AI(",
            "Anth" + "ropic(",
            "Generative" + "Model(",
            "chat" + ".completions",
            "messages" + ".create",
            "generate" + "_content",
        ]
        files = [
            Path("backend/services/marc_generator.py"),
            Path("backend/services/rag_loader.py"),
            Path("backend/schemas/llm_output.py"),
        ]

        combined_source = "\n".join(path.read_text(encoding="utf-8") for path in files)
        for fragment in suspicious_fragments:
            self.assertNotIn(fragment, combined_source)

    def test_marc_generator_supports_backend_local_import(self) -> None:
        backend_dir = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-c", "import services.marc_generator"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    _ = unittest.main()
