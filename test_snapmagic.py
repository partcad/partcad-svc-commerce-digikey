#
# partcad-svc-commerce-digikey, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""Tests of the SnapMagic plugin, with SnapMagic answered from a table.

The answers have the shape SnapMagic's API answers SnapMagic's own CAD plugins
with - a search's 'hits' and 'results', 'download_part's link, the login's
token, and 'error'/'status' in a 200 - as seen once without credentials, with
values made up. Nothing here touches the network.
"""

import base64
import io
import json
import os
import runpy
import urllib.parse
import zipfile

import plugin_models as pm
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
plugin = runpy.run_path(os.path.join(_HERE, "snapmagic_repo.py"), run_name="snapmagic_under_test")
SnapMagic = plugin["SnapMagic"]

WEB = "https://www.snapeda.com"
API = WEB + "/api/v1"
FILE = "https://snapeda.s3.amazonaws.com/downloads/LM358DR.zip?X-Amz-Signature=x"


def _result(mpn, manufacturer, url_maker, has_3d, package="SOIC-8"):
    return {
        "part_number": mpn,
        "name": mpn,
        "manufacturer": manufacturer,
        "urlmanufacturer": urllib.parse.quote(url_maker),
        "has_3d": has_3d,
        "has_symbol": True,
        "has_footprint": True,
        "uniqueid": "",
        "short_description": "Dual standard operational amplifier",
        "package": {"name": package},
        "_links": {"self": {"href": "/parts/%s/%s/view-part/" % (mpn, urllib.parse.quote(url_maker))}},
    }


RESULTS = [
    _result("LM358DRE4", "Texas Instruments", "Texas Instruments", True),
    _result("LM358DR", "Rohm Semiconductor", "Rohm", True),
    _result("LM358DR", "Texas Instruments", "Texas Instruments", True),
    _result("LM358DR2G", "ON Semiconductor", "Onsemi", True),
    _result("LM358DRT", "NXP Semiconductors", "NXP Semiconductors", False),
]


def _zip():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("LM358DR/LM358DR.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        z.writestr("LM358DR/how-to-import.htm", "<html></html>")
    return out.getvalue()


class Wire:
    def __init__(self):
        self.asked = []
        self.token = "token-1"
        self.download = {"url": FILE, "status": "logged_in", "error": None}

    def __call__(self, url, headers=None, data=None, method=None, timeout=60):
        self.asked.append((url, data, method))
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        if url == WEB + "/account/api-login/":
            form = dict(urllib.parse.parse_qsl(data.decode()))
            if (form.get("username"), form.get("password")) == ("me@example.com", "right"):
                body = {"status": "logged_in", "token": self.token, "user_email": "me@example.com"}
            else:
                body = {"status": "incorrect_credentials"}
            return pm.Response(200, {}, json.dumps(body).encode(), url)
        if url.startswith(API) and query.get("token") != self.token:
            body = {"hits": 0, "results": [], "error": "not logged in", "message": "Error", "pages": []}
            return pm.Response(200, {}, json.dumps(body).encode(), url)
        if parts.path == "/api/v1/parts/search":
            found = [r for r in RESULTS if r["part_number"].lower().startswith(query["q"].lower())]
            body = {"hits": len(found), "results": found, "error": None, "pages": []}
            return pm.Response(200, {}, json.dumps(body).encode(), url)
        if parts.path == "/api/v1/parts/download_part":
            return pm.Response(200, {}, json.dumps(self.download).encode(), url)
        if url == FILE:
            return pm.Response(200, {}, _zip(), url)
        return pm.Response(404, {}, b"{}", url)


@pytest.fixture
def snapmagic(tmp_path, monkeypatch):
    monkeypatch.setenv("PARTCAD_SNAPMAGIC_CACHE", str(tmp_path))
    monkeypatch.delenv("SNAPMAGIC_TOKEN", raising=False)

    def make(token="token-1"):
        made = SnapMagic({"parameters": {"token": token}})
        made.http.request = Wire()
        return made

    return make


def test_a_part_is_a_manufacturers_named_by_both(snapmagic):
    config = snapmagic().get("objects/part/LM358DR~texas-instruments")
    assert config["type"] == "step"
    assert config["vendor"] == "Texas Instruments" and config["sku"] == "LM358DR"
    assert config["url"] == WEB + "/parts/LM358DR/Texas%20Instruments/view-part/"
    assert "CC BY-SA 4.0" in config["desc"]


def test_a_manufacturer_is_known_by_the_name_in_its_address_too(snapmagic):
    """DigiKey links 'Onsemi', SnapMagic names it 'ON Semiconductor'."""
    assert snapmagic().get("objects/part/LM358DR2G~onsemi")["vendor"] == "ON Semiconductor"


def test_a_number_two_makers_have_needs_the_maker(snapmagic, capsys):
    assert pm.serve(snapmagic(), "objects/part/LM358DR") is None
    assert "made by Rohm Semiconductor and by Texas Instruments" in capsys.readouterr().err


def test_the_step_comes_out_of_the_zip(snapmagic):
    made = snapmagic()
    config = made.get("objects/part/LM358DR~texas-instruments")
    assert base64.b64decode(made.get("files/" + config["path"])).startswith(b"ISO-10303-21")
    (url, _, _), *_ = [a for a in made.http.request.asked if "download_part" in a[0]]
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert query["format"] == "step" and query["manufacturer"] == "Texas Instruments" and query["token"] == "token-1"


def test_the_download_link_is_never_kept(snapmagic):
    made = snapmagic()
    config = made.get("objects/part/LM358DR~texas-instruments")
    made.get("files/" + config["path"])
    made.get("files/" + config["path"])
    assert len([a for a in made.http.request.asked if "download_part" in a[0]]) == 2


def test_a_part_without_a_model_is_found_and_not_served(snapmagic):
    hits = snapmagic().get("search/part?q=LM358DR&limit=10")
    assert "LM358DR~texas-instruments" in hits and "LM358DR2G~on-semiconductor" in hits
    assert "type" not in hits["LM358DRT~nxp-semiconductors"]
    assert "no 3D model" in hits["LM358DRT~nxp-semiconductors"]["desc"]


def test_a_search_costs_one_request(snapmagic):
    made = snapmagic()
    made.get("search/part?q=LM358DR&limit=10")
    assert len(made.http.request.asked) == 1


def test_without_a_token_it_says_how_to_log_in(snapmagic, capsys):
    assert pm.serve(snapmagic(token=""), "objects/part/LM358DR~texas-instruments") is None
    assert "pc login //pub/svc/commerce/digikey:snapmagic_repo" in capsys.readouterr().err


def test_an_expired_token_says_to_log_in_again(snapmagic, capsys):
    made = snapmagic(token="stale")
    assert pm.serve(made, "objects/part/LM358DR~texas-instruments") is None
    assert "SnapMagic says 'not logged in'" in capsys.readouterr().err


@pytest.mark.parametrize(
    "answer, said",
    [
        ({"url": "", "status": "logged_in", "error": "download limit exceeded"}, "try again later"),
        ({"url": "", "status": "unverified_email", "error": None}, "verify your SnapMagic account's email"),
        ({"url": "", "status": "logged_in", "error": "No models for this part"}, "has no model of it"),
        ({"url": "", "status": "logged_in", "error": None}, "has no 3D model of it"),
    ],
)
def test_what_snapmagic_says_of_a_download_is_said(snapmagic, capsys, answer, said):
    made = snapmagic()
    config = made.get("objects/part/LM358DR~texas-instruments")
    made.http.request.download = answer
    assert pm.serve(made, "files/" + config["path"]) is None
    assert said in capsys.readouterr().err


def test_logging_in_exchanges_the_password_for_a_token_and_keeps_only_the_token(snapmagic):
    made = snapmagic(token="")
    assert made.credentials_from({"username": "me@example.com", "password": "right"}) == {"token": "token-1"}
    with pytest.raises(pm.LoginFailed, match="incorrect_credentials"):
        made.credentials_from({"username": "me@example.com", "password": "wrong"})
    assert made.whoami({"token": "token-1"}) == "your SnapMagic account"
    assert made.whoami({"token": "stale"}) is None


def test_the_login_asks_for_the_user_name_and_password(snapmagic):
    spec = snapmagic().login_spec()
    assert [c["name"] for c in spec["capture"]] == ["username", "password"]
    assert spec["capture"][1]["ask"]["secret"] is True


def test_partcad_runs_it_and_reads_the_answer_from_output():
    result = runpy.run_path(
        os.path.join(_HERE, "snapmagic_repo.py"),
        init_globals={"request": {"key": "meta", "parameters": {}}},
        run_name="get",
    )
    assert result["output"]["result"]["searchKinds"] == ["part"]
