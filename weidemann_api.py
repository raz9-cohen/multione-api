import os
import re
import requests
from urllib.parse import urlparse

from fastapi import FastAPI, APIRouter, HTTPException
from playwright.sync_api import sync_playwright

from normalizers import normalize_weidemann_machine


app = FastAPI()
router = APIRouter()

BASE_URL = "https://shop.weidemann-online.com"
LOGIN_URL = f"{BASE_URL}/estore/pgk/de/login"
OAUTH_URL = f"{BASE_URL}/estore/pgk/de/oauth"


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

def _submit_containing_form(field):
    field.locator("xpath=ancestor::form[1]").locator(
        'input[type="submit"]:visible, button[type="submit"]:visible'
    ).first.click()


def _visible_login_problem(page):
    return page.evaluate(
        """() => {
            const visible = (el) => {
                const box = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return box.width > 0
                    && box.height > 0
                    && style.visibility !== "hidden"
                    && style.display !== "none";
            };

            const errors = [...document.querySelectorAll(
                ".gigya-error-msg, .gigya-form-error-msg"
            )].filter(visible).map((el) => (
                el.textContent.replace(/\\s+/g, " ").trim()
            )).filter(Boolean);

            if (errors.length) {
                return errors.join(" ");
            }

            const captcha = document.querySelector(
                '[data-gigya-name="saptcha"][data-is-active="true"]'
            );
            if (captcha && visible(captcha)) {
                return "Weidemann login is showing a captcha.";
            }

            const verification = document.querySelector(
                ".gigya-composite-control-tfa-verification-widget, .gigya-tfa"
            );
            if (verification && visible(verification)) {
                return "Weidemann login is asking for a verification code.";
            }

            return "";
        }"""
    )


def _shop_session_ready(url):
    parsed = urlparse(url)
    if parsed.hostname != "shop.weidemann-online.com":
        return False
    if "gigyaraas/login" in parsed.path:
        return False
    if "sso.login" in (parsed.query or ""):
        return False
    return True


def _wait_until_shop(context, page):
    shop_page = None

    for _ in range(90):
        for open_page in context.pages:
            if _shop_session_ready(open_page.url):
                shop_page = open_page
                break

        if shop_page is not None:
            break

        try:
            problem = _visible_login_problem(page)
        except Exception:
            problem = ""

        if problem:
            raise RuntimeError(problem)

        page.wait_for_timeout(1000)

    if shop_page is None:
        try:
            problem = _visible_login_problem(page)
        except Exception:
            problem = ""

        if problem:
            raise RuntimeError(problem)

        raise RuntimeError(
            "Weidemann login did not return to the shop. "
            f"Current URL: {page.url}"
        )

    try:
        shop_page.wait_for_load_state(
            "domcontentloaded",
            timeout=15000,
        )
    except Exception:
        pass

    return shop_page


def login_with_playwright(username, password):
    playwright = sync_playwright().start()
    browser = None

    try:
        print("1. Opening Weidemann login...", flush=True)

        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto(
            LOGIN_URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        print("2. Waiting for Wacker login page...", flush=True)

        page.wait_for_url(
            "**mylogin.wackerneusongroup.com/**",
            timeout=30000,
        )

        page.wait_for_timeout(3000)

        print("3. Wacker login page loaded", flush=True)

        username_input = page.locator(
            'input[data-gigya-name="loginID"]:visible'
        ).first

        username_input.wait_for(
            state="visible",
            timeout=15000,
        )

        username_input.fill(username)

        print("4. Username entered", flush=True)

        _submit_containing_form(username_input)

        print("5. Username step submitted", flush=True)

        password_input = page.locator(
            'input[data-gigya-name="password"]:visible'
        )

        try:
            password_input.first.wait_for(
                state="visible",
                timeout=8000,
            )
        except Exception:
            password_method = page.locator(
                '[data-auth-method="password"]:visible'
            )
            if password_method.count() == 0:
                raise
            password_method.first.click()
            password_input.first.wait_for(
                state="visible",
                timeout=15000,
            )

        password_input.first.fill(password)

        print("6. Password entered", flush=True)

        print("7. Submitting password...", flush=True)

        _submit_containing_form(password_input.first)

        print("URL after login:", page.url, flush=True)

        shop_page = _wait_until_shop(context, page)

        print("8. Returned to Weidemann", flush=True)

        shop_page.wait_for_timeout(3000)

        print("9. Final browser URL:", shop_page.url, flush=True)

        return playwright, browser, context

    except Exception:
        if browser is not None:
            browser.close()
        playwright.stop()
        raise


# --------------------------------------------------
# BROWSER -> REQUESTS SESSION
# --------------------------------------------------

def requests_session_from_browser(context):
    session = requests.Session()

    for cookie in context.cookies():
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path", "/"),
        )

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    })

    return session


