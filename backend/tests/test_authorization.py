"""Authorization tests: vertical escalation, horizontal access (IDOR) and deny-by-default.

These exercise the policy that `rbac.PERMISSIONS` declares and that
`zero_trust.secured` plus `patients.load_patient_or_404` enforce. Authentication
itself (token forgery, expiry, device binding, refresh reuse) is covered by
test_api.py and is not repeated here.

Two properties matter most and are asserted throughout:
  * a role without a permission is refused with 403 (policy failure)
  * a record outside a user's scope is indistinguishable from one that does not
    exist - 404, never 403, so the endpoint cannot be used to enumerate patients
"""
import pytest

from tests.conftest import UA, login


# --------------------------------------------------------------- fixtures ---
@pytest.fixture(scope="module")
def second_dentist(app):
    """A second dentist, so one clinician's records can be probed by another."""
    client = app.test_client()
    admin_h = login(client, "admin")
    r = client.post("/api/admin/users", headers=admin_h, json={
        "name": "Other Dentist", "email": "other.dentist@test.local",
        "password": "Other-dentist-1", "role": "dentist", "clinic_name": "Other Clinic"})
    assert r.status_code in (201, 409), r.get_json()
    rr = client.post("/api/auth/login",
                     json={"email": "other.dentist@test.local", "password": "Other-dentist-1"}, headers=UA)
    assert rr.status_code == 200, rr.get_json()
    return {"Authorization": f"Bearer {rr.get_json()['data']['access_token']}", **UA}


@pytest.fixture(scope="module")
def owned_patient(app):
    """A patient created by (and therefore belonging to) the primary dentist."""
    client = app.test_client()
    h = login(client, "dentist")
    r = client.post("/api/patients", headers=h, json={
        "name": "Owned Patient", "age": 44, "sex": "female", "contact": "5550101"})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["data"]["patient_id"]


# ------------------------------------------- A. vertical privilege escalation ---
# Each case names the permission the role lacks, so a failure says why it matters.
FORBIDDEN = [
    ("auditor",    "get",   "/api/patients",            "auditor has no patient:read"),
    ("auditor",    "post",  "/api/patients",            "auditor has no patient:write"),
    ("technician", "post",  "/api/patients",            "technician has no patient:write"),
    ("technician", "get",   "/api/audit/logs",          "technician has no audit:read"),
    ("technician", "post",  "/api/reports",             "technician has no report:generate"),
    ("technician", "get",   "/api/review/queue",        "technician has no review:read"),
    ("technician", "get",   "/api/admin/users",         "technician has no admin:users"),
    ("dentist",    "get",   "/api/admin/users",         "dentist has no admin:users"),
    ("dentist",    "get",   "/api/admin/config",        "dentist has no admin:config"),
    ("dentist",    "get",   "/api/audit/logs",          "dentist has no audit:read"),
    ("dentist",    "get",   "/api/security-lab",        "dentist has no security_lab:run"),
    ("dentist",    "get",   "/api/security/sessions",   "dentist has no security:read"),
    ("admin",      "post",  "/api/analyses",            "admin has no analysis:run"),
    ("admin",      "post",  "/api/radiographs",         "admin has no radiograph:upload"),
    ("admin",      "post",  "/api/reports",             "admin has no report:generate"),
    ("auditor",    "get",   "/api/review/queue",        "auditor has no review:read"),
    ("auditor",    "get",   "/api/recall",              "auditor has no care:read"),
]


@pytest.mark.parametrize("role,method,path,reason", FORBIDDEN,
                         ids=[f"{r}-cannot-{m}-{p}" for r, m, p, _ in FORBIDDEN])
def test_role_without_permission_is_refused(client, role, method, path, reason):
    headers = login(client, role)
    response = getattr(client, method)(path, headers=headers, json={})
    assert response.status_code == 403, f"{reason}: got {response.status_code}"
    assert response.get_json()["error"]["message"] == "You do not have permission for this action"


def test_only_a_dentist_may_sign_off_a_review(client):
    """Clinical sign-off belongs to the dentist alone - an admin must not self-authorise it."""
    for role in ("admin", "technician", "auditor"):
        r = client.post("/api/review/ANA-does-not-exist", headers=login(client, role),
                        json={"decision": "accept"})
        assert r.status_code == 403, f"{role} reached review sign-off"


