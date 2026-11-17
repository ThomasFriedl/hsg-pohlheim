# HSG Pohlheim – Statistik-App

Web-App fürs iPhone mit Tabelle, Spielen, Spielberichten und Spielerstatistik
der HSG Pohlheim (Regionalliga Männer Hessen). Die Daten kommen von nuLiga Hessen
und werden von GitHub Actions automatisch nach jedem Spieltag aktualisiert.

## Inhalt

| Datei / Ordner | Zweck |
| --- | --- |
| `config.json` | Einstellungen: Saison, Staffel, Mannschaft. Hier passt du später andere Teams an. |
| `scraper/abruf.py` | Das Programm, das die Daten von nuLiga holt. |
| `requirements.txt` | Liste der Zusatzbibliotheken für das Programm. |
| `docs/` | Die Web-App. GitHub Pages veröffentlicht diesen Ordner. |
| `docs/data/app.json` | Die Daten für die App. Wird automatisch überschrieben. |
| `github-workflow/update.yml` | Der Zeitplan für GitHub Actions. Muss nach `.github/workflows/update.yml` (siehe Anleitung, Schritt 4). |

## Von Hand testen (optional, am Mac)

```
pip3 install -r requirements.txt
python3 scraper/abruf.py
```

Danach steht in `docs/data/app.json` der aktuelle Stand.
