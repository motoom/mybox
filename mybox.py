"""Box met getypeerde JSON-serialisatie ingebouwd.

    from mybox import MyBox

    doos = MyBox(order)
    tekst = doos.to_json(indent=4)
    terug = MyBox.from_json(tekst)      # date, time, Decimal en bytes intact

Gewone Box kan de dict-kant prima aan, maar json kent alleen str, int, float,
bool, None, list en dict. Een date of Decimal moet je zelf vertalen, en als je
naar een kale string vertaalt is bij het inlezen niet meer te zien wat het ooit
was: "27.50" kan net zo goed een artikelnummer zijn.

Daarom krijgt elke omgezette waarde een type-label mee. default= mag namelijk
niet alleen een string teruggeven, maar elk serialiseerbaar object - dus ook
een dict, die json vervolgens gewoon verder serialiseert:

    "prijs": {"__type__": "Decimal", "waarde": "27.50"}

Bij het lezen ziet object_hook dat label en bouwt het origineel terug.
"""

import base64
import datetime
import decimal
import keyword
import re

from box import Box, BoxList

__all__ = ["MyBox", "MyBoxList", "json_default", "json_object_hook"]

TYPE_SLEUTEL = "__type__"

# De labels die json_object_hook mag terugbouwen. Alles daarbuiten laat hij
# staan; zie de docstring van json_object_hook.
ONZE_TYPES = frozenset({"datetime", "date", "time", "Decimal",
                        "bytes", "bytearray"})

# Bytes moeten als tekst in JSON. base64 is compact en zit in elke taal;
# zie coderingen.py voor de meting achter die keuze. De codering gaat mee in
# de JSON, zodat oude bestanden leesbaar blijven als je hier iets omzet.
BYTES_CODERING = "base64"

BYTES_CODEERDERS = {
    # naam:     (coderen naar tekst,                            terug naar bytes)
    "base64":   (lambda b: base64.b64encode(b).decode("ascii"), base64.b64decode),
    "hex":      (lambda b: b.hex(),                             bytes.fromhex),
    "base85":   (lambda b: base64.b85encode(b).decode("ascii"), base64.b85decode),
    "urlsafe":  (lambda b: base64.urlsafe_b64encode(b).decode("ascii"),
                 base64.urlsafe_b64decode),
    "base32":   (lambda b: base64.b32encode(b).decode("ascii"), base64.b32decode),
    }


def json_default(waarde):
    """Vertaalt onbekende types naar een dict met een type-label erbij."""
    # Let op de volgorde: datetime is een subclass van date, dus die moet
    # eerst, anders vangt de date-tak je datetimes af en verlies je de tijd.
    # (time is geen subclass van date, die staat er los van.)
    if isinstance(waarde, datetime.datetime):
        return {TYPE_SLEUTEL: "datetime", "waarde": waarde.isoformat()}
    if isinstance(waarde, datetime.date):
        return {TYPE_SLEUTEL: "date", "waarde": waarde.isoformat()}
    if isinstance(waarde, datetime.time):
        return {TYPE_SLEUTEL: "time", "waarde": waarde.isoformat()}
    if isinstance(waarde, decimal.Decimal):
        # str, niet float: anders verlies je precisie en trailing nullen
        return {TYPE_SLEUTEL: "Decimal", "waarde": str(waarde)}
    if isinstance(waarde, (bytes, bytearray)):
        # Bytes decoderen kan niet - willekeurige bytes zijn zelden geldige
        # UTF-8 - dus coderen we ze naar tekst.
        codeer, _ = BYTES_CODEERDERS[BYTES_CODERING]
        return {TYPE_SLEUTEL: type(waarde).__name__,
                "codering": BYTES_CODERING,
                "waarde": codeer(waarde)}
    raise TypeError(f"Niet serialiseerbaar: {type(waarde).__name__}")


