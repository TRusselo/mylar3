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
    done = 0
    now = time.time()
    for root, dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith(ARCHIVE_EXT):
                continue
            path = os.path.join(root, name)
            try:
                if now - os.path.getmtime(path) < SETTLE_SECONDS:
                    continue
                if unpack(path):
                    done += 1
            except Exception as e:
                logger.warn('[ARCHIVE] Unable to unpack %s: %s' % (path, e))
    return done


def prepare(path):
    if not path:
        return None
    try:
        if os.path.isdir(path):
            unpack_folder(path)
            return None
        if os.path.isfile(path) and path.lower().endswith(ARCHIVE_EXT):
            return unpack(path)
    except Exception as e:
        logger.warn('[ARCHIVE] Unable to unpack %s: %s' % (path, e))
    return None
