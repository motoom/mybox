"""Tests voor mybox.

Draaien met:

    python3 -m unittest test_mybox -v
    python3 test_mybox.py

Het zwaartepunt ligt op het INLEZEN van JSON uit andere systemen. Die JSON
bevat geen datetimes of Decimals, maar wel keys waar dot-notatie op stukloopt
en af en toe iets dat op ons type-label lijkt. De eigen serialisatie wordt
getest op een round-trip per type; de coderingen anders dan base64 niet, die
zijn een keuzemogelijkheid en geen hoofdweg.
"""

import datetime
import decimal
import json
import pathlib
import tempfile
import unittest

from box import BoxError

from mybox import MyBox, MyBoxList, json_default, json_object_hook


class VreemdeJsonInlezen(unittest.TestCase):
    """Het hoofdgebruik: JSON van elders naar binnen halen."""

    def test_gewoon_object(self):
        doos = MyBox.from_json('{"naam": "Klaas", "leeftijd": 42}')
        self.assertEqual(doos.naam, "Klaas")
        self.assertEqual(doos.leeftijd, 42)

    def test_json_types_blijven_wat_ze_zijn(self):
        doos = MyBox.from_json(
            '{"s": "tekst", "i": 42, "f": 1.5, "b": true, "n": null}')
        self.assertIsInstance(doos.s, str)
        self.assertIsInstance(doos.i, int)
        self.assertIsInstance(doos.f, float)
        self.assertIs(doos.b, True)
        self.assertIsNone(doos.n)

    def test_nesting_en_lijsten(self):
        doos = MyBox.from_json('{"a": {"b": {"c": [1, {"d": 2}]}}}')
        self.assertEqual(doos.a.b.c[0], 1)
        self.assertEqual(doos.a.b.c[1].d, 2)

    def test_unicode(self):
        doos = MyBox.from_json('{"naam": "Jos\\u00e9", "emoji": "\\ud83d\\udce6"}')
        self.assertEqual(doos.naam, "José")
        self.assertEqual(doos.emoji, "📦")

    def test_lijst_op_hoogste_niveau_vraagt_om_MyBoxList(self):
        with self.assertRaises(BoxError):
            MyBox.from_json('[{"a": 1}]')
        lijst = MyBoxList.from_json('[{"a": 1}, {"a": 2}]')
        self.assertEqual([e.a for e in lijst], [1, 2])

    def test_uit_bestand(self):
        with tempfile.TemporaryDirectory() as tijdelijk:
            pad = pathlib.Path(tijdelijk, "data.json")
            pad.write_text('{"a": 1}', encoding="utf-8")
            self.assertEqual(MyBox.from_json(filename=pad).a, 1)


class VreemdeKeys(unittest.TestCase):
    """JSON van buiten zit vol keys waar dot-notatie op vastloopt."""

    def test_streepje_krijgt_een_alias(self):
        doos = MyBox.from_json('{"created-at": "2026-09-12"}')
        self.assertEqual(doos.created_at, "2026-09-12")
        self.assertEqual(doos["created-at"], "2026-09-12")
        # De originele key blijft staan, de alias is geen extra veld:
        self.assertEqual(list(doos.keys()), ["created-at"])

    def test_spatie_krijgt_ook_een_alias(self):
        self.assertEqual(MyBox({"met spatie": 1}).met_spatie, 1)

    def test_cijfer_aan_het_begin_krijgt_x_ervoor(self):
        # box_safe_prefix, standaard "x"
        self.assertEqual(MyBox({"2026": "jaar"}).x2026, "jaar")

    def test_botsing_met_dict_methode_geeft_de_methode(self):
        # Dit is geen bug maar wel een valkuil: .items is de methode.
        doos = MyBox({"items": "mijn waarde"})
        self.assertTrue(callable(doos.items))
        self.assertEqual(doos["items"], "mijn waarde")

    def test_keyword_alleen_via_haakjes(self):
        # getattr werkt, maar doos.class is een SyntaxError in je broncode.
        doos = MyBox({"class": "A"})
        self.assertEqual(doos["class"], "A")
        self.assertEqual(getattr(doos, "class"), "A")


class TypeLabelRoundTrip(unittest.TestCase):
    """Onze eigen serialisatie: eruit en er weer in."""

    def test_alle_types(self):
        origineel = {
            "date": datetime.date(2026, 9, 12),
            "datetime": datetime.datetime(2026, 9, 12, 14, 30),
            "datetime-tz": datetime.datetime(
                2026, 9, 12, 14, 30, tzinfo=datetime.timezone.utc),
            "time": datetime.time(9, 0),
            "time-tz": datetime.time(17, 30, tzinfo=datetime.timezone.utc),
            "Decimal": decimal.Decimal("27.50"),
            "bytes": b"\x3a\x91\x07\xff",
            "bytearray": bytearray(b"abc"),
        }
        doos = MyBox(origineel)
        terug = MyBox.from_json(doos.to_json())
        self.assertEqual(terug.to_dict(), origineel)
        for sleutel, waarde in origineel.items():
            self.assertIs(type(terug[sleutel]), type(waarde), sleutel)

    def test_decimal_houdt_trailing_nul(self):
        terug = MyBox.from_json(MyBox({"p": decimal.Decimal("27.50")}).to_json())
        self.assertEqual(str(terug.p), "27.50")

    def test_datetime_gaat_voor_date(self):
        # datetime is een subclass van date; verkeerde vololgorde in
        # json_default kost je de tijdcomponent.
        label = json_default(datetime.datetime(2026, 9, 12, 14, 30))
        self.assertEqual(label["__type__"], "datetime")

    def test_onbekend_type_geeft_TypeError(self):
        with self.assertRaises(TypeError):
            MyBox({"x": {1, 2}}).to_json()      # een set kan niet


