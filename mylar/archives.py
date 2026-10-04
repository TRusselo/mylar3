import os
import shutil
import time
import zipfile

import mylar
from mylar import logger
from lib.rarfile import rarfile

COMIC_EXT = ('.cbz', '.cbr', '.cb7', '.pdf')
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.avif', '.jxl')
ARCHIVE_EXT = ('.zip', '.rar')
SETTLE_SECONDS = 120
MIN_PAGES = 3


def _open(path):
    if zipfile.is_zipfile(path):
        return zipfile.ZipFile(path)
    try:
        if rarfile.is_rarfile(path):
            return rarfile.RarFile(path)
    except Exception:
        pass
    return None


def _is_dir(info):
    test = getattr(info, 'is_dir', None) or getattr(info, 'isdir', None)
    return bool(test()) if test else info.filename.endswith('/')


def unpack(path):
    try:
        arc = _open(path)
    except Exception as e:
        logger.warn('[ARCHIVE] Unable to open %s: %s' % (path, e))
        return None
    if arc is None:
        return None
    is_zip = isinstance(arc, zipfile.ZipFile)
    with arc:
        files = [i for i in arc.infolist() if not _is_dir(i)]
        comics = [i for i in files if i.filename.lower().endswith(COMIC_EXT)]
        images = [i for i in files if i.filename.lower().endswith(IMAGE_EXT)]
        if not comics:
            if len(images) < MIN_PAGES:
                logger.info('[ARCHIVE] %s holds no comics or comic pages - leaving it alone.' % os.path.basename(path))
                return None
            arc_kind = 'comic'
        else:
            arc_kind = 'pack'
            dest = os.path.splitext(path)[0]
            os.makedirs(dest, exist_ok=True)
            out = []
            for info in comics:
                target = os.path.join(dest, os.path.basename(info.filename))
                if not (os.path.isfile(target) and os.path.getsize(target) == info.file_size):
                    with arc.open(info) as src, open(target + '.part', 'wb') as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
                    os.replace(target + '.part', target)
                out.append(target)
    if arc_kind == 'comic':
        target = os.path.splitext(path)[0] + ('.cbz' if is_zip else '.cbr')
        if os.path.exists(target):
            logger.info('[ARCHIVE] %s is a comic, but %s already exists - leaving it alone.' % (os.path.basename(path), os.path.basename(target)))
            return None
        os.rename(path, target)
        logger.info('[ARCHIVE] %s is a single comic - renamed to %s' % (os.path.basename(path), os.path.basename(target)))
        return 'comic', target
    logger.info('[ARCHIVE] Extracted %s comics from %s into %s' % (len(out), os.path.basename(path), dest))
    if getattr(mylar.CONFIG, 'ARCHIVE_DELETE', True) is not False:
        try:
            os.remove(path)
        except Exception as e:
            logger.warn('[ARCHIVE] Extracted %s but could not remove it: %s' % (os.path.basename(path), e))
    return 'pack', dest


def unpack_folder(folder):
    done = []
    now = time.time()
    for root, dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith(ARCHIVE_EXT):
                continue
            path = os.path.join(root, name)
            try:
                if now - os.path.getmtime(path) < SETTLE_SECONDS:
                    continue
                res = unpack(path)
                if res and res[0] == 'pack':
                    done.append(res[1])
            except Exception as e:
                logger.warn('[ARCHIVE] Unable to unpack %s: %s' % (path, e))
    return done


def prepare(path):
    if not path:
        return None, []
    try:
        if os.path.isdir(path):
            return None, unpack_folder(path)
        if os.path.isfile(path) and path.lower().endswith(ARCHIVE_EXT):
            res = unpack(path)
            return res, ([res[1]] if res and res[0] == 'pack' else [])
    except Exception as e:
        logger.warn('[ARCHIVE] Unable to unpack %s: %s' % (path, e))
    return None, []


def review_dir():
    configured = getattr(mylar.CONFIG, 'ARCHIVE_REVIEW_DIR', None)
    if configured and configured != 'None':
        return configured
    if mylar.CONFIG.CHECK_FOLDER:
        return os.path.join(os.path.dirname(os.path.normpath(mylar.CONFIG.CHECK_FOLDER)), 'mylar-review')
    return os.path.join(mylar.CONFIG.CACHE_DIR or '/config/mylar/cache', 'mylar-review')


def _leftover_action():
    return (getattr(mylar.CONFIG, 'ARCHIVE_LEFTOVERS', None) or 'review').lower()


def _dispose(path, rel_dir):
    if _leftover_action() == 'delete':
        os.remove(path)
        return 'deleted'
    dest = os.path.join(review_dir(), rel_dir) if rel_dir else review_dir()
    os.makedirs(dest, exist_ok=True)
    target = os.path.join(dest, os.path.basename(path))
    if os.path.exists(target):
        base, ext = os.path.splitext(target)
        target = '%s (%s)%s' % (base, int(time.time()), ext)
    shutil.move(path, target)
    return 'moved'


def _moving():
    return (getattr(mylar.CONFIG, 'FILE_OPTS', None) or 'move') == 'move'


def cleanup(folders):
    if not folders or not _moving():
        return
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        left = [os.path.join(r, n) for r, _, ns in os.walk(folder) for n in ns]
        comics = [p for p in left if p.lower().endswith(COMIC_EXT)]
        try:
            for p in comics:
                _dispose(p, os.path.basename(folder))
            if comics:
                logger.info('[ARCHIVE] %s %s issues from %s that nothing on the watchlist wanted%s' % (
                    'Deleted' if _leftover_action() == 'delete' else 'Moved', len(comics), os.path.basename(folder),
                    '' if _leftover_action() == 'delete' else ' to %s' % review_dir()))
            shutil.rmtree(folder)
        except Exception as e:
            logger.warn('[ARCHIVE] Unable to clear %s: %s' % (folder, e))


def sweep(folder, started):
    if not folder or not os.path.isdir(folder) or not _moving():
        return
    cutoff = started - SETTLE_SECONDS
    kept, junk = 0, 0
    for root, dirs, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)
            try:
                if os.path.getmtime(path) >= cutoff:
                    continue
                if name.lower().endswith(COMIC_EXT + ARCHIVE_EXT):
                    _dispose(path, os.path.relpath(root, folder) if root != folder else '')
                    kept += 1
                else:
                    os.remove(path)
                    junk += 1
            except Exception as e:
                logger.warn('[FOLDER MONITOR] Unable to clear %s: %s' % (path, e))
    for root, dirs, names in os.walk(folder, topdown=False):
        if root != folder and not os.listdir(root):
            try:
                os.rmdir(root)
            except Exception:
                pass
    if kept or junk:
        logger.info('[FOLDER MONITOR] Cleared the monitored folder: %s unfiled comics %s, %s other files deleted.' % (
            kept, 'deleted' if _leftover_action() == 'delete' else 'moved to %s' % review_dir(), junk))
