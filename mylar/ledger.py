import datetime
import html as _html
import json
import re
import threading
import time

import requests
from collections import defaultdict

import mylar
from mylar import db, logger

OWNED = ('Downloaded', 'Archived')
TRADE_TYPES = ('TPB', 'HC', 'GN')
KINDS = ['gap', 'unrecognised', 'after_last', 'before_first', 'after_cutoff']

_NUM = r'\d+(?:\.\d+|\.[A-Za-z]+)?'
_RANGE = r'(%s)\s*(?:[-–—]|to|through)\s*(%s)|(%s)' % (_NUM, _NUM, _NUM)
_SEG = re.compile(
    r'((?:[A-Z0-9][\w\'’.:/&!-]*(?:\s+(?:of|the|and|vs\.?|&|in|a|an|to|de|du|[A-Z0-9][\w\'’.:/&!-]*))*?)?)'
    r'\s*(?:\((\d{4})\))?\s*(?:issues?\s*)?#\s*(%s(?:\s*(?:[-–—,&]|and|to)\s*#?\s*%s)*)' % (_NUM, _NUM))

_lock = threading.Lock()
_status = {'running': False, 'done': 0, 'total': 0, 'phase': None, 'started': None, 'finished': None, 'error': None, 'note': None}


def status():
    return dict(_status)


