import json
import math
import requests
from bs4 import BeautifulSoup
from getpass import getpass
from normalizers import normalize_multione_machine

BASE_URL = "https://b2b.multione-csf.com"

LOGIN_URL = f"{BASE_URL}/account/login"
SERIALS_URL = f"{BASE_URL}/api/serial/filtered/"
SPAREPARTS_BASE_URL = f"{BASE_URL}/api/spareparts/drafts"


# --------------------------------------------------
# 1. LOGIN
# --------------------------------------------------

session = requests.Session()

login_page = session.get(LOGIN_URL)

print("Login page status:", login_page.status_code)

if not login_page.ok:
    print("Could not open MultiOne login page.")
    raise SystemExit

soup = BeautifulSoup(login_page.text, "html.parser")

password_input = soup.find("input", {"type": "password"})

if not password_input:
    print("Password field not found.")
    raise SystemExit

password_field_name = password_input.get("name")

username = input("MultiOne username: ")
password = getpass("MultiOne password: ")

login_payload = {
    "username": username,
    password_field_name: password,
    "returnUrl": "",
    "commit": "Login",
}

login_response = session.post(
    LOGIN_URL,
    data=login_payload,
    allow_redirects=True
)

print("Login status:", login_response.status_code)
print("Final URL:", login_response.url)

if "/ui/direct-dealer" not in login_response.url:
    print("Login failed.")
    raise SystemExit

print("Login succeeded.")


# --------------------------------------------------
# 2. MY SERIALS PAYLOAD
# --------------------------------------------------

def build_serials_payload():
    return {
        "$id": "1",
        "p_name": "",
        "p_warehouseCode": "",
        "pd_name": "",
        "s_no": "",
        "soh_purchase_document": "",
        "soh_sell_document": "",
        "soh_tag": ""
    }


# --------------------------------------------------
# 3. GET ALL MY SERIALS
# --------------------------------------------------

print("\nLoading My Serials...")

page_size = 50

first_response = session.post(
    SERIALS_URL,
    params={
        "$top": page_size,
        "$skip": 0,
        "$count": "true"
    },
    json=build_serials_payload()
)

print("My Serials status:", first_response.status_code)

if not first_response.ok:
    print("Failed to load My Serials.")
    print(first_response.text[:500])
    raise SystemExit

first_data = first_response.json()

total_serials = first_data.get("Count", 0)
all_serials = first_data.get("data", [])

total_pages = math.ceil(total_serials / page_size)

for page in range(1, total_pages):
    skip = page * page_size

    response = session.post(
        SERIALS_URL,
        params={
            "$top": page_size,
            "$skip": skip,
            "$count": "true"
        },
        json=build_serials_payload()
    )

    if not response.ok:
        print(f"Failed loading serials at skip={skip}")
        print("Status:", response.status_code)
        raise SystemExit

    page_data = response.json()
    all_serials.extend(page_data.get("data", []))

print("Total serials expected:", total_serials)
print("Total serials loaded:", len(all_serials))


# --------------------------------------------------
# 4. FIND MACHINE BY SERIAL
# --------------------------------------------------

serial = input("\nEnter MultiOne serial number: ").strip()

machine = None

for item in all_serials:
    if str(item.get("s_no", "")).strip() == serial:
        machine = item
        break

if machine is None:
    print(f"Serial {serial} was not found in My Serials.")
    raise SystemExit

print("\n--- MACHINE FOUND ---")
print("Serial:", machine.get("s_no"))
print("Serial ID:", machine.get("s_id"))
print("Catalog product ID:", machine.get("s_catalog_p_id"))
print("Model number:", machine.get("p_code"))
print("Model name:", machine.get("pd_name"))
print("Owner:", machine.get("p_name"))


# --------------------------------------------------
# 5. GET SERIAL-SPECIFIC DRAWINGS + PARTS
# --------------------------------------------------

catalog_product_id = machine.get("s_catalog_p_id")

spareparts_url = (
    f"{SPAREPARTS_BASE_URL}/"
    f"{catalog_product_id}/serial/{serial}"
)

spareparts_response = session.get(spareparts_url)

print("\nSpareparts status:", spareparts_response.status_code)

if not spareparts_response.ok:
    print("Failed to load spareparts.")
    print(spareparts_response.text[:500])
    raise SystemExit

spareparts_data = spareparts_response.json()

if not spareparts_data.get("success"):
    print("MultiOne returned success=False.")
    print(spareparts_data.get("errors"))
    raise SystemExit

drawings = spareparts_data.get("data", [])

print("Number of drawings:", len(drawings))


# --------------------------------------------------
# 6. NORMALIZE
# --------------------------------------------------

normalized = normalize_multione_machine(
    serial=serial,
    machine=machine,
    drawings=drawings
)


# --------------------------------------------------
# 7. DATA QUALITY CHECK
# --------------------------------------------------

drawings_without_image = 0
components_without_parts = 0
multi_part_references = 0
preferred_parts = 0
alternative_parts = 0
disabled_parts = 0

for drawing in drawings:

    if not drawing.get("media", []):
        drawings_without_image += 1

    for component in drawing.get("components", []):

        parts = component.get("parts", [])

        if not parts:
            components_without_parts += 1

        if len(parts) > 1:
            multi_part_references += 1

        for part in parts:

            if part.get("dcp_preferred"):
                preferred_parts += 1

            if part.get("dcp_alternative"):
                alternative_parts += 1

            if part.get("dcp_disabled"):
                disabled_parts += 1


# --------------------------------------------------
# 8. SAVE JSON
# --------------------------------------------------

filename = f"multione_{serial}.json"

with open(filename, "w", encoding="utf-8") as file:
    json.dump(
        normalized,
        file,
        indent=2,
        ensure_ascii=False
    )


# --------------------------------------------------
# 9. SUMMARY
# --------------------------------------------------

total_parts = sum(
    len(assembly["parts"])
    for assembly in normalized["assemblies"]
)

print("\n--- DATA QUALITY CHECK ---")
print("Total drawings:", len(drawings))
print("Drawings without image:", drawings_without_image)
print("Components without parts:", components_without_parts)
print("References with multiple parts:", multi_part_references)
print("Preferred parts:", preferred_parts)
print("Alternative parts:", alternative_parts)
print("Disabled parts:", disabled_parts)

print("\n--- DONE ---")
print("Serial:", serial)
print("Model:", normalized["model"]["model_number"])
print("Model name:", normalized["model"]["model_name"])
print("Assemblies:", len(normalized["assemblies"]))
print("Total assembly-part rows:", total_parts)
print("Saved normalized data to:", filename)