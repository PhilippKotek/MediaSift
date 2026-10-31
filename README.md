# MediaSift

MediaSift sammelt aus mehreren Quellordnern einmalige Bilder und kopiert alle Videos in einen neuen Exportordner. Die Quellordner bleiben unverändert.

## Funktionsweise

- Unterordner der ausgewählten Quellen werden durchsucht. Überlappende Quellordner werden nur einmal berücksichtigt.
- JPEG, PNG, WebP, BMP und einseitige TIFFs werden anhand ihrer dekodierten Pixel nach EXIF-Ausrichtung verglichen. Dateinamen und gewöhnliche Metadaten zählen nicht als Bildinhalt. Pro Gruppe gleicher Bilder wird die Datei mit dem alphabetisch ersten Pfad kopiert.
- GIFs, animierte oder mehrseitige Bilder werden übersprungen und im Fenster gemeldet. Ähnliche, skalierte oder neu komprimierte Bilder können unterschiedliche Pixel haben und bleiben dann getrennt.
- MP4, MOV, M4V, AVI, MKV, WebM und WMV werden anhand ihrer Dateiendung als Videos erkannt. Jedes Video wird ohne Duplikatprüfung kopiert.
- Jeder Export erzeugt einen eigenen Ordner `MediaSift_JJJJMMTT_HHMMSS` mit `Bilder` und `Videos`. Bei gleichen Dateinamen werden Zusätze wie `_2` vergeben. Das Ziel darf nicht innerhalb einer Quelle liegen.

## Start aus Python

Voraussetzung: Windows mit Python 3.10 oder neuer. In PowerShell im Repository:

```powershell
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe app.py
```

Im Fenster Quellordner und Zielordner auswählen, **Scan starten**, Ergebnisse prüfen und **Ergebnisse exportieren**. Der Abbruch stoppt nach der aktuell verarbeiteten Datei; ein bereits teilweise gefüllter Exportordner bleibt bestehen.

## Windows-EXE bauen

```powershell
.\build.ps1
```

Für den EXE-Build ist Python 3.11 nötig. Das Skript findet eine mit `uv` verwaltete oder über `py` installierte Python-3.11-Version, installiert die Build-Abhängigkeiten in `.venv-build` und erstellt `dist\MediaSift.exe`. Falls Python 3.11 fehlt, kann es mit `uv python install 3.11` installiert werden. Die EXE enthält Python und die Bibliotheken und benötigt auf dem Zielrechner keine separate Python-Installation. Die EXE wird auf Windows gebaut und ist für Windows bestimmt.

## Tests

```powershell
.venv\Scripts\python.exe -m pip install -e '.[test]'
.venv\Scripts\python.exe -m pytest -q
```
