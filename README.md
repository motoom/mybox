# mybox

Een herbruikbare `MyBox`-klasse bovenop
[python-box](https://github.com/cdgriffith/Box), die JSON-serialisatie
meebrengt voor types die `json` zelf niet kent. Bedoeld als bouwsteen om in
eigen scripts te importeren.

## Het probleem

```python
order = {"besteld-op": datetime.date(2026, 9, 12),
         "prijs": decimal.Decimal("27.50")}

json.dumps(order)
# TypeError: Object of type date is not JSON serializable
```

## De oplossing

```python
from mybox import MyBox

doos = MyBox(order)
tekst = doos.to_json(indent=4)
terug = MyBox.from_json(tekst)     # date en Decimal komen intact terug
```

Elke omgezette waarde krijgt een type-label mee, zodat bij het inlezen nog
te zien is wat het was:

```json
"prijs": {"__type__": "Decimal", "waarde": "27.50"}
```

Ondersteund: `date`, `datetime`, `time`, `Decimal`, `bytes` en `bytearray`.

## Bestanden

| bestand | |
|---|---|
| `mybox.py` | `MyBox` en `MyBoxList` - dit is waar het om gaat |
| `test_mybox.py` | 35 tests |
| `startpunt.py` | voorbeelden: attribuut-toegang, JSON, JSON Lines, Jinja2 |
| `coderingen.py` | vergelijking van manieren om bytes in JSON te zetten |
| `startpunt-oud.py` | het bestand van voor MyBox, als vergelijking |
| `pyproject.toml` | pakketdefinitie, voor `pip install -e .` |

## Extra's

`describe()` zet alle velden op een rij, met het pad zoals je het intypt:

```
doos: MyBox met 7 velden
  doos.naam              str       'Klaas Vaak'
  doos.besteld_op        date      2026-09-12    # key is "besteld-op"
  doos.bezorgvenster     MyBox     2 velden
  doos.bezorgvenster.van time      09:00:00
```

Waar dot-notatie niet kan - een key die een Python keyword is, of die botst
met een dict-methode zoals `items` - toont het de `[...]`-vorm met de reden.

`MyBoxList` doet hetzelfde voor JSON waarvan het hoogste niveau een lijst is,
inclusief JSON Lines (`multiline=True`).

## Installeren

Als afhankelijkheid in een ander project, rechtstreeks vanaf GitHub:

```
pip install git+https://github.com/motoom/mybox.git
```

Werkt ook in een `requirements.txt`. Zet er een tag of commit-hash achter
voor een installatie die niet meeverandert als `mybox.py` later wijzigt:

```
pip install git+https://github.com/motoom/mybox.git@v0.1.0
```

Om `mybox.py` zelf te bewerken, clone je de repo en installeer je editable:

```
git clone https://github.com/motoom/mybox.git
cd mybox
pip install -e .
```

De `-e` houdt `mybox.py` op zijn plek, zodat wijzigingen meteen doorwerken in
elk script dat het importeert. `python-box` wordt in beide gevallen als
afhankelijkheid meegeïnstalleerd.

## Draaien

```
python3 startpunt.py
python3 -m unittest test_mybox -v
```

Het Jinja2-voorbeeld in `startpunt.py` wordt overgeslagen als Jinja2 niet
geïnstalleerd is; de rest draait zonder.

## Licentie

MIT, zie [LICENSE](LICENSE).