def _clean(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    return re.sub(r'\s+', ' ', _html.unescape(text)).strip()


def _clauses(text):
    return [m.group(1) for m in re.finditer(
        r'\bcollect(?:s|ing|ed)?\b[:\s]*(.+?)(?:(?<![#\d])\.(?!\d)\s|[!?]\s|\|\||$)', text, re.I)]


def _numbers(spec):
    nums = []
    for a, b, c in re.findall(_RANGE, spec):
        if c:
            nums.append(c)
        elif a.isdigit() and b.isdigit() and 0 <= int(b) - int(a) <= 200:
            nums.extend(str(n) for n in range(int(a), int(b) + 1))
        else:
            nums.extend([a, b])
    return nums


def parse_collects(text):
    segs = []
    for clause in _clauses(_clean(text)):
        clause = re.split(r'\b(?:and material from|material from|plus material|and the|plus the|plus a|plus an|and a never|and stories from)\b',
                          clause, flags=re.I)[0]
        last = None
        for m in _SEG.finditer(clause):
            name = (m.group(1) or '').strip(' ,&-')
            name = re.sub(r'^(?:and|plus|&|the series|issues?)\s+', '', name, flags=re.I).strip()
            if name.lower() in ('', 'issues', 'issue', 'and', 'plus'):
                of = re.match(r'\s*of\s+(?:the\s+)?(?:ongoing\s+|original\s+|classic\s+)?([A-Z][\w\'’.:/& -]*?)\s+(?:series|mini-?series|comic|title|run)\b',
                              clause[m.end():])
                name = of.group(1).strip() if of else (last[0] if last else None)
                year = m.group(2) or (last[1] if last else None)
            else:
                year = m.group(2)
            nums = _numbers(m.group(3))
            if nums:
                segs.append((name, year, nums))
                last = (name, year)
    return segs


def _norm(s):
    s = (s or '').lower().replace('&', 'and')
    s = re.sub(r'\(\d{4}\)', '', s)
    s = re.sub(r'^the\s+', '', s.strip())
    return re.sub(r'[^a-z0-9]', '', s)


def _num_key(n):
    n = str(n).strip().upper().lstrip('0')
    return n or '0'


def _trade_base(name):
    name = re.split(r'[:–-]', name or '')[0]
    name = re.sub(r'\b(deluxe|edition|omnibus|vol(ume)?\.?\s*\d*|tpb|hc|collection|complete|the)\b', ' ', name, flags=re.I)
    return re.sub(r'\s+', ' ', name).strip()


class _Library(object):
    def __init__(self, myDB):
        self.comics = {r['ComicID']: dict(r) for r in myDB.select('SELECT ComicID, ComicName, ComicYear FROM comics')}
        self.byname = defaultdict(list)
        for cid, c in self.comics.items():
            self.byname[_norm(c['ComicName'])].append(cid)
        self.issues = defaultdict(dict)
        for i in myDB.select('SELECT IssueID, ComicID, Issue_Number, ReleaseDate FROM issues'):
            self.issues[i['ComicID']][_num_key(i['Issue_Number'])] = dict(i)

    def pick(self, name, year, nums, before, exclude):
        best = None
        for cid in self.byname.get(_norm(name), []):
            if cid == exclude:
                continue
            c = self.comics[cid]
            if year and str(c['ComicYear']) != str(year):
                continue
            iss = self.issues[cid]
            have = [n for n in nums if _num_key(n) in iss]
            if not have:
                continue
            if before and any((iss[_num_key(n)]['ReleaseDate'] or '') > before for n in have):
                continue
            score = (len(have), c['ComicYear'] or '')
            if best is None or score > best[0]:
                best = (score, cid)
        return best[1] if best else None

    def resolve(self, segs, trade_name, before, exclude):
        found, missing = [], []
        for name, year, nums in segs:
            nm = name or _trade_base(trade_name)
            cid = self.pick(nm, year, nums, before, exclude)
            if cid is None:
                missing.append({'series': nm, 'year': year, 'nums': nums})
                continue
            for n in nums:
                i = self.issues[cid].get(_num_key(n))
                if i:
                    if i['IssueID'] not in found:
                        found.append(i['IssueID'])
                else:
                    missing.append({'series': nm, 'year': year, 'nums': [n]})
        return found, missing


def _ensure_table(myDB):
    myDB.action('CREATE TABLE IF NOT EXISTS ledger_collects (TradeIssueID TEXT UNIQUE, TradeComicID TEXT, Source TEXT, '
                'Collects TEXT, IssueIDs TEXT, Unresolved TEXT, Updated TEXT)')
    myDB.action('CREATE TABLE IF NOT EXISTS ledger_metron (TradeIssueID TEXT UNIQUE, MetronID TEXT, Updated TEXT)')


class _Metron(object):
    SPACING = 4.0
    BUDGET = 300

    def __init__(self, token):
        self.s = requests.Session()
        self.s.headers.update({'Authorization': 'Bearer %s' % token, 'User-Agent': 'Mylar3 ledger'})
        self.last = 0
        self.used = 0

    def get(self, path, **params):
        for attempt in range(3):
            if self.used >= self.BUDGET:
                raise Exception('Stopped after %s Metron requests this run - run it again later for the rest' % self.BUDGET)
            wait = self.SPACING - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            r = self.s.get('https://metron.cloud/api/' + path, params=params, timeout=(10, 60))
            self.last = time.time()
            self.used += 1
            if r.status_code == 429:
                time.sleep(max(int(r.headers.get('Retry-After') or 120), 60))
                continue
            r.raise_for_status()
            return r.json()
        raise Exception('Metron kept rate limiting requests')


def _reprint_segments(reprints, trade_year):
    segs = []
    for x in reprints or []:
        m = re.match(r'^(.*?)\s*\((\d{4})\)\s*#\s*(\S+)$', (x.get('issue') or '').strip())
        if not m:
            continue
        name, year, num = m.group(1).strip(), m.group(2), m.group(3)
        name = re.sub(r'\s+(TPB|HC|GN|Omnibus)$', '', name, flags=re.I)
        if trade_year and year.isdigit() and int(year) > int(trade_year):
            continue
        segs.append((name, year, [num]))
    return segs


def metron_token():
    import os
    tok = os.environ.get('METRON_API_TOKEN') or getattr(mylar.CONFIG, 'METRON_API_TOKEN', None)
    return tok if tok and tok != 'None' else None


def metron_test(token=None):
    token = (token or '').strip() or metron_token()
    if not token:
        return {'ok': False, 'message': 'No Metron API token is set.'}
    try:
        r = requests.get('https://metron.cloud/api/publisher/', params={'name': 'Marvel'},
                         headers={'Authorization': 'Bearer %s' % token, 'User-Agent': 'Mylar3 ledger'}, timeout=(8, 20))
    except requests.exceptions.ConnectTimeout:
        return {'ok': False, 'message': 'Metron is not responding right now (connection timed out). The site may be down - try again later.'}
    except requests.exceptions.ConnectionError:
        return {'ok': False, 'message': 'Could not connect to Metron. The site may be down - try again later.'}
    except Exception as e:
        return {'ok': False, 'message': 'Could not reach Metron: %s' % e}
    if r.status_code == 200:
        return {'ok': True, 'message': 'Connected to Metron.'}
    if r.status_code in (401, 403):
        return {'ok': False, 'message': 'Metron rejected the token. Generate a new one on your Metron profile page.'}
    if r.status_code == 429:
        return {'ok': False, 'message': 'Metron is rate limiting requests. Try again in a minute.'}
    return {'ok': False, 'message': 'Metron answered with HTTP %s.' % r.status_code}


def start_build(force=False):
    with _lock:
        if _status['running']:
            return False
        _status.update(running=True, done=0, total=0, phase='Preparing', error=None, note=None,
                       started=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), finished=None)
    threading.Thread(target=_build, args=(force,), name='LedgerBuild').start()
    return True


