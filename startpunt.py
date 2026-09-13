import datetime
import decimal
import pathlib
import textwrap

from mybox import MyBox, MyBoxList

# Een voorbeeld data structuur:

order = {
    "naam": "Klaas Vaak",
    "email": "k.vaak@gmail.com",
    "artikelen": ["OP205", "OP210", "TS216", "PZ001"],
    "besteld-op": datetime.date(2026,9,12),
    "prijs": decimal.Decimal("27.50"),
    "bezorgvenster": {
        "van": datetime.time(9,0),
        "tot": datetime.time(12,30),
        },
    "verzendopties": {
        "spoed": False,
        "handtekening": True,
        }
    }

# MyBox wikkelt de dict in een object met attribuut-toegang, en weet hoe het
# de types moet serialiseren die json zelf niet kent. Zie mybox.py.
# De drie opties hieronder staan uitgelegd in de docstring van MyBox:
#
#     python3 -c "from mybox import MyBox; help(MyBox)"
doos = MyBox(order, box_dots=True, default_box=True,
             default_box_create_on_get=False)


def toon(expressie, waarde):
    """Print de expressie en wat die oplevert, zodat de uitvoer zichzelf uitlegt."""
    print(f"  {expressie:34} {waarde!r}")


if __name__ == "__main__":
    # Attribuut-toegang in plaats van order["naam"]
    toon("doos.naam", doos.naam)
    toon("doos.email", doos.email)

    # Geneste dicts zijn zelf ook weer een MyBox
    toon("doos.verzendopties.handtekening", doos.verzendopties.handtekening)
    toon("doos.bezorgvenster.van", doos.bezorgvenster.van)

    # "besteld-op" heeft een streepje en is dus geen geldige attribuutnaam.
    # Box maakt daar automatisch een alias met underscore voor;
    # de originele key blijft gewoon bestaan. Vandaar twee keer dezelfde
    # waarde langs twee wegen:
    toon("doos.besteld_op", doos.besteld_op)
    toon('doos["besteld-op"]', doos["besteld-op"])

    # Pad als string, in plaats van doos["verzendopties"]["spoed"] (box_dots)
    toon('doos["verzendopties.spoed"]', doos["verzendopties.spoed"])

    # Lijsten worden een BoxList
    toon("doos.artikelen[0]", doos.artikelen[0])
    toon("type(doos.artikelen)", type(doos.artikelen))

    # Onbekende key: lege Box, geen KeyError (default_box)
    toon("doos.kortingscode", doos.kortingscode)

    # Kwijt in je eigen data? describe() zet alle velden op een rij, met het
    # pad zoals je het intypt. Waar dot-notatie niet kan, staat de [...]-vorm
    # met de reden erbij.
    print()
    print(doos.describe())
    print()

    # Serialiseren kan nu gewoon. Waar json.dumps(order) faalde op de date en
    # de Decimal, regelt MyBox dat zelf:
    regels = doos.to_json(indent=4, sort_keys=True)
    print(regels)

    # En weer terug, met de types intact:
    heen_en_terug = MyBox.from_json(regels)

    print(repr(heen_en_terug.besteld_op))       # weer een echte date
    print(repr(heen_en_terug.prijs))            # weer een echte Decimal
    print(heen_en_terug.prijs * 3)              # en er valt mee te rekenen

    # Niets verloren onderweg:
    print(heen_en_terug.to_dict() == order)

    # order dekt date, time en Decimal af. Voor de volledigheid nog de
    # gevallen die daar niet in zitten: een datetime, tijdzone-info, en bytes.
    agenda = MyBox({
        "dag": datetime.date(2026, 9, 12),
        "openingstijd": datetime.time(9, 0),
        "gesloten-om": datetime.time(17, 30, tzinfo=datetime.timezone.utc),
        "gewijzigd": datetime.datetime(2026, 9, 12, 14, 30),
        "xorkey": b"\x3a\x91\x07\xff\x42\x00\xbe\x6d\x18\xc3",
        })
    tekst = agenda.to_json(indent=4, sort_keys=True)
    print(tekst)
    print(MyBox.from_json(tekst).to_dict() == agenda.to_dict())

    # --- Meerdere orders: JSON Lines --------------------------------------
    #
    # MyBox verwacht een JSON-object; staat er op het hoogste niveau een
    # lijst, dan heb je MyBoxList nodig.
    orders = MyBoxList([
        order,
        {**order, "naam": "Pietje Puk", "prijs": decimal.Decimal("8.05")},
        ])

    # Met multiline=True komt er een compleet JSON-object op elke regel, zonder
    # omsluitende [ ] en zonder komma's. Zo kun je regels toevoegen of lezen
    # zonder het hele bestand in te laden - vandaar dat logs dit gebruiken.
    #
    # Let op: multiline werkt alleen SAMEN met een bestandsnaam. Zonder
    # filename wordt de vlag genegeerd en krijg je gewoon een array terug.
    # En schrijven naar een bestand geeft None terug, niet de tekst.
    pad = pathlib.Path(__file__).with_name("orders.jsonl")

    # try/finally, zodat het bestand ook opgeruimd wordt als er hierbinnen
    # iets misgaat. Wil je zelf in orders.jsonl kijken, haal dan de finally
    # weg of zet er een print(pad) bij en onderbreek het script.
    try:
        orders.to_json(pad, multiline=True)

        print(f"\n{pad.name}, {len(pad.read_text().splitlines())} regels:")
        for regel in pad.read_text().splitlines():
            print(" ", regel[:78], "...")

        # Inlezen kan uit het bestand, of uit een string die je al hebt:
        uit_bestand = MyBoxList.from_json(filename=pad, multiline=True)
        uit_string = MyBoxList.from_json(pad.read_text(), multiline=True)

        print(uit_bestand[1].naam, repr(uit_bestand[1].prijs))
        print(uit_bestand.to_list() == uit_string.to_list() == orders.to_list())
    finally:
        # missing_ok, anders krijg je hier alsnog een FileNotFoundError
        # bovenop de fout die je eigenlijk wilde zien.
        pad.unlink(missing_ok=True)
        print(f"{pad.name} opgeruimd:", not pad.exists())

    # --- In een Jinja2-template ---------------------------------------------
    #
    # Jinja's punt werkt net als die van Box in twee stappen: eerst getattr,
    # dan [...]. Daardoor kan {{ order.verzendopties.spoed }} ook op een kale
    # dict. Wat NIET op een kale dict kan is order.besteld_op, want die key
    # heet "besteld-op" en bestaat dus niet onder die naam. Een MyBox heeft
    # die alias wel, en is verder gewoon een dict - Jinja hoeft er niets
    # voor te weten.
    #
    # {{ order.besteld-op }} is trouwens geen optie: Jinja leest dat als
    # order.besteld MIN op.
    try:
        from jinja2 import Environment
    except ImportError:
        print("\n(jinja2 niet geinstalleerd, template overgeslagen)")
    else:
        # dedent, anders erft de uitvoer de inspringing van deze broncode.
        sjabloon = Environment(trim_blocks=True, lstrip_blocks=True).from_string(
            textwrap.dedent("""\
                Beste {{ order.naam }},

                Je bestelling van {{ order.besteld_op }} met {{ order.artikelen | length }} artikelen
                wordt bezorgd tussen {{ order.bezorgvenster.van }} en {{ order.bezorgvenster.tot }}.
                Totaal: EUR {{ order.prijs }}
                {% if order.verzendopties.handtekening %}
                Let op: er wordt om een handtekening gevraagd.
                {% endif %}
                """))
        print()
        print(sjabloon.render(order=doos))

        # En de valkuil: een key die botst met een dict-methode geeft in
        # Jinja net zo goed de methode terug, zonder foutmelding. Vandaar
        # dat describe() daar de [...]-vorm voor toont.
        botsing = MyBox({"items": "mijn eigen waarde"})
        for expressie in ("d.items", "d['items']"):
            uit = Environment().from_string("{{ %s }}" % expressie).render(d=botsing)
            print(f"  {expressie:12} -> {uit[:44]}")
