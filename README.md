# CAT Flyradar – firmware

Færdige firmware-filer til CAT Flyradar på M5Stack Tab5. Kildekoden ligger ikke her.

Tab5 (fra version 1.12) læser `version.json` ved start og hver 6. time. Er `build` højere end
den version, der kører, viser Tab5 en grøn knap "NY x.xx". Et tryk på "Opdater nu" henter
filen fra `firmware/`, kontrollerer den med `md5` og genstarter.

| Fil | Indhold |
|---|---|
| `version.json` | Nyeste version: `version`, `build`, `bin` (adresse på filen), `size`, `md5`, `notes` |
| `firmware/` | Firmware-filer (`.bin`) til opdatering over Wi-Fi |
| `fleet.json` | Flådelisten (registreringer), som Tab5 henter (fra version 1.18) |
| `flights.json` | Flådens enkelte flyvninger fra de sidste 2 døgn (fra 1.19). Laves hver nat af `tools/flights.py` ud fra adsb.lol's åbne historik (ODbL). Kun enkelte flyvninger, ingen summer |
| `hexcache.json` | Transponder-koder for flåden, som jobbet har fundet |

## Ret flådelisten

1. Åbn `fleet.json` her på GitHub og tryk på blyanten (Edit).
2. Tilføj eller fjern registreringer. Hver står i anførselstegn og adskilles med komma,
   fx `"OY-CDJ", "OY-NEW"` (ingen komma efter den sidste).
3. Tryk **Commit changes**.

Tab5 henter listen ved start og hver 30. minut (GitHub kan være op til 5 minutter om at
vise den nye fil). Er filen forkert skrevet, beholder Tab5 den gamle liste. Højst 48 fly.
Fly med kaldesignal CAT1–CAT9999 kommer stadig med, også selv om de ikke står på listen.

Bygget til board **M5Tab5** (M5Stack-pakken), partition *Default (2 x 6.5 MB app)*.

## Transponder-kode mangler

Jobbet finder flyenes transponder-kode i en offentlig flydatabase. Mangler et fly (står i
loggen i grenen `log`), kan koden skrives i `fleet.json`:

```json
{
  "fleet": [ "OY-CDJ", "OY-ASH" ],
  "hex": { "OY-ASH": "45abcd" }
}
```

Koden står på Tab5's detaljeside ("ICAO ..."), når flyet har været set.
