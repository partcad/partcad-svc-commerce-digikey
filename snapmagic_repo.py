#
# partcad-svc-commerce-digikey, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""SnapMagic Search (formerly SnapEDA) 3D models as PartCAD parts: a 'basic' repository plugin.

Published as //pub/svc/commerce/digikey/snapmagic, beside DigiKey's catalogue,
because that is where DigiKey sends its customers for a model: most of the
"EDA / CAD Models" DigiKey lists for a product are SnapMagic pages. A DigiKey
part with no model file of DigiKey's own is an alias of its model here.

A part is a manufacturer's part, named by its part number and its
manufacturer, '<MPN>~<manufacturer>' ('LM358DR~texas-instruments'), as two
manufacturers can share a part number. It says that manufacturer and part
number as its 'vendor' and 'sku', so a store that quotes by them - DigiKey's,
Octopart's - can price it, and its geometry is SnapMagic's STEP model of it.

SnapMagic has no public API (an official one is offered on request, at
https://www.snapeda.com/get-api/). What this asks is what SnapMagic's own CAD
plugins for KiCad and Fusion ask, with the user's own SnapMagic account:

    POST /account/api-login/                     username, password -> {"status", "token"}
    GET  /api/v1/parts/search?q=&token=          {"hits", "results": [{part_number, manufacturer, has_3d, ...}]}
    GET  /api/v1/parts/download_part?...&format=step&token=
                                                 {"url", "status", "error"}: a short-lived link
                                                 to the STEP file, or to a zip holding it

The password is used once, to get the token, and never kept: 'pc login' keeps
the token, as this plugin's 'token' parameter. SnapMagic's terms ask for its
written permission before any automated access, and make every model CC BY-SA
4.0 with its Design Exception: fetch them for yourself, as you need them, and
never put one in a package.
"""

import io
import re
import urllib.parse
import zipfile

import plugin_models as pm  # PartCAD's toolkit for model sites, on the path of every plugin it runs

# When this plugin's answers stopped meaning what they meant before. PartCAD
# keys everything it caches of this package on it, so raise it with any change
# to what is answered.
#
# v1: SnapMagic's 3D models by MPN and manufacturer; 'login' with the account's token.
CACHE_VERSION = 1

WEB = "https://www.snapeda.com"
API = WEB + "/api/v1"

# The name of a part: its MPN, '~', and its manufacturer's slug.
SEPARATOR = "~"


def slug(text):
    text = urllib.parse.unquote(str(text or "")).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def fold(text):
    return re.sub(r"[^0-9a-z]+", "", str(text or "").lower())


def key_of(mpn, manufacturer):
    """A part's name: its MPN, with what a name cannot hold percent-encoded, '~' and its maker's slug."""
    return "%s%s%s" % (urllib.parse.quote(str(mpn), safe="-._"), SEPARATOR, slug(manufacturer))


def link_of(result):
    """The page of a part on SnapMagic, as its search links it."""
    href = ((result.get("_links") or {}).get("self") or {}).get("href")
    return urllib.parse.urljoin(WEB, href) if href else None


def makers_of(result):
    """Every slug a result's manufacturer goes by: its name, and the one in its address ('Onsemi')."""
    names = {slug(result.get("manufacturer")), slug(result.get("urlmanufacturer"))}
    href = ((result.get("_links") or {}).get("self") or {}).get("href") or ""
    parts = href.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "parts":
        names.add(slug(parts[2]))
    return names - {""}


class SnapMagic(pm.Site):
    NAME = "snapmagic"
    TITLE = "SnapMagic"
    URL = WEB
    DESC = (
        "SnapMagic Search (SnapEDA) 3D models of manufacturers' parts, by part number and manufacturer: "
        "'<MPN>~<manufacturer>'. Nothing is listed; search instead. Downloading takes a SnapMagic account."
    )
    VERSION = CACHE_VERSION
    HOMEPAGE = "https://github.com/partcad/partcad-svc-commerce-digikey"
    PACKAGE = "//pub/svc/commerce/digikey/snapmagic"
    LOGIN_INSTRUCTIONS = (
        "SnapMagic's downloads take a SnapMagic (snapeda.com) account, which is free. What is needed is its user "
        "name (or email) and password, which the plugin exchanges for a token once, as SnapMagic's own CAD plugins "
        "do, and does not keep. An account made by signing in with Google needs a password set first, on "
        "snapeda.com's account page."
    )
    CREDENTIALS = {"token": "SNAPMAGIC_TOKEN"}

    def __init__(self, request=None):
        super().__init__(request)
        self.token = pm.credential(self.request, "token", "SNAPMAGIC_TOKEN")

    def login_command(self):
        return "pc login %s:snapmagic_repo" % self.PACKAGE.rpartition("/")[0]

    # -- the wire --

    def ask(self, path, what, query, ttl=pm.DAY):
        if not self.token:
            raise pm.NeedsCredentials(
                "snapmagic: %s needs a SnapMagic account: '%s', or SNAPMAGIC_TOKEN" % (what, self.login_command())
            )
        url = "%s/%s?%s" % (API, path, urllib.parse.urlencode(dict(query, token=self.token)))
        answer = self.http.json(
            url, what, ttl=ttl, valid=lambda value: isinstance(value, dict) and not value.get("error")
        )
        if not isinstance(answer, dict):
            raise pm.SiteError("snapmagic: %s: SnapMagic answered no JSON object" % what)
        error = str(answer.get("error") or "")
        status = str(answer.get("status") or "")
        if error or status not in ("", "logged_in"):
            said = error or status
            if status == "not_logged_in" or "logged in" in said or "token" in said:
                raise pm.NeedsCredentials(
                    "snapmagic: %s: SnapMagic says '%s': '%s' again" % (what, said, self.login_command())
                )
            if status == "unverified_email":
                raise pm.NeedsCredentials("snapmagic: %s: verify your SnapMagic account's email first" % what)
            if "limit" in said:
                raise pm.Refused("snapmagic: %s: SnapMagic says '%s'; try again later" % (what, said))
            if "no models" in said.lower():
                raise pm.NotFound("snapmagic: %s: SnapMagic has no model of it" % what)
            raise pm.SiteError("snapmagic: %s: SnapMagic says '%s'" % (what, said))
        return answer

    def results(self, text, what):
        answer = self.ask("parts/search", what, {"q": text})
        return [r for r in answer.get("results") or [] if isinstance(r, dict) and r.get("part_number")]

    # -- a model site, as plugin_models asks one --

    def valid_id(self, model_id):
        mpn, _, maker = model_id.rpartition(SEPARATOR) if SEPARATOR in model_id else (model_id, "", "")
        return bool(mpn.strip()) and len(model_id) <= 200

    def model(self, model_id):
        mpn, separator, maker = model_id.rpartition(SEPARATOR) if SEPARATOR in model_id else (model_id, "", "")
        mpn = urllib.parse.unquote(mpn)
        found = [r for r in self.results(mpn, "part %s" % model_id) if fold(r["part_number"]) == fold(mpn)]
        if separator:
            found = [r for r in found if maker in makers_of(r)]
        modelled = [r for r in found if r.get("has_3d")]
        if len({slug(r.get("manufacturer")) for r in found}) > 1 and not separator:
            raise pm.NotFound(
                "snapmagic: %s is made by %s: name one, '%s'"
                % (
                    mpn,
                    " and by ".join(sorted({str(r.get("manufacturer")) for r in found})),
                    key_of(mpn, found[0]["manufacturer"]),
                )
            )
        if not found:
            raise pm.NotFound("snapmagic: SnapMagic has no part %s" % model_id)
        return self.model_of((modelled or found)[0], model_id)

    def model_of(self, result, model_id=None):
        model_id = model_id or key_of(result["part_number"], result.get("manufacturer"))
        files = []
        if result.get("has_3d"):
            name = "%s.step" % re.sub(r"[^A-Za-z0-9._-]+", "_", result["part_number"])
            files.append(pm.File("step", name, result=result))
        package = (result.get("package") or {}).get("name") if isinstance(result.get("package"), dict) else None
        desc = result.get("short_description") or ""
        if package and package.strip("-"):
            desc = "%s (%s)" % (desc, package) if desc else package
        model = pm.Model(
            model_id,
            title="%s %s" % (result.get("manufacturer") or "", result["part_number"]),
            url=link_of(result),
            files=files,
            desc=desc,
            license="CC-BY-SA-4.0 WITH SnapEDA Design Exception 1.0",
        )
        model.result = result
        return model

    def search(self, text, limit):
        models = []
        for result in self.results(text, "a search for '%s'" % text)[:limit]:
            models.append(self.model_of(result))
        return models

    def find(self, text, limit=None):
        # A part has one model, so a hit is named by the part alone, not '<part>;file=step'.
        named = {}
        for name, config in super().find(text, limit).items():
            base, parameters = pm.parse_name(name)
            named[base if set(parameters) <= {"file"} else name] = config
        return named

    def unserved(self, model):
        return "SnapMagic has no 3D model of it"

    def part_config(self, model, file):
        config = super().part_config(model, file)
        result = model.result
        config["desc"] = "%s: %s. 3D model from SnapMagic (CC BY-SA 4.0, with SnapEDA's Design Exception)." % (
            model.title.strip(),
            model.desc or "no description",
        )
        # A manufacturer's part: what any store quotes by.
        config["vendor"] = result.get("manufacturer")
        config["sku"] = result["part_number"]
        config["parameters"] = {k: v for k, v in config["parameters"].items() if k != "source"}
        return config

    def download(self, model, file):
        result = file.extra["result"]
        what = "the 3D model of %s" % model.id
        query = {
            "part_number": result["part_number"],
            "manufacturer": result.get("manufacturer") or "",
            "has_symbol": "true" if result.get("has_symbol") else "false",
            "has_footprint": "true" if result.get("has_footprint") else "false",
            "uniqueid": result.get("uniqueid") or "",
            "format": "step",
        }
        # A link that lasts minutes: never kept.
        answer = self.ask("parts/download_part", what, query, ttl=0)
        url = answer.get("url")
        if not url:
            raise pm.NotFound("snapmagic: %s: SnapMagic has no 3D model of it" % what)
        data = self.http.download(urllib.parse.urljoin(WEB, url), what)
        if pm.is_zip(data):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                steps = [m for m in archive.namelist() if m.lower().endswith((".step", ".stp"))]
                if not steps:
                    raise pm.NotFound("snapmagic: %s came without a STEP file in it" % what)
                return archive.read(sorted(steps, key=len)[0])
        if not data.lstrip()[:12].upper().startswith(b"ISO-10303-21"):
            raise pm.SiteError("snapmagic: %s is neither a STEP file nor a zip of one" % what)
        return data

    # -- logging in --

    def credentials_from(self, captured):
        """The token for what was captured: a token, or a user name and password exchanged for one."""
        if str(captured.get("token") or "").strip():
            return {"token": str(captured["token"]).strip()}
        username = str(captured.get("username") or "").strip()
        password = str(captured.get("password") or "")
        if not username or not password:
            return {"token": ""}
        response = self.http.request(
            WEB + "/account/api-login/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode({"username": username, "password": password}).encode("utf-8"),
            method="POST",
        )
        try:
            answer = response.json()
        except ValueError:
            answer = {}
        if answer.get("status") != "logged_in" or not answer.get("token"):
            raise pm.LoginFailed(
                "snapmagic: SnapMagic did not take that user name and password (%s)"
                % (answer.get("status") or "HTTP %d" % response.status)
            )
        return {"token": str(answer["token"])}

    def whoami(self, credentials):
        token = credentials.get("token")
        if not token:
            return None
        self.token = token
        # What SnapMagic's own plugins ask to check a token.
        try:
            self.ask("parts/search", "a check of the token", {"q": "test-search"}, ttl=0)
        except pm.NeedsCredentials:
            return None
        return "your SnapMagic account"

    def login_spec(self):
        return {
            "url": WEB + "/account/login/",
            "title": "SnapMagic",
            "capture": [
                {"name": "username", "ask": {"label": "Your SnapMagic user name or email", "secret": False}},
                {"name": "password", "ask": {"label": "Your SnapMagic password (used once, not kept)", "secret": True}},
            ],
        }


def get(key):
    return pm.serve(SnapMagic(globals().get("request")), key)


# Last, so that everything above is defined when PartCAD runs this.
if __name__ == "get":
    output = {"result": get(request["key"])}  # noqa: F821 - injected by the runtime
elif __name__ == "login":
    output = {"result": pm.login(SnapMagic(globals().get("request")), globals().get("partcad_login"))}
else:
    output = {}
