import pytest

from mylar import search_filer


@pytest.mark.unit
@pytest.mark.parametrize('name,expected', [
    ('X-Men - Battle of the Atom Complete', 'X-Men - Battle of the Atom'),
    ('Batman: Hush - The Complete Collection', 'Batman: Hush'),
    ('Saga Complete Series', 'Saga'),
])
def test_strips_complete(name, expected):
    out = search_filer.without_complete({'series_name': name, 'series_name_decoded': name, 'issue_number': '1'})
    assert out['series_name'] == expected and out['series_name_decoded'] == expected and out['issue_number'] == '1'


@pytest.mark.unit
@pytest.mark.parametrize('name', ['Completely Insane', 'The Incomplete Guide', 'X-Men', 'Complete'])
def test_leaves_other_titles(name):
    assert search_filer.without_complete({'series_name': name}) is None
