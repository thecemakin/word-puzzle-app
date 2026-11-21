from fastapi.testclient import TestClient

from app.main import app


def test_openapi_schema_has_complete_metadata_and_error_responses() -> None:
    with TestClient(app) as client:
        res = client.get("/openapi.json")
    assert res.status_code == 200
    spec = res.json()

    assert spec["info"]["version"] == "0.1.0"
    assert "ErrorResponse" in spec["components"]["schemas"]

    tag_names = {t["name"] for t in spec.get("tags", [])}
    assert {"system", "auth", "users", "games"}.issubset(tag_names)

    for path, methods in spec["paths"].items():
        if not path.startswith("/api/v1/"):
            continue
        for method, operation in methods.items():
            assert operation.get("summary"), f"Missing summary on {method.upper()} {path}"
            assert operation.get("tags"), f"Missing tags on {method.upper()} {path}"
            assert operation.get("responses"), f"Missing responses on {method.upper()} {path}"
