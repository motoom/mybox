"""Vergelijkt manieren om bytes als tekst in JSON te krijgen.

Hoort bij startpunt.py, waar de serializer bytes met base64 codeert.
JSON kent alleen tekst, dus binaire data moet gecodeerd worden. Dat kan op
veel manieren; dit script zet ze naast elkaar op de dingen die tellen:
grootte, leesbaarheid, en of je je data ongeschonden terugkrijgt.

Belangrijk: we meten de lengte NA json.dumps(), niet de kale codering.
JSON moet sommige tekens escapen, en dat verschil is precies waar een paar
theoretisch-zuinige coderingen alsnog sneuvelen.
"""

import base64
import json
import random

# Twee testgevallen: een korte sleutel, en een grotere blob om de
# overhead zichtbaar te maken. Vaste seed, zodat iedereen dezelfde uitkomst
# krijgt - met os.urandom() varieert de laatste kolom per run.
XORKEY = b"\x3a\x91\x07\xff\x42\x00\xbe\x6d\x18\xc3"
BLOB = random.Random(0).randbytes(3000)

CODERINGEN = {
    # naam:            (coderen,                                    decoderen)
    "hex (base16)":    (lambda b: b.hex(),                          bytes.fromhex),
    "base32":          (lambda b: base64.b32encode(b).decode(),     base64.b32decode),
    "base64":          (lambda b: base64.b64encode(b).decode(),     base64.b64decode),
    "base64 urlsafe":  (lambda b: base64.urlsafe_b64encode(b).decode(),
                        base64.urlsafe_b64decode),
    "base85":          (lambda b: base64.b85encode(b).decode(),     base64.b85decode),
    "ascii85":         (lambda b: base64.a85encode(b).decode(),     base64.a85decode),
    # De latin-1 truc: elke byte 0-255 mapt op precies een codepoint, dus
    # technisch lossless. Kijk wat JSON ermee doet.
    "latin-1 truc":    (lambda b: b.decode("latin-1"),
                        lambda s: s.encode("latin-1")),
}


def toon(tekst, breedte=26):
    """Laat de codering zien, of een repr als het geen leesbare tekst is."""
    if len(tekst) <= breedte and tekst.isprintable():
        return tekst
    return (repr(tekst)[:breedte - 2] + "..")


if __name__ == "__main__":
    kop = f"{'codering':16} {'XORKEY als tekst':26} {'ruw':>6} {'JSON':>6} {'escape':>7} {'3000B':>7} {'=':>5}"
    print(kop)
    print("-" * len(kop))

    for naam, (codeer, decodeer) in CODERINGEN.items():
        tekst = codeer(XORKEY)

        # json.dumps zet er aanhalingstekens omheen (+2) en escapet wat moet.
        ruw_blob = codeer(BLOB)
        json_blob = json.dumps(ruw_blob)
        escape_kosten = len(json_blob) - len(ruw_blob) - 2

        lossless = decodeer(codeer(XORKEY)) == XORKEY

        print(f"{naam:16} {toon(tekst):26} "
              f"{len(ruw_blob):>6} {len(json_blob):>6} {escape_kosten:>7} "
              f"{len(json_blob) / len(BLOB):>6.2f}x {lossless!s:>5}")

    print()
    print("Te lezen als:")
    print("  ruw     = lengte van de codering zelf (3000 bytes invoer)")
    print("  JSON    = lengte na json.dumps(), dus wat er echt op schijf staat")
    print("  escape  = wat JSON er bovenop legt aan escape-sequences")
    print("  3000B   = overhead t.o.v. de ruwe bytes, na JSON")
    print()
    print("Wat opvalt:")
    print("  * latin-1 is lossless, maar levert controletekens op die JSON als")
    print("    \\u00XX moet escapen: zes tekens per byte. Daarmee de duurste.")
    print("  * ascii85 en base85 zijn ruw even groot, maar het Adobe-alfabet")
    print("    van ascii85 bevat \" en \\ en betaalt dus escape-kosten.")
    print("  * base85 is het zuinigst, base64 kost 6% meer. startpunt.py kiest")
    print("    toch base64: dat zit in elke taal, base85 praktisch alleen in")
    print("    Python - en dan nog in twee onderling incompatibele varianten.")
    print("  * hex is het duurst van de serieuze opties, maar leest als je")
    print("    bronliteral. Bij korte sleutels is dat vaak meer waard.")
