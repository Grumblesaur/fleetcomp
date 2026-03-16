import sys
import json
import csv
from pathlib import Path
from typing import Iterator

Columns = ['Player', 'Ship', 'Tier', 'Type']
Format = '{Player},{Ship},{Tier},{Type}'

def create_rows(deserialized_json: dict) -> Iterator[dict]:
    for username, ship_tiers in deserialized_json.items():
        for tier, ship_types in ship_tiers.items():
            for ship_type, ships in ship_types.items():
                for ship in ships:
                    yield dict(zip(Columns, [username, ship, tier, ship_type]))


def main():
    files = [Path(arg) for arg in sys.argv[1:]]
    if not files:
        files = [Path('team.json')]

    for json_file in files:
        with open(json_file, 'r', encoding='utf-8') as jf:
            deserialized_json = json.load(jf)
        with open(json_file.with_name(json_file.stem + '.csv'), 'w', encoding='utf-8') as cf:
            dw = csv.DictWriter(cf, fieldnames=Columns)
            for row in create_rows(deserialized_json):
                dw.writerow(row)


if __name__ == '__main__':
    main()