class VreemdTypeLabel(unittest.TestCase):
    """Vreemde JSON mag toevallig ook een veld __type__ hebben."""

    def test_onbekend_label_blijft_staan(self):
        doos = MyBox.from_json('{"a": {"__type__": "Gebruiker", "naam": "x"}}')
        self.assertEqual(doos.a.naam, "x")
        self.assertEqual(doos.a["__type__"], "Gebruiker")

    def test_bekend_label_zonder_waarde_blijft_staan(self):
        doos = MyBox.from_json('{"a": {"__type__": "date"}}')
        self.assertIsInstance(doos.a, MyBox)

    def test_bekend_label_met_onzin_blijft_staan(self):
        doos = MyBox.from_json(
            '{"a": {"__type__": "Decimal", "waarde": "geen getal"}}')
        self.assertIsInstance(doos.a, MyBox)

    def test_label_dat_geen_string_is(self):
        self.assertIsInstance(MyBox.from_json('{"a": {"__type__": 42}}').a, MyBox)


class JsonLines(unittest.TestCase):

    ORDERS = [{"nr": 1, "naam": "Klaas"}, {"nr": 2, "naam": "Pietje"}]

    def test_schrijven_en_lezen_via_bestand(self):
        with tempfile.TemporaryDirectory() as tijdelijk:
            pad = pathlib.Path(tijdelijk, "orders.jsonl")
            retour = MyBoxList(self.ORDERS).to_json(pad, multiline=True)
            self.assertIsNone(retour)        # schrijven geeft None terug
            self.assertEqual(len(pad.read_text().splitlines()), 2)
            terug = MyBoxList.from_json(filename=pad, multiline=True)
            self.assertEqual(terug.to_list(), self.ORDERS)

    def test_lezen_uit_string(self):
        # Kale BoxList struikelt hierover; MyBoxList vangt het af.
        tekst = "\n".join(json.dumps(o) for o in self.ORDERS)
        self.assertEqual(MyBoxList.from_json(tekst, multiline=True).to_list(),
                         self.ORDERS)

    def test_lege_regels_worden_overgeslagen(self):
        tekst = "\n".join(json.dumps(o) for o in self.ORDERS) + "\n\n"
        self.assertEqual(len(MyBoxList.from_json(tekst, multiline=True)), 2)

    def test_multiline_zonder_filename_wordt_genegeerd(self):
        # Gedrag van Box zelf: je krijgt een gewone array, zonder waarschuwing.
        uit = MyBoxList(self.ORDERS).to_json(multiline=True)
        self.assertTrue(uit.lstrip().startswith("["))


class Describe(unittest.TestCase):

    def test_toont_pad_en_waarde(self):
        tekst = MyBox({"a": {"b": 1}}).describe("d")
        self.assertIn("d.a.b", tekst)
        self.assertIn("1", tekst)

    def test_alias_wordt_gemeld(self):
        tekst = MyBox({"created-at": 1}).describe("d")
        self.assertIn("d.created_at", tekst)
        self.assertIn('key is "created-at"', tekst)

    def test_haakjes_waar_dot_niet_kan(self):
        tekst = MyBox({"items": 1, "class": 2, "2026": 3}).describe("d")
        self.assertIn("d['items']", tekst)
        self.assertIn("d['class']", tekst)
        self.assertIn("d.x2026", tekst)       # deze kan juist wel

    def test_lijst_toont_eerste_element(self):
        tekst = MyBox({"regels": [{"art": "OP205"}]}).describe("d")
        self.assertIn("d.regels[0].art", tekst)

    def test_lege_box(self):
        self.assertIn("lege", MyBox({}).describe("d"))

    def test_lijst_meldt_afwijkende_elementen(self):
        tekst = MyBoxList([{"a": 1, "b": 2}, {"a": 1}]).describe("l")
        self.assertIn("Let op", tekst)
        self.assertIn("index 1", tekst)

    def test_homogene_lijst_meldt_niets(self):
        tekst = MyBoxList([{"a": 1}, {"a": 2}]).describe("l")
        self.assertNotIn("Let op", tekst)

    def test_enkelvoud_en_meervoud(self):
        self.assertIn("1 veld", MyBox({"a": 1}).describe("d"))
        self.assertIn("2 velden", MyBox({"a": 1, "b": 2}).describe("d"))


class BoxGedragDatWeAannemen(unittest.TestCase):
    """Aannames over Box waar mybox op leunt; breken die, dan breekt mybox."""

    def test_subclass_plant_zich_voort(self):
        doos = MyBox({"a": {"b": 1}, "lijst": [{"c": 2}]})
        self.assertIsInstance(doos.a, MyBox)
        self.assertIsInstance(doos.lijst[0], MyBox)
        self.assertIsInstance(MyBox.from_json('{"a": {"b": 1}}').a, MyBox)

    def test_MyBoxList_maakt_MyBox_elementen(self):
        self.assertIsInstance(MyBoxList([{"a": 1}])[0], MyBox)

    def test_eigen_default_wint(self):
        uit = MyBox({"d": datetime.date(2026, 9, 12)}).to_json(
            default=lambda w: "vervangen")
        self.assertIn("vervangen", uit)

    def test_box_opties_werken_nog(self):
        doos = MyBox({"a": {"b": 1}}, box_dots=True, default_box=True,
                     default_box_create_on_get=False)
        self.assertEqual(doos["a.b"], 1)
        self.assertEqual(doos.bestaat_niet, MyBox())
        self.assertNotIn("bestaat_niet", doos)      # create_on_get uit


if __name__ == "__main__":
    unittest.main(verbosity=2)
