import os
import math
import requests

from fastapi import FastAPI, APIRouter, HTTPException
from normalizers import normalize_peruzzo_machine


app = FastAPI()
router = APIRouter()


PERUZZO_USERNAME = os.getenv("PERUZZO_USERNAME")
PERUZZO_PASSWORD = os.getenv("PERUZZO_PASSWORD")


BASE_API = "https://sparepartsapi.theasp.cloud"

LOGIN_URL = f"{BASE_API}/api/tenantaccess/Login"
SEARCH_MY_ARTICLES_URL = f"{BASE_API}/api/peruzzo/searchmyarticles"
GET_BOARDS_URL = f"{BASE_API}/api/serialnumber/GetBoardsGrouped"
PARTS_SEARCH_URL = f"{BASE_API}/api/partapi/search"

PORTAL_ORIGIN = "https://peruzzo.theasp.cloud"
PORTAL_REFERER = "https://peruzzo.theasp.cloud/"


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

def create_peruzzo_headers():
    if not PERUZZO_USERNAME or not PERUZZO_PASSWORD:
        raise RuntimeError("Peruzzo credentials are not configured.")

    login_payload = {
        "UserName": PERUZZO_USERNAME,
        "Password": PERUZZO_PASSWORD,
        "Code": "peruzzo.theasp.cloud"
    }

    login_headers = {
        "Origin": PORTAL_ORIGIN,
        "Referer": PORTAL_REFERER,
        "Accept": "*/*",
        "culture": "en-US",
        "Content-Type": "application/json; charset=utf-8",
    }

    response = requests.post(
        LOGIN_URL,
        json=login_payload,
        headers=login_headers
    )

    response.raise_for_status()

    login_data = response.json()
    token = login_data.get("token")

    if not token:
        raise RuntimeError(
            "Peruzzo login succeeded but no token was returned."
        )

    return {
        "Authorization": f"Bearer {token}",
        "Origin": PORTAL_ORIGIN,
        "Referer": PORTAL_REFERER,
        "Accept": "*/*",
        "culture": "en-US",
        "Content-Type": "application/json; charset=utf-8",
    }


# --------------------------------------------------
# MACHINE SEARCH PAYLOAD
# --------------------------------------------------

def build_machine_search_payload(page):
    return {
        "Id": "00000000-0000-0000-0000-000000000000",
        "ItemOrder": 0,
        "ActionName": None,
        "Mode": 0,
        "Documents": None,
        "Tavole": None,
        "FullTextValue": None,
        "SerialNumber": None,
        "CategoryName": None,
        "BrandId": None,
        "BrandCode": None,
        "BrandName": None,
        "CatalogueId": None,
        "CatalogueCode": None,
        "CatalogueName": None,
        "ArticleId": None,
        "ArticleCode": None,
        "ArticleName": None,
        "Container": None,
        "PersistentType": None,
        "FilePath": None,
        "StorageFileName": None,
        "Active": True,
        "Page": page,
        "PageSize": 50,
        "Lang": None,
        "TypeCode": None,
        "UserId": None,
        "RecordId": None,
        "CatalogueEmpty": False,
        "Total": 0,
        "DynamiqFilter": "",
        "DynamiqOrder": ""
    }


# --------------------------------------------------
# GET ALL MACHINES
# --------------------------------------------------

def get_all_peruzzo_machines(headers):
    first_response = requests.post(
        SEARCH_MY_ARTICLES_URL,
        json=build_machine_search_payload(1),
        headers=headers
    )

    first_response.raise_for_status()

    first_data = first_response.json()

    total_machines = first_data.get("total", 0)
    page_size = first_data.get("pageSize", 50)

    all_machines = first_data.get("items", [])

    total_pages = math.ceil(total_machines / page_size)

    for page in range(2, total_pages + 1):
        response = requests.post(
            SEARCH_MY_ARTICLES_URL,
            json=build_machine_search_payload(page),
            headers=headers
        )

        response.raise_for_status()

        page_data = response.json()
        all_machines.extend(
            page_data.get("items", [])
        )

    return all_machines


# --------------------------------------------------
# FIND MACHINE
# --------------------------------------------------

def find_peruzzo_machine(machines, serial):
    for machine in machines:
        if str(
            machine.get("matricola", "")
        ).strip() == serial.strip():
            return machine

    return None


# --------------------------------------------------
# GET BOARDS
# --------------------------------------------------

def get_peruzzo_boards(headers, article_id):
    response = requests.get(
        GET_BOARDS_URL,
        params={"id": article_id},
        headers=headers
    )

    response.raise_for_status()

    return response.json()


# --------------------------------------------------
# GET PARTS FOR BOARD
# --------------------------------------------------

def get_parts_for_board(headers, board_id):
    payload = {
        "Id": board_id,
        "Page": 1,
        "Total": 0,
        "PageSize": 1000,
        "FullTextValue": None,
        "DynamiqFilter": "",
        "DynamiqOrder": ""
    }

    response = requests.post(
        PARTS_SEARCH_URL,
        json=payload,
        headers=headers
    )

    response.raise_for_status()

    data = response.json()

    return data.get("items", [])


# --------------------------------------------------
# FULL MACHINE RETRIEVAL
# --------------------------------------------------

def get_peruzzo_machine_data(serial):
    headers = create_peruzzo_headers()

    machines = get_all_peruzzo_machines(
        headers
    )

    machine = find_peruzzo_machine(
        machines,
        serial
    )

    if machine is None:
        return None

    article_id = machine.get("articleId")

    board_groups = get_peruzzo_boards(
        headers,
        article_id
    )

    parts_by_board = {}

    for group in board_groups:
        for board in group.get("boards", []):
            board_id = board.get("id")

            if board_id is None:
                continue

            parts_by_board[board_id] = (
                get_parts_for_board(
                    headers,
                    board_id
                )
            )

    return normalize_peruzzo_machine(
        serial=serial,
        machine=machine,
        board_groups=board_groups,
        parts_by_board=parts_by_board
    )


# --------------------------------------------------
# API ENDPOINT
# --------------------------------------------------

@router.get("/peruzzo/machine/{serial}")
def peruzzo_machine(serial: str):
    try:
        normalized = get_peruzzo_machine_data(
            serial
        )

        if normalized is None:
            raise HTTPException(
                status_code=404,
                detail=f"Peruzzo serial {serial} was not found."
            )

        return normalized

    except HTTPException:
        raise

    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail=f"Peruzzo API request failed: {error}"
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


app.include_router(router)
