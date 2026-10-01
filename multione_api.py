import requests
from bs4 import BeautifulSoup
import os
from fastapi import FastAPI
import math
from normalizers import normalize_multione_machine

app = FastAPI()


MULTIONE_USERNAME = os.getenv("MULTIONE_USERNAME")
MULTIONE_PASSWORD = os.getenv("MULTIONE_PASSWORD")

BASE_URL = "https://b2b.multione-csf.com"
LOGIN_URL = f"{BASE_URL}/account/login"
SERIALS_URL = f"{BASE_URL}/api/serial/filtered/"
SPAREPARTS_BASE_URL = f"{BASE_URL}/api/spareparts/drafts"


def get_multione_drawings(session, machine, serial):
    catalog_product_id = machine.get("s_catalog_p_id")

    spareparts_url = (
        f"{SPAREPARTS_BASE_URL}/"
        f"{catalog_product_id}/serial/{serial}"
    )

    response = session.get(spareparts_url)
    response.raise_for_status()

    data = response.json()

    if not data.get("success"):
        raise RuntimeError(
            f"MultiOne returned success=False: {data.get('errors')}"
        )

    return data.get("data", [])

def find_multione_machine(serials, serial):
    for item in serials:
        if str(item.get("s_no", "")).strip() == serial.strip():
            return item

    return None

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


def get_all_multione_serials(session):
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

    first_response.raise_for_status()

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

        response.raise_for_status()

        page_data = response.json()
        all_serials.extend(page_data.get("data", []))

    return all_serials


def create_multione_session():
    session = requests.Session()

    login_page = session.get(LOGIN_URL)
    login_page.raise_for_status()

    soup = BeautifulSoup(login_page.text, "html.parser")

    password_input = soup.find("input", {"type": "password"})

    if not password_input:
        raise RuntimeError("Password field not found.")

    password_field_name = password_input.get("name")

    login_payload = {
        "username": MULTIONE_USERNAME,
        password_field_name: MULTIONE_PASSWORD,
        "returnUrl": "",
        "commit": "Login",
    }

    login_response = session.post(
        LOGIN_URL,
        data=login_payload,
        allow_redirects=True,
    )

    if "/ui/direct-dealer" not in login_response.url:
        raise RuntimeError("MultiOne login failed.")

    return session

@app.get("/ping")
def ping():
    return {"status": "ok"}

@app.get("/multione/login-test")
def multione_login_test():
    create_multione_session()

    return {
        "status": "ok",
        "message": "MultiOne login succeeded"
    }


@app.get("/multione/serials-test")
def multione_serials_test():
    session = create_multione_session()
    serials = get_all_multione_serials(session)

    return {
        "count": len(serials)
    }

@app.get("/multione/machine/{serial}")
def get_multione_machine(serial: str):
    session = create_multione_session()
    serials = get_all_multione_serials(session)

    machine = find_multione_machine(
        serials,
        serial
    )

    if machine is None:
        return {
            "found": False,
            "serial": serial
        }

    drawings = get_multione_drawings(
        session,
        machine,
        serial
    )

    normalized = normalize_multione_machine(
        serial=serial,
        machine=machine,
        drawings=drawings
    )

    return normalized