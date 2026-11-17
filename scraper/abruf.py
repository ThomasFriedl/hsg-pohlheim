"""
Holt Tabelle, Spiele und Spielberichte einer Mannschaft von nuLiga
und schreibt alles in docs/data/app.json fuer die Web-App.

Aufruf (lokal oder in GitHub Actions):  python scraper/abruf.py
Einstellungen stehen in config.json im Hauptordner.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
BERICHTE = DATA / "berichte"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

BASE = CFG["verband_url"].rstrip("/") + "/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/"
CH = quote(CFG["saison"])
GROUP = CFG["staffel"]
TEAM = CFG["mannschaft"]
PAUSE = float(CFG.get("pause_zwischen_abrufen_sekunden", 3))

session = requests.Session()
session.headers["User-Agent"] = "HSG-Statistik (privates Projekt, 1 Abruf je Spieltag)"


# ---------------------------------------------------------------- Hilfen
def hole(url):
    """Seite abrufen, mit Pause und bis zu 3 Versuchen."""
    for versuch in range(3):
        try:
            time.sleep(PAUSE)
            r = session.get(url, timeout=30)
            r.raise_for_status()
            r.encoding = r.encoding or "utf-8"
            return BeautifulSoup(r.text, "html.parser")
        except requests.RequestException as e:
            print(f"  Fehler bei Versuch {versuch + 1}: {e}")
    raise RuntimeError(f"Seite nicht erreichbar: {url}")


def text(el):
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def zahl(s):
    m = re.search(r"-?\d+", s or "")
    return int(m.group()) if m else 0


def tabellen_mit(soup, pflicht):
    """Liefert (Tabelle, Spaltenindex, Datenzeilen) fuer jede Tabelle,
    deren Kopfzeile alle Pflicht-Spaltennamen enthaelt."""
    treffer = []
    for tab in soup.find_all("table"):
        zeilen = tab.find_all("tr")
        for i, z in enumerate(zeilen):
            zellen = [text(c) for c in z.find_all(["th", "td"])]
            if all(p in zellen for p in pflicht):
                idx = {name: n for n, name in enumerate(zellen) if name}
                treffer.append((tab, idx, zeilen[i + 1:]))
                break
    return treffer


def zellen(zeile):
    return zeile.find_all(["td", "th"])


def ist_team(name):
    return TEAM.lower() in (name or "").lower()


# ---------------------------------------------------------------- Tabelle
def lade_tabelle():
    soup = hole(f"{BASE}groupPage?championship={CH}&group={GROUP}")
    t = tabellen_mit(soup, ["Rang", "Mannschaft", "Punkte"])
    if not t:
        raise RuntimeError("Tabelle nicht gefunden – hat sich die nuLiga-Seite geaendert?")
    _, idx, zeilen = t[0]
    tabelle = []
    for z in zeilen:
        c = zellen(z)
        if len(c) <= idx["Punkte"]:
            continue
        g = lambda k: text(c[idx[k]]) if k in idx and idx[k] < len(c) else ""
        tabelle.append({
            "rang": zahl(g("Rang")),
            "mannschaft": g("Mannschaft"),
            "spiele": zahl(g("Begegnungen")),
            "s": zahl(g("S")), "u": zahl(g("U")), "n": zahl(g("N")),
            "tore": g("Tore"), "diff": g("+/-"), "punkte": g("Punkte"),
        })
    return tabelle


# ---------------------------------------------------------------- Spiele
def lade_spiele():
    url = (f"{BASE}teamPortrait?teamtable={CFG['teamtable']}"
           f"&pageState=vorrunde&championship={CH}&group={GROUP}")
    soup = hole(url)
    t = tabellen_mit(soup, ["Datum", "Heimmannschaft", "Gastmannschaft"])
    if not t:
        raise RuntimeError("Spielplan der Mannschaft nicht gefunden.")
    _, idx, zeilen = t[0]
    spiele, datum, tag = [], "", ""
    for z in zeilen:
        c = zellen(z)
        if len(c) <= idx["Gastmannschaft"]:
            continue
        g = lambda k: text(c[idx[k]]) if k in idx and idx[k] < len(c) else ""
        datum = g("Datum") or datum
        tag = g("Tag") or tag
        heim, gast = g("Heimmannschaft"), g("Gastmannschaft")
        if not (ist_team(heim) or ist_team(gast)):
            continue
        link = z.find("a", href=re.compile("groupMeetingReport"))
        meeting = None
        ergebnis = None
        if link:
            m = re.search(r"meeting=(\d+)", link["href"])
            meeting = m.group(1) if m else None
            if re.match(r"^\d+:\d+$", text(link)):
                ergebnis = text(link)
        genehmigt = bool(z.find("img", title=re.compile("genehmigt", re.I)))
        spiele.append({
            "tag": tag, "datum": datum, "zeit": g("Zeit").replace(" h", ""),
            "nr": g("Nr."), "heim": heim, "gast": gast,
            "ergebnis": ergebnis, "meeting": meeting, "genehmigt": genehmigt,
        })
    return spiele


# ---------------------------------------------------------------- Spielbericht
def lies_bericht(meeting):
    soup = hole(f"{BASE}groupMeetingReport?meeting={meeting}&championship={CH}&group={GROUP}")
    bericht = {"meeting": meeting, "teams": [], "verlauf": [], "ergebnis": "", "halbzeit": "", "ort": ""}

    for tab, idx, zeilen in tabellen_mit(soup, ["Trikot", "Tore", "7M"]):
        kopf = tab.find_previous("h2")
        spieler = []
        for z in zeilen:
            c = zellen(z)
            if len(c) < len(idx):
                continue
            g = lambda k: text(c[idx[k]]) if k in idx and idx[k] < len(c) else ""
            trikot = g("Trikot")
            if not trikot or not trikot.isdigit():   # A–E sind Offizielle
                continue
            sm = re.match(r"(\d+)\s*/\s*(\d+)", g("7M"))
            zeitstrafen = sum(1 for k in ("1.", "2.", "3.") if g(k))
            spieler.append({
                "nr": int(trikot),
                "name": g("Name, Vorname") or g("Name"),
                "tore": zahl(g("Tore")),
                "7m_tore": int(sm.group(1)) if sm else 0,
                "7m_versuche": int(sm.group(2)) if sm else 0,
                "gelb": 1 if g("g. Karte") else 0,
                "zeitstrafen": zeitstrafen,
                "rot": 1 if (g("o.B.") or g("m.B.")) else 0,
            })
        bericht["teams"].append({"name": text(kopf), "spieler": spieler})

    for _, idx, zeilen in tabellen_mit(soup, ["Zeit", "Stand", "Ereignis"]):
        for z in zeilen:
            c = zellen(z)
            g = lambda k: text(c[idx[k]]) if k in idx and idx[k] < len(c) else ""
            if g("Zeit"):
                bericht["verlauf"].append({
                    "seite": g("Team"), "zeit": g("Zeit"), "stand": g("Stand"),
                    "ereignis": g("Ereignis"), "person": g("Person"),
                })

    for z in soup.find_all("tr"):
        c = [text(x) for x in zellen(z)]
        if len(c) >= 2 and c[0] == "Ergebnis":
            m = re.match(r"(\d+:\d+)\s*(?:\((\d+:\d+)\))?", c[1])
            if m:
                bericht["ergebnis"], bericht["halbzeit"] = m.group(1), m.group(2) or ""
        if "Spielort" in c:
            i = c.index("Spielort")
            if i + 1 < len(c):
                bericht["ort"] = c[i + 1]
    return bericht


# ---------------------------------------------------------------- Statistik
def spielerstatistik(berichte):
    stat = {}
    for b in berichte:
        for team in b["teams"]:
            if not ist_team(team["name"]):
                continue
            for s in team["spieler"]:
                p = stat.setdefault(s["name"], {
                    "name": s["name"], "nr": s["nr"], "einsaetze": 0, "tore": 0,
                    "7m_tore": 0, "7m_versuche": 0, "zeitstrafen": 0, "gelb": 0, "rot": 0,
                })
                p["einsaetze"] += 1
                p["nr"] = s["nr"]
                for k in ("tore", "7m_tore", "7m_versuche", "zeitstrafen", "gelb", "rot"):
                    p[k] += s[k]
    liste = sorted(stat.values(), key=lambda p: (-p["tore"], p["name"]))
    for p in liste:
        p["tore_pro_spiel"] = round(p["tore"] / p["einsaetze"], 2) if p["einsaetze"] else 0
    return liste


# ---------------------------------------------------------------- Ablauf
def main():
    BERICHTE.mkdir(parents=True, exist_ok=True)
    print("Tabelle …")
    tabelle = lade_tabelle()
    print("Spiele …")
    spiele = lade_spiele()

    berichte = []
    for sp in spiele:
        if not sp["meeting"] or not sp["ergebnis"]:
            continue
        datei = BERICHTE / f"{sp['meeting']}.json"
        if datei.exists():
            b = json.loads(datei.read_text(encoding="utf-8"))
        else:
            print(f"Spielbericht {sp['heim']} – {sp['gast']} …")
            b = lies_bericht(sp["meeting"])
            if sp["genehmigt"]:          # nur endgueltige Berichte dauerhaft speichern
                datei.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
        sp["halbzeit"] = b.get("halbzeit", "")
        sp["ort"] = b.get("ort", "")
        berichte.append(b)

    app = {
        "aktualisiert": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "mannschaft": TEAM,
        "liga": CFG["liga_name"],
        "live_ticker_url": CFG.get("live_ticker_url", ""),
        "quelle": f"{BASE}groupPage?championship={CH}&group={GROUP}",
        "tabelle": tabelle,
        "spiele": spiele,
        "spieler": spielerstatistik(berichte),
        "berichte": {b["meeting"]: b for b in berichte},
    }
    (DATA / "app.json").write_text(json.dumps(app, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fertig: {len(tabelle)} Teams, {len(spiele)} Spiele, {len(berichte)} Spielberichte.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("FEHLER:", e)
        sys.exit(1)
