import pytest

import mylar
from mylar import importstatus


@pytest.fixture(autouse=True)
def reset_state(monkeypatch, tmp_path):
    monkeypatch.setattr(mylar, 'DATA_DIR', str(tmp_path), raising=False)
    importstatus.start('import')
    importstatus.finish()
    yield


@pytest.mark.unit
def test_import_progress_and_stop():
    assert importstatus.running() is None
    importstatus.start('import', 'Importing 4 series')
    importstatus.update(series_total=4)
    importstatus.current_series('Test Hero (v2020)')
    importstatus.inc('series_done')
    snap = importstatus.snapshot()
    assert snap['running'] and snap['phase'] == 'importing' and snap['series_current'] == 'Test Hero (v2020)'
    assert importstatus.running() == 'import'
    assert importstatus.request_stop() is True
    assert importstatus.stop_requested() and importstatus.snapshot()['phase'] == 'stopping'
    importstatus.finish('stopped')
    snap = importstatus.snapshot()
    assert not snap['running'] and snap['result'] == 'stopped' and not snap['stop_requested']
    assert importstatus.request_stop() is False


@pytest.mark.unit
def test_phase_ignored_when_idle():
    importstatus.phase('scanning')
    assert importstatus.running() is None


@pytest.mark.unit
def test_resume_marker_roundtrip():
    assert importstatus.load_resume() is None
    importstatus.save_resume({'action': 'massimport', 'series': None})
    assert importstatus.load_resume()['action'] == 'massimport'
    importstatus.clear_resume()
    assert importstatus.load_resume() is None
    importstatus.clear_resume()
