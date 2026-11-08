# DigiKey for PartCAD

DigiKey, published with the other stores as `//pub/svc/commerce/digikey`, in two parts:

* **a store**, `//pub/svc/commerce/digikey:digikey`, that quotes DigiKey part numbers - and any
  manufacturer's part DigiKey lists, by its manufacturer and part number - at DigiKey's prices
  for your country, in your currency, with DigiKey's stock;
* **a catalogue**, `//pub/svc/commerce/digikey/products`, whose child packages are DigiKey's
  own categories, each searched with DigiKey's own search, and walked down with
  `pc list packages`. A product is two kinds of part:
  * **the manufacturer's part**, named `<MPN>~<manufacturer>` (`ATMEGA328P-PU~microchip-technology`),
    with the product's 3D model as its geometry, and its manufacturer and part number as its
    `vendor` and `sku` - so that any store quoting by manufacturer's part number prices it,
    DigiKey's among them;
  * **an alias of it per DigiKey number** it is sold as (`ATMEGA328P-PU-ND`; a resistor's cut
    tape, tape and reel, and Digi-Reel are three), saying `vendor: digikey`, its `sku`, and the
    pack size as `count_per_sku` (a reel of 5000 is `5000`).

  An assembly links the manufacturer's part. PartCAD counts it as bought because an alias of
  it names a vendor and an SKU, and orders it by whichever alias suits the quantity: ten come
  off cut tape, five thousand as the reel.

