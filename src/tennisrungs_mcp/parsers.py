"""Parse observed server-rendered HTML. Never execute page JavaScript."""
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from .models import (HistoryRow, Ladder, Match, Proposal, Ranking,
                     UnsupportedContract)


def soup(html):
    return BeautifulSoup(html, "html.parser")


def text(node):
    return node.get_text(" ", strip=True)


def team_id(href):
    value = parse_qs(urlparse(href).query).get("teamId", [None])[0]
    return int(value) if value and value.isdigit() else None


def is_login(html):
    s = soup(html)
    return bool(s.select('input[type="password"]')) or "LogIn to Your TennisRungs" in text(s)


def current_ladders(html):
    s = soup(html)
    group = next((n for n in s.find_all(["fieldset", "section"])
                  if "MY CURRENT LADDERS" in text(n)), None)
    if group is None:
        raise UnsupportedContract("Current-ladder section not found")
    rows = []
    seen = set()
    for a in group.select('a[href]'):
        m = re.search(r"/Ladders/Rankings/(\d+)", a["href"], re.I)
        if m and int(m[1]) not in seen:
            seen.add(int(m[1]))
            rows.append(Ladder(int(m[1]), text(a)))
    return rows


def my_matches(html):
    s = soup(html)
    panel = s.select_one("#tabs-1")
    if panel is None:
        raise UnsupportedContract("Own-challenges panel not found")
    rows = []
    for row in panel.select("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            continue
        ladder, opponent, details = (text(c) for c in cells[:3])
        link = cells[1].select_one('a[href*="PlayerMatches"]')
        status = next((v for v in ["PROPOSED", "ACCEPTED", "PENDING"]
                       if re.search(rf"\b{v}\b", details)), "UNKNOWN")
        cid = None
        lid = None
        for a in row.select('a[href], [onclick]'):
            href = a.get("href", "")
            q = parse_qs(urlparse(href).query)
            if q.get("challengeId"):
                cid = int(q["challengeId"][0])
                lid = int(q["ladderId"][0]) if q.get("ladderId") else None
            handler = a.get("onclick", "")
            m = re.search(r"WithdrawChallenge\(this,\s*(\d+)", handler)
            if m:
                cid = int(m[1])
        when = re.search(r"Scheduled For:\s*(.*?)(?=Location:|$)", details)
        location = re.search(r"Location:\s*(.*)$", details)
        rows.append(Match(cid, ladder, opponent, status,
                          when[1].strip() if when else None,
                          location[1].strip() if location else None,
                          team_id(link["href"]) if link else None, lid))
    return rows


def open_proposals(html):
    panel = soup(html).select_one("#tabs-5")
    if panel is None:
        raise UnsupportedContract("Open-proposals panel not found")
    rows = []
    for row in panel.select("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            continue
        action = row.select_one('[onclick*="AcceptProposal"]')
        if not action:
            raise UnsupportedContract("Proposal identity missing; refusing partial proposal")
        m = re.search(r"cId=(\d+)&acceptedBy=(\d+)", action["onclick"])
        if not m:
            raise UnsupportedContract("Proposal identity contract changed")
        detail = text(cells[2]).split("@", 1)
        rows.append(Proposal(int(m[1]), int(m[2]), text(cells[0]), text(cells[1]),
                             detail[0].strip(), detail[1].strip() if len(detail) > 1 else None))
    return rows


def table_with_headers(html, required):
    s = soup(html)
    for table in s.select("table"):
        headers = [text(h) for h in table.select("th")]
        if all(h in headers for h in required):
            return table
    raise UnsupportedContract("Expected table schema not found")


def rankings(html):
    table = table_with_headers(html, ["Rank", "Player", "Record", "Points"])
    out = []
    for row in table.select("tr"):
        c = row.find_all("td", recursive=False)
        if len(c) < 7:
            continue
        a = c[1].select_one('a[href*="PlayerMatches"]')
        tid = team_id(a["href"]) if a else None
        if tid is None:
            raise UnsupportedContract("Ranking team identity missing")
        out.append(Ranking(tid, text(a), text(c[0]), text(c[2]), text(c[3]), text(c[4]), text(c[5])))
    return out


def history(html):
    table = table_with_headers(html, ["Date", "Vs.", "Result", "Score"])
    out = []
    for row in table.select("tr"):
        c = row.find_all("td", recursive=False)
        if len(c) != 4:
            continue
        a = c[1].select_one('a[href*="PlayerMatches"]')
        out.append(HistoryRow(text(c[0]), text(a) if a else text(c[1]),
                              team_id(a["href"]) if a else None, text(c[2]), text(c[3])))
    return out


def coverage(html, rows, label=None):
    s = soup(html)
    # Legacy DataTables pagination may be entirely server-rendered client-side.
    # Fail closed rather than declaring visible page rows complete.
    paged = bool(s.select('.dataTables_paginate, .pagination, a[rel="next"]'))
    warnings = ["Pagination controls detected; complete coverage not established"] if paged else []
    complete = not paged
    if label:
        m = re.search(re.escape(label) + r"\s*\((\d+)\)", text(s))
        if m and int(m[1]) != len(rows):
            complete = False
            warnings.append("Displayed count differs from parsed count")
    return complete, warnings


def proposal_form(html):
    s = soup(html)
    form = s.find("form")
    if not form:
        raise UnsupportedContract("Proposal form not found")
    names = {e.get("name") for e in form.select("input,select")}
    required = {"TeamId", "Location", "MatchDate", "PreferredLocation", "Hour", "Minute", "AmOrPm", "ShowMyEmail"}
    if not required <= names:
        raise UnsupportedContract("Proposal form schema changed")
    defaults = [(e["name"], e.get("value", "")) for e in form.select('input[type="hidden"][name]')]
    options = {e.get("name"): {o.get("value", text(o)) for o in e.select("option")}
               for e in form.select("select[name]")}
    return defaults, options
