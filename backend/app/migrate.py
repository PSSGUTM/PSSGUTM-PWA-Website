"""Migrasi ringan: tambah lajur baharu pada jadual sedia ada (dipanggil oleh seed dan main)."""
from .database import engine


def run_migrations():
    """create_all tidak tambah lajur pada jadual sedia ada; tambah lajur baharu secara selamat."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    ucols = {c["name"] for c in insp.get_columns("users")}
    if "payout_qr2_file" not in ucols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN payout_qr2_file VARCHAR(255)"))
    if "is_treasurer" not in ucols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_treasurer BOOLEAN DEFAULT FALSE"))
    for name, ddl in (("short_name", "VARCHAR(40) DEFAULT ''"), ("block", "VARCHAR(40) DEFAULT ''"),
                      ("pickup_point_id", "INTEGER"),
                      ("licence_file", "VARCHAR(255)"), ("licence_expiry", "DATE"), ("insurance_file", "VARCHAR(255)"),
                      ("passenger_ok", "BOOLEAN DEFAULT FALSE"), ("passenger_request", "BOOLEAN DEFAULT FALSE"),
                      ("theme", "VARCHAR(8) DEFAULT 'auto'"), ("gender_request", "VARCHAR(10) DEFAULT ''"),
                      ("prebet_request", "BOOLEAN DEFAULT FALSE")):
        if name not in ucols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
    pcols = {c["name"] for c in insp.get_columns("driver_payouts")}
    for name, ddl in (("batch", "VARCHAR(40) DEFAULT ''"), ("driver_id", "INTEGER"),
                      ("receipt_file", "VARCHAR(255)"), ("received", "BOOLEAN DEFAULT FALSE"), ("received_at", "TIMESTAMP")):
        if name not in pcols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE driver_payouts ADD COLUMN {name} {ddl}"))
    ecols = {c["name"] for c in insp.get_columns("training_events")}
    if "auto_off" not in ecols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE training_events ADD COLUMN auto_off BOOLEAN DEFAULT FALSE"))
    bcols = {c["name"] for c in insp.get_columns("bookings")}
    for name, ddl in (("ehailing", "BOOLEAN DEFAULT FALSE"), ("ehailing_note", "VARCHAR(300) DEFAULT ''"),
                      ("manual", "BOOLEAN DEFAULT FALSE"), ("seat", "VARCHAR(8)"),
                      ("cancelled_by_event", "BOOLEAN DEFAULT FALSE"),
                      ("pickup_place", "VARCHAR(120) DEFAULT ''")):
        if name not in bcols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE bookings ADD COLUMN {name} {ddl}"))
    cols = {c["name"] for c in insp.get_columns("training_sessions")}
    for name, ddl in (("one_off_date", "DATE"), ("trip_only", "VARCHAR(10)"), ("activity_group", "VARCHAR(32)"), ("activity_fee", "FLOAT"),
                      ("km", "FLOAT"), ("motor_max_km", "FLOAT"), ("car_price", "FLOAT"), ("motor_price", "FLOAT"),
                      ("pickup_mode", "VARCHAR(10)"), ("gather_place", "VARCHAR(120) DEFAULT ''"),
                      ("return_place", "VARCHAR(120) DEFAULT ''"),
                      ("return_same", "BOOLEAN DEFAULT FALSE"),
                      ("fee_by_assoc", "BOOLEAN DEFAULT FALSE"), ("assoc_settled", "BOOLEAN DEFAULT FALSE")):
        if name not in cols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE training_sessions ADD COLUMN {name} {ddl}"))
    vcols = {c["name"] for c in insp.get_columns("vehicles")}
    for name, ddl in (("brand", "VARCHAR(40) DEFAULT ''"), ("colour", "VARCHAR(30) DEFAULT ''")):
        if name not in vcols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE vehicles ADD COLUMN {name} {ddl}"))
    if "venues" in insp.get_table_names() and "college_code" not in {c["name"] for c in insp.get_columns("venues")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE venues ADD COLUMN college_code VARCHAR(10) DEFAULT ''"))
    if "prebet_availability" in insp.get_table_names() and "vehicle_id" not in {
            c["name"] for c in insp.get_columns("prebet_availability")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE prebet_availability ADD COLUMN vehicle_id INTEGER"))
    _drop_pickup_unique(insp)
    if "kind_name" not in vcols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE vehicles ADD COLUMN kind_name VARCHAR(60) DEFAULT ''"))
    if "category" not in vcols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE vehicles ADD COLUMN category VARCHAR(10) DEFAULT ''"))
    ncols = {c["name"] for c in insp.get_columns("notifications")}
    for name, ddl in (("severity", "VARCHAR(10) DEFAULT 'info'"), ("link", "VARCHAR(80) DEFAULT ''"), ("ref", "VARCHAR(80) DEFAULT ''")):
        if name not in ncols:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE notifications ADD COLUMN {name} {ddl}"))


def _drop_pickup_unique(insp):
    """Satu kolej kini boleh ada banyak checkpoint: buang kekangan unik (kolej, jantina) pada jadual lama."""
    from sqlalchemy import text
    if engine.dialect.name != "postgresql" or "pickup_points" not in insp.get_table_names():
        return
    for uc in insp.get_unique_constraints("pickup_points"):
        if set(uc.get("column_names") or []) == {"college_id", "gender"} and uc.get("name"):
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE pickup_points DROP CONSTRAINT "{uc["name"]}"'))


def enable_rls():
    """Supabase mendedahkan jadual 'public' melalui API REST awam. Hidupkan RLS (tanpa polisi) pada semua jadual
    supaya akses anon ditolak. App ini bersambung terus ke Postgres sebagai pemilik jadual, jadi tidak terjejas."""
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "DO $$ DECLARE r record; BEGIN "
                "FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP "
                "EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename); "
                "END LOOP; END $$;"))
    except Exception as e:  # jangan gagalkan permulaan app
        print("RLS tidak dapat dihidupkan:", e)
