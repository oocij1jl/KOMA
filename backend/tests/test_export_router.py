import json
import unittest

from fastapi.testclient import TestClient
from pymarc import MARCReader

from backend.main import app

SAMPLE_FIELDS = [
    {"tag": "020", "ind1": " ", "ind2": " ", "subfields": [{"code": "a", "value": "9788936434120"}]},
    {"tag": "245", "ind1": "1", "ind2": "0", "subfields": [{"code": "a", "value": "소년이 온다"}, {"code": "c", "value": "한강"}]},
    {"tag": "260", "ind1": " ", "ind2": " ", "subfields": [{"code": "b", "value": "창비"}, {"code": "c", "value": "2014"}]},
]


class ExportRouterTests(unittest.TestCase):
    def test_export_json_returns_fields_as_is(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/export/marc", json={"fields": SAMPLE_FIELDS, "format": "json"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/json")
        body = response.json()
        self.assertEqual(len(body), 3)
        self.assertEqual(body[1]["tag"], "245")
        self.assertEqual(body[1]["subfields"][0]["value"], "소년이 온다")

    def test_export_mrk_produces_readable_marc_text(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/export/marc", json={"fields": SAMPLE_FIELDS, "format": "mrk"})

        self.assertEqual(response.status_code, 200)
        text = response.content.decode("utf-8")
        self.assertIn("=020", text)
        self.assertIn("=245  10$a소년이 온다$c한강", text)
        self.assertIn("=260", text)

    def test_export_mrc_produces_valid_binary_marc_record(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/export/marc", json={"fields": SAMPLE_FIELDS, "format": "mrc"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/marc")

        # 진짜 pymarc 리더로 다시 파싱해서 왕복(round-trip)이 되는지 확인한다.
        reader = MARCReader(response.content, to_unicode=True, force_utf8=True)
        records = list(reader)
        self.assertEqual(len(records), 1)
        record = records[0]

        isbn_field = record.get_fields("020")[0]
        self.assertEqual(isbn_field.get_subfields("a")[0], "9788936434120")

        title_field = record.get_fields("245")[0]
        self.assertEqual(title_field.indicator1, "1")
        self.assertEqual(title_field.indicator2, "0")
        self.assertEqual(title_field.get_subfields("a")[0], "소년이 온다")
        self.assertEqual(title_field.get_subfields("c")[0], "한강")

    def test_export_accepts_indicator1_indicator2_naming_like_generate_output(self) -> None:
        """편집 화면에서 GeneratedField 모양(indicator1/indicator2) 그대로 보내도 동작해야 한다."""
        fields = [
            {"tag": "020", "indicator1": " ", "indicator2": " ", "subfields": [{"code": "a", "value": "9788936434120"}]},
            {"tag": "245", "indicator1": "1", "indicator2": "0", "subfields": [{"code": "a", "value": "소년이 온다"}]},
        ]
        with TestClient(app) as client:
            response = client.post("/api/export/marc", json={"fields": fields, "format": "mrc"})

        self.assertEqual(response.status_code, 200)
        reader = MARCReader(response.content, to_unicode=True, force_utf8=True)
        record = list(reader)[0]
        title_field = record.get_fields("245")[0]
        self.assertEqual(title_field.indicator1, "1")
        self.assertEqual(title_field.indicator2, "0")

    def test_export_rejects_empty_fields(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/export/marc", json={"fields": [], "format": "mrc"})

        self.assertEqual(response.status_code, 422)

    def test_export_defaults_to_mrk_format(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/export/marc", json={"fields": SAMPLE_FIELDS})

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.headers["content-type"])


if __name__ == "__main__":
    unittest.main()