The geometry is the 3D model DigiKey hands out for the product - or, where DigiKey has no model
file but links its SnapMagic page, SnapMagic's model of it, from
[SnapMagic for PartCAD](https://github.com/partcad/partcad-repo-snapmagic) (below).

Both are one script, `digikey.py`, asking DigiKey's **Product Information API v4**
(<https://developer.digikey.com>), which is DigiKey's own, versioned and documented.

## Setting it up

The API is free, and takes an app of your own: sign in at <https://developer.digikey.com>,
create an organization, then a **production** app subscribed to *Product Information V4*,
and copy its Client ID and Client Secret. Then:

```shell
pc login //pub/svc/commerce/digikey:digikey_repo
pc login //pub/svc/commerce/digikey:digikey
```

PartCAD keeps the two values in `~/.partcad/config.yaml`, under `parameters`, by each
plugin's name: the store and the catalogue are two plugins and keep their keys apart, so log
in to both. `DIGIKEY_CLIENT_ID` and `DIGIKEY_CLIENT_SECRET` work too, where the plugin's
sandbox sees the environment. Never put either in a package. Your own prices ("MyPricing")
are asked for with your DigiKey account number, the `account` parameter.

## Using it

```shell
pc list packages //pub/svc/commerce/digikey/products...
pc search parts -P //pub/svc/commerce/digikey/products -k ATmega328P
pc search parts -P //pub/svc/commerce/digikey/products/integrated-circuits-ics/embedded-microcontrollers -k "avr dip"
pc info "//pub/svc/commerce/digikey/products:ATMEGA328P-PU~microchip-technology"
pc supply quote "//pub/svc/commerce/digikey/products:ATMEGA328P-PU~microchip-technology#10"
pc supply quote "//pub/svc/commerce/digikey/products:ATMEGA328P-PU-ND#10"
```

A search finds both kinds: the manufacturer's part first, then an alias per DigiKey number.

A part of your own package is quoted by DigiKey if it says either DigiKey's number or its
manufacturer's:

```yaml
parts:
  mcu:
    type: step
    path: atmega328p.step
    vendor: Microchip Technology   # the manufacturer, as DigiKey spells it
    sku: ATMEGA328P-PU             # its part number
suppliers:
  //pub/svc/commerce/digikey:digikey:
```

## How DigiKey is asked

| What PartCAD asks | DigiKey API v4 |
| --- | --- |
| the categories (`deps`, `meta`) | `GET /products/v4/search/categories`, kept a week |
| a search (`search/part`) | `POST /products/v4/search/keyword`, with a `CategoryFilter` in a category; and the same search with `SearchOptions: [Has3DModel]`, to know which products are worth asking for media |
| a part (`objects/part/<number>`) | `GET /products/v4/search/<number>/productdetails`, then `.../media` for its model |
| its model (`files/...`) | the media link, when it is a model file (or a zip of one) |
| a DigiKey number (`avail`, `quote`) | `.../productdetails`, live prices |
| a manufacturer's number | `GET /products/v4/search/<MPN>/pricing`, every listing with live prices |

Every request carries the token (OAuth 2.0 client credentials, kept for its ten minutes) and
your locale - `X-DIGIKEY-Locale-Site`, `-Language`, `-Currency` from PartCAD's `country`,
`language` and `currency`, falling back to what DigiKey has. A product sold in several
packagings (cut tape, tape and reel, a tube) is a part per DigiKey number; a manufacturer's
part is quoted in the packaging that makes the quantity cheapest, raised to its minimum. A
DigiKey number sold only in multiples of a standard package (a reel, whose minimum is the reel)
is a pack of that many, and is quoted per reel.

## SnapMagic's models

DigiKey's API gives CAD as links among a product's media, and most of them are a CAD
partner's page, not a file: mostly SnapMagic's (`snapeda.com/parts/<MPN>/<manufacturer>/...`).
So the manufacturer's part of a product with no model file of DigiKey's own, whose media link
a SnapMagic page, is an `alias` of SnapMagic's part, and its DigiKey numbers are aliases of it
as always:

```yaml
# what //pub/svc/commerce/digikey/products:LM358DR~texas-instruments answers
type: alias
source: //pub/collection/snapmagic/models:LM358DR~texas-instruments
vendor: Texas Instruments
sku: LM358DR
```

SnapMagic's part is served by its own package,
[`//pub/collection/snapmagic`](https://github.com/partcad/partcad-repo-snapmagic), which needs
a SnapMagic account of your own:

```shell
pc login //pub/collection/snapmagic:snapmagic_repo     # your snapeda.com user name and password
pc search parts -P //pub/collection/snapmagic/models -k LM358DR
```

A part number two manufacturers have needs the manufacturer
(`LM358DR~rohm-semiconductor`), and the one a DigiKey link names is the manufacturer as
SnapMagic spells it. `snapmagic: false` on `digikey_repo` turns the aliases off. Every model is
SnapMagic's, under CC BY-SA 4.0 with its Design Exception: fetched for you, as you need it,
never put into a package; see that package for what to know about SnapMagic's API.

## What it cannot do (yet)

* **Not every product has a model to build.** Only a media link to a file PartCAD reads (or a
  zip of one), or to a SnapMagic page, gives a part geometry; a product with neither is found
  by a search, said to have no model, and not served. It is still sold: declare a part of your
  own with its `vendor` and `sku`. And a SnapMagic page may have no 3D model on it, which the
  alias then says when it is built.
* **The quota is 1,000 requests a day** (120 a minute). A search is two requests and one
  more per product DigiKey says it has a model of; answers are kept (prices for an hour,
  products and searches for a day) so that asking again is free.
* **No cart or order.** DigiKey's cart and ordering APIs need a 3-legged sign-in and, to
  order, a credit account.
* DigiKey's terms (its API User Agreement) allow an internal application for purchasing from
  DigiKey, require attribution, and forbid bulk download and building a database of DigiKey's
  data: the catalogue lists nothing and is searched, and the keys are each user's own.

Run end to end in PartCAD 0.9.22 - the categories, a search in one, a part built from DigiKey's
model, a part built through its SnapMagic alias, a quote of both - against servers standing in
for DigiKey's and SnapMagic's APIs (the plugins' `api` parameters point them there). Ordering a
manufacturer's part by the alias that suits the quantity needs a PartCAD that counts a part
with such aliases as bought; one that does not quotes it by its MPN instead. Not yet
against DigiKey's or SnapMagic's own, for want of credentials: the tests answer DigiKey in the
shapes of its Swagger and SnapMagic in the shapes its API answered without credentials. The
first live run should confirm the media types DigiKey uses for model files.

## Tests

```shell
pip install pytest
pip install --no-deps partcad    # for plugin_models, which PartCAD gives every plugin
pytest
```

`distributor.py` is shared, byte for byte, with the other distributor packages (Octopart,
McMaster-Carr); it is edited in `incubator/_shared/` of the PartCAD repository and copied here,
and `distributor.sha256` is its digest, which the tests hold this copy to.
