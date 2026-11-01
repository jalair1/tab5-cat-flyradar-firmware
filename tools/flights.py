#!/usr/bin/env python3
"""Plukker flådens flyvninger fra de sidste 2 døgn ud af adsb.lol's daglige historik
(github.com/adsblol/globe_history_YYYY) og skriver flights.json.
Kun enkelte flyvninger (ingen summer), og kun 2 døgn."""
import csv, gzip, io, json, math, os, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

LOG = []
def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)

TOKEN = os.environ.get('GITHUB_TOKEN', '')
def get(url, binary=False, api=False):
    req = urllib.request.Request(url, headers={'User-Agent': 'tab5-cat-flyradar-flights'})
    if api and TOKEN:
        req.add_header('Authorization', 'Bearer ' + TOKEN)
        req.add_header('Accept', 'application/vnd.github+json')
    with urllib.request.urlopen(req, timeout=120) as r:
        d = r.read()
    return d if binary else d.decode('utf-8', 'replace')

# ---------------------------------------------------------------- flåden og transponder-koder
fj = json.load(open('fleet.json'))
fleet = [r.strip().upper() for r in fj['fleet']]
log('Flaade:', len(fleet), 'fly')
hexmap = {}
# 1) gemte koder fra tidligere kørsler, 2) koder skrevet i fleet.json ("hex": {"OY-ABC": "45abcd"})
try: cache = json.load(open('hexcache.json'))
except Exception: cache = {}
for r, h in list(cache.items()) + list((fj.get('hex') or {}).items()):
    if r.upper() in fleet and h: hexmap[r.upper()] = (h.strip().lower(), '')
try:
    db = gzip.decompress(get('https://raw.githubusercontent.com/wiedehopf/tar1090-db/csv/aircraft.csv.gz', binary=True)).decode('utf-8', 'replace')
    want = set(fleet)
    for line in db.splitlines():
        f = line.split(';')
        if len(f) > 2 and f[1].strip().upper() in want and f[1].strip().upper() not in hexmap:
            hexmap[f[1].strip().upper()] = (f[0].strip().lower(), f[2].strip())
except Exception as e:
    log('Flydatabase-fejl:', e)
# 3) fly der sender lige nu (adsb.lol live)
miss = [r for r in fleet if r not in hexmap]
if miss:
    try:
        live = json.loads(get('https://api.adsb.lol/v2/reg/' + ','.join(miss)))
        for ac in live.get('ac', []):
            r = (ac.get('r') or '').upper()
            if r in miss: hexmap[r] = (ac['hex'].lower(), ac.get('t', ''))
    except Exception as e:
        log('adsb.lol live-fejl:', e)
for r, (h, t) in hexmap.items(): cache[r] = h
json.dump(dict(sorted(cache.items())), open('hexcache.json', 'w'), indent=1)
log('Transponder-koder fundet:', len(hexmap), 'af', len(fleet))
for r in fleet:
    if r not in hexmap: log('  mangler kode for', r)
hex2reg = {h: (r, t) for r, (h, t) in hexmap.items()}

# ---------------------------------------------------------------- lufthavne (OurAirports)
airports = []
try:
    txt = get('https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv')
    for row in csv.DictReader(io.StringIO(txt)):
        if row['type'] not in ('large_airport', 'medium_airport', 'small_airport'): continue
        code = (row.get('icao_code') or row.get('gps_code') or row['ident']).strip()
        if len(code) != 4 or not code.isalpha(): continue
        airports.append((float(row['latitude_deg']), float(row['longitude_deg']), code.upper(),
                         0 if row['type'] == 'large_airport' else 1 if row['type'] == 'medium_airport' else 2))
except Exception as e:
    log('Lufthavns-fejl:', e)
log('Lufthavne:', len(airports))

def km(a, b, c, d):
    p1, p2 = math.radians(a), math.radians(c)
    dl = math.radians(d - b); dp = p2 - p1
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1, math.sqrt(h)))

def nearest(lat, lon, maxkm=12):
    best, bd = '', maxkm
    for a in airports:
        if abs(a[0] - lat) > 0.3: continue
        d = km(lat, lon, a[0], a[1]) - (2 if a[3] == 0 else 0)   # foretræk store lufthavne lidt
        if d < bd: bd, best = d, a[2]
    return best

