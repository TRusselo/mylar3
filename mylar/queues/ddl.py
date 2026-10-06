"""DDL queue worker functions."""

import datetime
import os
import re
import time

import mylar
from .. import logger, helpers
from mylar import db, getcomics
from mylar.downloaders import mediafire, mega, pixeldrain


ACTIVE = [None]


def waiting_ids():
    with mylar.DDL_QUEUE.mutex:
        ids = {str(i.get('id')) for i in list(mylar.DDL_QUEUE.queue) if isinstance(i, dict)}
    if ACTIVE[0] is not None:
        ids.add(str(ACTIVE[0]))
    return ids


def reload_saved(myDB):
    try:
        myDB.action("UPDATE ddl_info SET status='Queued' WHERE status='Downloading' AND jd2_job_id IS NULL")
        chk = myDB.selectone("SELECT count(*) AS count FROM ddl_info WHERE status='Queued' AND jd2_job_id IS NULL").fetchone()
        if chk and chk['count']:
            from mylar import webserve
            logger.info('[DDL-QUEUE] Picking up %s downloads that were waiting when Mylar stopped.' % chk['count'])
            webserve.WebInterface().ddl_requeue(mode='restart_queue')
    except Exception as e:
        logger.warn('[DDL-QUEUE] Unable to reload the saved queue: %s' % e)


def ddl_downloader(queue):
    myDB = db.DBConnection()
    link_type_failure = {}
    reload_saved(myDB)
    while True:
        if mylar.DDL_LOCK is True:
            time.sleep(5)

        elif mylar.DDL_LOCK is False and queue.qsize() >= 1:
            item = queue.get(True)

            if item == 'exit':
                logger.info('Cleaning up workers for shutdown')
                break

            ACTIVE[0] = item.get('id')
            try:
                ddl_process(myDB, item, link_type_failure)
            except Exception as e:
                logger.exception('[DDL-QUEUE] Error while handling %s: %s' % (item.get('series'), e))
                try:
                    ddl_give_up(myDB, item, {'id': item['id']}, link_type_failure)
                except Exception as e2:
                    logger.warn('[DDL-QUEUE] Unable to mark %s as failed: %s' % (item.get('series'), e2))
            finally:
                ACTIVE[0] = None
        else:
            time.sleep(5)


