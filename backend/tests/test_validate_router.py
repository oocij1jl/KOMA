import unittest

from fastapi.testclient import TestClient

from backend.main import app


VALID_FIELDS = [
    {"tag": "020", "ind1": " ", "ind2": " ", "subfields": [{"code": "a", "value": "9788936434120"}]},
    {"tag": "245", "ind1": "1", "ind2": "0", "subfields": [{"code": "a", "value": "소년이 온다"}]},
    {"tag": "260", "ind1": " ", "ind2": " ", "subfields": [{"code": "b", "value": "창비"}, {"code": "c", "value": "2014"}]},
]


class ValidateRouterTests(unittest.TestCase):
    def test_valid_record_returns_no_errors(self) -> None:
        with TestClient(app) as client:
            response = client.post("/api/validate", json={"fields": VALID_FIELDS})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["valid"])
        self.assertEqual(body["error_count"], 0)
        self.assertEqual(body["errors"], [])

    def test_missing_required_tag_reports_error(self) -> None:
        fields = [f for f in VALID_FIELDS if f["tag"] != "260"]
        with TestClient(app) as client:
            response = client.post("/api/validate", json={"fields": fields})

        body = response.json()
        self.assertFalse(body["valid"])
        self.assertTrue(any(err["field"] == "260" for err in body["errors"]))

    def test_invalid_tag_format_reports_error(self) -> None:
        fields = VALID_FIELDS + [{"tag": "12", "ind1": " ", "ind2": " ", "subfields": []}]
        with TestClient(app) as client:
            response = client.post("/api/validate", json={"fields": fields})

        body = response.json()
        self.assertFalse(body["valid"])
        self.assertTrue(any(err["field"] == "12" for err in body["errors"]))

    def test_invalid_isbn_format_reports_error(self) -> None:
        fields = [
            {"tag": "020", "ind1": " ", "ind2": " ", "subfields": [{"code": "a", "value": "abc"}]},
            VALID_FIELDS[1],
            VALID_FIELDS[2],
        ]
        with TestClient(app) as client:
            response = client.post("/api/validate", json={"fields": fields})

        body = response.json()
        self.assertFalse(body["valid"])
        self.assertTrue(any("ISBN" in err["message"] for err in body["errors"]))

    def test_056_082_650_produce_review_warnings(self) -> None:
        fields = VALID_FIELDS + [
            {"tag": "056", "ind1": " ", "ind2": " ", "subfields": [{"code": "a", "value": "813.7"}]},
        ]
        with TestClient(app) as client:
            response = client.post("/api/validate", json={"fields": fields})

        body = response.json()
        self.assertTrue(body["valid"])
        self.assertEqual(body["warning_count"], 1)
        self.assertEqual(body["warnings"][0]["field"], "056")

    def test_accepts_indicator1_indicator2_naming_like_generate_output(self) -> None:
        """/api/generate가 돌려주는 GeneratedField는 indicator1/indicator2를 쓴다.
        편집 화면에서 리매핑 없이 그대로 돌아와도 지시기호가 조용히 공백으로
        무시되지 않고 실제 값으로 검증돼야 한다."""
        fields = [
            {"tag": "020", "indicator1": " ", "indicator2": " ", "subfields": [{"code": "a", "value": "9788936434120"}]},
            {"tag": "245", "indicator1": "1", "indicator2": "0", "subfields": [{"code": "a", "value": "소년이 온다"}]},
            {"tag": "260", "indicator1": " ", "indicator2": " ", "subfields": [{"code": "b", "value": "창비"}, {"code": "c", "value": "2014"}]},
            # 지시기호가 2자리로 잘못 들어와도(indicator1 별칭 경로로) 여전히 에러로 잡혀야 함
            {"tag": "500", "indicator1": "12", "indicator2": " ", "subfields": [{"code": "a", "value": "메모"}]},
        ]
        with TestClient(app) as client:
            response = client.post("/api/validate", json={"fields": fields})

        body = response.json()
        self.assertFalse(body["valid"])
        self.assertTrue(
            any(err["field"] == "500" and "ind1" in err["message"] for err in body["errors"]),
            body["errors"],
        )


if __name__ == "__main__":
    unittest.main()