# --------------------------------------------------
# OAUTH
# --------------------------------------------------

def get_oauth_token(session):
    print("10. Requesting /oauth...", flush=True)

    response = session.get(
        OAUTH_URL,
        timeout=30,
    )

    print(
        "11. /oauth HTTP status:",
        response.status_code,
        flush=True,
    )

    response.raise_for_status()

    data = response.json()
    access_token = data.get("access_token")

    print(
        "12. access_token received:",
        bool(access_token),
        flush=True,
    )

    if not access_token:
        raise RuntimeError(
            "/oauth succeeded but no access_token was returned"
        )

    return data


# --------------------------------------------------
# SERIAL -> MATERIAL
# --------------------------------------------------

def get_material_from_serial(session, serial_number):
    url = (
        f"{BASE_URL}"
        f"/estore/pgk/de/dashboard/serial/details/{serial_number}"
    )

    response = session.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    match = re.search(
        r'Material:\s*</td>\s*<td class="value">\s*(\d+)',
        response.text,
    )

    if not match:
        raise RuntimeError(
            f"Could not find Material for serial {serial_number}"
        )

    return match.group(1)


# --------------------------------------------------
# MATERIAL -> SPAREPART LISTS
# --------------------------------------------------

def get_sparepart_lists(session, access_token, material):
    url = (
        f"{BASE_URL}"
        f"/ws/v2/pgk/machine/sparepartlists/{material}"
        "?mode=unrestricted&lang=en&lang=en"
    )

    response = session.get(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        timeout=30,
    )

    print(
        "Sparepart lists HTTP status:",
        response.status_code,
        flush=True,
    )

    response.raise_for_status()

    return response.json()


# --------------------------------------------------
# CATALOG -> BOM
# --------------------------------------------------

def get_bom_tree(
    session,
    access_token,
    sparepart_list_product_code,
):
    url = (
        f"{BASE_URL}"
        f"/ws/v2/pgk/machine/bomtree/"
        f"{sparepart_list_product_code}/"
        "?mode=unrestricted&lang=en&lang=en"
    )

    response = session.get(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        timeout=30,
    )

    print(
        "BOM tree HTTP status:",
        response.status_code,
        flush=True,
    )

    response.raise_for_status()

    return response.json()


# --------------------------------------------------
# DRAWING ASSETS - LAZY RESOLUTION
# --------------------------------------------------

