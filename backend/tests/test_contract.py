"""API contract: every route is classified and documented, and every JSON reply uses the envelope."""
from app.api.docs import SUMMARIES, build_spec
from tests.conftest import UA


def test_every_api_route_is_classified_and_documented(app):
    spec = build_spec(app)
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        view = app.view_functions[rule.endpoint]
        assert getattr(view, "zero_trust_permission", None) or getattr(view, "zero_trust_public", False), rule.rule
    ops = [op for methods in spec["paths"].values() for op in methods.values()]
    assert len(ops) >= 45
    for op in ops:
        assert op["summary"] and "responses" in op
        if op["security"]:
            assert op["x-permission"] and "401" in op["responses"] and "403" in op["responses"]


def test_request_bodies_come_from_the_validation_schemas(app):
    spec = build_spec(app)
    body = spec["paths"]["/api/patients"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": "#/components/schemas/PatientIn"}
    patient = spec["components"]["schemas"]["PatientIn"]
    assert patient["additionalProperties"] is False and "hba1c" in patient["properties"]
    upload = spec["paths"]["/api/radiographs"]["post"]["requestBody"]["content"]
    assert "multipart/form-data" in upload


def test_summaries_point_at_real_endpoints(app):
    assert set(SUMMARIES) <= set(app.view_functions)


def test_envelope_on_success_and_errors(client, dentist):
    for path, headers in (("/api/health", UA), ("/api/patients", dentist), ("/api/patients", UA),
                          ("/api/nope", UA), ("/api/patients/99999999", dentist)):
        body = client.get(path, headers=headers).get_json()
        assert set(body) == {"data", "meta", "error", "mode"}, path
