

import datetime
import decimal

# Een voorbeeld data structuur:

order = {
    "naam": "Klaas Vaak",
    "email": "k.vaak@gmail.com",
    "artikelen": ["OP205", "OP210", "TS216", "PZ001"],
    "besteld-op": datetime.date(2026,9,12),
    "prijs": decimal.Decimal("27.50"),
    "verzendopties": {
        "spoed": False,
        "handtekening": True,
        }
    }


if __name__ == "__main__":
    print(order)
    import json
    print(json.dumps(order, indent=4, sort_keys=True)) # faalt omdat JSON standaard geen datetimes en decimals kan serialiseren
