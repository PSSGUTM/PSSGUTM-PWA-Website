import os
import tempfile

# Mesti set sebelum import app
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"

import pytest
from fastapi.testclient import TestClient

from app import models, security
from app.database import Base, SessionLocal, engine
from app.main import app
from app.seed import run as seed_run


@pytest.fixture(autouse=True)
def fresh_db():
    security._hits.clear()
    Base.metadata.drop_all(bind=engine)
    seed_run()
    yield


@pytest.fixture(autouse=True)
def legacy_prefs_on(monkeypatch):
    """Ujian lama guna jadual berulang; mod produksi lalai ialah ikut tarikh sahaja."""
    from app import config
    monkeypatch.setattr(config, "AUTO_FROM_PREFERENCES", True)
    monkeypatch.setattr(config, "REQUIRE_PREBET_CONFIRM", False)  # ujian fasa 6 hidupkan sendiri
    monkeypatch.setattr(config, "LONE_FEMALE_RULE", False)
    monkeypatch.setattr(config, "REQUIRE_LICENCE", False)
    monkeypatch.setattr(config, "ENFORCE_CUTOFF", False)   # ujian fasa 7 hidupkan sendiri


@pytest.fixture
def client():
    return TestClient(app)


def college_id(code):
    with SessionLocal() as db:
        return db.query(models.College).filter_by(code=code).one().id


def add_roster(member_no, gender=None, code=None):
    with SessionLocal() as db:
        col = db.query(models.College).filter_by(code=code).one() if code else None
        db.add(models.MemberRoster(member_no=member_no, name="",
                                   gender=models.Gender(gender) if gender else None,
                                   college_id=col.id if col else None))
        db.commit()


def make_user(client, n=1, code="K9", gender="female", role=None, is_driver=False):
    member_no = f"SG2627{n:03d}" if not is_driver else f"MT{n:03d}"
    add_roster(member_no)
    body = {"name": f"Ahli {n}", "member_no": member_no,
            "phone": "0123456789", "email": f"ahli{n}@test.com", "password": "password123",
            "gender": gender, "college_id": college_id(code), "is_driver": is_driver}
    r = client.post("/auth/register", json=body)
    assert r.status_code == 201, r.text
    uid = r.json()["user"]["id"]
    if role:
        with SessionLocal() as db:
            db.get(models.User, uid).role = role
            db.commit()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, uid


def make_admin(client):
    return make_user(client, 99, code="K9", gender="female", role=models.Role.admin)[0]


def set_prefs(client, headers, going=True, returning=True):
    r = client.put("/transport/preferences", headers=headers, json={"items": [
        {"session_id": 1, "active": True, "going": going, "returning": returning},
        {"session_id": 2, "active": True, "going": going, "returning": returning}]})
    assert r.status_code == 200, r.text
    return r


def first_event(client, admin_h):
    return client.get("/admin/dashboard", headers=admin_h).json()[0]


def venue_id(client, admin_h, name):
    return next(v["id"] for v in client.get("/admin/venues", headers=admin_h).json() if v["name"] == name)


VEHICLE_5 = {"name": "Myvi A", "vehicle_type": "car", "seat_rows": "1,3", "driver_gender": "male"}


def approved_driver_car(client, admin_h, n=5, name="Myvi Ali", gender="male"):
    """Driver daftar sendiri -> hantar kereta 5 seat -> admin lulus. Return (headers, user_id, vehicle_id)."""
    dh, uid = make_user(client, n, is_driver=True, code="KTDI", gender=gender)
    r = client.post("/driver/vehicles", headers=dh,
                    json={"name": name, "plate_no": "abc1234", "vehicle_type": "car", "seats": 5})
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    assert client.post(f"/admin/vehicles/{vid}/approve", headers=admin_h).status_code == 200
    return dh, uid, vid
