#
# partcad-svc-commerce-digikey, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""Tests of the DigiKey plugin, with DigiKey answered from a table.

The answers have the shape the Product Information API v4 answers with - its
categories, a keyword search, a product's details and its media - with values
made up. Nothing here touches the network.
"""

import base64
import hashlib
import json
import os
import runpy

import distributor as d
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
plugin = runpy.run_path(os.path.join(_HERE, "digikey.py"), run_name="digikey_under_test")
DigiKey = plugin["DigiKey"]

API = "https://api.digikey.com"
TOKEN = API + "/v1/oauth2/token"
MODEL = "https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/1234/ATMEGA328P-PU.step"


def _variation(sku, package, moq, pricing, stock, standard=25):
    return {
        "DigiKeyProductNumber": sku,
        "PackageType": {"Id": 1, "Name": package},
        "StandardPricing": [{"BreakQuantity": q, "UnitPrice": p, "TotalPrice": q * p} for q, p in pricing],
        "MyPricing": [],
        "MarketPlace": False,
        "QuantityAvailableforPackageType": stock,
        "MinimumOrderQuantity": moq,
        "StandardPackage": standard,
    }


ATMEGA = {
    "Description": {
        "ProductDescription": "IC MCU 8BIT 32KB FLASH 28DIP",
        "DetailedDescription": "AVR ATmega Microcontroller IC 8-Bit 20MHz 32KB (16K x 16) FLASH 28-PDIP",
    },
    "Manufacturer": {"Id": 150, "Name": "Microchip Technology"},
    "ManufacturerProductNumber": "ATMEGA328P-PU",
    "UnitPrice": 2.89,
    "ProductUrl": "https://www.digikey.com/en/products/detail/microchip-technology/ATMEGA328P-PU/1914589",
    "DatasheetUrl": "https://ww1.microchip.com/downloads/en/DeviceDoc/ATmega328P.pdf",
    "PhotoUrl": "https://mm.digikey.com/photo.jpg",
    "ProductVariations": [_variation("ATMEGA328P-PU-ND", "Tube", 1, [(1, 2.89), (25, 2.41), (100, 2.19)], 18000)],
    "QuantityAvailable": 18000,
    "ProductStatus": {"Id": 0, "Status": "Active"},
    "Discontinued": False,
    "EndOfLife": False,
    "Parameters": [
        {"ParameterId": 1, "ParameterText": "Core Processor", "ValueText": "AVR"},
        {"ParameterId": 2, "ParameterText": "Program Memory Size", "ValueText": "32KB (16K x 16)"},
        {"ParameterId": 3, "ParameterText": "Package / Case", "ValueText": '28-DIP (0.300", 7.62mm)'},
    ],
    "Category": {
        "CategoryId": 32,
        "Name": "Integrated Circuits (ICs)",
        "ChildCategories": [{"CategoryId": 685, "Name": "Embedded - Microcontrollers", "ChildCategories": []}],
    },
}

RESISTOR = {
    "Description": {"ProductDescription": "RES 10K OHM 1% 1/10W 0603", "DetailedDescription": "10 kOhms 1% 0.1W"},
    "Manufacturer": {"Name": "YAGEO"},
    "ManufacturerProductNumber": "RC0603FR-0710KL",
    "ProductUrl": "https://www.digikey.com/en/products/detail/yageo/RC0603FR-0710KL/727212",
    "ProductVariations": [
        _variation("311-10.0KHRCT-ND", "Cut Tape (CT)", 1, [(1, 0.1), (10, 0.019), (100, 0.0085)], 4000000),
        _variation("311-10.0KHRTR-ND", "Tape & Reel (TR)", 5000, [(5000, 0.0024)], 3900000, standard=5000),
    ],
    "ProductStatus": {"Status": "Active"},
    "Category": {"CategoryId": 2, "Name": "Resistors", "ChildCategories": [{"CategoryId": 52, "Name": "Chip"}]},
}

TABLE = {
    TOKEN: (200, {"access_token": "token-1", "expires_in": 599, "token_type": "Bearer"}),
    API
    + "/products/v4/search/categories": (
        200,
        {
            "ProductCount": 15000000,
            "Categories": [
                {
                    "CategoryId": 32,
                    "ParentId": 0,
                    "Name": "Integrated Circuits (ICs)",
                    "ProductCount": 650000,
                    "Children": [
                        {"CategoryId": 685, "ParentId": 32, "Name": "Embedded - Microcontrollers", "ProductCount": 9000}
                    ],
                },
                {"CategoryId": 2, "ParentId": 0, "Name": "Resistors", "ProductCount": 1200000, "Children": []},
            ],
        },
    ),
    # A search; and the same search of what has a 3D model, which the resistor has not.
    API
    + "/products/v4/search/keyword": lambda body: (
        200,
        {"Products": [ATMEGA] if "Has3DModel" in str(body) else [ATMEGA, RESISTOR], "ProductsCount": 2},
    ),
    # Every listing of a manufacturer's part, with live prices.
    API
    + "/products/v4/search/ATMEGA328P-PU/pricing?limit=10&excludeMarketplace=true": (
        200,
        {"ProductPricings": [dict(ATMEGA, Categories=[{"CategoryId": 685}])], "ProductsCount": 1},
    ),
    API
    + "/products/v4/search/RC0603FR-0710KL/pricing?limit=10&excludeMarketplace=true": (
        200,
        {
            "ProductPricings": [
                {
                    "ManufacturerProductNumber": "RC0603FR-0710KL",
                    "Manufacturer": {"Id": 13, "Name": "YAGEO"},
                    "Description": {"ProductDescription": "RES 10K OHM 1% 1/10W 0603"},
                    "QuantityAvailable": 7900000,
                    "IsDiscontinued": False,
                    "IsObsolete": False,
                    "Categories": [{"CategoryId": 52, "Level": 2, "Name": "Chip Resistor"}],
                    "ProductVariations": RESISTOR["ProductVariations"],
                }
            ],
            "ProductsCount": 1,
        },
    ),
    API + "/products/v4/search/ATMEGA328P-PU-ND/productdetails": (200, {"Product": ATMEGA}),
    API + "/products/v4/search/311-10.0KHRCT-ND/productdetails": (200, {"Product": RESISTOR}),
    API + "/products/v4/search/311-10.0KHRTR-ND/productdetails": (200, {"Product": RESISTOR}),
    API
    + "/products/v4/search/ATMEGA328P-PU-ND/media": (
        200,
        {
            "MediaLinks": [
                {"MediaType": "Datasheets", "Title": "ATmega328P", "Url": "https://ww1.microchip.com/x.pdf"},
                {"MediaType": "Product Photos", "Title": "28-DIP", "Url": "https://mm.digikey.com/photo.jpg"},
                {"MediaType": "3D Models", "Title": "ATMEGA328P-PU.step", "Url": MODEL},
                {"MediaType": "EDA / CAD Models", "Title": "by SnapEDA", "Url": "https://www.snapeda.com/parts/x"},
            ]
        },
    ),
    API + "/products/v4/search/311-10.0KHRCT-ND/media": (200, {"MediaLinks": []}),
    MODEL: (200, b"ISO-10303-21;\nEND-ISO-10303-21;\n"),
}


class Wire:
    def __init__(self, table):
        self.table = dict(table)
        self.asked = []

    def __call__(self, url, headers=None, data=None, method=None, timeout=60):
        self.asked.append((url, dict(headers or {}), data))
        if url not in self.table:
            return d.pm.Response(404, {}, b'{"detail": "not found"}', url)
        answer = self.table[url]
        status, body = answer(data) if callable(answer) else answer
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        return d.pm.Response(status, {}, body, url)


@pytest.fixture
def digikey(tmp_path, monkeypatch):
    monkeypatch.setenv("PARTCAD_DIGIKEY_CACHE", str(tmp_path))
    monkeypatch.delenv("DIGIKEY_CLIENT_ID", raising=False)
    monkeypatch.delenv("DIGIKEY_CLIENT_SECRET", raising=False)

    def make(user=None, **parameters):
        parameters.setdefault("client_id", "client-1")
        parameters.setdefault("client_secret", "secret-1")
        made = DigiKey({"parameters": parameters, "userInfo": user or {"country": "US", "currency": "USD"}})
        made.http.request = Wire(TABLE)
        return made

    return make


def _asked(made, url):
    return [(headers, body) for asked, headers, body in made.http.request.asked if asked == url]


def test_every_request_carries_the_token_and_the_users_locale(digikey):
    made = digikey(user={"country": "DE", "language": "de", "currency": "EUR"})
    made.get("deps")
    (headers, _), *_ = _asked(made, API + "/products/v4/search/categories")
    assert headers["Authorization"] == "Bearer token-1"
    assert headers["X-DIGIKEY-Client-Id"] == "client-1"
    assert (headers["X-DIGIKEY-Locale-Site"], headers["X-DIGIKEY-Locale-Language"]) == ("DE", "de")
    assert headers["X-DIGIKEY-Locale-Currency"] == "EUR"


def test_a_country_or_currency_digikey_has_not_falls_back_to_its_own(digikey):
    assert digikey(user={"country": "ZZ", "currency": "XYZ"}).locale() == ("US", "en", "USD")
    assert digikey(user={"country": "GB", "currency": "JPY"}).locale() == ("GB", "en", "GBP")


def test_the_categories_are_the_packages(digikey):
    made = digikey()
    assert made.get("deps") == ["integrated-circuits-ics", "resistors"]
    assert made.get("integrated-circuits-ics/deps") == ["embedded-microcontrollers"]
    meta = made.get("integrated-circuits-ics/embedded-microcontrollers/meta")
    assert "Embedded - Microcontrollers" in meta["desc"]
    assert meta["url"].endswith("/685")
    assert meta["suppliers"] == {"//pub/svc/commerce/digikey:digikey": {}}


def test_a_search_in_a_category_filters_by_it(digikey):
    made = digikey()
    hits = made.get("integrated-circuits-ics/embedded-microcontrollers/search/part?q=atmega&limit=5")
    (_, body), *_ = _asked(made, API + "/products/v4/search/keyword")
    assert body == {
        "Keywords": "atmega",
        "Limit": 5,
        "Offset": 0,
        "FilterOptionsRequest": {"CategoryFilter": [{"Id": "685"}]},
    }
    # The product's part, then an alias of it per DigiKey number; what has no model is found, not served.
    assert list(hits) == [
        "ATMEGA328P-PU~microchip-technology",
        "ATMEGA328P-PU-ND",
        "RC0603FR-0710KL~yageo",
        "311-10.0KHRCT-ND",
        "311-10.0KHRTR-ND",
    ]
    assert hits["ATMEGA328P-PU~microchip-technology"]["type"] == "step"
    assert hits["ATMEGA328P-PU-ND"]["source"] == ":ATMEGA328P-PU~microchip-technology"
    assert "type" not in hits["RC0603FR-0710KL~yageo"] and "type" not in hits["311-10.0KHRCT-ND"]
    # DigiKey has no model of the resistor, which the second search said: its media are not asked for.
    assert _asked(made, API + "/products/v4/search/311-10.0KHRCT-ND/media") == []
    assert len(_asked(made, API + "/products/v4/search/keyword")) == 2


def test_the_packagings_of_a_product_share_their_media(digikey):
    made = digikey()
    for sku in ("311-10.0KHRCT-ND", "311-10.0KHRTR-ND"):
        made.model_of(next(p for p in made.products_of(RESISTOR) if p.sku == sku))
    assert len(_asked(made, API + "/products/v4/search/311-10.0KHRCT-ND/media")) == 1
    assert _asked(made, API + "/products/v4/search/311-10.0KHRTR-ND/media") == []


def test_an_account_number_asks_for_its_own_prices(digikey):
    made = digikey(account="1234567")
    made.get("objects/part/ATMEGA328P-PU-ND")
    (headers, _), *_ = _asked(made, API + "/products/v4/search/ATMEGA328P-PU-ND/productdetails")
    assert headers["X-DIGIKEY-Account-Id"] == "1234567"
    made = digikey()
    made.get("objects/part/ATMEGA328P-PU-ND")
    (headers, _), *_ = _asked(made, API + "/products/v4/search/ATMEGA328P-PU-ND/productdetails")
    assert "X-DIGIKEY-Account-Id" not in headers and "X-DIGIKEY-Customer-Id" not in headers


def test_a_product_is_a_part_with_its_digikey_model(digikey):
    made = digikey()
    config = made.get("objects/part/ATMEGA328P-PU~microchip-technology")
    assert config["type"] == "step"
    # Bought by the manufacturer's part number, which DigiKey's store quotes in its cheapest packaging.
    assert (config["vendor"], config["sku"]) == ("Microchip Technology", "ATMEGA328P-PU")
    assert config["desc"].startswith("Microchip Technology ATMEGA328P-PU: IC MCU 8BIT 32KB FLASH 28DIP.")
    assert "Core Processor: AVR" in config["desc"] and "Sold by DigiKey as ATMEGA328P-PU-ND (Tube)" in config["desc"]
    assert base64.b64decode(made.get("files/" + config["path"])).startswith(b"ISO-10303-21")


def test_a_digikey_number_is_an_alias_of_its_products_part(digikey):
    made = digikey()
    config = made.get("objects/part/ATMEGA328P-PU-ND")
    assert (config["type"], config["source"]) == ("alias", ":ATMEGA328P-PU~microchip-technology")
    assert (config["vendor"], config["sku"]) == ("digikey", "ATMEGA328P-PU-ND") and "count_per_sku" not in config


def test_a_full_reel_is_one_sku_of_its_size(digikey):
    made = digikey()
    made.http.request.table[API + "/products/v4/search/311-10.0KHRCT-ND/media"] = (200, {"MediaLinks": [SNAPEDA_LINK]})
    reel = made.get("objects/part/311-10.0KHRTR-ND")
    assert (reel["source"], reel["count_per_sku"]) == (":RC0603FR-0710KL~yageo", 5000)
    cut = made.get("objects/part/311-10.0KHRCT-ND")
    assert "count_per_sku" not in cut
    # Two reels for 6000, priced by the piece.
    cart = {
        "parts": {"r": {"vendor": "digikey", "sku": "311-10.0KHRTR-ND", "count": 6000, "count_per_sku": 5000}},
        "skus": [{"vendor": "digikey", "sku": "311-10.0KHRTR-ND", "count": 2, "parts": ["r"]}],
    }
    (line,) = made.quote({"cart": cart})["lines"]
    assert (line["packs"], line["quantity"]) == (2, 10000) and line["price"] == pytest.approx(24.0)


def test_a_partners_cad_page_is_not_taken_for_a_model(digikey):
    made = digikey()
    model = made.model("ATMEGA328P-PU-ND")
    assert [f.name for f in model.files] == ["ATMEGA328P-PU.step"]


def test_digikeys_number_is_quoted_at_its_breaks(digikey):
    cart = {"parts": {"mcu": {"vendor": "digikey", "sku": "ATMEGA328P-PU-ND", "count": 30}}}
    answer = digikey().quote({"cart": cart})
    assert answer["currency"] == "USD"
    assert answer["price"] == pytest.approx(30 * 2.41)
    assert answer["lines"][0]["stock"] == 18000


def test_a_manufacturers_part_is_quoted_in_the_cheapest_packaging(digikey):
    """Looked up with live prices ('pricing'), not with the search's, which can be a day old."""
    made = digikey()
    answer = made.avail({"vendor": "Yageo", "sku": "RC0603FR-0710KL", "count": 100})
    assert answer["available"] is True and answer["sku"] == "311-10.0KHRCT-ND"
    answer = made.avail({"vendor": "Yageo", "sku": "RC0603FR-0710KL", "count": 10000})
    assert answer["sku"] == "311-10.0KHRTR-ND"