def _build(force):
    from mylar import cv
    try:
        myDB = db.DBConnection()
        _ensure_table(myDB)
        trades = myDB.select("SELECT i.IssueID, i.ComicID, c.ComicName FROM issues i JOIN comics c ON c.ComicID=i.ComicID "
                             "WHERE coalesce(c.Corrected_Type, c.Type) IN ('TPB','HC','GN')")
        done = set() if force else {r['TradeIssueID'] for r in myDB.select("SELECT TradeIssueID FROM ledger_collects WHERE Source='comicvine'")}
        todo = [t for t in trades if t['IssueID'] not in done]
        _status.update(total=len(todo), phase='Reading ComicVine descriptions')
        lib = _Library(myDB)
        for k in range(0, len(todo), 100):
            batch = todo[k:k + 100]
            url = '%sissues/?api_key=%s&format=json&filter=id:%s&field_list=id,description,deck,store_date,cover_date,volume&limit=100' % (
                mylar.CVURL, mylar.CONFIG.COMICVINE_API, '|'.join(str(t['IssueID']) for t in batch))
            r = cv.cv_request(url, timeout=60)
            results = {str(x['id']): x for x in (r.json().get('results') or [])}
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            for t in batch:
                x = results.get(str(t['IssueID']))
                if x is None:
                    continue
                text = (x.get('description') or '') + ' || ' + (x.get('deck') or '')
                segs = parse_collects(text)
                found, missing = lib.resolve(segs, (x.get('volume') or {}).get('name') or t['ComicName'],
                                             x.get('store_date') or x.get('cover_date'), t['ComicID'])
                clause = _clauses(_clean(text))
                myDB.upsert('ledger_collects', {'TradeComicID': t['ComicID'], 'Source': 'comicvine',
                                                'Collects': clause[0][:400] if clause else None,
                                                'IssueIDs': json.dumps(found), 'Unresolved': json.dumps(missing), 'Updated': now},
                            {'TradeIssueID': t['IssueID']})
            _status['done'] = min(len(todo), k + 100)
        token = metron_token()
        metron_note = None
        if token:
            try:
                _metron_pass(myDB, lib, token, force)
            except Exception as e:
                logger.warn('[LEDGER] Metron pass stopped: %s' % e)
                metron_note = 'ComicVine contents saved. Metron could not be read (%s) - run it again later.' % e.__class__.__name__
        _status.update(phase='Finished', note=metron_note)
        logger.info('[LEDGER] Collected-edition contents read for %s trade issues.' % len(todo))
    except Exception as e:
        logger.warn('[LEDGER] Building collected-edition data failed: %s' % e)
        _status.update(error=str(e), phase='Failed')
    finally:
        _status.update(running=False, finished=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))


