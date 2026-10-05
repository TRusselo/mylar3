import datetime
import os
import re
from collections import defaultdict

import mylar
from mylar import db, logger

COMIC_EXT = ('.cbz', '.cbr', '.cb7', '.pdf')
STORE_WINDOW = 21
COVER_WINDOW = 120
MAX_REFRESH = 15


def _norm(name):
    name = (name or '').lower().replace('&', 'and')
    name = re.sub(r'\bversus\b|\bvs\b\.?', 'vs', name)
    name = re.sub(r'\(\d{4}\)', '', name)
    name = re.sub(r'^the\s+', '', name.strip())
    return re.sub(r'[^a-z0-9]', '', name)


def _num(n):
    n = str(n or '').strip().upper().lstrip('0')
    return n or '0'


def _date(s):
    try:
        return datetime.date.fromisoformat((s or '')[:10])
    except ValueError:
        return None


def folder_date(path):
    for part in reversed(os.path.normpath(path).split(os.sep)):
        m = re.match(r'(\d{4})[.\-_ ](\d{2})[.\-_ ](\d{2})\b', part)
        if m:
            try:
                return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
    return None


class _Index(object):
    def __init__(self):
        myDB = db.DBConnection()
        self.byname = defaultdict(list)
        for c in myDB.select('SELECT ComicID, ComicName FROM comics'):
            self.byname[_norm(c['ComicName'])].append(c['ComicID'])
        self.issues = defaultdict(dict)
        for i in myDB.select('SELECT IssueID, ComicID, Issue_Number, ReleaseDate, IssueDate FROM issues'):
            self.issues[i['ComicID']][_num(i['Issue_Number'])] = (i['IssueID'], _date(i['ReleaseDate']), _date(i['IssueDate']))

    def find(self, name, issue, when):
        best = None
        for cid in self.byname.get(_norm(name), []):
            hit = self.issues[cid].get(_num(issue))
            if not hit:
                continue
            iid, store, cover = hit
            if store:
                gap = abs((store - when).days)
                if gap > STORE_WINDOW:
                    continue
            elif cover:
                gap = abs((cover - when).days)
                if gap > COVER_WINDOW:
                    continue
            else:
                continue
            if best is None or gap < best[0]:
                best = (gap, iid, cid)
        return best

    def stale(self, name, when):
        out = []
        for cid in self.byname.get(_norm(name), []):
            dates = [d for _, s, c in self.issues[cid].values() for d in (s or c,) if d]
            if not dates or max(dates) < when - datetime.timedelta(days=7):
                out.append(cid)
        return out


def _parse(folder, filename):
    from mylar import filechecker
    try:
        res = filechecker.FileChecker(dir=folder, file=filename).listFiles()
    except Exception:
        return None
    if not res or res.get('parse_status') != 'success' or not res.get('series_name') or not res.get('issue_number'):
        return None
    return res['series_name'], str(res['issue_number'])


def tag(folder):
    if not folder or not os.path.isdir(folder):
        return 0
    todo = []
    for root, dirs, names in os.walk(folder):
        when = folder_date(root)
        if not when:
            continue
        for name in names:
            if name.lower().endswith(COMIC_EXT) and '[__' not in name:
                todo.append((root, name, when))
    if not todo:
        return 0
    index = _Index()
    tagged, refreshed, pending = 0, set(), []
    for root, name, when in todo:
        parsed = _parse(root, name)
        if not parsed:
            continue
        hit = index.find(parsed[0], parsed[1], when)
        if hit is None:
            pending.append((root, name, when, parsed))
            continue
        tagged += _rename(root, name, hit[1])
    if pending:
        from mylar import updater
        for root, name, when, parsed in pending:
            for cid in index.stale(parsed[0], when):
                if cid not in refreshed and len(refreshed) < MAX_REFRESH:
                    refreshed.add(cid)
                    try:
                        updater.dbUpdate(ComicIDList=[cid], calledfrom='packdate')
                    except Exception as e:
                        logger.warn('[PACK-DATE] Unable to refresh %s: %s' % (cid, e))
        if refreshed:
            index = _Index()
            for root, name, when, parsed in pending:
                hit = index.find(parsed[0], parsed[1], when)
                if hit is not None:
                    tagged += _rename(root, name, hit[1])
    if tagged:
        logger.info('[PACK-DATE] Matched %s issues straight to your series using the pack release dates%s.' % (
            tagged, (' (refreshed %s series first)' % len(refreshed)) if refreshed else ''))
        from mylar import archives
        archives.note('matched %s issues by pack date' % tagged)
    return tagged


def _rename(root, name, issueid):
    base, ext = os.path.splitext(name)
    target = os.path.join(root, '%s [__%s__]%s' % (base, issueid, ext))
    if os.path.exists(target):
        return 0
    try:
        os.rename(os.path.join(root, name), target)
    except Exception as e:
        logger.warn('[PACK-DATE] Unable to tag %s: %s' % (name, e))
        return 0
    return 1
