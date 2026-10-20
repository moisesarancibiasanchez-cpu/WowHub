"""Steps 2-9 of atomic build, all using extract_file properly."""
import subprocess
import sys


def get_from_git(ref_path):
    r = subprocess.run(["git", "show", ref_path], capture_output=True)
    return r.stdout


def extract(src, dest):
    c = get_from_git(src)
    if b"\x00" in c:
        print(f"FAIL {src} has nulls")
        sys.exit(1)
    with open(dest, "wb") as fp:
        fp.write(c)
    print(f"  ok {dest}: {len(c)} bytes")


def commit(msg):
    subprocess.run(["git", "add", "-A"], capture_output=True)
    r = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
    print(r.stdout.strip()[-200:] if r.stdout else "(empty)")
    if r.returncode != 0:
        print("STDERR:", r.stderr[:400])
        sys.exit(1)


# Step 2: Migration
print("=== STEP 2 ===")
extract("main:alembic/versions/2026_10_16_hu50_65_produccion.py",
        "alembic/versions/2026_10_16_hu50_65_produccion.py")
commit("""feat(hu50-65/migration): migracion aditiva V134.2-Produccion-v2

Commit 2/10. 6 tablas + 15 columnas + 5 indices.
down_revision = 2026_10_07_0002.""")

# Step 3: Models
print("=== STEP 3 ===")
for f in ["production.py", "insumo_movement.py", "payment_record.py",
          "notification.py", "customer.py", "order.py", "product.py",
          "quote.py", "__init__.py"]:
    extract(f"main:app/models/{f}", f"app/models/{f}")
commit("""feat(hu50-65/models): 6 modelos nuevos + extensiones a 4 tablas

Commit 3/10. Capa de datos completa de HU_50-65.
Los 6 modelos usan String(20/40) en lugar de Enum types (alinea con
la migracion Alembic -> sin CREATE TYPE problem en create_all).""")

# Step 4: Services
print("=== STEP 4 ===")
for f in ["production_service.py", "payment_record_service.py",
          "notification_service_v2.py"]:
    extract(f"main:app/services/{f}", f"app/services/{f}")
commit("""feat(hu50-65/services): 3 servicios HU_50-65

Commit 4/10. ProductionService, PaymentRecordService, NotificationService.""")

# Step 5: Schemas
print("=== STEP 5 ===")
for f in ["inline.py", "payment_record.py", "notification.py"]:
    extract(f"main:app/schemas/{f}", f"app/schemas/{f}")
commit("""feat(hu50-65/schemas): 3 schemas Pydantic v2 HU_50-65

Commit 5/10. inline.py (HU_50, 51), payment_record.py (HU_56, 57),
notification.py (HU_62, 63).""")

# Step 6: Independent routers
print("=== STEP 6 ===")
for f in ["production.py", "payment_records.py"]:
    extract(f"main:app/api/v1/{f}", f"app/api/v1/{f}")
commit("""feat(hu50-65/api): 2 routers independientes (production + payment_records)

Commit 6/10. Routers HU_52, 53, 65, 56, 57.
NO conectados a main.py todavia.""")

# Step 7: Inline + subrouters
print("=== STEP 7 ===")
for f in ["customers.py", "products.py", "notifications.py", "__init__.py"]:
    extract(f"main:app/api/v1/{f}", f"app/api/v1/{f}")
commit("""feat(hu50-65/api): routers extendidos (inline + notifications subrouters)

Commit 7/10. HU_50 inline customer, HU_51 inline product, HU_62/63
templates/log/send subrouters en notifications.py.""")

# Step 8: Wiring
print("=== STEP 8 ===")
for f in ["app/main.py", "app/f0_baseline/router.py"]:
    extract(f"main:{f}", f)
commit("""feat(hu50-65/wiring): main.py incluye routers + f0_baseline allowlist

Commit 8/10. Punto de integracion. Sin esto, los routers existen pero
no aparecen en OpenAPI.""")

# Step 9: Tests
print("=== STEP 9 ===")
for f in ["tests/test_hu50_65_produccion.py", "tests/conftest.py"]:
    extract(f"main:{f}", f)
commit("""test(hu50-65): 34 tests + fixtures conftest

Commit 9/10. tests/test_hu50_65_produccion.py + tests/conftest.py.""")

print("=== DONE ===")
r = subprocess.run(["git", "log", "--oneline", "-11"], capture_output=True, text=True)
print(r.stdout)