def _metron_pass(myDB, lib, token, force):
    checked = set() if force else {r['TradeIssueID'] for r in myDB.select('SELECT TradeIssueID FROM ledger_metron')}
    rows = myDB.select("SELECT l.TradeIssueID, l.TradeComicID, l.IssueIDs, i.Issue_Number, c.ComicName, c.ComicYear, i.ReleaseDate "
                       "FROM ledger_collects l JOIN issues i ON i.IssueID=l.TradeIssueID JOIN comics c ON c.ComicID=l.TradeComicID")
    todo = [r for r in rows if r['IssueIDs'] in (None, '[]') and r['TradeIssueID'] not in checked]
    _status.update(phase='Reading Metron reprint lists', done=0, total=len(todo))
    api = _Metron(token)
    for n, t in enumerate(todo, 1):
        mid = None
        res = api.get('issue/', cv_id=t['TradeIssueID']).get('results') or []
        if not res:
            res = api.get('issue/', series_name=t['ComicName'], number=t['Issue_Number']).get('results') or []
            res = [x for x in res if str(t['ComicYear']) in (x.get('issue') or '')] or res[:1]
        if res:
            mid = res[0]['id']
            detail = api.get('issue/%s/' % mid)
            year = (t['ReleaseDate'] or '')[:4] or t['ComicYear']
            segs = _reprint_segments(detail.get('reprints'), year)
            if segs:
                before = t['ReleaseDate'] or None
                found, missing = lib.resolve(segs, t['ComicName'], before, t['TradeComicID'])
                if found:
                    names = sorted({'%s #%s' % (sg[0], sg[2][0]) for sg in segs})
                    myDB.upsert('ledger_collects', {'Source': 'metron', 'Collects': ('Metron: ' + ', '.join(names))[:400],
                                                    'IssueIDs': json.dumps(found), 'Unresolved': json.dumps(missing),
                                                    'Updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')},
                                {'TradeIssueID': t['TradeIssueID']})
        myDB.upsert('ledger_metron', {'MetronID': str(mid) if mid else None, 'Updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')},
                    {'TradeIssueID': t['TradeIssueID']})
        _status['done'] = n


COVERAGE = ['fills_gaps', 'covered', 'partly', 'not_in_library', 'unknown']


def _norm(name):
    return re.sub(r'[^a-z0-9]+', '', (name or '').lower().replace('&', 'and'))


def _trades(myDB, status, comics):
    _ensure_table(myDB)
    out = []
    for r in myDB.select('SELECT * FROM ledger_collects'):
        t = status.get(r['TradeIssueID'])
        c = comics.get(r['TradeComicID'])
        if t is None or c is None:
            continue
        found = [f for f in json.loads(r['IssueIDs'] or '[]') if f in status and status[f]['ComicID'] in comics]
        unresolved = json.loads(r['Unresolved'] or '[]')
        own = [f for f in found if status[f]['Status'] in OWNED]
        found_names = {_norm(comics[status[f]['ComicID']]['ComicName']) for f in found}
        same = [u for u in unresolved if _norm(u.get('series')) in found_names]
        other = [u for u in unresolved if _norm(u.get('series')) not in found_names]
        if not r['Collects']:
            cov = 'unknown'
        elif not found:
            cov = 'not_in_library' if unresolved else 'unknown'
        elif len(own) < len(found):
            cov = 'fills_gaps'
        elif same:
            cov = 'partly'
        else:
            cov = 'covered'
        out.append({'row': r, 'trade': t, 'comic': c, 'found': found, 'own': own, 'unresolved': unresolved,
                    'other': other, 'coverage': cov})
    return out


def _lookups(myDB):
    status = {r['IssueID']: r for r in myDB.select('SELECT IssueID, ComicID, Issue_Number, Status FROM issues')}
    comics = {r['ComicID']: r for r in myDB.select('SELECT ComicID, ComicName, ComicYear, ComicPublisher, Corrected_Type, Type, Have, Total FROM comics')}
    return status, comics


