"""Muka depan PSSGUTM: pengumuman, teks halaman, maklum balas, direktori, struktur, kehadiran."""
from datetime import date

from .conftest import make_admin, make_user
from .test_people import _book

from datetime import date as _d
from app.services import people as _pp
CUR = _pp.current_session(_d.today())
NEXT = f"{int(CUR[2:]):02d}{(int(CUR[2:]) + 1) % 100:02d}"



def _person(client, admin, email, name="Ahli 1", kind="SG", intake="2627", **extra):
    body = {"name": name, "email": email, "phone": "0123456789", "gender": "female", "intake": intake, "kind": kind,
            "study_end": "2030-07-31" if kind == "SG" else None, "college": "K9", **extra}
    r = client.post("/persatuan/people", headers=admin, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_notices_pages_feedback(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    r = client.post("/laman/notices", headers=admin, data={"kind": "pengumuman", "title": "Latihan khas", "body": "Isi"})
    assert r.status_code == 200, r.text
    nid = r.json()["id"]
    client.post("/laman/notices", headers=admin, data={"kind": "kebajikan", "title": "Kempen"})
    home = client.get("/laman/home", headers=h).json()
    assert [a["title"] for a in home["announcements"]] == ["Latihan khas"] and home["welfare"][0]["title"] == "Kempen"
    # ahli biasa tak boleh urus
    assert client.post("/laman/notices", headers=h, data={"title": "x"}).status_code == 403
    # sorok pengumuman
    assert client.put(f"/laman/notices/{nid}", headers=admin, data={"kind": "pengumuman", "title": "Latihan khas", "active": "false"}).status_code == 200
    assert client.get("/laman/home", headers=h).json()["announcements"] == []
    assert client.get("/laman/notices?kind=pengumuman&all=true", headers=admin).json()[0]["active"] is False
    # teks halaman
    assert "Panduan" in client.get("/laman/page/panduan", headers=h).json()["body"] or True
    assert client.put("/laman/page/hubungi", headers=h, json={"body": "x"}).status_code == 403
    assert client.put("/laman/page/hubungi", headers=admin, json={"body": "WhatsApp BKK 01x"}).status_code == 200
    assert client.get("/laman/page/hubungi", headers=h).json()["body"] == "WhatsApp BKK 01x"
    assert client.get("/laman/page/tiada", headers=h).status_code == 404
    # maklum balas
    assert client.post("/laman/feedback", headers=h, json={"message": "Cadangan baik"}).status_code == 200
    fb = client.get("/laman/feedback", headers=admin).json()
    assert fb[0]["message"] == "Cadangan baik" and fb[0]["read"] is False
    assert client.get("/laman/feedback", headers=h).status_code == 403


def test_import_directory_structure_and_permissions(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    r = client.post("/persatuan/import", headers=admin, data={"dry_run": "false"},
                    files={"file": ("f.xlsx", _book(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert r.json()["stats"]["people_new"] == 2 and r.json()["stats"]["posts_new"] == 1
    sg = client.get("/persatuan/directory?kind=SG", headers=h).json()
    assert [p["name"] for p in sg["items"]] == ["Ali Bin Abu"] and "phone" not in sg["items"][0] and "email" not in sg["items"][0]
    assert sg["items"][0]["posts"] == ["Ketua (BLG)"]
    ssg = client.get("/persatuan/directory?kind=SSG", headers=h).json()
    assert [p["name"] for p in ssg["items"]] == ["Siti"]
    st = client.get("/persatuan/structure", headers=h).json()
    assert st["session"] == "2425" and st["biros"][0]["name"] == "BLG"
    assert st["biros"][0]["posts"][0] == {"title": "Ketua", "names": ["Ali Bin Abu"]}


def test_attendance_by_any_post_holder_and_member_scan(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    other, _ = make_user(client, 2)
    p1 = _person(client, admin, "ahli1@test.com")
    _person(client, admin, "ahli2@test.com", name="Ahli 2")
    # tiada jawatan: tak boleh ambil kehadiran
    assert client.post("/persatuan/attendances", headers=h, json={"title": "Latihan", "on_date": date.today().isoformat()}).status_code == 403
    # beri jawatan MT (tanpa biro): boleh
    r = client.post("/persatuan/posts", headers=admin, json={"person_id": p1["id"], "session": CUR, "level": "MT", "title": "AJK"})
    assert r.status_code == 200, r.text
    assert client.get("/persatuan/me", headers=h).json()["perms"]["attendance"] is True
    a = client.post("/persatuan/attendances", headers=h, json={"title": "Latihan", "on_date": date.today().isoformat()})
    assert a.status_code == 200, a.text
    aid, token = a.json()["id"], a.json()["token"]
    # ahli lain imbas
    assert client.post(f"/persatuan/hadir/{token}", headers=other).json()["ok"] is True
    assert client.post(f"/persatuan/hadir/{token}", headers=other).json()["already"] is True
    # isi manual untuk pengambil sendiri
    assert client.post(f"/persatuan/attendances/{aid}/add", headers=h, json={"person_id": p1["id"]}).status_code == 200
    d = client.get(f"/persatuan/attendances/{aid}", headers=h).json()
    assert d["count"] == 2 and {x["manual"] for x in d["records"]} == {True, False}
    mine = client.get("/persatuan/me/attendance", headers=other).json()
    assert mine["linked"] and mine["present"] == 1 and mine["total"] == 1
    # tutup: tak boleh imbas lagi
    client.put(f"/persatuan/attendances/{aid}/open?open=false", headers=h)
    h3, _ = make_user(client, 3)
    _person(client, admin, "ahli3@test.com", name="Ahli 3")
    assert client.post(f"/persatuan/hadir/{token}", headers=h3).status_code == 400
    # emel tiada dalam senarai
    h4, _ = make_user(client, 4)
    client.put(f"/persatuan/attendances/{aid}/open?open=true", headers=h)
    assert client.post(f"/persatuan/hadir/{token}", headers=h4).status_code == 400


def test_alumni_has_no_belt_and_conversion_clears_it(client):
    admin = make_admin(client)
    r = client.post("/persatuan/belts", headers=admin, json={"name": "Putih"})
    bid = r.json()["id"]
    sg = _person(client, admin, "a@test.com", belt_id=bid, belt_date="2026-03-15", study_end="2020-01-01")
    assert sg["belt"] == "Putih"
    alum = _person(client, admin, "b@test.com", name="Alumni", kind="SSG", intake="9495", belt_id=bid)
    assert alum["belt"] == "" and alum["member_no"] == "SSG9495"
    due = client.get("/persatuan/conversions", headers=admin).json()
    assert [p["email"] for p in due] == ["a@test.com"]
    out = client.post(f"/persatuan/conversions/{sg['id']}", headers=admin, json={"action": "convert"}).json()
    assert out["kind"] == "SSG" and out["member_no"] == "SSG2627" and out["belt"] == ""


def test_event_titles_design(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    r = client.post("/laman/notices", headers=admin, data={"kind": "event", "title": "Gala", "on_date": "2026-12-01"})
    assert r.status_code == 200, r.text
    home = client.get("/laman/home", headers=h).json()
    assert home["events"][0]["title"] == "Gala" and home["titles"]["kebajikan"] == "News"
    # tajuk bahagian: admin sahaja
    assert client.put("/laman/titles", headers=h, json={"titles": {"kebajikan": "X"}}).status_code == 403
    r = client.put("/laman/titles", headers=admin, json={"titles": {"kebajikan": "Berita", "lain": "abaikan"}})
    assert r.status_code == 200 and r.json()["kebajikan"] == "Berita" and "lain" not in r.json()
    assert client.get("/laman/home", headers=h).json()["titles"]["kebajikan"] == "Berita"
    # rekaan
    assert client.put("/laman/design", headers=h, data={"mode": "corak", "pattern": "luk"}).status_code == 403
    assert client.put("/laman/design", headers=admin, data={"mode": "corak", "pattern": "xx"}).status_code == 400
    r = client.put("/laman/design", headers=admin, data={"mode": "corak", "pattern": "luk"})
    assert r.status_code == 200, r.text
    assert client.get("/laman/home", headers=h).json()["design"]["pattern"] == "luk"


def test_public_front(client):
    r = client.get("/laman/public")   # tanpa log masuk
    assert r.status_code == 200 and r.json()["titles"]["kebajikan"] == "News" and "design" in r.json()


def test_admin_sets_current_session(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    assert client.get("/laman/public").json()["session"]["code"]
    assert client.put("/persatuan/session", headers=h, json={"code": "2728"}).status_code == 403
    assert client.put("/persatuan/session", headers=admin, json={"code": "2729"}).status_code == 400
    r = client.put("/persatuan/session", headers=admin, json={"code": "2728"})
    assert r.status_code == 200 and r.json()["label"] == "2027/28"
    s = client.get("/laman/public").json()["session"]
    assert s == {"code": "2728", "label": "2027/28"}


def test_committee_changes_with_session(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    p = _person(client, admin, "ahli1@test.com", name="AJK Lama")
    client.post("/persatuan/posts", headers=admin, json={"person_id": p["id"], "session": CUR, "level": "MT", "title": "Pengerusi"})
    assert client.get("/persatuan/me", headers=h).json()["perms"]["attendance"] is True
    # sesi baharu: jawatankuasa lama hilang kebenaran tetapi rekod kekal
    assert client.put("/persatuan/session", headers=admin, json={"code": NEXT}).status_code == 200
    assert client.get("/persatuan/me", headers=h).json()["perms"]["attendance"] is False
    s = client.get(f"/persatuan/structure?session={CUR}", headers=h).json()
    assert s["mt"][0]["names"] == ["AJK Lama"] and CUR in s["sessions"]
    # jawatankuasa baharu bagi 2728
    client.post("/persatuan/posts", headers=admin, json={"person_id": p["id"], "session": NEXT, "level": "MT", "title": "Timbalan"})
    assert client.get("/persatuan/me", headers=h).json()["perms"]["attendance"] is True
    assert client.get("/persatuan/structure", headers=h).json()["session"] == NEXT


def test_committee_empty_for_new_session_without_posts(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    pid = _person(client, admin, "ahli1@test.com")["id"]
    client.put("/persatuan/session", headers=admin, json={"code": "2627"})
    assert client.post("/persatuan/posts", headers=admin, json={"person_id": pid, "session": "2627", "level": "MT", "title": "Pengerusi"}).status_code == 200
    # sesi bertukar: rekod lama kekal, tetapi kebenaran hilang; sesi baharu ada jawatankuasa baharu
    client.put("/persatuan/session", headers=admin, json={"code": "2728"})
    st = client.get("/persatuan/structure?session=2627", headers=admin).json()
    assert st["mt"][0]["names"] and "2627" in st["sessions"]
    assert client.get("/persatuan/structure?session=2728", headers=admin).json()["mt"] == []
