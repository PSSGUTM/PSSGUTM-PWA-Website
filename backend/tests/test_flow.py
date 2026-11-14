from app import models

from .conftest import (VEHICLE_5, add_roster, approved_driver_car, college_id, first_event, make_admin,
                       make_user, set_prefs, venue_id)

PNG = ("x.png", b"\x89PNG\r\n" + b"0" * 50, "image/png")


def set_years(value):
    """Lalai produksi = semua sesi layak. Ujian yang menguji sekatan sesi menetapkannya dahulu."""
    from app.database import SessionLocal
    with SessionLocal() as db:
        db.merge(models.Setting(key="eligible_years", value=value))
        db.commit()


def past_day(monkeypatch, ev, days=1):
    """Bayaran prebet hanya genap selepas tarikh latihan: anggap hari ini = selepas latihan itu."""
    from datetime import date, timedelta
    from app.services import booking as svc
    d = date.fromisoformat(ev["training_date"]) + timedelta(days=days)
    monkeypatch.setattr(svc, "today_my", lambda: d)


def going3(ev):
    return {k: ev["going"][k] for k in ("passengers", "assigned", "unassigned")}


def finalise_first(client, admin, venue="L50"):
    ev = first_event(client, admin)
    client.put(f"/admin/events/{ev['event_id']}/venue", headers=admin,
               json={"venue_id": venue_id(client, admin, venue)})
    assert client.post(f"/admin/events/{ev['event_id']}/finalise", headers=admin).status_code == 200
    return ev


def test_registration_rules_and_roster(client):
    set_years("2627")
    base = {"name": "Ali", "phone": "0123456789", "email": "x@test.com", "password": "password123",
            "gender": "female", "college_id": college_id("K9")}
    # Bukan ahli sah (tiada dalam senarai)
    r = client.post("/auth/register", json={**base, "member_no": "SG2627777"})
    assert r.status_code == 400 and "senarai" in r.json()["detail"]
    # Ahli sah sesi lain: boleh daftar, tetapi TIDAK boleh tempah latihan biasa
    add_roster("SG2425001")
    r = client.post("/auth/register", json={**base, "member_no": "SG2425001", "email": "old@test.com"})
    assert r.status_code == 201
    h_old = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pr = client.get("/transport/preferences", headers=h_old).json()
    assert pr["eligibility"]["eligible"] is False
    r = client.put("/transport/preferences", headers=h_old, json={"items": [
        {"session_id": pr["sessions"][0]["session_id"], "active": True, "going": True, "returning": True}]})
    assert r.status_code == 400 and "sesi" in r.json()["detail"]
    # KP belum ada checkpoint: boleh daftar tetapi belum boleh tempah
    add_roster("SG2627001")
    r = client.post("/auth/register", json={**base, "member_no": "SG2627001", "email": "kp@test.com",
                                            "college_id": college_id("KP")})
    assert r.status_code == 201
    hk = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/transport/preferences", headers=hk).json()["eligibility"]["eligible"] is False
    # K9 hanya ada checkpoint perempuan: ahli lelaki K9 boleh daftar tetapi belum boleh tempah
    add_roster("SG2627002")
    r = client.post("/auth/register", json={**base, "member_no": "SG2627002", "email": "k9m@test.com", "gender": "male"})
    assert r.status_code == 201
    hm = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/transport/preferences", headers=hm).json()["eligibility"]["eligible"] is False
    # Kolej daripada senarai ahli mengatasi input; jantina: pilihan pendaftar didahulukan (CSV kadang tersalah)
    add_roster("SG2627003", gender="female", code="K9")
    r = client.post("/auth/register", json={**base, "member_no": "SG2627003", "gender": "male",
                                            "college_id": college_id("K10")})
    assert r.status_code == 201 and r.json()["user"]["gender"] == "male"
    dup = client.post("/auth/register", json={**base, "member_no": "sg2627003", "email": "y@test.com"})
    assert dup.status_code == 409


def test_college_other_free_text(client):
    admin = make_admin(client)
    add_roster("SG2627100")
    r = client.post("/auth/register", json={"name": "Aina", "member_no": "SG2627100", "phone": "0123456789",
                                            "email": "aina@test.com", "password": "password123", "gender": "female",
                                            "college_other": "Rumah sewa Taman U"})
    assert r.status_code == 201 and r.json()["user"]["college_other"] == "Rumah sewa Taman U"
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    el = client.get("/transport/preferences", headers=h).json()["eligibility"]
    assert el["eligible"] is False and "Rumah sewa" in el["reason"]
    stats = client.get("/admin/stats", headers=admin).json()
    assert stats["other_colleges"] == [{"name": "Rumah sewa Taman U", "count": 1}]
    # Kod kolej (borang) juga diterima
    add_roster("SG2627101")
    r = client.post("/auth/register", json={"name": "Siti", "member_no": "SG2627101", "phone": "0123456789",
                                            "email": "siti@test.com", "password": "password123", "gender": "female",
                                            "college_code": "K9"})
    assert r.status_code == 201 and r.json()["user"]["college_id"] == college_id("K9")


def test_roster_csv_import_and_password_change(client):
    admin = make_admin(client)
    csv_bytes = (b"no ahli,nama,jantina,kolej\nSG2627050,Ali,L,K10\nSG2627051,Aina,P,K9\nSG2627052,Bad,X,K9\n")
    r = client.post("/admin/roster/import", headers=admin, files={"file": ("r.csv", csv_bytes, "text/csv")})
    assert r.json()["added"] == 2 and r.json()["error_count"] == 1
    reg = client.post("/auth/register", json={"name": "Ali", "member_no": "SG2627050", "phone": "0123456789",
                                              "email": "ali@test.com", "password": "password123"})
    assert reg.status_code == 201 and reg.json()["user"]["gender"] == "male"   # daripada senarai ahli
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    assert client.put("/auth/password", headers=h, json={"current_password": "salah", "new_password": "passbaru123"}).status_code == 400
    assert client.put("/auth/password", headers=h, json={"current_password": "password123", "new_password": "passbaru123"}).status_code == 200
    assert client.post("/auth/login", json={"identifier": "SG2627050", "password": "passbaru123"}).status_code == 200


def test_admin_only(client):
    h, _ = make_user(client, 1)
    assert client.get("/admin/dashboard", headers=h).status_code == 403
    assert client.get("/admin/dashboard").status_code == 401


def test_checkpoint_and_fees_by_category(client):
    h, _ = make_user(client, 1, "K9", "female")     # jauh, kereta RM4
    set_prefs(client, h)
    day = client.get("/bookings", headers=h).json()[0]
    assert {t["direction"] for t in day["trips"]} == {"going", "returning"}
    assert day["trips"][0]["checkpoint"] == "Bus Stop K9" and day["payment"]["amount"] == 4.0
    h2, _ = make_user(client, 2, "KTF", "female")   # dekat, kereta RM3
    set_prefs(client, h2)
    assert client.get("/bookings", headers=h2).json()[0]["payment"]["amount"] == 3.0


def test_venue_exclusion_and_restore(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1, "KTF", "female")
    set_prefs(client, h)
    ev = first_event(client, admin)
    client.put(f"/admin/events/{ev['event_id']}/venue", headers=admin,
               json={"venue_id": venue_id(client, admin, "Dewan Merdeka, KRP")})   # KTF terkecuali
    day = client.get("/bookings", headers=h).json()[0]
    assert all(t["status"] == "ineligible" for t in day["trips"]) and day["payment"] is None
    client.put(f"/admin/events/{ev['event_id']}/venue", headers=admin,
               json={"venue_id": venue_id(client, admin, "Dewan Serbaguna, KTHO")})
    day = client.get("/bookings", headers=h).json()[0]
    assert all(t["status"] == "confirmed" for t in day["trips"]) and day["payment"]["status"] == "unpaid"