def json_object_hook(gelezen):
    """Bouwt de originele objecten terug uit het type-label.

    json roept dit aan voor elke dict die het tegenkomt. Zit er geen label in,
    dan laten we de dict ongemoeid en maakt MyBox er daarna een MyBox van.

    Het label is een eigen afspraak, geen standaard. Vreemde JSON mag dus
    best een veld __type__ hebben; die blijft onaangeroerd, ook als de
    waarde toevallig "date" is maar de rest niet klopt. Liever een dict
    teruggeven dan het inlezen van een heel bestand laten klappen.
    """
    soort = gelezen.get(TYPE_SLEUTEL)

    # Alleen ingrijpen als het er echt als een van ons uitziet. JSON uit een
    # ander systeem mag toevallig ook een veld __type__ hebben, en dan is het
    # gewoon data die je onaangeroerd wilt terugkrijgen.
    if soort not in ONZE_TYPES or "waarde" not in gelezen:
        return gelezen

    try:
        if soort == "datetime":
            return datetime.datetime.fromisoformat(gelezen["waarde"])
        if soort == "date":
            return datetime.date.fromisoformat(gelezen["waarde"])
        if soort == "time":
            return datetime.time.fromisoformat(gelezen["waarde"])
        if soort == "Decimal":
            return decimal.Decimal(gelezen["waarde"])
        # bytes of bytearray. Ontbreekt het codering-veld, dan komt de JSON
        # uit een versie die altijd base64 schreef.
        _, decodeer = BYTES_CODEERDERS[gelezen.get("codering", "base64")]
        ruw = decodeer(gelezen["waarde"])
        return ruw if soort == "bytes" else bytearray(ruw)
    except (ValueError, TypeError, ArithmeticError, KeyError):
        # Label klopt, inhoud niet. Liever de dict teruggeven dan de hele
        # inleesactie laten klappen op een veld dat niet van ons blijkt.
        return gelezen


_MIST = object()


def _meervoud(aantal, enkelvoud, meervoud):
    """'1 veld' maar '2 velden' - in lesmateriaal valt dat anders op."""
    return f"{aantal} {enkelvoud if aantal == 1 else meervoud}"


def _attribuutnaam(sleutel):
    """De attribuutnaam die Box voor deze key aanmaakt, of None.

    conversion_box vervangt tekens die niet in een naam mogen door een
    underscore, en zet box_safe_prefix ("x") voor een key die met een
    cijfer begint.
    """
    if not isinstance(sleutel, str):
        return None
    if sleutel.isidentifier():
        return sleutel
    kandidaat = re.sub(r"\W", "_", sleutel)
    if kandidaat[:1].isdigit():
        kandidaat = "x" + kandidaat
    return kandidaat if kandidaat.isidentifier() else None


def _toegang(doos, sleutel):
    """Hoe benader je doos[sleutel]? Geeft (achtervoegsel, opmerking).

    Dot-notatie kan niet altijd, en dat is precies wat describe() zichtbaar
    hoort te maken. Drie gevallen waarin je terug moet naar [...]:
    de key is een Python keyword, hij botst met een dict-methode zoals
    items of keys, of er valt geen geldige naam van te maken.
    """
    waarde = doos[sleutel]
    naam = _attribuutnaam(sleutel)

    if naam and not keyword.iskeyword(naam):
        # Testen, niet aannemen: bij een key als "items" geeft getattr de
        # METHODE terug in plaats van je data.
        gevonden = getattr(doos, naam, _MIST)
        if gevonden is waarde or gevonden == waarde:
            return f".{naam}", "" if naam == sleutel else f'key is "{sleutel}"'

    if naam and keyword.iskeyword(naam):
        reden = f"{naam!r} is een keyword"
    elif naam:
        reden = f"{naam!r} botst met een methode"
    else:
        reden = "geen geldige naam"
    return f"[{sleutel!r}]", reden


def _samenvatting(waarde):
    """Korte omschrijving van een waarde: type plus iets zinnigs erbij."""
    soort = type(waarde).__name__
    if isinstance(waarde, Box):
        return soort, _meervoud(len(waarde), "veld", "velden")
    if isinstance(waarde, (list, tuple)):
        return soort, _meervoud(len(waarde), "element", "elementen")
    if isinstance(waarde, (bytes, bytearray)):
        return soort, f"{len(waarde)} bytes"
    if isinstance(waarde, (datetime.date, datetime.time, decimal.Decimal)):
        # De type-kolom zegt al date/time/Decimal; repr zou dat herhalen.
        return soort, str(waarde)
    tekst = repr(waarde)
    return soort, tekst if len(tekst) <= 34 else tekst[:31] + "..."


