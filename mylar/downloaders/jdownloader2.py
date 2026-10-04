#  This file is part of Mylar.
#
#  Provides a lightweight wrapper around the JDownloader2 remote API so
#  GetComics links can be handed off for downloading.

import json
import os
import datetime
import time
from typing import Any, Dict, List, Optional

import requests

import mylar
from mylar import db, logger


class JDownloader2(object):
    """Simple helper for submitting links to JDownloader2 and polling status."""

    LINKGRABBER_ENDPOINT = 'linkgrabberv2/addLinks'
    LINKGRABBER_QUERY_ENDPOINT = 'linkgrabberv2/queryLinks'
    DOWNLOADS_ENDPOINT = 'downloadsV2/queryLinks'

    def __init__(self, base_url: Optional[str] = None, timeout: int = 30, session: Optional[requests.Session] = None):
        self.base_url = (base_url or mylar.CONFIG.JD2_URL or '').rstrip('/')
        if not self.base_url:
            raise ValueError('JD2 URL is not configured')
        self.timeout = timeout
        self.session = session or requests.Session()

        self.destination_root = mylar.CONFIG.JD2_DEST_DIR
        self.destination_folder = None
        if self.destination_root:
            self.destination_folder = self.destination_root
            try:
                os.makedirs(self.destination_folder, exist_ok=True)
            except Exception as err:
                logger.warn('[JD2] Unable to ensure destination folder exists: %s', err)
                self.destination_folder = None

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def submit(self, links: dict, package_name: str, record_id: Optional[str] = None) -> Dict[str, Any]:
        """Submit a link to JD2 and return the assigned job id (if any)."""
        query = {
            'assignJobID': True,
            'autostart': True,
            'packageName': package_name,
           
        }
        if self.destination_folder:
            query['destinationFolder'] = self.destination_folder
        endpoint = self._url(self.LINKGRABBER_ENDPOINT)
        payload = None
        job_id = None
        
        for url, priority in links.items():
            query['priority'] = priority
            query['links'] = url
            params = {'query': json.dumps(query)}
            try:
                resp = self.session.get(
                    endpoint,
                    params=params,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
            except Exception as err:
                logger.error('[JD2] Failed to submit %s (url=%s params=%s): %s', package_name, endpoint, params, err)
                continue
            if payload is None or job_id is None:
                try:
                    payload = resp.json() or None
                    if isinstance(payload, dict):
                        data = payload.get('data', payload)
                        if isinstance(data, dict):
                            job_id = data.get('id') or data.get('jobID')
                            time.sleep(1)
                except Exception as json_err:
                    logger.warn('[JD2] Unable to decode submit response JSON: %s', json_err)
                    
        if job_id is None:
            logger.error('[JD2] No job id returned for %s', package_name)
            return {'status': False, 'jobid': None, 'error': err}

        if record_id:
            try:
                myDB = db.DBConnection()
                myDB.upsert(
                    'ddl_info',
                    {
                        'jd2_job_id': str(job_id),
                        'status': 'Queued',
                        'updated_date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                    },
                    {'id': record_id},
                )
            except Exception as err:
                logger.error('[JD2] Unable to update database for job id %s for record %s: %s', job_id, record_id, err)
                return {'status': False, 'jobid': None, 'error': err}
    
        return {'status': True, 'jobid': str(job_id), 'payload': payload}

    def query_links(self, id: str) -> Dict[str, Any]:

        query = {
            "jobUUIDs": list(id),
        }

        endpoint = self._url(self.LINKGRABBER_QUERY_ENDPOINT)
        try:
            response = requests.get(endpoint, params=json.dumps(query), timeout=self.timeout)
            response.raise_for_status()
        except Exception as err:
            logger.error(
                "[JD2] Failed to query links (url=%s id=%s): %s",
                endpoint,
                id,
                err,
            )
            
        try:
            payload = response.json() or {}
        except Exception as json_err:
            logger.warning("[JD2] Unable to decode links JSON: %s", json_err)
            payload = {}

        data = payload.get("data", payload if isinstance(payload, list) else [])
        result = data if isinstance(data, list) else []
        return result

    def query(self, job_ids: List[str]) -> List[Dict[str, Any]]:
        if not job_ids:
            return []
        query = {
            'jobUUID': True,
            'jobUUIDs': job_ids,
            'status': True,
            'finished': True,
            'packageUUID': True,
            'uuid': True,
            'name': True,
            'maxResults': 1000,
            'startAt': 0,
        }
        endpoint = self._url(self.DOWNLOADS_ENDPOINT)
        params = {'queryParams': json.dumps(query)}
        try:
            resp = self.session.get(
                endpoint,
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except Exception as err:
            logger.error('[JD2] Failed to query job ids %s (url=%s params=%s): %s', job_ids, endpoint, params, err)
            return []

        try:
            payload = resp.json() or {}
        except Exception as json_err:
            logger.warn('[JD2] Unable to decode query response JSON: %s', json_err)
            payload = {}


        data = payload.get('data', payload if isinstance(payload, list) else [])
        return data if isinstance(data, list) else []

    DONE = ('finished', 'finished(mirror)', 'done', 'extraction ok', 'crc ok')
    DEAD = ('offline', 'file not found', 'not available', 'plugin defect', 'aborted', 'blocked by cloudflare', 'failed', 'error')

    def _links(self, endpoint, query):
        query = dict(query, status=True, finished=True, packageUUID=True, jobUUID=True, uuid=True, name=True, maxResults=1000, startAt=0)
        r = self.session.get(self._url(endpoint), params={'queryParams': json.dumps(query)}, timeout=self.timeout)
        r.raise_for_status()
        data = (r.json() or {}).get('data') or []
        return [l for l in data if isinstance(l, dict)]

    def _package_links(self, job_id):
        own = self._links('downloadsV2/queryLinks', {'jobUUIDs': [job_id]})
        packages = sorted({l.get('packageUUID') for l in own if l.get('packageUUID')})
        if not packages:
            return own, packages
        return self._links('downloadsV2/queryLinks', {'packageUUIDs': packages}), packages

    def status(self, job_id: str) -> Dict[str, Any]:
        if job_id is None:
            return {'found': False, 'status': None, 'data': None}
        try:
            links, packages = self._package_links(job_id)
        except Exception as err:
            logger.warn('[JD2] Unable to query job %s: %s', job_id, err)
            return {'found': True, 'status': None, 'data': None}
        if not links:
            return {'found': False, 'status': None, 'data': None}
        done = [l for l in links if l.get('finished') is True or any(d in str(l.get('status') or '').lower() for d in self.DONE)]
        if done:
            return {'found': True, 'status': 'Finished', 'data': done[0]}
        states = [str(l.get('status') or '').lower() for l in links]
        if all(st and any(d in st for d in self.DEAD) for st in states):
            return {'found': True, 'status': 'Failed', 'data': links[0],
                    'reason': '; '.join(sorted({str(l.get('status')) for l in links}))}
        return {'found': True, 'status': links[0].get('status') or 'Queued', 'data': links[0]}

    def remove(self, job_id: str) -> None:
        if not job_id:
            return
        try:
            links, packages = self._package_links(job_id)
            names = {l.get('packageName') or '' for l in links}
            if packages:
                self.session.get(self._url('downloadsV2/removeLinks'), params={'linkIds': '[]', 'packageIds': json.dumps(packages)}, timeout=self.timeout)
            r = self.session.get(self._url('linkgrabberv2/queryPackages'), params={'queryParams': json.dumps({'uuid': True, 'name': True})}, timeout=self.timeout)
            pkg_names = {p.get('uuid'): p.get('name') for p in (r.json() or {}).get('data') or [] if isinstance(p, dict)}
            down = self.session.get(self._url('downloadsV2/queryPackages'), params={'queryParams': json.dumps({'uuid': True, 'name': True})}, timeout=self.timeout)
            gone = {p.get('name') for p in (down.json() or {}).get('data') or [] if isinstance(p, dict) and p.get('uuid') in packages}
            names = {n for n in names if n} | gone
            stale = [u for u, n in pkg_names.items() if n in names]
            if stale:
                self.session.get(self._url('linkgrabberv2/removeLinks'), params={'linkIds': '[]', 'packageIds': json.dumps(stale)}, timeout=self.timeout)
        except Exception as err:
            logger.warn('[JD2] Unable to remove job %s from JD2: %s', job_id, err)
