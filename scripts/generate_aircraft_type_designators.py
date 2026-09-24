from __future__ import annotations

import csv
from typing import cast

import httpx
import nodriver as nd
from defusedxml import ElementTree as ET

type Row = dict[str, str | list[str]]

KEYS: list[str] = [
    "ICAO Code",
    "Classification",
    "Category",
    "Wing Span(m)",
    "Length(m)",
    "Height(m)",
    "MTOW(t)",
    "Fuel Capacity(ltr)",
    "Maximum Range(Nm)",
    "Persons On Board",
    "Take Off Distance(m)",
    "Landing Distance(m)",
    "Absolute Ceiling(x100ft)",
    "Optimum Ceiling(x100ft)",
    "Maximum Speed(kts / M)",
    "Optimum Speed(kts / M)",
    "Maximum Climb Rate(ft / min)",
    "List of Manufacturers",
]


def get_sitemap() -> None:
    url = "https://doc8643.com/static/sitemap.xml"
    r = httpx.get(url)
    with open("sitemap.xml", "wb") as f:
        _ = f.write(r.content)


# Had to remove 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' from the root tag for it to parse
def parse_xml(xmlfile: str) -> list[str]:
    tree = ET.parse(xmlfile)
    root = tree.getroot()
    assert root is not None, f"{xmlfile} has no root element"
    endpoints: list[str] = []
    for url in root.findall("url"):
        loc = url.find("loc")
        if loc is None or loc.text is None:
            continue
        if "/aircraft/" in loc.text:
            endpoints.append(loc.text)
    return endpoints


async def scrape_aircraft(browser: nd.Browser, endpoint: str) -> list[Row]:
    values: list[str | list[str]] = []
    data: Row = {}

    tab: nd.Tab = await browser.get(endpoint)
    await tab.sleep(3)
    await tab.get_content()

    code_class_cat: list[nd.Element] = await tab.select_all("h1")
    for each in code_class_cat:
        values.append(each.text)

    tech: list[nd.Element] = await tab.select_all(".tech-data")
    tech_values = cast("list[nd.Element]", await tech[0].query_selector_all(".pe-0"))
    for each in tech_values:
        values.append(each.text)

    manufacturers = cast("list[nd.Element]", await tech[1].query_selector_all(".pe-1"))
    temp: list[str] = [each.text for each in manufacturers]
    values.append(temp)

    for index, each in enumerate(values):
        data[KEYS[index]] = each

    return [data]


async def main() -> list[Row]:
    # get_sitemap()
    endpoints = parse_xml("sitemap.xml")
    browser = await nd.start(headless=True)

    rows: list[Row] = []
    for index, endpoint in enumerate(endpoints):
        rows.extend(await scrape_aircraft(browser, endpoint))
        print(index)

    return rows


if __name__ == "__main__":
    all_rows = nd.loop().run_until_complete(main())

    with open("icao.csv", "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=KEYS)
        writer.writeheader()
        writer.writerows(all_rows)