def test_without_credentials_the_root_loads_and_says_what_it_needs(digikey, capsys):
    made = digikey(client_id="", client_secret="")
    assert made.get("meta")["searchKinds"] == ["part"]
    assert made.get("deps") == []
    assert "pc login //pub/svc/commerce/digikey:digikey" in capsys.readouterr().err
    assert made.avail({"vendor": "digikey", "sku": "ATMEGA328P-PU-ND", "count": 1})["available"] is False


def test_partcad_runs_it_and_reads_the_answer_from_output():
    result = runpy.run_path(
        os.path.join(_HERE, "digikey.py"), init_globals={"request": {"key": "meta", "parameters": {}}}, run_name="get"
    )
    assert result["output"]["result"]["manufacturable"] is False


def test_logging_in_checks_the_app_with_digikey(digikey):
    made = digikey()
    assert made.whoami({"client_id": "client-1", "client_secret": "secret-1"}).startswith("the DigiKey app")
    made.http.request.table[TOKEN] = (401, {"error": "invalid_client"})
    assert made.whoami({"client_id": "client-2", "client_secret": "wrong"}) is None
    spec = made.login_spec()
    assert [c["name"] for c in spec["capture"]] == ["client_id", "client_secret"]


def test_the_shared_module_is_the_one_every_distributor_plugin_has():
    with open(os.path.join(_HERE, "distributor.py"), "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(_HERE, "distributor.sha256")) as f:
        assert (
            digest == f.read().split()[0]
        ), "distributor.py differs from the shared copy: run incubator/_shared/copy.sh"


# --- drawn with SnapMagic's model -------------------------------------------------

SNAPEDA = "https://www.snapeda.com/parts/RC0603FR-0710KL/YAGEO/view-part/?ref=digikey"
SNAPEDA_LINK = {"MediaType": "EDA / CAD Models", "Title": "by SnapEDA", "Url": SNAPEDA}


def test_a_product_digikey_has_no_model_file_of_is_snapmagics(digikey):
    made = digikey()
    made.http.request.table[API + "/products/v4/search/311-10.0KHRCT-ND/media"] = (200, {"MediaLinks": [SNAPEDA_LINK]})
    config = made.get("objects/part/RC0603FR-0710KL~yageo")
    assert config["type"] == "alias"
    assert config["source"] == "//pub/collection/snapmagic/models:RC0603FR-0710KL~yageo"
    assert (config["vendor"], config["sku"]) == ("YAGEO", "RC0603FR-0710KL")
    # Its DigiKey numbers are aliases of it, bought from DigiKey.
    cut = made.get("objects/part/311-10.0KHRCT-ND")
    assert (cut["source"], cut["vendor"], cut["sku"]) == (":RC0603FR-0710KL~yageo", "digikey", "311-10.0KHRCT-ND")


def test_snapmagic_can_be_turned_off(digikey, capsys):
    made = digikey(snapmagic="false")
    made.http.request.table[API + "/products/v4/search/311-10.0KHRCT-ND/media"] = (200, {"MediaLinks": [SNAPEDA_LINK]})
    assert d.pm.serve(made, "objects/part/RC0603FR-0710KL~yageo") is None
    assert "has no 3D model at DigiKey" in capsys.readouterr().err
    assert d.pm.serve(made, "objects/part/311-10.0KHRCT-ND") is None


def test_a_model_file_of_digikeys_own_comes_before_snapmagic(digikey):
    made = digikey()
    made.http.request.table[API + "/products/v4/search/ATMEGA328P-PU-ND/media"][1]["MediaLinks"].append(
        {"MediaType": "EDA / CAD Models", "Url": "https://www.snapeda.com/parts/ATMEGA328P-PU/Microchip/view-part/"}
    )
    assert made.get("objects/part/ATMEGA328P-PU~microchip-technology")["type"] == "step"


@pytest.mark.parametrize(
    "mpn, maker, name",
    [
        ("LM358DR2G", "Onsemi", "LM358DR2G~onsemi"),
        ("LM358DR", "Texas%20Instruments", "LM358DR~texas-instruments"),
        ("LM358DR2G (PROMOTION)", "ON Semiconductor", "LM358DR2G%20%28PROMOTION%29~on-semiconductor"),
    ],
)
def test_snapmagics_name_is_the_one_its_plugin_answers_to(mpn, maker, name):
    """partcad-repo-snapmagic's key_of spells these the same; its tests hold it to these very names."""
    url = "https://www.snapeda.com/parts/%s/%s/view-part/?ref=digikey" % (mpn, maker)
    assert plugin["snapmagic_of"]([{"MediaType": "EDA Models", "Url": url}]) == name
    assert plugin["snapmagic_of"]([{"MediaType": "Datasheets", "Url": "https://www.ti.com/x.pdf"}]) is None
