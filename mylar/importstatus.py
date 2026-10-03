#  This file is part of Mylar.
#
#  Mylar is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Mylar is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
#  implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
#  License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Mylar.  If not, see <http://www.gnu.org/licenses/>.

# Live progress for library scans / mass imports (and ComicVine rate-limit waits),
# polled by the web ui via webserve.import_progress.

import threading
import time

_lock = threading.RLock()

PHASES = {'idle': 'Idle',
          'scanning': 'Scanning files',
          'metadata': 'Reading metadata',
          'cv_lookup': 'ComicVine lookup',
          'saving': 'Saving scan results',
          'importing': 'Importing series',
          'stopping': 'Stopping'}

def _blank():
    return {'phase': 'idle',
            'mode': None,
            'started': None,
            'finished': None,
            'result': None,
            'message': None,
            'stop_requested': False,
            'files_found': 0,
            'files_total': 0,
            'files_parsed': 0,
            'files_analyzed': 0,
            'parse_failures': 0,
            'issueids_total': 0,
            'issueids_resolved': 0,
            'series_total': 0,
            'series_done': 0,
            'series_added': 0,
            'series_manual': 0,
            'series_noresults': 0,
            'series_failed': 0,
            'series_current': None,
            'series_started': None,
            'phase_started': None}

_state = _blank()
_ratelimit = {'until': None, 'reason': None, 'resource': None, 'attempt': 0, 'count': 0}


def start(mode, message=None):
    global _state
    with _lock:
        rl_count = _ratelimit['count']
        _state = _blank()
        _state['mode'] = mode
        _state['started'] = time.time()
        _state['phase_started'] = _state['started']
        _state['phase'] = 'scanning' if mode == 'scan' else 'importing'
        _state['message'] = message
        _state['rl_base'] = rl_count


def phase(name, message=None):
    with _lock:
        _state['phase'] = name
        _state['phase_started'] = time.time()
        if message is not None:
            _state['message'] = message


def update(**kwargs):
    with _lock:
        _state.update(kwargs)


def inc(key, amount=1):
    with _lock:
        _state[key] = _state.get(key, 0) + amount


def current_series(name):
    with _lock:
        _state['series_current'] = name
        _state['series_started'] = time.time()


def finish(result='completed', message=None):
    with _lock:
        if _state['mode'] is None:
            return
        _state['phase'] = 'idle'
        _state['finished'] = time.time()
        _state['result'] = result
        _state['series_current'] = None
        _state['stop_requested'] = False
        if message is not None:
            _state['message'] = message


def running():
    with _lock:
        return _state['mode'] if _state['phase'] != 'idle' else None


def request_stop():
    with _lock:
        if _state['phase'] == 'idle':
            return False
        _state['stop_requested'] = True
        _state['phase'] = 'stopping'
        return True


def stop_requested():
    return _state['stop_requested']


def set_ratelimit(reason, resource, wait, attempt):
    with _lock:
        _ratelimit['until'] = time.time() + wait
        _ratelimit['reason'] = reason
        _ratelimit['resource'] = resource
        _ratelimit['attempt'] = attempt
        _ratelimit['count'] += 1


def clear_ratelimit():
    with _lock:
        _ratelimit['until'] = None
        _ratelimit['attempt'] = 0


def ratelimit_remaining():
    until = _ratelimit['until']
    if until is None:
        return 0
    return max(0, until - time.time())


def snapshot():
    with _lock:
        s = dict(_state)
        rl = dict(_ratelimit)
    now = time.time()
    s['phase_label'] = PHASES.get(s['phase'], s['phase'])
    s['running'] = s['phase'] != 'idle'
    end = s['finished'] if s['finished'] else now
    s['elapsed'] = int(end - s['started']) if s['started'] else 0
    s['eta'] = None
    remaining = ratelimit_remaining()
    s['ratelimit'] = {'active': remaining > 0,
                      'remaining': int(remaining),
                      'reason': rl['reason'],
                      'resource': rl['resource'],
                      'attempt': rl['attempt'],
                      'waits': rl['count'] - s.pop('rl_base', 0)}
    if s['running'] and s['phase_started']:
        spent = now - s['phase_started']
        done = total = 0
        if s['phase'] == 'importing':
            done, total = s['series_done'], s['series_total']
        elif s['phase'] == 'metadata':
            done, total = s['files_analyzed'], s['files_total']
        elif s['phase'] == 'cv_lookup':
            done, total = s['issueids_resolved'], s['issueids_total']
        if done > 0 and total > done and spent > 0:
            s['eta'] = int(spent / done * (total - done))
    return s
