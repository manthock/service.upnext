# -*- coding: utf-8 -*-

import json
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
    """Normalize a Skip Intro window to seconds."""
    try:
        end_seconds = float(end)
    except (TypeError, ValueError):
        return None

    try:
        start_seconds = (
            float(start)
            if start is not None
            else 1.0
        )
    except (TypeError, ValueError):
        start_seconds = 1.0

    start_seconds = max(1.0, start_seconds)

    try:
        total_time = float(total_time)
    except (TypeError, ValueError):
        total_time = 0

    if total_time > 0:
        if start_seconds >= total_time:
            return None
        end_seconds = min(total_time, end_seconds)

    if end_seconds <= start_seconds:
        return None

    return start_seconds, end_seconds



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
    season = media_context.get('season')
    episode = media_context.get('episode')

    if season is None or episode is None:
        return None

    query = {
        'season': season,
        'episode': episode,
    }

    tmdb_id = media_context.get('tmdb_id')
    imdb_id = media_context.get('imdb_id')

    if tmdb_id is not None:
        query['tmdb_id'] = tmdb_id
    elif imdb_id:
        query['imdb_id'] = imdb_id
    else:
        return None

    url = '{0}?{1}'.format(
        THEINTRODB_URL,
        urllib.parse.urlencode(query),
    )

    data = _request_json(url)

    if not isinstance(data, dict):
        return None

    for segment_name in ('recap', 'intro'):
        entries = data.get(segment_name) or []

        valid_entries = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            try:
                end_ms = float(entry.get('end_ms'))
            except (TypeError, ValueError):
                continue

            start_ms = entry.get('start_ms')

            try:
                start_ms = (
                    float(start_ms)
                    if start_ms is not None
                    else None
                )
            except (TypeError, ValueError):
                start_ms = None

            if (
                start_ms is not None
                and end_ms <= start_ms
            ):
                continue

            valid_entries.append(
                (end_ms, start_ms)
            )

        if not valid_entries:
            continue

        end_ms, start_ms = sorted(
            valid_entries,
            key=lambda value: value[0],
        )[0]

        window = _normalize_window(
            None if start_ms is None else start_ms / 1000.0,
            end_ms / 1000.0,
            total_time,
        )

        if window:
            return window

    return None

def _fetch_introdb(media_context, total_time):
    """Resolve intro/recap end from IntroDB.app."""
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
        '{0}?{1}'.format(
            INTRODB_URL,
            query,
        )
    )

    if not isinstance(data, dict):
        return None

    for segment_name in ('recap', 'intro'):
        segment = data.get(segment_name)

        if not isinstance(segment, dict):
            continue

        start_ms = segment.get('start_ms')
        end_ms = segment.get('end_ms')

        if end_ms is not None:
            window = _normalize_window(
                None if start_ms is None
                else float(start_ms) / 1000.0,
                float(end_ms) / 1000.0,
                total_time,
            )
        else:
            window = _normalize_window(
                segment.get('start_sec'),
                segment.get('end_sec'),
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