def test_permission_denials_are_audited(client):
    """A refusal must leave a trace; silent denials hide reconnaissance."""
    client.get("/api/admin/users", headers=login(client, "dentist"))
    recent = client.get("/api/audit/logs", headers=login(client, "admin")).get_json()["data"]
    assert any(e["action"] == "PERMISSION_DENIED" for e in recent[:25])


# ----------------------------------------------- B. horizontal access (IDOR) ---
def test_another_dentist_cannot_read_the_patient(client, owned_patient, second_dentist):
    r = client.get(f"/api/patients/{owned_patient}", headers=second_dentist)
    assert r.status_code == 404, "patient readable by a clinician outside the care team"


def test_another_dentist_cannot_modify_the_patient(client, owned_patient, second_dentist):
    r = client.patch(f"/api/patients/{owned_patient}", headers=second_dentist, json={"age": 99})
    assert r.status_code == 404


def test_out_of_scope_patient_is_404_not_403(client, owned_patient, second_dentist):
    """403 would confirm the record exists, turning the endpoint into an enumerator."""
    present = client.get(f"/api/patients/{owned_patient}", headers=second_dentist)
    absent = client.get("/api/patients/999999", headers=second_dentist)
    assert present.status_code == absent.status_code == 404
    assert present.get_json()["error"]["message"] == absent.get_json()["error"]["message"]


def test_patient_list_is_scoped_to_the_owner(client, owned_patient, second_dentist):
    mine = client.get("/api/patients", headers=login(client, "dentist")).get_json()["data"]
    theirs = client.get("/api/patients", headers=second_dentist).get_json()["data"]
    assert owned_patient in [p["patient_id"] for p in mine]
    assert owned_patient not in [p["patient_id"] for p in theirs]


def test_technician_not_on_the_care_team_cannot_read_the_patient(client, owned_patient):
    r = client.get(f"/api/patients/{owned_patient}", headers=login(client, "technician"))
    assert r.status_code == 404


def test_admin_may_read_any_patient(client, owned_patient):
    """Positive control: admin is in ALL_PATIENT_ROLES, so scoping must not block it."""
    assert client.get(f"/api/patients/{owned_patient}", headers=login(client, "admin")).status_code == 200


def test_care_team_membership_grants_access(client, owned_patient, second_dentist):
    """Positive control: the deny is scope-based, not a blanket refusal."""
    users = client.get("/api/admin/users", headers=login(client, "admin")).get_json()["data"]
    other = next(u for u in users if u["email"] == "other.dentist@test.local")

    assert client.get(f"/api/patients/{owned_patient}", headers=second_dentist).status_code == 404
    added = client.post(f"/api/patients/{owned_patient}/care-team",
                        headers=login(client, "admin"), json={"user_id": other["doctor_id"]})
    assert added.status_code == 200, added.get_json()
    assert client.get(f"/api/patients/{owned_patient}", headers=second_dentist).status_code == 200


# --------------------------- C. nested resources must inherit the patient scope ---
@pytest.mark.parametrize("suffix", ["perio-charts", "care-plan", "progression"])
def test_nested_patient_resources_are_scoped(client, suffix):
    """A sub-resource must not be reachable when its parent patient is not."""
    owner = login(client, "dentist")
    created = client.post("/api/patients", headers=owner, json={
        "name": "Nested Scope", "age": 50, "sex": "male", "contact": "5550202"})
    pid = created.get_json()["data"]["patient_id"]

    r = client.post("/api/admin/users", headers=login(client, "admin"), json={
        "name": "Third Dentist", "email": "third.dentist@test.local",
        "password": "Third-dentist-1", "role": "dentist", "clinic_name": "Third Clinic"})
    assert r.status_code in (201, 409)
    tok = client.post("/api/auth/login",
                      json={"email": "third.dentist@test.local", "password": "Third-dentist-1"},
                      headers=UA).get_json()["data"]["access_token"]
    outsider = {"Authorization": f"Bearer {tok}", **UA}

    assert client.get(f"/api/patients/{pid}/{suffix}", headers=outsider).status_code == 404
    assert client.get(f"/api/patients/{pid}/{suffix}", headers=owner).status_code == 200


# --------------------------------------------- D. manipulated identifiers ---
@pytest.mark.parametrize("raw", ["0", "-1", "999999999999", "abc", "1%20OR%201=1", "1;2"])
def test_manipulated_patient_identifiers_never_return_data(client, raw):
    """The int converter plus the scope check must leave no readable path."""
    r = client.get(f"/api/patients/{raw}", headers=login(client, "dentist"))
    assert r.status_code in (404, 400), f"id {raw!r} returned {r.status_code}"