# ---------------------------------------------------------------- hent spor for 2 døgn
today = datetime.now(timezone.utc).date()
days = [today - timedelta(days=2), today - timedelta(days=1)]
points = {}   # hex -> list of (t, lat, lon, alt or None, ground, call)
got_days = []
for day in days:
    repo = f'adsblol/globe_history_{day.year}'
    tagbase = f'v{day.strftime("%Y.%m.%d")}-planes-readsb'
    rel = None
    for inst in ('prod-0', 'staging-0', 'prod-1'):
        try:
            rel = json.loads(get(f'https://api.github.com/repos/{repo}/releases/tags/{tagbase}-{inst}', api=True))
            break
        except Exception as e:
            log('ingen udgivelse', tagbase + '-' + inst, '-', e)
    if not rel:
        continue
    assets = sorted(rel['assets'], key=lambda a: a['name'])
    assets = [a for a in assets if '.tar' in a['name']]
    log(day, rel['tag_name'], [(a['name'], round(a['size'] / 1e9, 2)) for a in assets])
    if not assets or not hex2reg:
        continue
    os.makedirs('/tmp/tr', exist_ok=True)
    pats = [f'*trace_full_{h}.json' for h in hex2reg]
    urls = ' '.join(f'"{a["browser_download_url"]}"' for a in assets)
    cmd = (f'for u in {urls}; do curl -sSL --retry 3 "$u"; done | '
           f'tar -x -C /tmp/tr --wildcards --ignore-failed-read ' + ' '.join(f"'{p}'" for p in pats) + ' 2>/tmp/tar.err; true')
    t0 = time.time()
    subprocess.run(cmd, shell=True)
    log('  hentet og pakket ud paa', round(time.time() - t0), 's')
    found = 0
    for root, _, files in os.walk('/tmp/tr'):
        for fn in files:
            if not fn.startswith('trace_full_'): continue
            hx = fn[len('trace_full_'):-5].lower()
            path = os.path.join(root, fn)
            raw = open(path, 'rb').read()
            os.remove(path)
            try:
                if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
                tr = json.loads(raw)
            except Exception as e:
                log('  kunne ikke laese', fn, e); continue
            found += 1
            base = tr.get('timestamp', 0)
            lst = points.setdefault(hx, [])
            for p in tr.get('trace', []):
                if len(p) < 4 or p[1] is None: continue
                alt = p[3]
                gs = p[4] if len(p) > 4 else None
                flags = p[6] if len(p) > 6 and isinstance(p[6], int) else 0
                # på jorden: meldt "ground", eller langsom og lav / uden højde
                ground = alt == 'ground' or (gs is not None and gs < 50 and (alt is None or alt < 2000))
                if alt is None and not ground: continue           # ukendt højde: spring over
                call = ''
                if len(p) > 8 and isinstance(p[8], dict):
                    call = (p[8].get('flight') or '').strip()
                lst.append((base + p[0], p[1], p[2], None if ground else alt, ground, call, bool(flags & 2)))
    log('  spor fundet for', found, 'fly')
    got_days.append(day.isoformat())

# ---------------------------------------------------------------- del sporene op i flyvninger
flights = []
for hx, pts in points.items():
    reg, typ = hex2reg[hx]
    pts.sort()
    cur = None
    last = None
    def close(f, lp):
        if not f: return
        dur = f['last'][0] - f['first'][0]
        if dur < 300 or f['nmkm'] < 5: return            # for kort: støj
        lt, la, lo, alt = f['last'][0], f['last'][1], f['last'][2], f['last'][3]
        ft, fa, fo, falt = f['first'][0], f['first'][1], f['first'][2], f['first'][3]
        flights.append({
            'reg': reg, 'type': typ, 'call': f['call'],
            'from': nearest(fa, fo) if (falt is None or falt < 4000) else '',
            'to': nearest(la, lo) if (f['landed'] or (alt is not None and alt < 4000)) else '',
            'dep': int(ft), 'arr': int(lt), 'sec': int(dur), 'nm': round(f['nmkm'] / 1.852),
        })
    for p in pts:
        t, la, lo, alt, ground, call, newleg = p
        if cur and last:
            gap = t - last[0]
            low = last[3] is None or last[3] < 3000
            if ground or newleg or gap > 3 * 3600 or (gap > 20 * 60 and low):
                cur['landed'] = ground or (gap > 20 * 60 and low) or (newleg and low)
                close(cur, last); cur = None
        if not ground and alt is not None:
            if not cur:
                cur = {'first': p, 'last': p, 'nmkm': 0.0, 'call': '', 'landed': False}
            else:
                cur['nmkm'] += km(cur['last'][1], cur['last'][2], la, lo)
                cur['last'] = p
            if call: cur['call'] = call
        last = p
    if cur:
        cur['landed'] = False
        close(cur, last)
# Ukendt lufthavn (ingen dækning): brug ruten for kaldesignalet (adsb.lol's rutefiler)
routes = {}
def route(call):
    if call in routes: return routes[call]
    r = None
    try:
        d = json.loads(get(f'https://vrs-standing-data.adsb.lol/routes/{call[:2]}/{call}.json'))
        aps = d.get('_airports') or []
        if len(aps) >= 2: r = (aps[0].get('icao', ''), aps[-1].get('icao', ''))
    except Exception:
        pass
    routes[call] = r
    return r
for f in flights:
    if f['call'] and (not f['from'] or not f['to']):
        r = route(f['call'])
        if r:
            if not f['from']: f['from'] = r[0]
            if not f['to']: f['to'] = r[1]
flights.sort(key=lambda f: (f['dep'], f['reg']))
log('Flyvninger:', len(flights))

out = {'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'days': got_days, 'flights': flights}
if got_days:
    json.dump(out, open('flights.json', 'w'), separators=(',', ':'))
    log('flights.json skrevet')
else:
    log('Ingen dage hentet - flights.json uaendret')
open('/tmp/flights_log.txt', 'w').write('\n'.join(LOG) + '\n')
