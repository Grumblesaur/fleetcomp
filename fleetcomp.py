import json
import sys
import copy
import argparse
from enum import StrEnum
from pathlib import Path
from typing import Self, Iterator, Callable
from collections import Counter
from itertools import combinations
from more_itertools import take, ilen


class ShipType(StrEnum):
    SS = "SS"
    DD = "DD"
    CA = "CA"
    BB = "BB"
    CV = "CV"


class ConfigurationError(Exception):
    pass


class Quit(Exception):
    pass


class Ship:
    def __init__(self, ship_name: str, ship_type: ShipType | str, player: str):
        self.name = ship_name
        self.type = ship_type if isinstance(ship_type, ShipType) else ShipType(ship_type)
        self.player = player

    def __hash__(self):
        return hash((self.__class__, self.name, self.type, self.player))

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name!r}, {self.type!r}, {self.player!r})'


class Player:
    def __init__(self, name: str, ships: dict[str, list]):
        self.name = name
        shipset = set[Ship]()
        for ship_type_str, ship_list in ships.items():
            for ship_name in ship_list:
                shipset.add(Ship(ship_name, ShipType(ship_type_str), name))
        self.ships = frozenset(shipset)

    def __bool__(self) -> bool:
        return bool(self.ships)

    def __repr__(self):
        return f'<{self.__class__.__name__}: {self.name}>'


class RestrictionSet:
    def __init__(self, rules: dict[str, dict], team_size: int = 7, tier: int = 10):
        bans = rules.pop('Banned', {})
        self.size_limit = rules.pop('TeamSize', team_size)
        self.tier = rules.pop('Tier', tier)
        self.banned_ships = set(bans.pop('ships', []))
        self.banned_types = set(bans.pop('types', []))
        self.restrictions = {}
        for name, rule in rules.items():
            self.restrictions[name] = {
                "rtype": rule["rtype"],
                rule["rtype"]: rule[rule["rtype"]],
                "allowed": rule["allowed"],
            }

    def with_team_size(self, n: int) -> Self:
        new = copy.deepcopy(self)
        new.size_limit = n
        return new

    def is_banned(self, ship: Ship) -> bool:
        return ship.name in self.banned_ships or ship.type in self.banned_types


    @classmethod
    def load(cls, json_path: Path, team_size: int = 7) -> Self:
        with open(json_path, 'r', encoding='utf-8') as f:
            return cls(json.load(f), team_size=team_size)

    def is_valid(self, composition: set[Ship]) -> bool:
        if len(composition) > self.size_limit:
            return False
        rcounts = Counter()
        for ship in composition:
            if self.is_banned(ship):
                return False
            for rname, rinfo in self.restrictions.items():
                if rinfo["rtype"] == "ships":
                    rcounts[rname] += ship.name in rinfo["ships"]
                else:
                    rcounts[rname] += ship.type in rinfo["types"]
        for rule, c in rcounts.items():
            if c > self.restrictions[rule]["allowed"]:
                return False
        return True

    def is_full_team(self, composition: set[Ship]) -> bool:
        return len(composition) == self.size_limit

    def team_compositions(self, selected: set[Ship], group: list[Player]) -> Iterator[set[Ship]]:
        if self.is_valid(selected) and self.is_full_team(selected):
            yield selected
            return
        if not group:
            return
        for ship in group[0].ships:
            yield from self.team_compositions(selected | {ship}, group[1:])