def missing_data(cutoff=None):
    myDB = db.DBConnection()
    comics = {r['ComicID']: r for r in myDB.select('SELECT ComicID, ComicName, ComicYear, ComicPublisher, Have, Total FROM comics')}
    owned = defaultdict(list)
    rows = []
    for i in myDB.select('SELECT IssueID, ComicID, Issue_Number, Int_IssueNumber, IssueName, ReleaseDate, IssueDate, Status FROM issues'):
        if i['Status'] in OWNED:
            if i['Int_IssueNumber'] is not None:
                owned[i['ComicID']].append(i['Int_IssueNumber'])
        elif i['Status'] != 'Ignored':
            rows.append(i)
    lo = {c: min(v) for c, v in owned.items()}
    hi = {c: max(v) for c, v in owned.items()}

    status, tcomics = _lookups(myDB)
    trades, by_issue, by_series = [], defaultdict(list), defaultdict(list)
    for x in _trades(myDB, status, tcomics):
        idx = len(trades)
        cids = sorted({status[f]['ComicID'] for f in x['found']})
        trades.append([x['comic']['ComicName'], x['comic']['ComicYear'], x['trade']['Issue_Number'], x['row']['TradeComicID'],
                       1 if x['trade']['Status'] in OWNED else 0, COVERAGE.index(x['coverage'])])
        for f in x['found']:
            by_issue[f].append(idx)
        for cid in cids:
            by_series[cid].append(idx)

    pubs, pidx, series, sidx, out = [], {}, [], {}, []

    def series_index(cid):
        c = comics[cid]
        pub = c['ComicPublisher'] or '?'
        if pub not in pidx:
            pidx[pub] = len(pubs)
            pubs.append(pub)
        if cid not in sidx:
            sidx[cid] = len(series)
            series.append([c['ComicName'], c['ComicYear'], c['Have'] or 0, c['Total'] or 0, pidx[pub], cid, by_series.get(cid, [])])
        return sidx[cid]

    for i in rows:
        c = comics.get(i['ComicID'])
        if c is None:
            continue
        date = next((d for d in (i['ReleaseDate'], i['IssueDate']) if d and not d.startswith('0000')), '')
        n = i['Int_IssueNumber']
        if cutoff and date and date >= cutoff:
            kind = 4
        elif i['ComicID'] not in owned:
            kind = 1
        elif n is not None and lo[i['ComicID']] < n < hi[i['ComicID']]:
            kind = 0
        elif n is not None and n < lo[i['ComicID']]:
            kind = 3
        else:
            kind = 2
        out.append([kind, series_index(i['ComicID']), i['Issue_Number'] or '', n or 0, (i['IssueName'] or '')[:90], date, i['IssueID'], i['Status'],
                    by_issue.get(i['IssueID'], [])])
    missing_cids = {i['ComicID'] for i in rows}
    complete = [series_index(cid) for cid, c in comics.items()
                if cid not in missing_cids and (c['Total'] or 0) > 0 and (c['Have'] or 0) >= (c['Total'] or 0)]
    return {'kinds': KINDS, 'pubs': pubs, 'series': series, 'rows': out, 'cutoff': cutoff or '',
            'trades': trades, 'coverage': COVERAGE, 'complete': complete}


def _extra_name(u, found, status, comics):
    name = u.get('series') or ''
    if _norm(name) in ('annual', 'annuals') and found:
        name = '%s Annual' % comics[status[found[0]]['ComicID']]['ComicName']
    elif name.isupper():
        name = name.title()
    return '%s (%s)' % (name, u['year']) if u.get('year') else name


def collected_data():
    myDB = db.DBConnection()
    status, comics = _lookups(myDB)
    out = []
    for x in _trades(myDB, status, comics):
        r, t, c = x['row'], x['trade'], x['comic']
        lacking = [[f, comics[status[f]['ComicID']]['ComicName'], comics[status[f]['ComicID']]['ComicYear'], status[f]['Issue_Number'], status[f]['Status']]
                   for f in x['found'] if f not in x['own']]
        out.append({'iid': r['TradeIssueID'], 'cid': r['TradeComicID'], 'name': c['ComicName'], 'year': c['ComicYear'],
                    'pub': c['ComicPublisher'], 'type': c['Corrected_Type'] or c['Type'], 'num': t['Issue_Number'],
                    'tstatus': t['Status'], 'collects': r['Collects'] or '', 'found': len(x['found']), 'own': len(x['own']),
                    'unresolved': sum(len(u['nums']) for u in x['unresolved']), 'lacking': lacking, 'coverage': x['coverage'],
                    'extras': sorted({_extra_name(u, x['found'], status, comics) for u in x['other']})})
    return {'trades': out, 'build': status_summary(myDB)}


def status_summary(myDB=None):
    myDB = myDB or db.DBConnection()
    _ensure_table(myDB)
    row = myDB.selectone('SELECT count(*), max(Updated) FROM ledger_collects').fetchone()
    s = status()
    s.update(stored=row[0], updated=row[1], metron=bool(metron_token()),
             metron_found=myDB.selectone("SELECT count(*) FROM ledger_collects WHERE Source='metron'").fetchone()[0])
    return s
