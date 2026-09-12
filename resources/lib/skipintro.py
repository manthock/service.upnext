# -*- coding: utf-8 -*-

import json
import time
import urllib.parse
import urllib.request

import utils


THEINTRODB_URL = 'https://api.theintrodb.org/v2/media'
INTRODB_URL = 'https://api.introdb.app/segments'

REQUEST_TIMEOUT = 5

_CACHE = {}


def _parse_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_window(start, end, total_time):
    """Normalize a skip-intro window to seconds."""
    start = _parse_number(start)
    end = _parse_number(end)
    total_time = _parse_number(total_time)

    if start is None or end is None:
        return None

    # Reject obviously invalid windows.
    if start < 0 or end <= start:
        return None

    if total_time is not None and total_time > 0:
        if start >= total_time:
            return None
        end = min(end, total_time)

    if end <= start:
        return None

    return start, end


def _request_json(url):
    try:
        request = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Kodi-UpNext',
                'Accept': 'application/json',
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            data = response.read().decode('utf-8')

        return json.loads(data)

    except Exception as exc:
        utils.log(
            'SkipIntro request failed: {0}'.format(exc),
            name='SkipIntro',
            level=utils.LOGDEBUG,
        )

    return None


def _fetch_theintrodb(media_context, total_time):
    """Resolve intro/recap end from TheIntroDB."""
    tmdb_id = media_context.get('tmdb_id')
    season = media_context.get('season')
    episode = media_context.get('episode')

    if tmdb_id is None or season is None or episode is None:
        return None

    query = urllib.parse.urlencode({
        'tmdb_id': tmdb_id,
        'season': season,
        'episode': episode,
    })

    data = _request_json(
        '{0}?{1}'.format(THEINTRODB_URL, query)
    )

    if not data:
        return None

    # TheIntroDB may return the segment list directly or
    # wrap it in a media/segments object.
    segments = data

    if isinstance(data, dict):
        segments = (
            data.get('segments')
            or data.get('media')
            or data.get('data')
        )

    if not isinstance(segments, list):
        return None

    for segment in segments:
        if not isinstance(segment, dict):
            continue

        segment_type = str(
            segment.get('type')
            or segment.get('name')
            or ''
        ).lower()

        if segment_type not in (
            'intro',
            'recap',
            'opening',
        ):
            continue

        start = (
            segment.get('start')
            or segment.get('start_sec')
            or segment.get('start_seconds')
        )

        end = (
            segment.get('end')
            or segment.get('end_sec')
            or segment.get('end_seconds')
        )

        window = _normalize_window(
            start,
            end,
            total_time,
        )

        if window:
            return window

    return None


def _fetch_introdb(media_context, total_time):
    """Resolve intro end from IntroDB.app."""
    imdb_id = media_context.get('show_imdb_id')

    if not imdb_id:
        return None

    season = media_context.get('season')
    episode = media_context.get('episode')

    mapped_season = media_context.get('tvdb_season')
    mapped_episode = media_context.get('tvdb_episode')

    if mapped_season is not None:
        season = mapped_season

    if mapped_episode is not None:
        episode = mapped_episode

    if season is None or episode is None:
        return None

    query = urllib.parse.urlencode({
        'imdb_id': imdb_id,
        'season': season,
        'episode': episode,
    })

    data = _request_json(
        '{0}?{1}'.format(INTRODB_URL, query)
    )

    if not data:
        return None

    segments = data

    if isinstance(data, dict):
        segments = (
            data.get('segments')
            or data.get('data')
        )

    if not isinstance(segments, list):
        return None

    for segment in segments:
        if not isinstance(segment, dict):
            continue

        segment_type = str(
            segment.get('type')
            or segment.get('name')
            or ''
        ).lower()

        if segment_type not in (
            'intro',
            'recap',
            'opening',
        ):
            continue

        start = (
            segment.get('start')
            or segment.get('start_sec')
            or segment.get('start_seconds')
        )

        end = (
            segment.get('end')
            or segment.get('end_sec')
            or segment.get('end_seconds')
        )

        window = _normalize_window(
            start,
            end,
            total_time,
        )

        if window:
            return window

    return None


def resolve(media_context, total_time):
    """Resolve a Skip Intro window.

    Returns:
        (start_seconds, end_seconds)
        or None when no usable window is available.
    """
    if not isinstance(media_context, dict):
        return None

    key = (
        media_context.get('show_imdb_id'),
        media_context.get('tmdb_id'),
        media_context.get('season'),
        media_context.get('episode'),
        media_context.get('tvdb_season'),
        media_context.get('tvdb_episode'),
    )

    if key in _CACHE:
        return _CACHE[key]

    # Try TheIntroDB first.
    result = _fetch_theintrodb(
        media_context,
        total_time,
    )

    if result:
        _CACHE[key] = result
        return result

    # Then try IntroDB.app.
    result = _fetch_introdb(
        media_context,
        total_time,
    )

    if result:
        _CACHE[key] = result
        return result

    _CACHE[key] = None
    return None