class Team:
    def __init__(self, players: set[Player]):
        self.players = players

    @classmethod
    def load(cls, team_json: Path, tier: int) -> Self:
        with open(team_json, 'r', encoding='utf-8') as f:
             team_info = json.load(f)
        players = set()
        tier_key = str(tier)
        for name, player_info in team_info.items():
            players.add(Player(name, player_info[tier_key]))
        return cls(players)

    def select(self, names: set[str]):
        return self.__class__({player for player in self.players if player.name in names})

    def menu(self, team_size: int):
        options = {i: p.name for i, p in enumerate(self.players) if p}
        if (x := len(options)) < team_size:
            raise ConfigurationError(f'Team requires {team_size} players, but only {x} players have available ships. '
                                     f'Pass argument --team-size-override={x} to see what partial builds you can make.')
        while True:
            print(f"Who's playing? Enter {team_size} numbers separated by commas, or Q to quit.")
            for choice, name in options.items():
                print(f'{choice}:\t{name}')
            print()
            selections = input('Player numbers: ')
            if 'q' in selections.casefold():
                raise Quit("Team selection menu.")
            try:
                chosen_numbers = [int(s.strip()) for s in selections.split(',')]
            except ValueError:
                print(f'Invalid selection in {selections}. Try again.')
                print()
            else:
                if (x := len(chosen_numbers)) != team_size:
                    print(f'{x} teammates were selected, but {team_size} were needed. Try again.')
                else:
                    break
        chosen_names = {options[i] for i in chosen_numbers}
        return self.select(chosen_names)

    def generate_comps(self, restriction_set: RestrictionSet) -> Iterator[set[Ship]]:
        for group in combinations(self.players, restriction_set.size_limit):
            yield from restriction_set.team_compositions(set(), list(group))


def comps(team_data: Path = Path("team.json"), restriction_data: Path = Path("restrictions/31.json"), tso: int = None):
    # XXX: the head of this function and count() are similar;
    # we should perform this common boilerplate before dispatching to one or the other
    restrictions = RestrictionSet.load(restriction_data)
    if tso is not None:
        restrictions = restrictions.with_team_size(tso)
    team = Team.load(team_data, tier=restrictions.tier)
    division = team.menu(restrictions.size_limit)
    n = 1
    to_take = 1
    compgen = division.generate_comps(restrictions)
    while True:
        comp_batch = take(to_take, compgen)
        if not comp_batch:
            print(f'All {n} compositions have been expended.')
            break
        for comp in comp_batch:
            print(f"=== Composition #{n} ===")
            for ship in sorted(comp, key=lambda s: str(s.type)):
                print(f'{ship.player}: [{ship.type}] {ship.name}')
            n += 1
            print()
        instruction = input(f"Enter number of builds to generate, blank for 1, or Q to quit: ")
        if instruction.casefold().startswith('q'):
            break
        try:
            to_take = int(instruction)
        except ValueError:
            to_take = 1


def count(team_data: Path = Path("team.json"), restriction_data: Path = Path('restrictions/31.json'), tso: int = None):
    restrictions = RestrictionSet.load(restriction_data)
    team = Team.load(team_data, tier=restrictions.tier)
    if tso is not None:
        restrictions = restrictions.with_team_size(tso)
    if (x := sum(bool(player) for player in team.players)) < restrictions.size_limit:
        raise ConfigurationError(f'Team requires {restrictions.size_limit} players, but only {x} players have available ships. '
                                 f'Pass argument --team-size-override={x} to see what partial builds you can make.')
    compgen = team.generate_comps(restrictions)
    print("Legal team compositions:", ilen(compgen))


def dispatch(command: str) -> Callable:
    return {'comps': comps, 'count': count}[command]


def restriction_lookup(season_number: int) -> Path:
    if (p := Path(f'restrictions/{season_number}.json')).exists():
        return p
    raise ConfigurationError(f'Restrictions for season {season_number} not defined.')


def build_parser():
    parser = argparse.ArgumentParser(prog=sys.argv[0],
                                     description="Generate teamp compositions for clan battles.",
                                     epilog='')
    parser.add_argument('command', choices=['comps', 'count'])
    parser.add_argument('-t', '--team', type=Path, help="Specify a path to the team file (team.json will be used by default")
    parser.add_argument('-o', '--team-size-override', type=int, help="Specify a team size to override that of the restrictions.")
    rgroup = parser.add_mutually_exclusive_group()
    rgroup.add_argument('-r', '--restrictions', type=Path, help="Specify a path to the restrictions file.")
    rgroup.add_argument('-s', '--season', type=int, help="Specify a season number to look up restrictions for.")
    return parser


def main():
    parser = build_parser()
    namespace = parser.parse_args()
    if namespace.season:
        restriction_set = restriction_lookup(namespace.season)
    else:
        restriction_set = namespace.restrictions
    if namespace.team:
        team = namespace.team
    else:
        team = Path("team.json")

    tso = namespace.team_size_override
    procedure = dispatch(namespace.command)
    procedure(team_data=team, restriction_data=restriction_set, tso=tso)


if __name__ == '__main__':
    try:
        main()
    except Quit:
        pass
