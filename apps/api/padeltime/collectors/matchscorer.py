"""Read the public order-of-play widget linked by the official FIP website.

The widget's court columns contain the mixed men's/women's sequence. Join only
complete, unique team identities; never use match IDs, scores or API list order
as a substitute for the published sequence.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlsplit

WIDGET = 'https://widget.matchscorerlive.com'


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: object = None

    def find(self, tag=None, cls=None):
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and (cls is None or cls in child.attrs.get('class', '').split()):
                    yield child
                yield from child.find(tag, cls)

    def text(self):
        return ' '.join(c.text() if isinstance(c, Node) else c for c in self.children).strip()


class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node('root')
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), parent=self.current)
        self.current.children.append(node)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.current = node

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def normalized(value):
    value = unicodedata.normalize('NFKD', value)
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c)).lower()).strip()


def widget_path(record, day):
    from datetime import date
    organization = str(record.get('organization', ''))
    code, year = str(record.get('event_code', '')), str(record.get('year', ''))
    if organization != 'FIP' or not code.isdigit() or not re.fullmatch(r'20\d{2}', year):
        return None
    index = (date.fromisoformat(day) - date.fromisoformat(record['start_date_utc'][:10])).days + 1
    if index < 1 or day > record['end_date_utc'][:10]:
        return None
    return f'/screen/oopbyday/{organization}-{year}-{code}/{index}?t=tol'


def read_courts(html, source_url=None):
    root = Tree(html).root
    if source_url:
        selected = [n for n in root.find(cls='play-day-button') if 'active' in n.attrs.get('class', '').split()]
        if len(selected) != 1 or selected[0].parent.tag != 'a' or urlsplit(
                selected[0].parent.attrs.get('href', '')).path != urlsplit(source_url).path:
            return []  # A default/other day must never confirm today's sequence.
    courts = []
    for header in root.find(cls='schedule-header'):
        labels = list(header.find(cls='oop-court'))
        if len(labels) != 1:
            continue
        rows = []
        # Each published court is one column, with direct sibling match tables.
        for table in header.parent.children:
            if not isinstance(table, Node) or table.tag != 'table':
                continue
            teams = []
            for team in table.find('td', 'team'):
                people = []
                for group in team.find(cls='player-names'):
                    for line in group.find(cls='line-thin'):
                        spans = [n.text() for n in line.children if isinstance(n, Node) and n.tag == 'span']
                        people.append(spans)
                teams.append(people)
            statuses = [n.text() for n in table.find(cls='text-uppercase')]
            rows.append({'teams': teams, 'status': statuses[0] if len(statuses) == 1 else ''})
        courts.append((labels[0].text(), rows))
    return courts


def resolve_person(parts, players):
    if len(parts) != 2:
        return None
    initial, surname = map(normalized, parts)
    if not initial or not surname:
        return None
    candidates = [p.id for p in players.values() if normalized(p.name).startswith(initial + ' ') or (
        normalized(p.name).startswith(initial) and len(initial) == 1)]
    candidates = [id for id in candidates if normalized(players[id].name).endswith(' ' + surname)]
    return candidates[0] if len(candidates) == 1 else None


def apply_widget_order(matches, players, html, source_url):
    """Confirm a whole court day or none of it. Return confirmed court count."""
    confirmed = 0
    courts = read_courts(html, source_url)
    for court_name, rows in courts:
        if sum(normalized(name) == normalized(court_name) for name, _ in courts) != 1:
            continue
        candidates = [m for m in matches.values() if normalized(m.court) == normalized(court_name)]
        if not candidates or len(rows) != len(candidates):
            continue
        assignments = []
        for row in rows:
            if len(row['teams']) != 2 or any(len(team) != 2 for team in row['teams']):
                break
            ids = [[resolve_person(person, players) for person in team] for team in row['teams']]
            if any(id is None for team in ids for id in team) or len({id for team in ids for id in team}) != 4:
                break
            signature = {frozenset(team) for team in ids}
            found = [m for m in candidates if signature == {frozenset(m.players[:2]), frozenset(m.players[2:])}]
            if len(found) != 1:
                break
            assignments.append((found[0], row['status']))
        else:
            if len({m.id for m, _ in assignments}) != len(candidates):
                continue
            for index, (match, status) in enumerate(assignments, 1):
                match.order = index
                match.order_confirmed = True
                match.source_url = source_url
                # Explicit completion can correct a lagging Premier status. Scores
                # and CSS colours alone never establish a terminal state.
                if normalized(status) == 'completed':
                    match.status = 'FINISHED'
            confirmed += 1
    return confirmed
