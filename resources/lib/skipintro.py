# -*- coding: utf-8 -*-

import json
import urllib.parse
import urllib.request

import utils
import xbmc


THEINTRODB_URL = 'https://api.theintrodb.org/v2/media'
INTRODB_URL = 'https://api.introdb.app/segments'

REQUEST_TIMEOUT = 5

CHAPTER_MAX_PERCENT = 50
CHAPTER_MIN_TARGET = 20.0
CHAPTER_MIN_GAP = 20.0

FALLBACK_START = 15.0
FALLBACK_END = 90.0

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

def _get_chapter_starts(total_time):
    """Return chapter start times in seconds."""
    starts = []

    # Kodi JSON-RPC is the preferred source.
    try:
        result = xbmc.executeJSONRPC(
            json.dumps({
                'jsonrpc': '2.0',
                'method': 'Player.GetActivePlayers',
                'params': {},
                'id': 1,
            })
        )
        players = json.loads(result).get('result', [])
        player_id = None

        for player in players:
            if player.get('type') == 'video':
                player_id = player.get('playerid')
                break

        if player_id is not None:
            result = xbmc.executeJSONRPC(
                json.dumps({
                    'jsonrpc': '2.0',
                    'method': 'Player.GetProperties',
                    'params': {
                        'playerid': player_id,
                        'properties': ['chapters'],
                    },
                    'id': 1,
                })
            )

            chapters = (
                json.loads(result)
                .get('result', {})
                .get('chapters', [])
            )

            for chapter in chapters:
                value = chapter.get('time')

                if isinstance(value, dict):
                    hours = int(value.get('hours', 0))
                    minutes = int(value.get('minutes', 0))
                    seconds = int(value.get('seconds', 0))
                    milliseconds = int(
                        value.get('milliseconds', 0)
                    )

                    start = (
                        hours * 3600
                        + minutes * 60
                        + seconds
                        + milliseconds / 1000.0
                    )
                elif isinstance(value, (int, float)):
                    start = float(value)
                else:
                    start = None

                if start is not None:
                    starts.append(start)

    except Exception:
        pass

    if starts:
        return sorted(set(starts))

    # Fallback for Kodi builds exposing chapter information
    # through Player.Chapters.
    try:
        raw = xbmc.getInfoLabel('Player.Chapters')

        if raw:
            percentages = []

            for token in raw.split(','):
                token = token.strip()

                if not token:
                    continue

                try:
                    percentages.append(float(token))
                except ValueError:
                    return []

            for percentage in percentages:
                if 0 <= percentage < 100:
                    starts.append(
                        total_time * percentage / 100.0
                    )

    except Exception:
        pass

    return sorted(set(starts))
	
def _chapter_window(total_time):
    """Resolve a Skip Intro window from chapter markers."""
    try:
        total_time = float(total_time)
    except (TypeError, ValueError):
        return None

    if total_time <= 0:
        return None

    starts = _get_chapter_starts(total_time)

    if not starts:
        return None

    early_cutoff = total_time * (
        CHAPTER_MAX_PERCENT / 100.0
    )

    candidates = []
    previous_start = 0.0

    for start_time in starts:
        if start_time <= 0:
            previous_start = max(
                previous_start,
                start_time,
            )
            continue

        if start_time < CHAPTER_MIN_TARGET:
            previous_start = start_time
            continue

        if (
            start_time <= early_cutoff
            and start_time - previous_start >= CHAPTER_MIN_GAP
        ):
            candidates.append(start_time)

        previous_start = start_time

    if len(candidates) >= 2:
        return (
            candidates[0],
            candidates[1],
        )

    if len(candidates) == 1:
        return (
            1.0,
            candidates[0],
        )

    return None

def _manual_window(total_time):
    """Return the configured/manual Skip Intro window."""
    try:
        total_time = float(total_time)
    except (TypeError, ValueError):
        return None

    if total_time <= 0:
        return None

    start = max(
        1.0,
        min(
            FALLBACK_START,
            max(1.0, total_time - 1.0),
        ),
    )

    end = max(
        start + 1.0,
        min(FALLBACK_END, total_time),
    )

    if end <= start:
        return None

    return start, end

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

    # Fall back to chapter markers.
    result = _chapter_window(total_time)

    if result:
        _CACHE[key] = result
        return result

    # Finally use the manual fallback.
    result = _manual_window(total_time)

    _CACHE[key] = result
    return result