def _opmaak(kop, uit):
    """Zet de verzamelde regels uit in kolommen."""
    breedte = max(len(pad) for pad, _, _ in uit)
    regels = [kop, "-" * len(kop)]
    for pad, waarde, opmerking in uit:
        soort, samenvatting = _samenvatting(waarde)
        regel = f"  {pad:<{breedte}}  {soort:<9} {samenvatting}"
        if opmerking:
            regel = f"{regel:<{breedte + 50}}# {opmerking}"
        regels.append(regel.rstrip())
    return "\n".join(regels)


def _verzamel(waarde, pad, uit):
    """Loopt de structuur af en verzamelt (pad, waarde, opmerking)."""
    if isinstance(waarde, Box):
        for sleutel in waarde:
            achtervoegsel, opmerking = _toegang(waarde, sleutel)
            kind = waarde[sleutel]
            uit.append((pad + achtervoegsel, kind, opmerking))
            _verzamel(kind, pad + achtervoegsel, uit)
    elif isinstance(waarde, (list, tuple)) and waarde:
        # Niet elk element tonen; het eerste laat de vorm al zien.
        uit.append((f"{pad}[0]", waarde[0], f"eerste van {len(waarde)}"))
        _verzamel(waarde[0], f"{pad}[0]", uit)


class MyBox(Box):
    """Box die zijn eigen JSON-vertaling meebrengt.

    Alleen to_json en from_json zijn aangepast; verder is het een gewone Box,
    inclusief alle opties. De drie die in startpunt.py gebruikt worden:

    box_dots
        Een heel pad naar een geneste waarde mag als een string met punten:
        doos["verzendopties.spoed"] in plaats van door de lagen heen stappen.
        Werkt ook voor schrijven, voor `in`, voor .get() en met lijst-indexen:
        doos["artikelen[0]"]. Handig zodra het pad zelf data is - uit een
        configbestand of een formulierveld - want dan hoef je die string niet
        zelf te splitsen.

        De prijs: een punt is nu geen geldig teken meer in een key. Een dict
        met bijvoorbeeld "prijs.excl.btw" erin gaat al bij het AANMAKEN
        onderuit met een BoxKeyError, niet pas bij het opvragen.

    default_box
        Een onbekende key geeft een lege Box in plaats van een KeyError.
        Handig bij optionele velden, maar typefouten blijven zo stil.

    default_box_create_on_get
        Staat standaard aan, en dan SCHRIJFT Box een opgevraagde onbekende
        key meteen in de structuur; die staat later ineens in je JSON. Zet
        hem op False als je default_box gebruikt maar je data ongemoeid wilt
        laten.

    Let op bij uitbreiden: een attribuut zetten op een Box komt in de DATA
    terecht, niet op het object. Dus geen self.iets = ... in een subclass;
    methodes en class-attributen kunnen wel.
    """

    def describe(self, naam="doos"):
        """Beschrijf in leesbare vorm welke velden erin zitten.

        Per veld het pad zoals je het intypt, het type, en een korte
        samenvatting van de waarde. Geneste Boxen en lijsten gaat het
        achterna; van een lijst toont het het eerste element, want dat
        laat de vorm al zien.

        Waar dot-notatie niet kan staat de [...]-vorm, met de reden erbij.
        Dat gebeurt bij een key die een Python keyword is, die botst met
        een dict-methode zoals items of keys, of waar geen geldige naam
        van te maken valt.

        :param naam: naam van je variabele, zodat de paden leesbaar zijn
        :return: de beschrijving als string; print() hem zelf
        """
        uit = []
        _verzamel(self, naam, uit)
        if not uit:
            return f"{naam}: lege {type(self).__name__}"
        return _opmaak(f"{naam}: {type(self).__name__} met "
                       f"{_meervoud(len(self), 'veld', 'velden')}", uit)

    def to_json(self, filename=None, encoding="utf-8", errors="strict",
                **json_kwargs):
        """Serialiseer naar JSON, met json_default al ingevuld.

        Daardoor mogen date, datetime, time, Decimal, bytes en bytearray
        gewoon in je data staan. Ze krijgen een type-label mee, zodat
        from_json ze weer als het oorspronkelijke type teruggeeft.

        Alles gaat door naar json.dumps, dus indent=, sort_keys= en de rest
        werken zoals je gewend bent. Geef je zelf een default= mee, dan wint
        die van de onze.

        :param filename: indien opgegeven, schrijft naar dat bestand
        :param encoding: bestandscodering
        :param errors: hoe om te gaan met codeerfouten
        :param json_kwargs: extra argumenten voor json.dumps
        :return: de JSON-tekst, of None als je een filename meegaf
        """
        # setdefault, zodat een aanroeper zijn eigen default= kan meegeven.
        json_kwargs.setdefault("default", json_default)
        return super().to_json(filename, encoding, errors, **json_kwargs)

    @classmethod
    def from_json(cls, json_string=None, filename=None, encoding="utf-8",
                  errors="strict", **kwargs):
        """Lees JSON in, met json_object_hook al ingevuld.

        Waarden met een type-label komen terug als date, datetime, time,
        Decimal, bytes of bytearray; al het andere wordt een gewone MyBox.

        Staat er op het hoogste niveau een lijst in plaats van een object,
        dan heb je MyBoxList nodig - deze methode gooit dan een BoxError.

        Let op: json's eigen cls= kan hier niet doorheen, want from_json is
        een classmethod en die naam is al bezet door de klasse zelf. Een
        eigen JSONDecoder gebruik je dus via json.loads, en het resultaat
        wikkel je zelf in MyBox(...).

        :param json_string: tekst om aan json.loads te geven
        :param filename: bestand om te openen en aan json.load te geven
        :param encoding: bestandscodering
        :param errors: hoe om te gaan met codeerfouten
        :param kwargs: extra argumenten voor MyBox() of json.loads
        :return: een MyBox
        """
        # from_json is een classmethod, dus de naam cls is al bezet; vandaar
        # object_hook en geen JSONDecoder-subclass.
        kwargs.setdefault("object_hook", json_object_hook)
        return super().from_json(json_string, filename, encoding, errors,
                                 **kwargs)


