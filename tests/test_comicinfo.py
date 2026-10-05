import io
import os
import types
import zipfile

import pytest

import mylar
from mylar import comicinfo

ORIGINAL = '''<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Series>Test Hero</Series>
  <Number>12</Number>
  <Summary></Summary>
  <Notes>[CVDB12345]</Notes>
  <Writer>Hand Picked</Writer>
  <StoryArc>Big Event (Reading Order)</StoryArc>
  <StoryArcNumber>7</StoryArcNumber>
  <Tags>favourite</Tags>
  <GTIN>9781234567897</GTIN>
  <Pages>
    <Page Image="0" Type="FrontCover" ImageSize="123456" />
    <Page Image="1" ImageSize="99999" />
  </Pages>
</ComicInfo>'''.encode('utf-8')

TAGGED = '''<?xml version="1.0"?>
<ComicInfo>
  <Series>Test Hero (2019)</Series>
  <Number>12</Number>
  <Summary>The hero &amp; friends save the day.</Summary>
  <Notes>Tagged with ComicTagger [Issue ID 99999]</Notes>
  <Writer>Someone Else</Writer>
  <Penciller>Pen Person</Penciller>
  <Publisher>Test Comics</Publisher>
  <Year>2023</Year>
  <StoryArc>Different Arc</StoryArc>
</ComicInfo>'''.encode('utf-8')


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(mylar, 'CONFIG', types.SimpleNamespace(CT_TAG_MODE='fill', CT_CBZ_OVERWRITE=False), raising=False)


def field(xml, tag):
    import xml.etree.ElementTree as ET
    el = ET.fromstring(xml).find(tag)
    return None if el is None else (el.text or '').strip()


@pytest.mark.unit
def test_fill_keeps_every_existing_value():
    out, added, replaced = comicinfo.merge(ORIGINAL, TAGGED, 'fill')
    assert replaced == []
    assert sorted(added) == ['Penciller', 'Publisher', 'Summary', 'Year']
    for tag, value in (('Series', 'Test Hero'), ('Notes', '[CVDB12345]'), ('Writer', 'Hand Picked'),
                       ('StoryArc', 'Big Event (Reading Order)'), ('StoryArcNumber', '7'), ('Tags', 'favourite'), ('GTIN', '9781234567897')):
        assert field(out, tag) == value
    assert field(out, 'Summary') == 'The hero & friends save the day.'
    assert field(out, 'Penciller') == 'Pen Person' and field(out, 'Year') == '2023'
    assert b'ImageSize="123456"' in out and b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' in out
    text = out.decode()
    assert text.startswith(ORIGINAL.decode().split('<Summary>')[0])


@pytest.mark.unit
def test_nothing_new_returns_original_bytes():
    same = ORIGINAL.replace(b'<Summary></Summary>', b'<Summary>Already here</Summary>')
    tagged = b'<ComicInfo><Series>Other</Series><Writer>Other</Writer><Summary>New</Summary></ComicInfo>'
    out, added, replaced = comicinfo.merge(same, tagged, 'fill')
    assert out is same and not added and not replaced


@pytest.mark.unit
def test_overwrite_only_touches_comictagger_fields():
    out, added, replaced = comicinfo.merge(ORIGINAL, TAGGED, 'overwrite')
    assert field(out, 'Series') == 'Test Hero (2019)' and field(out, 'Writer') == 'Someone Else'
    assert 'Series' in replaced and 'Notes' in replaced
    assert field(out, 'Tags') == 'favourite' and field(out, 'GTIN') == '9781234567897'
    assert b'ImageSize="123456"' in out


@pytest.mark.unit
def test_no_original_uses_tagged():
    out, added, replaced = comicinfo.merge(None, TAGGED)
    assert out is TAGGED


@pytest.mark.unit
def test_unreadable_tagged_keeps_original():
    out, _, _ = comicinfo.merge(ORIGINAL, b'<ComicInfo><broken>')
    assert out is ORIGINAL


@pytest.mark.unit
def test_bom_and_utf16_survive():
    bom = b'\xef\xbb\xbf' + ORIGINAL
    out, added, _ = comicinfo.merge(bom, TAGGED)
    assert out.startswith(b'\xef\xbb\xbf') and 'Publisher' in added
    u16 = ORIGINAL.decode().replace('utf-8', 'utf-16').encode('utf-16')
    out, added, _ = comicinfo.merge(u16, TAGGED)
    assert out.decode('utf-16').count('<Publisher>Test Comics</Publisher>') == 1


def make_zip(path, cix, comment=b'cbl data'):
    with zipfile.ZipFile(path, 'w') as z:
        z.comment = comment
        z.writestr('001.jpg', b'page one')
        z.writestr('ComicInfo.xml', cix)
        z.writestr('002.jpg', b'page two')
    return str(path)


@pytest.mark.unit
def test_keep_existing_rewrites_archive(tmp_path):
    p = make_zip(tmp_path / 'a.cbz', TAGGED)
    assert comicinfo.keep_existing(ORIGINAL, p, 'fill')
    with zipfile.ZipFile(p) as z:
        assert [i.filename for i in z.infolist()] == ['001.jpg', 'ComicInfo.xml', '002.jpg']
        assert z.comment == b'cbl data' and z.read('001.jpg') == b'page one'
        cix = z.read('ComicInfo.xml')
    assert field(cix, 'Series') == 'Test Hero' and field(cix, 'Publisher') == 'Test Comics'
    assert os.listdir(tmp_path) == ['a.cbz']


@pytest.mark.unit
def test_keep_existing_restores_original_when_nothing_new(tmp_path):
    p = make_zip(tmp_path / 'b.cbz', b'<ComicInfo><Series>CT</Series></ComicInfo>')
    original = b'<ComicInfo><Series>Mine</Series></ComicInfo>'
    assert comicinfo.keep_existing(original, p, 'fill')
    with zipfile.ZipFile(p) as z:
        assert z.read('ComicInfo.xml') == original


@pytest.mark.unit
def test_skip_mode_leaves_file(tmp_path):
    p = make_zip(tmp_path / 'c.cbz', TAGGED)
    assert comicinfo.keep_existing(ORIGINAL, p, 'skip')
    with zipfile.ZipFile(p) as z:
        assert z.read('ComicInfo.xml') == TAGGED


@pytest.mark.unit
def test_mode_from_config():
    assert comicinfo.tag_mode() == 'fill'
    mylar.CONFIG.CT_TAG_MODE = None
    mylar.CONFIG.CT_CBZ_OVERWRITE = True
    assert comicinfo.tag_mode() == 'overwrite'
    mylar.CONFIG.CT_TAG_MODE = 'skip'
    assert comicinfo.tag_mode() == 'skip'


@pytest.mark.unit
def test_read_raw_from_rar():
    here = os.path.join(os.path.dirname(__file__), 'data', 'rar')
    assert comicinfo.read_raw(os.path.join(here, 'rar5-solid.rar')) is None