def get_drawing_assets(session, access_token, drawing_file):
    metadata_url = (
        f"{BASE_URL}"
        f"/ws/v2/pgk/machine/diagram/file/{drawing_file}"
        "?lang=en&lang=en"
    )

    response = session.get(
        metadata_url,
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    diagram_image = data.get("diagramImage") or {}
    diagram_coordinates = data.get("diagramCoordinates") or {}

    image_id = diagram_image.get("id")
    image_filename = diagram_image.get("filename")

    coordinates_id = diagram_coordinates.get("id")
    coordinates_filename = diagram_coordinates.get("filename")

    image_url = None
    coordinates_url = None

    if image_id and image_filename:
        image_url = (
            f"{BASE_URL}"
            f"/ws/v2/pgk/media/"
            f"{image_id}/{image_filename}"
            "?lang=en&lang=en"
        )

    if coordinates_id and coordinates_filename:
        coordinates_url = (
            f"{BASE_URL}"
            f"/ws/v2/pgk/media/"
            f"{coordinates_id}/{coordinates_filename}"
            "?lang=en&lang=en"
        )

    return {
        "metadata_url": metadata_url,
        "diagram_image": {
            "id": image_id,
            "filename": image_filename,
            "url": image_url,
        },
        "diagram_coordinates": {
            "id": coordinates_id,
            "filename": coordinates_filename,
            "url": coordinates_url,
        },
    }


def get_drawing_assets_from_metadata_url(
    session,
    access_token,
    metadata_url,
):
    marker = "/machine/diagram/file/"

    if marker not in metadata_url:
        raise ValueError(
            "Not a Weidemann drawing metadata URL"
        )

    drawing_file = (
        metadata_url
        .split(marker, 1)[1]
        .split("?", 1)[0]
    )

    return get_drawing_assets(
        session,
        access_token,
        drawing_file,
    )


# --------------------------------------------------
# FULL MACHINE RETRIEVAL
# --------------------------------------------------

def get_weidemann_machine_data(serial, username=None, password=None):
    if username is None:
        username = os.getenv("WEIDEMANN_USERNAME")
    if password is None:
        password = os.getenv("WEIDEMANN_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "Weidemann credentials are not configured."
        )

    playwright = None
    browser = None
    session = None

    try:
        print(
            "API: starting Weidemann retrieval",
            flush=True,
        )

        playwright, browser, context = login_with_playwright(
            username,
            password,
        )

        session = requests_session_from_browser(context)

        oauth_data = get_oauth_token(session)
        access_token = oauth_data["access_token"]

        print(
            "API: requesting serial material",
            flush=True,
        )

        material = get_material_from_serial(
            session,
            serial,
        )

        print(
            "API: requesting spare-part lists",
            flush=True,
        )

        sparepart_data = get_sparepart_lists(
            session,
            access_token,
            material,
        )

        sparepart_lists = sparepart_data.get(
            "sparepartLists",
            [],
        )

        if not sparepart_lists:
            raise RuntimeError(
                "No sparepart lists returned"
            )

        if len(sparepart_lists) > 1:
            raise RuntimeError(
                "Multiple sparepart lists returned. "
                "Selection logic has not been established yet."
            )

        product_code = sparepart_lists[0].get(
            "productCode"
        )

        if not product_code:
            raise RuntimeError(
                "Sparepart list has no productCode"
            )

        print(
            "API: requesting BOM tree",
            flush=True,
        )

        bom_tree = get_bom_tree(
            session,
            access_token,
            product_code,
        )

        print(
            "API: normalizing machine",
            flush=True,
        )

        result = normalize_weidemann_machine(
            serial,
            sparepart_data,
            bom_tree,
        )

        print(
            "API: retrieval completed",
            flush=True,
        )

        return result

    finally:
        if session is not None:
            session.close()

        if browser is not None:
            browser.close()

        if playwright is not None:
            playwright.stop()


# --------------------------------------------------
# API ENDPOINT
# --------------------------------------------------

@router.get("/weidemann/machine/{serial}")
def weidemann_machine(serial: str):
    serial = serial.strip()

    if not serial:
        raise HTTPException(
            status_code=400,
            detail="Serial cannot be empty",
        )

    try:
        return get_weidemann_machine_data(serial)

    except requests.RequestException as error:
        print(
            f"API: upstream request failed: {type(error).__name__}",
            flush=True,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Weidemann upstream request failed: "
                f"{type(error).__name__}"
            ),
        )

    except Exception as error:
        print(
            f"API: failed: {type(error).__name__}: {error}",
            flush=True,
        )

        raise HTTPException(
            status_code=500,
            detail=f"{type(error).__name__}: {error}",
        )


app.include_router(router)