def test_skip_then_locked_after_finalise(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    ev = first_event(client, admin)
    d = ev["training_date"]
    assert client.post("/bookings/skip", headers=h, json={"training_date": d}).status_code == 200
    day = client.get("/bookings", headers=h).json()[0]
    assert all(t["status"] == "skipped" for t in day["trips"]) and day["payment"] is None
    client.post("/bookings/skip", headers=h, json={"training_date": d, "skip": False})
    finalise_first(client, admin)
    r = client.post("/bookings/skip", headers=h, json={"training_date": d})
    assert r.status_code == 400 and "disahkan" in r.json()["detail"]


def test_seat_rules_by_gender_and_same_vehicle_both_ways(client):
    admin = make_admin(client)
    client.post("/admin/vehicles", headers=admin, json={**VEHICLE_5, "seat_rows": "1,1"})   # 2 penumpang
    for n in range(1, 4):                            # 3 lelaki K10, kereta muat 2
        h, _ = make_user(client, n, "K10", "male")
        set_prefs(client, h)
    ev = first_event(client, admin)
    assert going3(ev) == {"passengers": 3, "assigned": 2, "unassigned": 1}
    assert ev["extra_cars_needed"] == 1
    pax = client.get(f"/admin/passengers?training_date={ev['training_date']}", headers=admin).json()
    per_user = {}
    for p in pax:
        per_user.setdefault(p["user_id"], set()).add(p["vehicle_id"])
    assert all(len(v) == 1 for v in per_user.values())   # kenderaan sama pergi & balik


def test_cars_first_then_motorcycle_with_lower_fee(client):
    admin = make_admin(client)
    # Motosikal didaftar dahulu (id 1), kereta kemudian (id 2): kereta tetap diisi dahulu
    client.post("/admin/vehicles", headers=admin, json={"name": "Y15 Aina", "vehicle_type": "motorcycle",
                                                        "driver_gender": "female"})
    client.post("/admin/vehicles", headers=admin, json={"name": "Myvi", "vehicle_type": "car",
                                                        "seat_rows": "1,1", "driver_gender": "male"})
    h1, _ = make_user(client, 1, "K9", "female")
    h2, _ = make_user(client, 2, "K9", "female")
    h3, _ = make_user(client, 3, "K9", "female")
    for h in (h1, h2, h3):
        set_prefs(client, h)
    ev = first_event(client, admin)
    # kereta "1,1" muat 1 perempuan, motosikal 1 perempuan -> seorang belum dapat kenderaan
    assert going3(ev) == {"passengers": 3, "assigned": 2, "unassigned": 1}
    fees = sorted(client.get("/bookings", headers=h).json()[0]["payment"]["amount"] for h in (h1, h2, h3))
    assert fees == [2.0, 4.0, 4.0]   # motosikal jauh RM2; kereta RM4; yang belum dapat = anggaran kereta RM4


def test_overpayment_becomes_credit(client):
    admin = make_admin(client)
    approved_driver_car(client, admin)
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    pid = client.get("/bookings", headers=h).json()[0]["payment"]["id"]
    finalise_first(client, admin)
    assert client.post(f"/payments/{pid}/receipt", headers=h, files={"file": PNG}).json()["status"] == "pending"
    due = client.get("/bookings", headers=h).json()[0]["payment"]["due"]
    kurang = client.post(f"/admin/payments/{pid}/verify", headers=admin, json={"amount_paid": due - 1})
    assert kurang.status_code == 400
    assert client.post(f"/admin/payments/{pid}/verify", headers=admin, json={"amount_paid": due + 3}).status_code == 200
    me = client.get("/auth/me", headers=h).json()
    assert me["credit_balance"] == 3.0
    notes = client.get("/notifications", headers=h).json()
    assert any("kredit" in n["title"].lower() for n in notes)


def test_retention_purges_old_receipts_and_notifications(client):
    from datetime import date, datetime, timedelta
    from app import models
    from app.database import SessionLocal
    from app.services import retention
    make_user(client, 1)
    db = SessionLocal()
    try:
        uid = db.query(models.User).filter(models.User.role == models.Role.member).first().id
        old_d, new_d = date.today() - timedelta(days=400), date.today() - timedelta(days=10)
        db.add_all([
            models.Payment(user_id=uid, training_date=old_d, amount=4.0, status=models.PaymentStatus.paid, receipt_path="old.png"),
            models.Payment(user_id=uid, training_date=new_d, amount=4.0, status=models.PaymentStatus.paid, receipt_path="new.png"),
            models.Notification(user_id=uid, kind="info", title="lama", severity="info",
                                created_at=datetime.utcnow() - timedelta(days=400)),
            models.Notification(user_id=uid, kind="info", title="amaran lama", severity="warning",
                                created_at=datetime.utcnow() - timedelta(days=400)),
            models.Notification(user_id=uid, kind="info", title="baru", severity="info"),
        ])
        db.commit()
        n_receipts, n_notes = retention.run_retention(db)
        assert n_receipts == 1 and n_notes >= 1
        pays = {p.training_date: p for p in db.query(models.Payment).filter_by(user_id=uid)}
        assert pays[old_d].receipt_path is None and pays[old_d].status == models.PaymentStatus.paid   # rekod kekal
        assert pays[new_d].receipt_path == "new.png"
        titles = {n.title for n in db.query(models.Notification).filter_by(user_id=uid)}
        assert "lama" not in titles and "amaran lama" in titles and "baru" in titles
    finally:
        db.close()


def test_image_compression_keeps_qr_png_and_shrinks_photos():
    import io
    from PIL import Image
    from app import imaging
    photo = Image.new("RGB", (3200, 2400), (180, 40, 40))
    buf = io.BytesIO(); photo.save(buf, "PNG")
    data, ext = imaging.compress(buf.getvalue(), ".png", "")
    assert ext == ".jpg" and max(Image.open(io.BytesIO(data)).size) <= 1600 and len(data) < len(buf.getvalue())
    _, qr_ext = imaging.compress(buf.getvalue(), ".png", "qr_")
    assert qr_ext == ".png"
    fake = b"\x89PNG\r\n" + b"0" * 50
    assert imaging.compress(fake, ".png", "") == (fake, ".png")      # rosak -> fail asal dikekalkan


def test_unfinalised_warning_cleared_on_refinalise_and_stale_expire(client):
    from datetime import date, timedelta
    from app import models
    from app.database import SessionLocal
    from app.services import retention
    admin = make_admin(client)
    approved_driver_car(client, admin)
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    ev = finalise_first(client, admin)
    assert client.post(f"/admin/events/{ev['event_id']}/unfinalise", headers=admin).status_code == 200
    notes = client.get("/notifications", headers=h).json()
    assert any("ditarik balik" in n["title"] for n in notes)
    assert client.post(f"/admin/events/{ev['event_id']}/finalise", headers=admin).status_code == 200
    notes = client.get("/notifications", headers=h).json()
    assert not any("ditarik balik" in n["title"] for n in notes)          # hilang bila disahkan semula
    # amaran lapuk (tarikh latihan sudah lepas) dibuang; amaran lain kekal
    db = SessionLocal()
    try:
        uid = db.query(models.User).filter(models.User.role == models.Role.member).first().id
        old_d = date.today() - timedelta(days=5)
        db.add_all([
            models.Notification(user_id=uid, kind="driver", title="tick lama", severity="warning",
                                training_date=old_d, ref=f"tick:arrived:{uid}:{old_d.isoformat()}"),
            models.Notification(user_id=uid, kind="driver", title="tunggakan", severity="warning",
                                training_date=old_d, ref="arrears:summary"),
        ])
        db.commit()
        assert retention.expire_stale_warnings(db) >= 1
        titles = {n.title for n in db.query(models.Notification).filter_by(user_id=uid)}
        assert "tick lama" not in titles and "tunggakan" in titles
    finally:
        db.close()


def test_admin_users_list_has_block_and_checkpoint(client):
    admin = make_admin(client)
    make_user(client, 1)
    rows = client.get("/admin/users", headers=admin).json()
    assert rows and all("block" in r and "checkpoint" in r for r in rows)


def test_motorcycle_needs_same_gender(client):
    admin = make_admin(client)
    client.post("/admin/vehicles", headers=admin, json={"name": "Y15 Ali", "vehicle_type": "motorcycle",
                                                        "driver_gender": "male"})
    h, _ = make_user(client, 1, "K9", "female")
    set_prefs(client, h)
    assert first_event(client, admin)["going"]["assigned"] == 0


def test_finalise_payment_flow_no_cash_and_payout(client):
    admin = make_admin(client)
    dh, drv_id, vid = approved_driver_car(client, admin)
    assert client.put("/driver/payout", headers=dh, json={"payout_bank": "Maybank", "payout_account_no": "1234567890",
                                                          "payout_account_name": "Ali"}).status_code == 200
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    day = client.get("/bookings", headers=h).json()[0]
    assert day["car"] is None and day["payment"]["can_pay"] is False            # belum disahkan
    pid = day["payment"]["id"]
    assert client.post(f"/payments/{pid}/receipt", headers=h, files={"file": PNG}).status_code == 400

    ev = finalise_first(client, admin)
    day = client.get("/bookings", headers=h).json()[0]
    assert day["car"]["name"] == "Myvi Ali" and day["car"]["driver_name"] and day["payment"]["can_pay"] is True
    assert client.post(f"/admin/payments/{pid}/verify", headers=admin).status_code == 400   # tiada tunai
    assert client.post(f"/payments/{pid}/receipt", headers=h, files={"file": PNG}).json()["status"] == "pending"
    bad = client.post(f"/payments/{pid}/receipt", headers=h, files={"file": ("x.png", b"bukan gambar", "image/png")})
    assert bad.status_code == 400
    assert client.post(f"/admin/payments/{pid}/verify", headers=admin).status_code == 200

    rows = client.get(f"/admin/payouts?training_date={ev['training_date']}", headers=admin).json()
    assert rows[0]["collected"] == 4.0 and rows[0]["outstanding"] == 14.0   # bayaran ikut kolej penumpang (K9 = jauh)
    assert rows[0]["driver"]["account_no"] == "1234567890"
    assert client.post("/admin/payouts", headers=admin,
                       json={"vehicle_id": vid, "training_date": ev["training_date"]}).status_code == 200
    rows = client.get(f"/admin/payouts?training_date={ev['training_date']}", headers=admin).json()
    assert rows[0]["outstanding"] == 0.0
    assert client.post("/admin/payouts", headers=admin,
                       json={"vehicle_id": vid, "training_date": ev["training_date"]}).status_code == 400
    # Lain-lain ahli tak boleh lihat maklumat bayaran driver
    assert client.get("/admin/payouts?training_date=" + ev["training_date"], headers=h).status_code == 403


def test_cancel_event_carries_payment_as_credit(client):
    admin = make_admin(client)
    client.post("/admin/vehicles", headers=admin, json=VEHICLE_5)
    h, _ = make_user(client, 1, "K9", "female")    # RM4
    set_prefs(client, h)
    ev = finalise_first(client, admin)
    pid = client.get("/bookings", headers=h).json()[0]["payment"]["id"]
    client.post(f"/payments/{pid}/receipt", headers=h, files={"file": PNG})
    client.post(f"/admin/payments/{pid}/verify", headers=admin)
    client.post(f"/admin/events/{ev['event_id']}/cancel", headers=admin)
    assert client.get("/profile", headers=h).json()["credit_balance"] == 4.0    # bukan dipulangkan tunai
    mine = {p["id"]: p for p in client.get("/payments/me", headers=h).json()}
    assert mine[pid]["status"] == "void"


def test_driver_needs_approval_and_payout_privacy(client):
    admin = make_admin(client)
    dh, _ = make_user(client, 5, is_driver=True, code="KTDI", gender="male")
    r = client.post("/driver/vehicles", headers=dh,
                    json={"name": "Myvi Ali", "plate_no": "abc1234", "vehicle_type": "car", "seats": 5})
    assert r.status_code == 201 and r.json()["approval"] == "pending"
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    assert first_event(client, admin)["going"]["unassigned"] == 1              # belum diluluskan
    vid = r.json()["id"]
    assert client.post(f"/admin/vehicles/{vid}/approve", headers=admin).status_code == 200
    assert first_event(client, admin)["going"]["assigned"] == 1
    assert client.get("/auth/me", headers=dh).json()["role"] == "driver"
    day = client.get("/admin/dashboard", headers=admin).json()[0]["training_date"]
    man = client.get(f"/driver/manifest?training_date={day}", headers=dh).json()
    assert man["cars"][0]["passengers"][0]["checkpoint"] == "Bus Stop K9"
    assert client.get("/driver/payout", headers=h).json()["payout_account_no"] == ""   # data sendiri sahaja


def test_branding_public_and_admin_edit(client):
    admin = make_admin(client)
    assert client.get("/branding").json()["brand_primary"] == "#a8322a"
    assert client.put("/admin/branding", headers=admin, json={"brand_name": "PSSGUTM", "brand_primary": "merah",
                                                             "brand_accent": "#111111"}).status_code == 400
    r = client.put("/admin/branding", headers=admin, json={"brand_name": "PSSGUTM", "brand_primary": "#112233",
                                                          "brand_accent": "#445566"})
    assert r.json()["brand_primary"] == "#112233"
    assert client.get("/branding").json()["brand_name"] == "PSSGUTM"
    r = client.post("/admin/branding/reset-colours", headers=admin)   # set semula ke warna lalai
    assert r.status_code == 200
    assert r.json()["brand_primary"] == "#a8322a" and r.json()["brand_accent"] == "#d4a94e"
    assert r.json()["brand_name"] == "PSSGUTM"  # nama tak terjejas


def test_announcement_reaches_members(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    client.post("/admin/announce", headers=admin, json={"title": "Latihan dibatalkan", "body": "Hujan"})
    assert any(n["title"] == "Latihan dibatalkan" for n in client.get("/notifications", headers=h).json())


def test_admin_changes_eligible_years(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    assert client.get("/transport/preferences", headers=h).json()["eligibility"]["eligible"] is True
    set_prefs(client, h)
    assert client.get("/bookings", headers=h).json()
    assert client.put("/admin/settings/eligibility", headers=admin, json={"years": ["abc"]}).status_code == 400
    assert client.put("/admin/settings/eligibility", headers=admin, json={"years": ["2728"]}).status_code == 200
    assert client.get("/transport/preferences", headers=h).json()["eligibility"]["eligible"] is False
    assert all(t["status"] != "confirmed" for d in client.get("/bookings", headers=h).json() for t in d["trips"])
    assert client.get("/rules").json()["eligible_labels"] == ["27/28"]
    client.put("/admin/settings/eligibility", headers=admin, json={"years": ["2627", "2728"]})
    assert client.get("/transport/preferences", headers=h).json()["eligibility"]["eligible"] is True
    assert "2728" in client.get("/admin/settings/eligibility", headers=admin).json()["available"]


def test_extra_activity_multi_day_open_to_all(client):
    set_years("2627")
    from datetime import timedelta
    from app.services import booking as svc
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    add_roster("SG2425009")
    r = client.post("/auth/register", json={"name": "Lama", "member_no": "SG2425009", "phone": "0123456789",
                                            "email": "lama@test.com", "password": "password123",
                                            "gender": "female", "college_id": college_id("K9")})
    assert r.status_code == 201
    h_old = {"Authorization": f"Bearer {r.json()['access_token']}"}
    go = svc.today_my() + timedelta(days=3)
    ret = go + timedelta(days=1)
    r = client.post("/admin/activities", headers=admin,
                    json={"name": "Perkhemahan", "go_date": go.isoformat(), "return_date": ret.isoformat()})
    assert r.status_code == 201
    key = r.json()["id"]
    assert r.json()["go_date"] == go.isoformat() and r.json()["return_date"] == ret.isoformat()
    for hdr in (h, h_old):
        pr = client.get("/transport/preferences", headers=hdr).json()
        legs = [p for p in pr["sessions"] if p["one_off_date"]]
        assert {p["trip_only"] for p in legs} == {"going", "returning"}
        assert pr["activity_eligibility"]["eligible"] is True
        items = [{"session_id": p["session_id"], "active": True, "going": True, "returning": True} for p in legs]
        assert client.put("/transport/preferences", headers=hdr, json={"items": items}).status_code == 200
        days = {d["training_date"]: d for d in client.get("/bookings", headers=hdr).json() if d["is_activity"]}
        assert [t["direction"] for t in days[go.isoformat()]["trips"]] == ["going"]
        assert [t["direction"] for t in days[ret.isoformat()]["trips"]] == ["returning"]
        assert days[go.isoformat()]["venue"] is None
    # Ahli sesi lama masih tak boleh tick latihan biasa
    pr = client.get("/transport/preferences", headers=h_old).json()
    reg = [p for p in pr["sessions"] if not p["one_off_date"]][0]
    bad = client.put("/transport/preferences", headers=h_old, json={"items": [
        {"session_id": reg["session_id"], "active": True, "going": True, "returning": True}]})
    assert bad.status_code == 400
    # Dah ada tempahan: tak boleh padam
    assert client.delete(f"/admin/activities/{key}", headers=admin).status_code == 400
    r2 = client.post("/admin/activities", headers=admin,
                     json={"name": "Lain", "go_date": (go + timedelta(days=5)).isoformat()})
    assert client.delete(f"/admin/activities/{r2.json()['id']}", headers=admin).status_code == 200
    assert client.post("/admin/activities", headers=admin, json={
        "name": "Salah", "go_date": go.isoformat(),
        "return_date": (go - timedelta(days=1)).isoformat()}).status_code == 400


def test_venue_edit_and_delete(client):
    admin = make_admin(client)
    r = client.post("/admin/venues", headers=admin, json={"name": "Dewan Baru", "excluded_codes": []})
    vid = r.json()["id"]
    r = client.put(f"/admin/venues/{vid}", headers=admin, json={"name": "Dewan Baru 2", "excluded_codes": ["K9"], "active": True})
    assert r.json()["name"] == "Dewan Baru 2" and r.json()["excluded_codes"] == ["K9"]
    assert client.delete(f"/admin/venues/{vid}", headers=admin).status_code == 200
    # Venue yang sudah dipakai pada latihan tak boleh dipadam
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    ev = first_event(client, admin)
    used = venue_id(client, admin, "Dewan Serbaguna, KTHO")
    client.put(f"/admin/events/{ev['event_id']}/venue", headers=admin, json={"venue_id": used})
    assert client.delete(f"/admin/venues/{used}", headers=admin).status_code == 400


def test_activity_fee_and_free(client):
    from datetime import timedelta
    from app.services import booking as svc
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    d1 = svc.today_my() + timedelta(days=3)
    d2 = svc.today_my() + timedelta(days=5)
    paid = client.post("/admin/activities", headers=admin, json={"name": "Berbayar", "go_date": d1.isoformat(), "fee": 5}).json()
    free = client.post("/admin/activities", headers=admin, json={"name": "Percuma", "go_date": d2.isoformat()}).json()
    assert paid["fee"] == 5 and free["fee"] == 0
    pr = client.get("/transport/preferences", headers=h).json()["sessions"]
    items = [{"session_id": p["session_id"], "active": bool(p["one_off_date"]), "going": True, "returning": True} for p in pr]
    assert client.put("/transport/preferences", headers=h, json={"items": items}).status_code == 200
    days = {d["training_date"]: d for d in client.get("/bookings", headers=h).json() if d["is_activity"]}
    assert days[d1.isoformat()]["payment"]["amount"] == 5.0
    assert days[d2.isoformat()]["payment"] is None
    assert client.get(f"/admin/payouts?training_date={d2.isoformat()}", headers=admin).json() == []
    # Tukar yuran berbayar -> percuma, bayaran dibatalkan
    assert client.put(f"/admin/activities/{paid['id']}/fee", headers=admin, json={"fee": 0}).status_code == 200
    day = [d for d in client.get("/bookings", headers=h).json() if d["training_date"] == d1.isoformat()][0]
    assert day["payment"] is None or day["payment"]["status"] == "void"
    # Percuma -> berbayar
    assert client.put(f"/admin/activities/{free['id']}/fee", headers=admin, json={"fee": 3}).status_code == 200
    day = [d for d in client.get("/bookings", headers=h).json() if d["training_date"] == d2.isoformat()][0]
    assert day["payment"]["amount"] == 3.0


def test_ehailing_managed_by_admin(client):
    admin = make_admin(client)
    h1, _ = make_user(client, 1)     # tiada kereta langsung dalam sistem -> tiada kenderaan
    set_prefs(client, h1)
    ev = first_event(client, admin)
    eid = ev["event_id"]
    need = client.get(f"/admin/events/{eid}/needs-transport", headers=admin).json()
    assert {r["direction"] for r in need} == {"going", "returning"} and not any(r["ehailing"] for r in need)
    r = client.post(f"/admin/events/{eid}/ehailing", headers=admin,
                    json={"direction": "going", "note": "Grab ABC1234 8:40", "on": True})
    assert r.status_code == 200 and r.json()["notified"] == 1
    ov = r.json()["event"]
    assert ov["going"]["ehailing"] == 1 and ov["going"]["unassigned"] == 0 and ov["returning"]["unassigned"] == 1
    day = client.get("/bookings", headers=h1).json()[0]
    going = [t for t in day["trips"] if t["direction"] == "going"][0]
    assert going["ehailing"] is True and "Grab" in going["ehailing_note"]
    notes = client.get("/notifications", headers=h1).json()
    assert any("E-hailing" in n["title"] for n in notes)
    # Selepas disahkan: kedua-dua trip e-hailing -> tiada yuran persatuan (ahli bayar e-hailing sendiri)
    assert client.post(f"/admin/events/{eid}/finalise", headers=admin).status_code == 200
    day = client.get("/bookings", headers=h1).json()[0]
    assert not (day.get("payment") or {}).get("can_pay")
    assert not (day.get("payment") or {}).get("due")
    # Batalkan e-hailing -> yuran kembali
    r = client.post(f"/admin/events/{eid}/ehailing", headers=admin, json={"direction": "going", "on": False})
    assert r.json()["event"]["going"]["ehailing"] == 0


def test_member_feedback_reaches_admin(client):
    admin = make_admin(client)
    h, _ = make_user(client, 1)
    assert client.post("/feedback", json={"kind": "cadangan", "message": "x"}, headers=h).status_code == 422
    assert client.post("/feedback", json={"kind": "cadangan", "message": "Tambah mod gelap"}).status_code == 401
    assert client.post("/feedback", json={"kind": "cadangan", "message": "Tambah mod gelap"}, headers=h).status_code == 201
    assert client.get("/admin/feedback", headers=h).status_code == 403
    rows = client.get("/admin/feedback", headers=admin).json()
    assert len(rows) == 1 and rows[0]["status"] == "baru" and rows[0]["from"]["member_no"] == "SG2627001"
    assert client.put(f"/admin/feedback/{rows[0]['id']}", json={"status": "selesai"}, headers=admin).status_code == 200
    assert client.get("/admin/feedback", headers=admin).json()[0]["status"] == "selesai"
    assert client.delete(f"/admin/feedback/{rows[0]['id']}", headers=admin).status_code == 200


def test_admin_can_also_be_passenger(client):
    admin = make_admin(client)   # SG2627099 dipromosikan jadi admin
    el = client.get("/transport/preferences", headers=admin).json()["eligibility"]
    assert el["eligible"] is True
    set_prefs(client, admin)
    assert client.get("/bookings", headers=admin).json()


def test_treasurer_limited_access_and_driver_directory(client):
    admin = make_admin(client)
    tr, tid = make_user(client, 5)
    assert client.get("/admin/payments", headers=tr).status_code == 403
    assert client.put(f"/admin/users/{tid}/treasurer", json={"on": True}, headers=tr).status_code == 403
    assert client.put(f"/admin/users/{tid}/treasurer", json={"on": True}, headers=admin).status_code == 200
    assert client.get("/auth/me", headers=tr).json()["is_treasurer"] is True
    for ok in ("/admin/payments", "/admin/finance/drivers", "/admin/settings/payment", "/admin/dashboard"):
        assert client.get(ok, headers=tr).status_code == 200, ok
    for bad in ("/admin/users", "/admin/roster", "/admin/feedback", "/admin/vehicles"):
        assert client.get(bad, headers=tr).status_code == 403, bad
    assert client.post("/admin/announce", json={"title": "x", "body": ""}, headers=tr).status_code == 403
    # Bendahari tak boleh ubah kadar bayaran prebet / yuran, kaedah bayar atau lihat penyata untung
    rates = client.get("/admin/settings/rates", headers=admin)
    if rates.status_code == 200:
        assert client.put("/admin/settings/rates", json=rates.json(), headers=tr).status_code == 403
    assert client.put("/admin/settings/payout-mode", json={"mode": "bulanan"}, headers=tr).status_code == 403
    assert client.get("/admin/profit", headers=tr).status_code == 403
    # Direktori bank driver menunjukkan pemilik
    _, did, _ = approved_driver_car(client, admin, n=6)
    rows = client.get("/admin/finance/drivers", headers=tr).json()
    assert [r["id"] for r in rows] == [did] and rows[0]["vehicles"][0]["name"] == "Myvi Ali"


def test_admin_deletes_spam_accounts_and_vehicle_limits(client):
    admin = make_admin(client)
    spam, sid = make_user(client, 7)
    assert client.delete(f"/admin/users/{sid}", headers=spam).status_code == 403
    assert client.delete(f"/admin/users/{sid}", headers=admin).status_code == 200
    assert not any(u["id"] == sid for u in client.get("/admin/users", headers=admin).json())
    # Akaun yang ada tempahan tak boleh dipadam
    h, uid = make_user(client, 8)
    set_prefs(client, h)
    client.get("/bookings", headers=h)
    assert client.delete(f"/admin/users/{uid}", headers=admin).status_code == 400
    # Driver: had 5 kenderaan, admin boleh padam kenderaan yang belum digunakan
    dh, did = make_user(client, 9, is_driver=True)
    ids = []
    for i in range(5):
        r = client.post("/driver/vehicles", headers=dh, json={
            "name": f"Myvi {i}", "plate_no": f"ABC{i}", "vehicle_type": "car", "seats": 5, "available_days": "2,5"})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    r6 = client.post("/driver/vehicles", headers=dh, json={
        "name": "Myvi 6", "plate_no": "ABC6", "vehicle_type": "car", "seats": 5, "available_days": "2,5"})
    assert r6.status_code == 400
    assert client.delete(f"/admin/vehicles/{ids[0]}", headers=admin).status_code == 200


def test_treasurer_gets_payout_reminder(client):
    from datetime import date, timedelta
    from app.database import SessionLocal
    from app.services import booking as svc
    admin = make_admin(client)
    tr, tid = make_user(client, 5)
    client.put(f"/admin/users/{tid}/treasurer", json={"on": True}, headers=admin)
    dh, drv_id, vid = approved_driver_car(client, admin, n=6)
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    ev = finalise_first(client, admin)
    pid = client.get("/bookings", headers=h).json()[0]["payment"]["id"]
    client.post(f"/payments/{pid}/receipt", headers=h, files={"file": PNG})
    assert client.post(f"/admin/payments/{pid}/verify", headers=tr).status_code == 200
    d = date.fromisoformat(ev["training_date"])
    with SessionLocal() as db:
        assert svc.send_payout_reminders(db, today=d + timedelta(days=1)) == 1
        assert svc.send_payout_reminders(db, today=d + timedelta(days=1)) == 0   # tak berulang pada hari yang sama
    notes = client.get("/notifications", headers=tr).json()
    assert any(n["title"].startswith("Bayar prebet") for n in notes)
    # Bendahari boleh catat bayaran driver
    assert client.post("/admin/payouts", headers=tr, json={"vehicle_id": vid, "training_date": ev["training_date"]}).status_code == 200


def test_force_delete_account_with_history(client):
    admin = make_admin(client)
    dh, did, vid = approved_driver_car(client, admin, n=6)
    h, uid = make_user(client, 1)
    set_prefs(client, h)
    client.get("/bookings", headers=h)
    # Padam biasa ditolak, padam paksa (fasa ujian) berjaya dan buang semua rekod
    assert client.delete(f"/admin/users/{uid}", headers=admin).status_code == 400
    r = client.delete(f"/admin/users/{uid}?force=true", headers=admin)
    assert r.status_code == 200 and r.json()["forced"] is True
    assert not any(u["id"] == uid for u in client.get("/admin/users", headers=admin).json())
    # Driver yang ada kenderaan pun boleh dipadam paksa; kenderaannya turut dibuang
    assert client.delete(f"/admin/users/{did}", headers=admin).status_code == 400
    assert client.delete(f"/admin/users/{did}?force=true", headers=admin).status_code == 200
    assert not any(v["id"] == vid for v in client.get("/admin/vehicles", headers=admin).json())
    # No. ahli boleh didaftar semula selepas dipadam
    r = client.post("/auth/register", json={"name": "Ahli 1", "member_no": "SG2627001", "phone": "0123456789",
                                            "email": "ahli1@test.com", "password": "password123",
                                            "gender": "female", "college_id": college_id("K9")})
    assert r.status_code == 201
    # Admin dan diri sendiri tak boleh dipadam
    assert client.delete("/admin/users/1?force=true", headers=admin).status_code in (400, 404)


def test_roster_format_and_duplicates_rejected(client):
    admin = make_admin(client)
    csv_bytes = (b"no ahli,nama,jantina,kolej,ic,alamat\n"
                 b"SG2627060,Ali,L,K10,990101,Rumah A\n"
                 b"AB123,Salah Format,L,K10,,\n"
                 b"SG2627061,Dup Satu,L,K10,,\n"
                 b"sg2627061,Dup Dua,P,K9,,\n"
                 b"SG2627062,Aina,P,K9,,\n")
    r = client.post("/admin/roster/import", headers=admin, files={"file": ("r.csv", csv_bytes, "text/csv")}).json()
    assert r["added"] == 2                      # SG2627060 dan SG2627062 sahaja; kolum IC/alamat diabaikan
    assert r["error_count"] == 3                # format salah + dua baris duplicate
    assert any("Format" in e for e in r["errors"]) and sum("berulang" in e for e in r["errors"]) == 2
    nos = {x["member_no"] for x in client.get("/admin/roster", headers=admin).json()}
    assert "SG2627061" not in nos and "AB123" not in nos
    # Tambah manual: format salah ditolak, format betul diterima
    assert client.post("/admin/roster", headers=admin, json={"member_no": "XX1"}).status_code == 400
    assert client.post("/admin/roster", headers=admin, json={"member_no": "SG2627070"}).status_code == 201
    # Import semula tidak mengaktifkan semula ahli yang dinyahaktifkan
    rid = next(x["id"] for x in client.get("/admin/roster", headers=admin).json() if x["member_no"] == "SG2627060")
    assert client.put(f"/admin/roster/{rid}?active=false", headers=admin).status_code == 200
    client.post("/admin/roster/import", headers=admin, files={"file": ("r.csv", b"no ahli\nSG2627060\n", "text/csv")})
    row = next(x for x in client.get("/admin/roster", headers=admin).json() if x["member_no"] == "SG2627060")
    assert row["active"] is False
    # Daftar: no. tiada dalam senarai ditolak; format salah diberi petunjuk
    base = {"name": "Ali", "phone": "0123456789", "email": "z@test.com", "password": "password123",
            "gender": "female", "college_id": college_id("K9")}
    bad = client.post("/auth/register", json={**base, "member_no": "ABC"})
    assert bad.status_code == 400 and "Format" in bad.json()["detail"]
    missing = client.post("/auth/register", json={**base, "member_no": "SG2627999"})
    assert missing.status_code == 400 and "senarai" in missing.json()["detail"]
    inactive = client.post("/auth/register", json={**base, "member_no": "SG2627060"})
    assert inactive.status_code == 400


def test_forgot_password_admin_fallback_and_email_reset(client, monkeypatch):
    from app import mailer
    admin = make_admin(client)
    h, uid = make_user(client, 1)
    # Tiada emel dikonfigurasi: admin dimaklumkan, jawapan sama untuk akaun tak wujud
    r = client.post("/auth/forgot", json={"identifier": "SG2627001"})
    assert r.status_code == 200 and (r.json()["ok"], r.json()["mode"]) == (True, "admin")
    x = client.post("/auth/forgot", json={"identifier": "tiada@test.com"}).json()
    assert (x["ok"], x["mode"]) == (True, "admin")
    notes = client.get("/notifications", headers=admin).json()
    assert any(n["title"].startswith("Lupa kata laluan") for n in notes)
    # Mod emel: pautan sekali guna
    sent = {}
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send_mail", lambda to, subject, text: sent.update(to=to, text=text) or True)
    assert client.get("/auth/forgot/info").json()["mode"] == "email"
    assert client.post("/auth/forgot", json={"identifier": "ahli1@test.com"}).json()["mode"] == "email"
    assert sent["to"] == "ahli1@test.com"
    token = sent["text"].split("token=")[1].split()[0]
    assert client.post("/auth/reset", json={"token": token, "new_password": "pendek"}).status_code == 422
    assert client.post("/auth/reset", json={"token": "x" * 30, "new_password": "passbaru123"}).status_code == 400
    assert client.post("/auth/reset", json={"token": token, "new_password": "passbaru123"}).status_code == 200
    assert client.post("/auth/login", json={"identifier": "SG2627001", "password": "passbaru123"}).status_code == 200
    assert client.post("/auth/login", json={"identifier": "SG2627001", "password": "password123"}).status_code == 401
    # Token sekali guna sahaja
    assert client.post("/auth/reset", json={"token": token, "new_password": "lainlagi123"}).status_code == 400


def test_member_picks_dates_and_joins_nearest(client):
    admin = make_admin(client)
    approved_driver_car(client, admin, n=6)
    h, uid = make_user(client, 1)             # ahli baru, TIDAK set jadual berulang
    opts = client.get("/transport/dates", headers=h).json()
    assert opts and all(o["in_list"] is False for o in opts)
    first = opts[0]
    body = {"training_date": first["training_date"], "session_id": first["session_id"], "going": True, "returning": True}
    r = client.put("/transport/dates", headers=h, json=body)
    assert r.status_code == 200
    got = next(o for o in r.json() if o["training_date"] == first["training_date"] and o["session_id"] == first["session_id"])
    assert got["going"] and got["returning"] and got["in_list"]
    assert "Myvi Ali" in got["car"]             # terus masuk kenderaan untuk tarikh terdekat
    # Tarikh lain tak terjejas
    assert all(not o["in_list"] for o in r.json() if o["training_date"] != first["training_date"])
    # Batal tarikh itu
    r = client.put("/transport/dates", headers=h, json={**body, "going": False, "returning": False})
    got = next(o for o in r.json() if o["training_date"] == first["training_date"] and o["session_id"] == first["session_id"])
    assert not got["going"] and not got["returning"] and got["car"] == ""
    # Sehala sahaja
    r = client.put("/transport/dates", headers=h, json={**body, "returning": False})
    got = next(o for o in r.json() if o["training_date"] == first["training_date"] and o["session_id"] == first["session_id"])
    assert got["going"] and not got["returning"]


def test_new_member_with_schedule_joins_after_list_finalised(client):
    admin = make_admin(client)
    approved_driver_car(client, admin, n=6)
    h1, _ = make_user(client, 1)
    set_prefs(client, h1)
    ev = finalise_first(client, admin)
    # Ahli baru daftar SELEPAS senarai disahkan: masuk senarai & dapat seat kosong, kenderaan sedia ada tak diubah
    h2, _ = make_user(client, 2)
    set_prefs(client, h2)
    opts = client.get("/transport/dates", headers=h2).json()
    got = next(o for o in opts if o["training_date"] == ev["training_date"])
    assert got["in_list"] and got["event_status"] == "finalised" and "Myvi Ali" in got["car"]


def test_date_only_mode_ignores_recurring_prefs(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "AUTO_FROM_PREFERENCES", False)
    admin = make_admin(client)
    approved_driver_car(client, admin, n=6)
    h, _ = make_user(client, 1)
    set_prefs(client, h)                         # jadual berulang tak lagi menjana tempahan
    assert client.get("/bookings", headers=h).json() == []
    opts = client.get("/transport/dates", headers=h).json()
    first = opts[0]
    r = client.put("/transport/dates", headers=h, json={"training_date": first["training_date"],
                                                         "session_id": first["session_id"], "going": True, "returning": True})
    assert r.status_code == 200
    assert [d["training_date"] for d in client.get("/bookings", headers=h).json()] == [first["training_date"]]


def test_custom_rules_text_and_payout_qr_delete(client):
    admin = make_admin(client)
    assert client.get("/rules").json()["custom_rules"] == ""
    r = client.put("/admin/settings/rules", headers=admin, json={"text": "Syarat A\nSyarat B"})
    assert r.status_code == 200
    assert client.get("/rules").json()["custom_rules"] == "Syarat A\nSyarat B"
    client.put("/admin/settings/rules", headers=admin, json={"text": ""})
    assert client.get("/rules").json()["custom_rules"] == ""


def test_admin_seatmap_drag_rules_and_swap(client):
    admin = make_admin(client)
    approved_driver_car(client, admin, n=6)                       # driver lelaki, kereta 5 seat (1,3)
    hf1, f1 = make_user(client, 1)
    hf2, f2 = make_user(client, 2)
    hm, m1 = make_user(client, 3, "K10", gender="male")
    for h in (hf1, hf2, hm):
        set_prefs(client, h)
    eid = first_event(client, admin)["event_id"]
    sm = client.get(f"/admin/events/{eid}/seatmap", headers=admin).json()
    car = sm["cars"][0]
    going = car["directions"]["going"]["seated"]
    assert len(going) == 3
    by = {p["user_id"]: p for p in going}
    assert by[m1]["row"] == 0 and by[f1]["row"] == 1 and by[f2]["row"] == 1
    # perempuan ke sebelah driver lelaki: ditolak
    r = client.put(f"/admin/events/{eid}/seat", headers=admin,
                   json={"user_id": f1, "vehicle_id": car["vehicle_id"], "direction": "going", "row": 0, "col": 0})
    assert r.status_code == 400
    # tukar tempat dua perempuan dalam baris yang sama: dibenarkan
    a, b = (by[f1]["row"], by[f1]["col"]), (by[f2]["row"], by[f2]["col"])
    r = client.put(f"/admin/events/{eid}/seat", headers=admin,
                   json={"user_id": f1, "vehicle_id": car["vehicle_id"], "direction": "going", "row": b[0], "col": b[1]})
    assert r.status_code == 200, r.text
    now = {p["user_id"]: (p["row"], p["col"]) for p in r.json()["cars"][0]["directions"]["going"]["seated"]}
    assert now[f1] == b and now[f2] == a
    # kerusi disimpan selepas muat semula
    again = client.get(f"/admin/events/{eid}/seatmap", headers=admin).json()
    now2 = {p["user_id"]: (p["row"], p["col"]) for p in again["cars"][0]["directions"]["going"]["seated"]}
    assert now2 == now
    # keluarkan ahli daripada kenderaan
    r = client.put(f"/admin/events/{eid}/seat", headers=admin, json={"user_id": f2, "vehicle_id": None})
    assert r.status_code == 200
    assert any(u["user_id"] == f2 for u in r.json()["unassigned"])


def test_vehicle_kinds_admin_and_driver_pick(client):
    admin = make_admin(client)
    kinds = client.get("/admin/vehicle-kinds", headers=admin).json()
    assert {k["name"] for k in kinds} >= {"Kereta 5 tempat duduk", "Kereta 7 tempat duduk", "Motosikal"}
    assert client.post("/admin/vehicle-kinds", headers=admin, json={"name": "Van", "base": "car", "seat_rows": "1,2,2,2,x"}).status_code == 400
    r = client.post("/admin/vehicle-kinds", headers=admin, json={"name": "Van", "base": "car", "seat_rows": "1,2,2,2"})
    assert r.status_code == 201 and r.json()["capacity"] == 7
    kid = r.json()["id"]
    dh, _ = make_user(client, 6, is_driver=True, code="KTDI", gender="male")
    assert any(k["name"] == "Van" for k in client.get("/driver/kinds", headers=dh).json())
    r = client.post("/driver/vehicles", headers=dh, json={"name": "Van Ali", "plate_no": "vvv1", "kind_id": kid})
    assert r.status_code == 201, r.text
    assert r.json()["capacity"] == 7 and r.json()["seat_rows"] == "1,2,2,2" and r.json()["kind_name"] == "Van"
    # ubah jenis tak mengubah kenderaan sedia ada
    client.put(f"/admin/vehicle-kinds/{kid}", headers=admin, json={"name": "Van", "base": "car", "seat_rows": "1,3", "active": True})
    v = next(x for x in client.get("/admin/vehicles", headers=admin).json() if x["name"] == "Van Ali")
    assert v["capacity"] == 7


def test_google_login_existing_and_register_needs_roster(client, monkeypatch):
    from app import config, google_auth
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "cid")
    h, uid = make_user(client, 1)                       # emel ahli1@test.com
    cred = "x" * 30
    monkeypatch.setattr(google_auth, "verify", lambda c: {"email": "ahli1@test.com", "name": "Ahli 1"})
    r = client.post("/auth/google", json={"credential": cred})
    assert r.status_code == 200 and r.json()["user"]["id"] == uid
    # emel baru: minta pendaftaran
    monkeypatch.setattr(google_auth, "verify", lambda c: {"email": "baru@gmail.com", "name": "Orang Baru"})
    r = client.post("/auth/google", json={"credential": cred})
    assert r.json() == {"needs_registration": True, "email": "baru@gmail.com", "name": "Orang Baru"}
    # no. ahli tiada dalam senarai: ditolak
    body = {"credential": cred, "member_no": "SG2627777", "phone": "0123456789", "gender": "female", "college_code": "K9"}
    assert client.post("/auth/google", json=body).status_code == 400
    add_roster("SG2627777")
    r = client.post("/auth/google", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "baru@gmail.com"
    # log masuk semula guna Google
    assert client.post("/auth/google", json={"credential": cred}).status_code == 200
    # token tak sah
    def bad(c): raise google_auth.GoogleAuthError("tak sah")
    monkeypatch.setattr(google_auth, "verify", bad)
    assert client.post("/auth/google", json={"credential": cred}).status_code == 401


# ------------------------------------------------------------ Fasa 7

def test_walk_rule_college_venue_and_l50_excludes_nobody(client):
    admin = make_admin(client)
    r = client.post("/admin/venues", headers=admin, json={"college_code": "KDSE", "excluded_codes": []})
    assert r.status_code == 201 and r.json()["excluded_codes"] == ["KDSE"] and r.json()["college_code"] == "KDSE"
    v = {x["name"]: x for x in client.get("/admin/venues", headers=admin).json()}
    assert v["L50"]["excluded_codes"] == []        # bukan kolej: tiada siapa dikecualikan


def test_fixed_payout_and_combined_unpaid(client):
    from datetime import date, timedelta
    from app.database import SessionLocal
    from app.services import booking as svc
    admin = make_admin(client)
    dh, drv_id, vid = approved_driver_car(client, admin)       # prebet KTDI = kereta dekat = RM10 tetap
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    ev = finalise_first(client, admin)
    d = date.fromisoformat(ev["training_date"])
    with SessionLocal() as db:
        items = svc.payout_items(db, today=d + timedelta(days=1))
        assert [i["outstanding"] for i in items] == [14.0]
        ov = svc.payout_overview(db, today=d + timedelta(days=1))
        assert ov["drivers"][0]["total"] == 14.0 and ov["mode"] == "latihan"
    rates = client.get("/admin/settings/rates", headers=admin).json()
    assert rates["payouts"]["car"] == {"dekat": 10.0, "jauh": 14.0}
    assert rates["payouts"]["motorcycle"] == {"dekat": 1.0, "jauh": 2.0}


def test_pay_driver_one_receipt(client, monkeypatch):
    from datetime import date, timedelta
    admin = make_admin(client)
    dh, drv_id, vid = approved_driver_car(client, admin)
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    past_day(monkeypatch, finalise_first(client, admin))
    r = client.post("/admin/payouts/driver", headers=admin, data={"driver_id": drv_id}, files={"file": PNG})
    assert r.status_code == 200 and r.json()["amount"] == 14.0
    assert client.post("/admin/payouts/driver", headers=admin, data={"driver_id": drv_id}, files={"file": PNG}).status_code == 400
    mine = client.get("/driver/payouts", headers=dh).json()
    assert len(mine) == 1 and mine[0]["amount"] == 14.0 and mine[0]["received"] is False
    assert client.post(f"/driver/payouts/{mine[0]['id']}/received", headers=dh).status_code == 200
    assert client.get("/driver/payouts", headers=dh).json()[0]["received"] is True


def test_payout_mode_admin_only_and_notifies(client):
    admin = make_admin(client)
    dh, drv_id, vid = approved_driver_car(client, admin)
    assert client.put("/admin/settings/payout-mode", headers=dh, json={"mode": "mingguan"}).status_code == 403
    assert client.put("/admin/settings/payout-mode", headers=admin, json={"mode": "bogus"}).status_code == 422
    assert client.put("/admin/settings/payout-mode", headers=admin, json={"mode": "mingguan"}).status_code == 200
    assert any("Kaedah bayaran" in n["title"] for n in client.get("/notifications", headers=dh).json())


def test_tick_and_profit_admin_only(client):
    admin = make_admin(client)
    dh, drv_id, vid = approved_driver_car(client, admin)
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    ev = finalise_first(client, admin)
    t = client.put("/driver/tick", headers=dh, json={"training_date": ev["training_date"], "kind": "arrived"})
    assert t.status_code == 200
    assert client.get("/admin/profit", headers=dh).status_code == 403
    assert client.get("/admin/profit", headers=admin).status_code == 200


def test_cutoff_5pm_blocks_members_not_admin(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "ENFORCE_CUTOFF", True)
    from app.services import booking as svc
    from datetime import datetime
    admin = make_admin(client)
    h, uid = make_user(client, 1)
    ev = first_event(client, admin)
    d = datetime.fromisoformat(ev["training_date"]).date()
    from app.database import SessionLocal
    from app.models import TrainingEvent
    _db = SessionLocal()
    _sess_id = _db.get(TrainingEvent, ev["event_id"]).session_id
    _db.close()
    monkeypatch.setattr(svc, "now_my", lambda: datetime.combine(d, datetime.min.time()).replace(hour=17, minute=30))
    r = client.put("/transport/dates", headers=h, json={"training_date": ev["training_date"], "session_id": _sess_id,
                                                        "going": True, "returning": True})
    assert r.status_code == 400 and "ditutup" in r.json()["detail"]


def test_default_rules_and_contacts(client):
    admin = make_admin(client)
    rules = client.get("/rules").json()
    assert any("12:00" in x or "12" in x for x in rules["default_rules"]) and rules["default_rules"]
    c = client.get("/contacts", headers=admin).json()
    assert c["site"]["phone"] == "0192278390" and c["fallback"]["phone"] == "0192278390"


def test_payout_overview_and_driver_receipt_endpoints(client, monkeypatch):
    admin = make_admin(client)
    dh, drv_id, vid = approved_driver_car(client, admin)
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    past_day(monkeypatch, finalise_first(client, admin))
    ov = client.get("/admin/payouts/overview", headers=admin)
    assert ov.status_code == 200 and ov.json()["drivers"][0]["total"] == 14.0 and ov.json()["mode"]
    assert client.get("/admin/payouts/history", headers=admin).status_code == 200
    client.post("/admin/payouts/driver", headers=admin, data={"driver_id": drv_id}, files={"file": PNG})
    pid = client.get("/driver/payouts", headers=dh).json()[0]["id"]
    assert client.get(f"/driver/payouts/{pid}/receipt", headers=dh).status_code == 200
    other, _ = make_user(client, 2)   # bukan pemilik
    assert client.get(f"/driver/payouts/{pid}/receipt", headers=other).status_code == 404
    assert client.post(f"/driver/payouts/{pid}/received", headers=dh).status_code == 200


def test_reactivate_cancelled_event_restores_only_event_cancelled(client):
    admin = make_admin(client)
    client.post("/admin/vehicles", headers=admin, json=VEHICLE_5)
    a, aid = make_user(client, 1, "K9", "female")
    b, bid = make_user(client, 2, "K9", "female")
    set_prefs(client, a)
    set_prefs(client, b)
    ev = first_event(client, admin)
    # b batal sendiri dahulu
    assert client.post("/bookings/skip", headers=b, json={"training_date": ev["training_date"], "skip": True}).status_code == 200
    assert client.post(f"/admin/events/{ev['event_id']}/reactivate", headers=admin).status_code == 400  # belum dibatalkan
    assert client.post(f"/admin/events/{ev['event_id']}/cancel", headers=admin).status_code == 200
    assert client.post(f"/admin/events/{ev['event_id']}/reactivate", headers=make_user(client, 3)[0]).status_code == 403
    r = client.post(f"/admin/events/{ev['event_id']}/reactivate", headers=admin)
    assert r.status_code == 200 and r.json()["restored"] == 1
    assert r.json()["event"]["status"] == "open"
    from datetime import date
    from app.database import SessionLocal
    d = date.fromisoformat(ev["training_date"])
    with SessionLocal() as db:
        st = lambda uid: {x.status.value for x in db.query(models.Booking).filter_by(user_id=uid, training_date=d)}
        assert st(aid) == {"confirmed"}      # dipulihkan
        assert st(bid) == {"cancelled"}      # batal sendiri kekal batal


def test_delete_checkpoint_needs_move_when_used(client):
    admin = make_admin(client)
    h, uid = make_user(client, 1, "K9", "female")
    pts = client.get("/admin/pickup-points", headers=admin).json()
    k9 = college_id("K9")
    cur = next(p for p in pts if p["college_id"] == k9)
    # checkpoint baharu kolej sama
    new = client.post("/admin/pickup-points", headers=admin,
                      json={"name": "Bus Stop K9 B", "college_id": k9, "gender": "female", "active": True}).json()
    set_prefs(client, h)
    r = client.delete(f"/admin/pickup-points/{cur['id']}", headers=admin)
    assert r.status_code == 409 and "masih guna" in r.json()["detail"]
    assert client.delete(f"/admin/pickup-points/{cur['id']}?move_to={cur['id']}", headers=admin).status_code == 400
    assert client.delete(f"/admin/pickup-points/{cur['id']}?move_to={new['id']}", headers=admin).status_code == 200
    assert client.get("/profile", headers=h).json()["pickup_point_id"] in (None, new["id"])
    assert client.delete(f"/admin/pickup-points/{new['id']}", headers=h).status_code == 403


def test_theme_saved_per_account(client):
    h, _ = make_user(client, 1)
    h2, _ = make_user(client, 2)
    assert client.get("/profile", headers=h).json()["theme"] == "auto"
    assert client.put("/profile/theme", headers=h, json={"theme": "dark"}).status_code == 200
    assert client.put("/profile/theme", headers=h, json={"theme": "pink"}).status_code == 422
    assert client.get("/profile", headers=h).json()["theme"] == "dark"
    assert client.get("/profile", headers=h2).json()["theme"] == "auto"


def test_backup_export_admin_only_and_no_secrets(client):
    import io
    import zipfile
    admin = make_admin(client)
    dh, drv_id, vid = approved_driver_car(client, admin)
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    client.put("/driver/payout", headers=dh, json={"payout_bank": "Maybank", "payout_account_no": "1234567890123", "payout_account_name": "Ali"})
    assert client.get("/admin/export", headers=h).status_code == 403
    r = client.get("/admin/export", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"ahli_dan_prebet.csv", "kenderaan.csv", "tempahan.csv", "bayaran_ahli.csv", "bayaran_prebet.csv"} <= names
    allt = "".join(z.read(n).decode("utf-8-sig") for n in names)
    assert "ahli1@test.com" in allt and "0123" in allt
    assert "1234567890123" not in allt and "password_hash" not in allt and "$2b$" not in allt


def test_gender_choice_syncs_roster_notifies_admin_and_change_needs_approval(client):
    admin = make_admin(client)
    add_roster("SG2627090", gender="female", code="K9")
    r = client.post("/auth/register", json={"name": "Ali", "member_no": "SG2627090", "phone": "0123456789",
                                            "email": "g1@test.com", "password": "password123", "gender": "male"})
    assert r.status_code == 201 and r.json()["user"]["gender"] == "male"
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    uid = r.json()["user"]["id"]
    notes = client.get("/notifications", headers=admin).json()
    assert any("Jantina ahli berubah" in n["title"] for n in notes)
    rows = client.get("/admin/roster", headers=admin).json()
    assert any(x["member_no"] == "SG2627090" and x["gender"] == "male" for x in (rows if isinstance(rows, list) else rows.get("rows", [])))
    # tukar jantina: perlu kelulusan
    assert client.post("/profile/gender-request", headers=h, json={"gender": "male"}).status_code == 400
    assert client.post("/profile/gender-request", headers=h, json={"gender": "female"}).status_code == 200
    assert client.get("/profile", headers=h).json()["gender"] == "male"           # belum berubah
    assert client.put(f"/admin/users/{uid}/gender-request", headers=h, json={"approve": True}).status_code == 403
    assert client.put(f"/admin/users/{uid}/gender-request", headers=admin, json={"approve": True}).status_code == 200
    p = client.get("/profile", headers=h).json()
    assert p["gender"] == "female" and p["gender_request"] == ""


def test_pay_info_hidden_until_finalised_and_unfinalise(client, monkeypatch):
    admin = make_admin(client)
    dh, drv_id, vid = approved_driver_car(client, admin)
    h, _ = make_user(client, 1)
    set_prefs(client, h)
    client.put("/admin/settings/payment", headers=admin, json={"pay_bank": "Maybank", "pay_account_no": "5111", "pay_account_name": "PSSGUTM", "pay_notes": ""})
    assert client.get("/payment-info", headers=h).json()["locked"] is True
    assert client.get("/payment-info", headers=h).json()["pay_account_no"] == ""
    assert client.get("/payment-info/qr", headers=h).status_code == 403
    assert client.get("/payment-info", headers=admin).json()["pay_account_no"] == "5111"
    ev = finalise_first(client, admin)
    assert client.get("/payment-info", headers=h).json()["pay_account_no"] == "5111"
    ov = client.get("/admin/dashboard", headers=admin).json()[0]
    assert ov["payments"]["to_collect"] > 0 and ov["payout_due"] == 14.0
    # admin batalkan pengesahan -> bayaran ditutup semula, auto-sah dimatikan
    r = client.post(f"/admin/events/{ev['event_id']}/unfinalise", headers=admin)
    assert r.status_code == 200 and r.json()["event"]["status"] == "open" and r.json()["event"]["auto_off"] is True
    assert client.get("/payment-info", headers=h).json()["locked"] is True
    assert client.post(f"/admin/events/{ev['event_id']}/unfinalise", headers=admin).status_code == 400
    from app.database import SessionLocal
    from app.services import booking as svc
    from datetime import datetime
    with SessionLocal() as db:
        from app import models as m
        e = db.get(m.TrainingEvent, ev["event_id"])
        assert svc.auto_finalise(db, now=datetime.combine(e.training_date, datetime.min.time()).replace(hour=19, minute=30)) == 0
    assert client.post(f"/admin/events/{ev['event_id']}/finalise", headers=admin).status_code == 200
    # bayaran prebet sudah dibuat -> tak boleh batal pengesahan
    past_day(monkeypatch, ev)
    client.post("/admin/payouts/driver", headers=admin, data={"driver_id": drv_id}, files={"file": PNG})
    assert client.post(f"/admin/events/{ev['event_id']}/unfinalise", headers=admin).status_code == 400


def test_driver_gender_change_updates_vehicles(client):
    admin = make_admin(client)
    dh, drv_id, vid = approved_driver_car(client, admin)
    first = next(v for v in client.get("/admin/vehicles", headers=admin).json() if v["id"] == vid)
    other = "female" if first["driver_gender"] == "male" else "male"
    assert client.put(f"/admin/users/{drv_id}", headers=admin, json={"gender": other}).status_code == 200
    after = next(v for v in client.get("/admin/vehicles", headers=admin).json() if v["id"] == vid)
    assert after["driver_gender"] == other
    # data lama tak sepadan: naik taraf sekali (seed) menyelaraskan
    from app.database import SessionLocal
    from app import models as m
    from app.seed import upgrade_v8
    with SessionLocal() as db:
        db.get(m.Vehicle, vid).driver_gender = m.Gender.male if other == "female" else m.Gender.female
        db.query(m.Setting).filter_by(key="seed_v8").delete()
        db.commit()
        upgrade_v8(db)
        db.commit()
        assert db.get(m.Vehicle, vid).driver_gender.value == other


def test_member_requests_to_become_prebet_needs_admin_approval(client):
    admin = make_admin(client)
    h, uid = make_user(client, 1)
    assert client.post("/profile/prebet-request", headers=h).status_code == 200
    assert client.post("/profile/prebet-request", headers=h).status_code == 400   # sudah menunggu
    assert client.get("/profile", headers=h).json()["prebet_request"] is True
    assert any("Mohon jadi prebet" in n["title"] for n in client.get("/notifications", headers=admin).json())
    assert client.put(f"/admin/users/{uid}/prebet-request", headers=h, json={"approve": True}).status_code == 403
    assert client.put(f"/admin/users/{uid}/prebet-request", headers=admin, json={"approve": True}).status_code == 200
    p = client.get("/profile", headers=h).json()
    assert p["role"] == "driver" and p["passenger_ok"] is True and p["prebet_request"] is False
    assert client.put(f"/admin/users/{uid}/prebet-request", headers=admin, json={"approve": True}).status_code == 400
    # tolak
    h2, uid2 = make_user(client, 2)
    client.post("/profile/prebet-request", headers=h2)
    assert client.put(f"/admin/users/{uid2}/prebet-request", headers=admin, json={"approve": False}).status_code == 200
    p2 = client.get("/profile", headers=h2).json()
    assert p2["role"] == "member" and p2["prebet_request"] is False


def test_warning_deletable_only_on_next_training_date(client):
    from datetime import date, datetime
    from app import models
    from app.database import SessionLocal
    from app.services import booking as svc
    db = SessionLocal()
    try:
        sessions = db.query(models.TrainingSession).filter_by(active=True).all()
        assert sessions
        d = svc.upcoming_dates(db, date(2026, 11, 4), 0)  # Rabu 2026-11-04
        n = models.Notification(user_id=None, kind="x", title="t", severity="warning",
                                training_date=date(2026, 11, 4), created_at=datetime(2026, 11, 4, 1, 0))
        nxt = svc.warning_unlock_date(db, n)
        assert nxt > date(2026, 11, 4)
        assert not svc.warning_deletable(db, n, today=date(2026, 11, 4))
        assert svc.warning_deletable(db, n, today=nxt)
        info = models.Notification(user_id=None, kind="x", title="t", severity="info")
        assert svc.warning_deletable(db, info, today=date(2026, 11, 4))
    finally:
        db.close()


def test_payout_category_follows_passengers_not_driver():
    from types import SimpleNamespace as NS
    from app.services import booking as svc
    cols = {1: NS(category="dekat"), 2: NS(category="jauh")}
    users = {10: NS(college_id=1), 11: NS(college_id=1), 12: NS(college_id=2), 13: NS(college_id=None)}
    assert svc.payout_category([10, 11], users, cols) == "dekat"
    assert svc.payout_category([10, 12], users, cols) == "jauh"   # seorang jauh pun = kadar jauh
    assert svc.payout_category([13], users, cols) == "dekat"


def test_last_session_date_keeps_recent_card_until_next_training(client):
    from datetime import date
    from app.database import SessionLocal
    from app.services import booking as svc
    with SessionLocal() as db:
        # 2026-11-08 = Ahad; latihan Rabu (11/04) & Sabtu (11/07)
        assert svc.last_session_date(db, date(2026, 11, 8)) == date(2026, 11, 7)
        assert svc.last_session_date(db, date(2026, 11, 11)) == date(2026, 11, 11)  # Rabu: kotak Sabtu hilang
        assert svc.last_session_date(db, date(2026, 11, 5)) == date(2026, 11, 4)    # Khamis: kotak Rabu kekal


def test_activity_pickup_choice_for_outside_member_and_admin_adjust(client):
    from datetime import timedelta
    from app.services import booking as svc
    admin = make_admin(client)
    add_roster("SG2627100")
    r = client.post("/auth/register", json={"name": "Aina", "member_no": "SG2627100", "phone": "0123456789",
                                            "email": "aina@test.com", "password": "password123", "gender": "female",
                                            "college_other": "Rumah sewa Taman U"})
    out = {"Authorization": f"Bearer {r.json()['access_token']}"}
    out_id = r.json()["user"]["id"]
    inside, inside_id = make_user(client, 1)
    d = svc.today_my() + timedelta(days=3)
    act = client.post("/admin/activities", headers=admin, json={"name": "Hiking", "go_date": d.isoformat()}).json()
    assert act["pickup_mode"] == "kedua"

    def row(h):
        return next(x for x in client.get("/transport/dates", headers=h).json() if x["is_activity"])

    def pax():
        return [(p["name"], p["direction"], p["checkpoint"])
                for p in client.get(f"/admin/passengers?training_date={d.isoformat()}", headers=admin).json()]

    # Ahli tinggal luar boleh mohon aktiviti luar, tetapi wajib isi tempat
    o = row(out)
    assert o["eligible"] and o["can_tempat"] and not o["can_kolej"]
    base = {"training_date": d.isoformat(), "session_id": o["session_id"], "going": True, "returning": True}
    assert client.put("/transport/dates", headers=out, json={**base, "pickup": "tempat"}).status_code == 400
    ok = client.put("/transport/dates", headers=out, json={**base, "pickup": "tempat", "place": "Stesen LRT Rawang"})
    assert ok.status_code == 200, ok.text
    assert row(out)["my_places"] == {"going": {"kind": "tempat", "place": "Stesen LRT Rawang"},
                                     "returning": {"kind": "tempat", "place": "Stesen LRT Rawang"}}
    # Latihan biasa kekal tertutup untuk ahli tinggal luar
    pr = client.get("/transport/preferences", headers=out).json()
    assert pr["eligibility"]["eligible"] is False and pr["activity_eligibility"]["eligible"] is True

    # Ahli kolej: pergi di kolej, balik ke tempat lain (dua tempat berbeza)
    r = client.put("/transport/dates", headers=inside, json={
        **base, "pickup": "kolej", "return_pickup": "tempat", "return_place": "Rumah kakak, Skudai"})
    assert r.status_code == 200, r.text
    mine = row(inside)["my_places"]
    assert mine["going"]["kind"] == "kolej" and mine["returning"] == {"kind": "tempat", "place": "Rumah kakak, Skudai"}
    got = {(n, dr): c for n, dr, c in pax()}
    assert got[("Ahli 1", "returning")] == "Rumah kakak, Skudai" and got[("Ahli 1", "going")] != "Rumah kakak, Skudai"
    # Tukar pergi/balik tanpa hantar pilihan: pilihan sedia ada kekal
    assert client.put("/transport/dates", headers=inside, json={**base, "returning": False}).status_code == 200
    assert row(inside)["my_places"]["going"]["kind"] == "kolej"

    # Admin tukar tempat balik seorang ahli, dan kembali ke kolej
    r = client.put("/admin/bookings/pickup", headers=admin, json={
        "user_id": out_id, "training_date": d.isoformat(), "place": "Pintu Gerbang UTM", "direction": "returning"})
    assert r.status_code == 200 and r.json()["changed"] == 1
    got = {(n, dr): c for n, dr, c in pax()}
    assert got[("Aina", "returning")] == "Pintu Gerbang UTM" and got[("Aina", "going")] == "Stesen LRT Rawang"
    assert client.put("/admin/bookings/pickup", headers=admin, json={
        "user_id": out_id, "training_date": d.isoformat(), "place": ""}).status_code == 400  # tiada kolej

    assert client.put("/transport/dates", headers=inside, json={**base, "returning": True}).status_code == 200
    # Admin tetapkan tempat PERGI sahaja; balik kekal pilihan ahli (tak ditimpa)
    pick = f"/admin/activities/{act['id']}/pickup"
    r = client.put(pick, headers=admin, json={"pickup_mode": "kedua", "gather_place": "Dataran Cendekia"})
    assert r.status_code == 200 and r.json()["changed"] >= 2
    got = {(n, dr): c for n, dr, c in pax()}
    assert got[("Aina", "going")] == "Dataran Cendekia" and got[("Aina", "returning")] == "Pintu Gerbang UTM"
    o = row(out)
    assert o["fixed_go"] == "Dataran Cendekia" and o["fixed_return"] == "" and o["can_tempat"]
    # Balik tetap juga: semua kena ikut
    r = client.put(pick, headers=admin, json={"pickup_mode": "kedua", "gather_place": "Dataran Cendekia",
                                              "return_place": "Stesen LRT Rawang"})
    assert r.status_code == 200
    got = {(n, dr): c for n, dr, c in pax()}
    assert got[("Aina", "returning")] == "Stesen LRT Rawang" and got[("Ahli 1", "returning")] == "Stesen LRT Rawang"
    assert row(out)["fixed_return"] == "Stesen LRT Rawang"
    # Ahli tak boleh melawan tempat tetap
    assert client.put("/transport/dates", headers=out, json={**base, "pickup": "tempat", "place": "Tempat lain"}).status_code == 200
    assert {(n, dr): c for n, dr, c in pax()}[("Aina", "going")] == "Dataran Cendekia"
    # Balik = sama dengan pergi
    r = client.put(pick, headers=admin, json={"pickup_mode": "kedua", "gather_place": "Dataran Cendekia", "return_same": True})
    assert r.status_code == 200 and row(out)["fixed_return"] == "Dataran Cendekia"
    assert client.put(pick, headers=admin, json={"pickup_mode": "kedua", "return_same": True}).status_code == 400  # tiada tempat pergi
    # Lepaskan semula kepada pilihan ahli
    assert client.put(pick, headers=admin, json={"pickup_mode": "kedua"}).status_code == 200
    assert row(out)["fixed_go"] == "" and row(out)["fixed_return"] == ""


def test_activity_fee_by_association_and_driver_still_paid(client):
    from datetime import timedelta
    from app.services import booking as svc
    admin = make_admin(client)
    inside, inside_id = make_user(client, 1)
    d = svc.today_my() + timedelta(days=4)
    body = {"name": "Mendaki", "go_date": d.isoformat(), "car_price": 40, "motor_price": 3}
    act = client.post("/admin/activities", headers=admin, json={**body, "fee_by_assoc": True}).json()
    assert act["fee_by_assoc"] is True and act["assoc_settled"] is False
    o = next(x for x in client.get("/transport/dates", headers=inside).json() if x["is_activity"])
    assert o["assoc_pays"] is True
    base = {"training_date": d.isoformat(), "session_id": o["session_id"], "going": True, "returning": True}
    assert client.put("/transport/dates", headers=inside, json=base).status_code == 200
    pays = client.get("/payments/me", headers=inside).json()
    assert not [p for p in pays if p["training_date"] == d.isoformat() and p["status"] != "void"]  # ahli tak bayar
    # Tandakan sudah diserah hanya untuk aktiviti yang ditanggung persatuan
    fund = f"/admin/activities/{act['id']}/funding"
    r = client.put(fund, headers=admin, json={"assoc_settled": True})
    assert r.status_code == 200 and r.json()["assoc_settled"] is True
    # Tukar kembali: ahli bayar (lalai) dan bayaran wujud semula, dibundar ke atas
    r = client.put(fund, headers=admin, json={"fee_by_assoc": False})
    assert r.status_code == 200 and r.json()["fee_by_assoc"] is False and r.json()["assoc_settled"] is False
    pays = [p for p in client.get("/payments/me", headers=inside).json() if p["training_date"] == d.isoformat()]
    assert pays and pays[0]["status"] != "void" and pays[0]["due"] == float(int(pays[0]["due"]))
    assert client.put(fund, headers=admin, json={"assoc_settled": True}).status_code == 400
    # Fungsi: bayaran prebet tidak bergantung pada penanggung (aktiviti percuma sebenar sahaja tiada bayaran prebet)
    from types import SimpleNamespace as NS
    assert svc.activity_is_free(NS(activity_fee=0, car_price=40, motor_price=3, fee_by_assoc=True)) is False


def test_activity_price_rounds_up_to_whole_ringgit():
    from types import SimpleNamespace as NS
    from app.services import booking as svc
    s = NS(car_price=41.0, motor_price=3.4, activity_fee=0)
    assert svc.activity_price(s, "car", NS(capacity=4)) == 11.0     # 41 / 4 = 10.25 -> 11
    assert svc.activity_price(NS(car_price=40.0, motor_price=3.0, activity_fee=0), "car", NS(capacity=4)) == 10.0
    assert svc.activity_price(s, "motorcycle") == 4.0               # 3.4 -> 4


def test_switch_to_association_turns_paid_into_credit(client):
    from datetime import timedelta
    from app import models
    from app.database import SessionLocal
    from app.services import booking as svc
    admin = make_admin(client)
    inside, inside_id = make_user(client, 1)
    d = svc.today_my() + timedelta(days=4)
    act = client.post("/admin/activities", headers=admin, json={"name": "Rakit", "go_date": d.isoformat(),
                                                                 "car_price": 40, "motor_price": 3}).json()
    o = next(x for x in client.get("/transport/dates", headers=inside).json() if x["is_activity"])
    assert client.put("/transport/dates", headers=inside, json={
        "training_date": d.isoformat(), "session_id": o["session_id"], "going": True, "returning": True}).status_code == 200
    with SessionLocal() as db:   # anggap ahli sudah bayar RM10
        pay = db.query(models.Payment).filter_by(user_id=inside_id, training_date=d).first()
        assert pay is not None
        pay.amount, pay.status = 10.0, models.PaymentStatus.paid
        db.commit()
    fund = f"/admin/activities/{act['id']}/funding"
    assert client.put(fund, headers=admin, json={"fee_by_assoc": True}).status_code == 200
    with SessionLocal() as db:
        pay = db.query(models.Payment).filter_by(user_id=inside_id, training_date=d).first()
        assert pay.status == models.PaymentStatus.void
        assert db.get(models.User, inside_id).credit_balance == 10.0   # duit ahli masih ada sebagai kredit