class MyBoxList(BoxList):
    """BoxList met dezelfde JSON-vertaling als MyBox.

    Nodig als de JSON op het hoogste niveau een lijst is in plaats van een
    object, dus [ {...}, {...} ] en niet { ... }:

        MyBoxList(orders).to_json(indent=4)
        MyBoxList.from_json(tekst)

    Met multiline=True krijg je JSON Lines, een compleet JSON-object per
    regel; zie de docstrings van to_json en from_json.

    Let op: binnen een MyBox blijven geneste lijsten een gewone BoxList.
    Box maakt die klasse hard aan en laat zich daarin niet configureren.
    Dat geeft niets voor doos.to_json() - die serialiseert de hele structuur
    vanaf de top, dus onze default= komt overal langs. Het speelt alleen als
    je to_json() rechtstreeks op zo'n geneste lijst aanroept.
    """

    def __init__(self, iterable=None, box_class=MyBox, **box_options):
        """Maak een MyBoxList waarvan de elementen MyBox-objecten worden.

        :param iterable: de lijst of iterable om in te pakken
        :param box_class: klasse voor dicts in de lijst; standaard MyBox
        :param box_options: Box-opties, zie de docstring van MyBox
        """
        super().__init__(iterable, box_class=box_class, **box_options)

    def describe(self, naam="lijst"):
        """Beschrijf de vorm van de lijst aan de hand van het eerste element.

        Een lijst is meestal homogeen - denk aan regels uit een JSON
        Lines-bestand - dus het eerste element laat de vorm al zien. Wijken
        andere elementen af, dan meldt describe dat onderaan; juist bij
        ingelezen data is dat het soort verrassing dat je wilt zien.

        :param naam: naam van je variabele, zodat de paden leesbaar zijn
        :return: de beschrijving als string; print() hem zelf
        """
        soort = type(self).__name__
        if not self:
            return f"{naam}: lege {soort}"

        eerste = self[0]
        uit = []
        _verzamel(eerste, f"{naam}[0]", uit)
        kop = (f"{naam}: {soort} met "
               f"{_meervoud(len(self), 'element', 'elementen')}")
        if uit:
            tekst = _opmaak(kop, uit)
        else:
            # Een lijst met kale waarden erin valt niet uit te klappen.
            tekst = _opmaak(kop, [(f"{naam}[0]", eerste,
                                   f"eerste van {len(self)}")])


        if isinstance(eerste, Box):
            velden = set(eerste.keys())
            anders = [i for i, e in enumerate(self)
                      if not isinstance(e, Box) or set(e.keys()) != velden]
            if anders:
                tekst += (f"\n\n  Let op: {len(anders)} van de {len(self)} "
                          f"elementen "
                          f"{'heeft' if len(anders) == 1 else 'hebben'} "
                          f"andere velden, vanaf index {anders[0]}.")
        return tekst

    def to_json(self, filename=None, encoding="utf-8", errors="strict",
                multiline=False, **json_kwargs):
        """Serialiseer de lijst naar JSON, met json_default al ingevuld.

        Net als bij MyBox.to_json mogen date, datetime, time, Decimal,
        bytes en bytearray gewoon in je data staan.

        Met multiline=True krijg je JSON Lines: een compleet JSON-object
        per regel, zonder omsluitende [ ] en zonder komma's. Zo kun je
        regels toevoegen of lezen zonder het hele bestand in te laden -
        vandaar dat logs en grote datasets dit formaat gebruiken.

        Twee dingen om te weten over multiline, allebei van Box zelf:

        * Het werkt ALLEEN samen met een filename. Zonder bestandsnaam
          wordt de vlag genegeerd en krijg je gewoon een JSON-array
          terug, zonder enige waarschuwing.
        * Schrijven naar een bestand geeft None terug, niet de tekst.
          De regels worden aaneengeregen met een newline ertussen, maar
          het bestand eindigt niet op een newline.

        :param filename: indien opgegeven, schrijft naar dat bestand
        :param encoding: bestandscodering
        :param errors: hoe om te gaan met codeerfouten
        :param multiline: een object per regel; vereist een filename
        :param json_kwargs: extra argumenten voor json.dumps
        :return: de JSON-tekst, of None als je een filename meegaf
        """
        json_kwargs.setdefault("default", json_default)
        return super().to_json(filename, encoding, errors, multiline,
                               **json_kwargs)

    @classmethod
    def from_json(cls, json_string=None, filename=None, encoding="utf-8",
                  errors="strict", multiline=False, **kwargs):
        """Lees een JSON-lijst in, met json_object_hook al ingevuld.

        De elementen worden MyBox-objecten, en waarden met een type-label
        komen terug als date, datetime, time, Decimal, bytes of bytearray.

        Staat er op het hoogste niveau een object in plaats van een lijst,
        dan gooit dit een BoxError; gebruik dan MyBox.from_json.

        Met multiline=True lees je JSON Lines, uit een bestand of uit een
        string. Dat laatste is een uitbreiding op BoxList: die splitst
        alleen bij een filename en struikelt over een string met meerdere
        regels, met JSONDecodeError: Extra data.

        :param json_string: tekst met JSON, of met een object per regel
        :param filename: bestand om te openen
        :param encoding: bestandscodering
        :param errors: hoe om te gaan met codeerfouten
        :param multiline: lees een object per regel
        :param kwargs: extra argumenten voor MyBox() of json.loads
        :return: een MyBoxList
        """
        kwargs.setdefault("object_hook", json_object_hook)
        if json_string is not None and multiline:
            # Box splitst alleen bij een filename; voor een string doen we
            # het zelf. Lege regels overslaan, want JSON Lines-bestanden
            # eindigen vaak met een newline.
            return cls([MyBox.from_json(regel, **kwargs)
                        for regel in json_string.splitlines() if regel.strip()])
        return super().from_json(json_string, filename, encoding, errors,
                                 multiline, **kwargs)