def ddl_process(myDB, item, link_type_failure):
    if item['id'] not in mylar.DDL_QUEUED:
        mylar.DDL_QUEUED.append(item['id'])

    try:
        link_type_failure[item['id']].append(item['link_type_failure'])
    except Exception:
        pass

    if ddl_cancelled(item):
        return

    logger.info('Now loading request from DDL queue: %s' % item['series'])

    ctrlval = {'id':      item['id']}
    val = {'status':       'Downloading',
           'updated_date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
    myDB.upsert('ddl_info', val, ctrlval)

    if item['site'] == 'DDL(GetComics)':
        try:
            remote_filesize = item['remote_filesize']
        except Exception:
            try:
                remote_filesize = helpers.human2bytes(re.sub('/s', '', item['size'][:-1]).strip())
            except Exception:
                remote_filesize = 0

        if any([item['link_type'] == 'GC-Main', item['link_type'] == 'GC-Mirror']):
            ddz = getcomics.GC()
            ddzstat = ddz.downloadit(item['id'], item['link'], item['mainlink'], item['resume'], item['issueid'], remote_filesize)
        elif item['link_type'] == 'GC-Mega':
            meganz = mega.MegaNZ()
            ddzstat = meganz.ddl_download(item['link'], None, item['id'], item['issueid'], item['link_type'])
        elif item['link_type'] == 'GC-Media':
            mediaf = mediafire.MediaFire()
            ddzstat = mediaf.ddl_download(item['link'], item['id'], item['issueid'])
        elif item['link_type'] == 'GC-Pixel':
            pdrain = pixeldrain.PixelDrain()
            ddzstat = pdrain.ddl_download(item['link'], item['id'], item['issueid'])
        else:
            ddzstat = {'success': False, 'filename': None, 'path': None, 'link_type': item['link_type']}

    elif item['site'] == 'DDL(External)':
        meganz = mega.MegaNZ()
        ddzstat = meganz.ddl_download(item['link'], item['filename'], item['id'], item['issueid'], item['link_type'])

    if ddl_cancelled(item, ddzstat):
        return

    if ddzstat['success'] and ddzstat['filename'] is not None:
        filecondition = helpers.check_file_condition(ddzstat['path'])
        if not filecondition['status']:
            logger.warn(f"CRC Check: File {ddzstat['path']} failed condition check ({filecondition['quality']}).  Marking as failed.")
            ddzstat['success'] = False
            ddzstat['link_type_failure'] = item['link_type']

    if ddzstat['success'] is True:
        tdnow = datetime.datetime.now()
        nval = {'status':  'Completed',
                'updated_date': tdnow.strftime('%Y-%m-%d %H:%M')}
        myDB.upsert('ddl_info', nval, ctrlval)

    if all([ddzstat['success'] is True, mylar.CONFIG.POST_PROCESSING is True]):
        try:
            if ddzstat['filename'] is None:
                logger.info('%s successfully downloaded - now initiating post-processing for %s.' % (os.path.basename(ddzstat['path']), ddzstat['path']))
                mylar.PP_QUEUE.put({'nzb_name':     os.path.basename(ddzstat['path']),
                                    'nzb_folder':   ddzstat['path'],
                                    'failed':       False,
                                    'issueid':      None,
                                    'comicid':      item['comicid'],
                                    'apicall':      True,
                                    'ddl':          True,
                                    'download_info': {'provider': 'DDL', 'id': item['id']}})
            else:
                logger.info('%s successfully downloaded - now initiating post-processing for %s' % (ddzstat['filename'], ddzstat['path']))
                mylar.PP_QUEUE.put({'nzb_name':     ddzstat['filename'],
                                    'nzb_folder':   ddzstat['path'],
                                    'failed':       False,
                                    'issueid':      item['issueid'],
                                    'comicid':      item['comicid'],
                                    'apicall':      True,
                                    'ddl':          True,
                                    'download_info': {'provider': 'DDL', 'id': item['id']}})
        except Exception as e:
            logger.error('process error: %s [%s]' %(e, ddzstat))

        mylar.DDL_QUEUED.remove(item['id'])
        try:
            link_type_failure.pop(item['id'])
        except KeyError:
            pass

        try:
            pck_cnt = 0
            if item['comicinfo'][0]['pack'] is True:
                logger.fdebug('[PACK DETECTION] Attempting to remove issueids from the pack dont-queue list')
                for x,y in dict(mylar.PACK_ISSUEIDS_DONT_QUEUE).items():
                    if y == item['id']:
                        pck_cnt +=1
                        del mylar.PACK_ISSUEIDS_DONT_QUEUE[x]
                logger.fdebug('Successfully removed %s issueids from pack queue list as download is completed.' % pck_cnt)
        except Exception:
            pass

        ddl_cleanup(item['id'])

    elif all([ddzstat['success'] is True, mylar.CONFIG.POST_PROCESSING is False]):
        path = ddzstat['path']
        if ddzstat['filename'] is not None:
            path = os.path.join(path, ddzstat['filename'])
        logger.info('File successfully downloaded. Post Processing is not enabled - item retained here: %s' % (path,))
        ddl_cleanup(item['id'])
    else:
        if item['site'] == 'DDL(GetComics)':
            try:
                ltf = ddzstat['links_exhausted']
            except KeyError:
                logger.info('[Status: %s] Failed to download item from %s : %s ' % (ddzstat['success'], item['link_type'], ddzstat))
                try:
                    link_type_failure[item['id']].append(item['link_type'])
                except KeyError:
                    link_type_failure[item['id']] = [item['link_type']]
                logger.fdebug('[%s] link_type_failure: %s' % (item['id'], link_type_failure))
                ggc = getcomics.GC(comicid=item['comicid'], issueid=item['issueid'], oneoff=item['oneoff'])
                redo = ggc.parse_downloadresults(item['id'], item['mainlink'], item['comicinfo'], item['packinfo'], link_type_failure[item['id']])
                # parse_downloadresults re-queues the next link itself; when none are left it
                # only returns links_exhausted, so the item has to be failed here.
                if isinstance(redo, dict) and 'links_exhausted' in redo:
                    ddl_give_up(myDB, item, ctrlval, link_type_failure)
            else:
                ddl_give_up(myDB, item, ctrlval, link_type_failure)
        else:
            logger.info('[Status: %s] Failed to download item from %s : %s ' % (ddzstat['success'], item['site'], ddzstat))
            myDB.action('DELETE FROM ddl_info where id=?', [item['id']])
            mylar.search.FailedMark(item['issueid'], item['comicid'], item['id'], ddzstat['filename'], item['site'], retry=True)


def ddl_cancelled(item, ddzstat=None):
    if str(item['id']) not in mylar.DDL_CANCEL:
        if ddzstat is None or not ddzstat.get('cancelled'):
            return False
    mylar.DDL_CANCEL.discard(str(item['id']))
    logger.info('[DDL-ABORT] Dropped %s - it was aborted or removed from the queue.' % item['series'])
    if ddzstat and ddzstat.get('success') and ddzstat.get('path'):
        logger.info('[DDL-ABORT] The finished download was left at %s and will not be post-processed.' % ddzstat['path'])
    helpers.reverse_the_pack_snatch(item['id'], item['comicid'])
    for x, y in dict(mylar.PACK_ISSUEIDS_DONT_QUEUE).items():
        if y == item['id']:
            del mylar.PACK_ISSUEIDS_DONT_QUEUE[x]
    if item['id'] in mylar.DDL_QUEUED:
        mylar.DDL_QUEUED.remove(item['id'])
    ddl_cleanup(item['id'])
    return True


def ddl_give_up(myDB, item, ctrlval, link_type_failure):
    # every link for this item failed - mark it Failed instead of leaving the issue sitting at Snatched
    logger.info('[REDO] Exhausted all available links [%s] for issueid %s and was not able to download anything' % (link_type_failure.get(item['id']), item['issueid']))
    myDB.upsert('ddl_info', {'status': 'Failed',
                             'updated_date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}, ctrlval)
    helpers.reverse_the_pack_snatch(item['id'], item['comicid'])
    try:
        is_pack = item['comicinfo'][0]['pack'] is True
    except Exception:
        is_pack = False
    if all([not is_pack, not item.get('oneoff'), item.get('issueid') is not None]):
        try:
            mylar.search.FailedMark(item['issueid'], item['comicid'], item['id'], item['series'], item['site'], retry=True)
        except Exception as e:
            logger.warn('[REDO] Unable to mark issueid %s as Failed: %s' % (item['issueid'], e))
    if item['id'] in mylar.DDL_QUEUED:
        mylar.DDL_QUEUED.remove(item['id'])
    link_type_failure.pop(item['id'], None)
    ddl_cleanup(item['id'])


def ddl_cleanup(record_id):
    if getattr(mylar.CONFIG, 'KEEP_HTML_CACHE', False):
        logger.fdebug('[HTML-cleanup] KEEP_HTML_CACHE enabled; skipping removal for %s.', record_id)
        return

    tlnk = 'getcomics-%s.html' % record_id
    cache_path = os.path.join(mylar.CONFIG.CACHE_DIR, 'html_cache', tlnk)
    try:
        os.remove(cache_path)
    except FileNotFoundError:
        logger.fdebug('[HTML-cleanup] %s not found in html_cache. Nothing to remove.', tlnk)
    except Exception as e:
        logger.fdebug('[HTML-cleanup] Unable to remove %s from html_cache: %s. '
                      'Manual removal required or set `cleanup_cache=True` in the config.ini to '
                      'clean cache items on every startup. If this was a Retry - ignore this.',
                      tlnk, e)