def test_patient_search_cannot_carry_a_mongo_operator(client):
    """A search term that reached Mongo unvalidated could match every record."""
    r = client.get("/api/patients", headers=login(client, "dentist"),
                   query_string={"q": '{"$ne": null}'})
    assert r.status_code == 200
    assert isinstance(r.get_json()["data"], list)


# ------------------------------------------------ E. authentication state ---
def test_unauthenticated_requests_are_refused(client):
    for path in ("/api/patients", "/api/audit/logs", "/api/admin/users", "/api/review/queue"):
        assert client.get(path, headers=UA).status_code == 401, path


def test_revoked_session_loses_access_immediately(client):
    headers = login(client, "dentist")
    assert client.get("/api/patients", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/patients", headers=headers).status_code == 401


def test_unknown_routes_fail_closed(client):
    for path in ("/api/not-a-route", "/api/internal/debug"):
        assert client.get(path, headers=login(client, "dentist")).status_code in (403, 404), path


def test_unsupported_method_does_not_bypass_authorization(client):
    """A method the route does not declare must never reach the handler unauthenticated."""
    assert client.delete("/api/patients", headers=UA).status_code in (401, 403, 405)
    assert client.put("/api/admin/users", headers=login(client, "dentist")).status_code in (403, 405)


# ====================================================================
# Round two: bypasses that survive a correct permission check
# ====================================================================
import io  # noqa: E402

from tests.conftest import synthetic_radiograph  # noqa: E402


def _make_user(client, email, role, password):
    r = client.post("/api/admin/users", headers=login(client, "admin"), json={
        "name": email.split("@")[0], "email": email, "password": password,
        "role": role, "clinic_name": "Scoped Clinic"})
    assert r.status_code in (201, 409), r.get_json()
    rr = client.post("/api/auth/login", json={"email": email, "password": password}, headers=UA)
    assert rr.status_code == 200, rr.get_json()
    return {"Authorization": f"Bearer {rr.get_json()['data']['access_token']}", **UA}, rr.get_json()["data"]["user"]


# ------------------------------------- F. stale privileges in a live token ---
def test_demotion_applies_to_an_already_issued_token(client):
    """The role in the JWT is a UI hint. Policy must come from the database on every
    request, or a demoted user keeps their old powers until the token expires."""
    headers, user = _make_user(client, "demote.me@test.local", "admin", "Demote-me-pass-1")
    assert client.get("/api/admin/users", headers=headers).status_code == 200

    patched = client.patch(f"/api/admin/users/{user['doctor_id']}",
                           headers=login(client, "admin"), json={"role": "technician"})
    assert patched.status_code == 200, patched.get_json()

    # Same token, unexpired, still signed correctly - but the account is no longer admin.
    assert client.get("/api/admin/users", headers=headers).status_code == 403


def test_deactivation_revokes_live_sessions(client):
    headers, user = _make_user(client, "disable.me@test.local", "dentist", "Disable-me-pass-1")
    assert client.get("/api/patients", headers=headers).status_code == 200

    client.patch(f"/api/admin/users/{user['doctor_id']}",
                 headers=login(client, "admin"), json={"active": False})
    assert client.get("/api/patients", headers=headers).status_code in (401, 403)


def test_admin_cannot_demote_or_disable_itself(client):
    """Prevents an admin locking the last administrator out of the system."""
    me = client.get("/api/auth/me", headers=login(client, "admin")).get_json()["data"]
    admin_h = login(client, "admin")
    assert client.patch(f"/api/admin/users/{me['doctor_id']}", headers=admin_h,
                        json={"role": "technician"}).status_code == 409
    assert client.patch(f"/api/admin/users/{me['doctor_id']}", headers=admin_h,
                        json={"active": False}).status_code == 409


# ------------------------------------------------- G. mass assignment ---
@pytest.mark.parametrize("field,value", [
    ("doctor_id", "D-999999"),
    ("care_team", ["D-999999"]),
    ("patient_id", 4242),
    ("pseudo_id", "P-forged"),
])
def test_ownership_fields_cannot_be_set_through_the_patient_api(client, field, value):
    """Writing doctor_id or care_team directly would hand the attacker someone else's record."""
    headers = login(client, "dentist")
    created = client.post("/api/patients", headers=headers,
                          json={"name": "Mass Assign", "age": 30, field: value})
    assert created.status_code == 422, f"{field} was accepted on create"

    pid = client.post("/api/patients", headers=headers,
                      json={"name": "Mass Assign OK", "age": 30}).get_json()["data"]["patient_id"]
    updated = client.patch(f"/api/patients/{pid}", headers=headers, json={field: value})
    assert updated.status_code == 422, f"{field} was accepted on update"


def test_role_cannot_be_escalated_through_self_service(client):
    """No self:manage route may accept a role field."""
    headers = login(client, "technician")
    for path in ("/api/auth/me", "/api/auth/sessions"):
        assert client.post(path, headers=headers, json={"role": "admin"}).status_code in (403, 405)
    assert client.get("/api/auth/me", headers=headers).get_json()["data"]["role"] == "technician"


# --------------------------------- H. cross-tenant analyses and reports ---
@pytest.fixture(scope="module")
def foreign_analysis(app):
    """An analysis belonging to the primary dentist, plus an outsider's headers."""
    client = app.test_client()
    owner = login(client, "dentist")
    pid = client.post("/api/patients", headers=owner, json={
        "name": "Analysis Owner", "age": 61, "sex": "male"}).get_json()["data"]["patient_id"]
    up = client.post("/api/radiographs", headers=owner, content_type="multipart/form-data",
                     data={"image": (io.BytesIO(synthetic_radiograph(seed=7)), "scan.png")})
    assert up.status_code == 201, up.get_json()
    r = client.post("/api/analyses", headers=owner, json={
        "upload_id": up.get_json()["data"]["upload_id"], "patient_id": pid, "visit_date": "2026-01-15"})
    assert r.status_code == 201, r.get_json()
    outsider, _ = _make_user(client, "outsider.dentist@test.local", "dentist", "Outsider-pass-1")
    return r.get_json()["data"], owner, outsider


def test_another_dentist_cannot_read_the_analysis(client, foreign_analysis):
    analysis, owner, outsider = foreign_analysis
    aid = analysis["analysis_id"]
    assert client.get(f"/api/analyses/{aid}", headers=owner).status_code == 200
    assert client.get(f"/api/analyses/{aid}", headers=outsider).status_code == 404


def test_another_dentist_cannot_stream_the_analysis_images(client, foreign_analysis):
    """Image layers must inherit the scope of the analysis, not just of the route."""
    analysis, owner, outsider = foreign_analysis
    for url in analysis["images"].values():
        assert client.get(url, headers=owner).status_code == 200
        assert client.get(url, headers=outsider).status_code == 404


@pytest.mark.parametrize("layer", ["../../etc/passwd", "..%2fconfig", "raw/../annotated", "unknown"])
def test_image_layer_is_an_allow_list(client, foreign_analysis, layer):
    analysis, owner, _ = foreign_analysis
    r = client.get(f"/api/analyses/{analysis['analysis_id']}/image/{layer}", headers=owner)
    assert r.status_code in (404, 400), f"layer {layer!r} returned {r.status_code}"


def test_analysis_list_is_scoped(client, foreign_analysis):
    analysis, _owner, outsider = foreign_analysis
    visible = client.get("/api/analyses", headers=outsider).get_json()["data"]
    assert analysis["analysis_id"] not in [a["analysis_id"] for a in visible]


def test_another_dentist_cannot_download_the_report(client, foreign_analysis):
    analysis, owner, outsider = foreign_analysis
    aid = analysis["analysis_id"]
    # A report needs a signed-off analysis, which is itself dentist-only.
    signed = client.post(f"/api/review/{aid}", headers=owner, json={"decision": "approve"})
    assert signed.status_code == 200, signed.get_json()

    made = client.post("/api/reports", headers=owner, json={"analysis_id": aid})
    assert made.status_code == 201, made.get_json()
    rid = made.get_json()["data"]["report_id"]

    assert client.get(f"/api/reports/{rid}/download", headers=owner).status_code == 200
    assert client.get(f"/api/reports/{rid}/download", headers=outsider).status_code == 404
    assert rid not in [r["report_id"] for r in
                       client.get("/api/reports", headers=outsider).get_json()["data"]]


def test_outsider_cannot_sign_off_another_dentists_analysis(client, foreign_analysis):
    """review:signoff is a dentist permission, but it must still respect patient scope."""
    analysis, _owner, outsider = foreign_analysis
    r = client.post(f"/api/review/{analysis['analysis_id']}", headers=outsider,
                    json={"decision": "approve"})
    assert r.status_code == 404
