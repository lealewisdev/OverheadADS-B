import csv

import pdfplumber

types: dict[str, list[str]] = {
    "landplane": [],
    "amphibian": [],
    "seaplane": [],
    "gyroplane": [],
    "helicopter": [],
    "powered_lift": [],
}

CATEGORY_MAP: dict[str, str] = {
    "Fixed-wing": "landplane",
    "@Fixed-wing": "amphibian",
    "$Fixed-wing": "seaplane",
    "Gyroplane": "gyroplane",
    "Helicopter": "helicopter",
    "Powered-lift": "powered_lift",
}

TABLE_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
}


def csv_by_type() -> None:
    for aircraft_class, designators in types.items():
        with open(f"{aircraft_class}.csv", "w", newline="") as f:
            writer = csv.writer(f)
            for icao in designators:
                writer.writerow([icao])


def main() -> None:
    with pdfplumber.open("faa.pdf") as pdf:
        for page in pdf.pages[9:121]:
            for row in page.extract_table(TABLE_SETTINGS) or []:
                if len(row) < 2:
                    continue
                icao, category = row[0], row[1]
                aircraft_class = CATEGORY_MAP.get(str(category))
                if icao and aircraft_class:
                    types[aircraft_class].append(str(icao))
    csv_by_type()


if __name__ == "__main__":
    main()
