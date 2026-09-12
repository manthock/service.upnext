# -*- coding: utf-8 -*-
# GNU General Public License v2.0
# See COPYING or https://www.gnu.org/licenses/gpl-2.0.txt

"""IntroDB integration for service.upnext."""

from __future__ import absolute_import, division, unicode_literals

import json
import re

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen

try:
    from urllib.error import HTTPError, URLError
except ImportError:
    from urllib2 import HTTPError, URLError

try:
    import xbmc
except ImportError:
    xbmc = None

import utils


INTRODB_SEGMENTS_URL = 'https://api.introdb.app/segments'
INTRODB_TIMEOUT = 5

_CACHE = {}
_EPISODE_CACHE = {}
_SHOW_CACHE = {}


def _log(message, level=utils.LOGDEBUG):
    utils.log(message, name='IntroDB', level=level)


def _normalize_numeric_id(value):
    if value in (None, ''):
        return None

    match = re.search(r'(\d+)', str(value))

    if not match:
        return None

    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _normalize_imdb_id(value):
    if value in (None, ''):
        return None

    match = re.search(r'(tt\d{7,8})', str(value))

    if not match:
        return None

    return match.group(1)


def _parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_info_label(label):
    if xbmc is None:
        return ''

    try:
        return xbmc.getInfoLabel(label)
    except Exception:
        return ''


def _get_first_info_label(labels):
    for label in labels:
        value = _get_info_label(label)

        if value:
            return value

    return ''


def _get_active_player_id():
    result = utils.jsonrpc(
        method='Player.GetActivePlayers'
    )

    players = result.get('result', []) if result else []

    for player in players:
        if player.get('type') == 'video':
            return player.get('playerid')

    return None


def _get_current_playback_item():
    """Get the current Kodi playback item."""

    player_id = _get_active_player_id()

    if player_id is None:
        return None

    result = utils.jsonrpc(
        method='Player.GetItem',
        params={
            'playerid': player_id,
            'properties': [
                'episode',
                'imdbnumber',
                'season',
                'showtitle',
                'title',
                'tvshowid',
                'uniqueid',
                'file',
                'playcount',
            ],
        },
    )

    return (
        result.get('result', {}).get('item', {})
        if result
        else {}
    )


def _get_library_episode_identifiers(current_episode):
    if not current_episode:
        return {}

    episode_id = (
        current_episode.get('id') or
        current_episode.get('episodeid')
    )

    if not episode_id:
        episode_id = _normalize_numeric_id(
            _get_info_label('VideoPlayer.DBID')
        )

    if not episode_id:
        return {}

    episode_id = _normalize_numeric_id(episode_id)

    if episode_id is None:
        return {}

    cache_key = (
        'episode_identifiers',
        episode_id,
    )

    if cache_key in _EPISODE_CACHE:
        return _EPISODE_CACHE[cache_key]

    result = utils.jsonrpc(
        method='VideoLibrary.GetEpisodeDetails',
        params={
            'episodeid': episode_id,
            'properties': [
                'imdbnumber',
                'uniqueid',
                'tvshowid',
            ],
        },
    )

    details = (
        result.get('result', {}).get(
            'episodedetails',
            {}
        )
        if result
        else {}
    )

    details = details or {}

    identifiers = {
        'imdbnumber': details.get('imdbnumber'),
        'uniqueid': details.get('uniqueid') or {},
        'tvshowid': details.get('tvshowid'),
    }

    _EPISODE_CACHE[cache_key] = identifiers

    return identifiers


def _get_library_show_identifiers(current_episode):
    if not current_episode:
        return {}

    tvshow_id = current_episode.get('tvshowid')

    if tvshow_id in (None, -1, '-1'):
        episode_identifiers = _get_library_episode_identifiers(
            current_episode
        )

        tvshow_id = episode_identifiers.get('tvshowid')

    if tvshow_id in (None, -1, '-1'):
        tvshow_id = _normalize_numeric_id(
            _get_info_label('VideoPlayer.TvShowDBID')
        )

    if tvshow_id is None:
        return {}

    tvshow_id = _normalize_numeric_id(tvshow_id)

    if tvshow_id is None:
        return {}

    cache_key = (
        'tvshow_identifiers',
        tvshow_id,
    )

    if cache_key in _SHOW_CACHE:
        return _SHOW_CACHE[cache_key]

    result = utils.jsonrpc(
        method='VideoLibrary.GetTVShowDetails',
        params={
            'tvshowid': tvshow_id,
            'properties': [
                'imdbnumber',
                'uniqueid',
            ],
        },
    )

    details = (
        result.get('result', {}).get(
            'tvshowdetails',
            {}
        )
        if result
        else {}
    )

    details = details or {}

    identifiers = {
        'imdbnumber': details.get('imdbnumber'),
        'uniqueid': details.get('uniqueid') or {},
    }

    _SHOW_CACHE[cache_key] = identifiers

    return identifiers


def _get_playback_show_imdb_id(current_item, current_episode):
    """Resolve the IMDb ID of the TV show."""

    show_identifiers = _get_library_show_identifiers(
        current_episode
    )

    imdb_id = _normalize_imdb_id(
        show_identifiers.get('imdbnumber')
    )

    if imdb_id:
        return imdb_id

    unique_ids = show_identifiers.get('uniqueid') or {}

    if isinstance(unique_ids, dict):
        imdb_id = _normalize_imdb_id(
            unique_ids.get('imdb')
        )

        if imdb_id:
            return imdb_id

    return _normalize_imdb_id(
        _get_first_info_label([
            'VideoPlayer.TVshowIMDBNumber',
            'Container.ListItem.TVShowIMDBNumber',
            'ListItem.TVShowIMDBNumber',
        ])
    )


def _get_playback_imdb_id(current_item, current_episode):
    """Fallback IMDb resolution."""

    item = current_item or {}

    imdb_id = _normalize_imdb_id(
        item.get('imdbnumber')
    )

    if imdb_id:
        return imdb_id

    unique_ids = item.get('uniqueid') or {}

    if isinstance(unique_ids, dict):
        imdb_id = _normalize_imdb_id(
            unique_ids.get('imdb')
        )

        if imdb_id:
            return imdb_id

    show_identifiers = _get_library_show_identifiers(
        current_episode
    )

    imdb_id = _normalize_imdb_id(
        show_identifiers.get('imdbnumber')
    )

    if imdb_id:
        return imdb_id

    unique_ids = show_identifiers.get('uniqueid') or {}

    if isinstance(unique_ids, dict):
        imdb_id = _normalize_imdb_id(
            unique_ids.get('imdb')
        )

        if imdb_id:
            return imdb_id

    episode_identifiers = _get_library_episode_identifiers(
        current_episode
    )

    imdb_id = _normalize_imdb_id(
        episode_identifiers.get('imdbnumber')
    )

    if imdb_id:
        return imdb_id

    unique_ids = episode_identifiers.get('uniqueid') or {}

    if isinstance(unique_ids, dict):
        imdb_id = _normalize_imdb_id(
            unique_ids.get('imdb')
        )

        if imdb_id:
            return imdb_id

    return _normalize_imdb_id(
        _get_first_info_label([
            'VideoPlayer.IMDBNumber',
            'ListItem.IMDBNumber',
            'ListItem.UniqueID(imdb)',
            'VideoPlayer.UniqueID(imdb)',
        ])
    )


def _get_outro_start(payload):
    """Extract outro start from IntroDB response."""

    if not isinstance(payload, dict):
        return None

    outro = payload.get('outro')

    if not isinstance(outro, dict):
        return None

    start_ms = outro.get('start_ms')

    if start_ms is not None:
        try:
            return float(start_ms) / 1000.0
        except (TypeError, ValueError):
            pass

    start_sec = outro.get('start_sec')

    if start_sec is not None:
        try:
            return float(start_sec)
        except (TypeError, ValueError):
            pass

    return None


def _request(imdb_id, season, episode):
    """Request segment data from IntroDB."""

    query = urlencode({
        'imdb_id': imdb_id,
        'season': season,
        'episode': episode,
    })

    request = Request(
        '{}?{}'.format(
            INTRODB_SEGMENTS_URL,
            query
        ),
        headers={
            'Accept': 'application/json',
            'User-Agent': 'Kodi-service.upnext',
        },
    )

    _log(
        'IntroDB lookup: {} S{:02d}E{:02d}'.format(
            imdb_id,
            season,
            episode,
        ),
        utils.LOGINFO
    )

    try:
        response = urlopen(
            request,
            timeout=INTRODB_TIMEOUT
        )

        try:
            data = response.read()
        finally:
            response.close()

    except HTTPError as exc:
        _log(
            'IntroDB HTTP error {}: {}'.format(
                exc.code,
                exc,
            ),
            utils.LOGWARNING
        )
        return None

    except (URLError, IOError, OSError) as exc:
        _log(
            'IntroDB request failed: {}'.format(exc),
            utils.LOGWARNING
        )
        return None

    try:
        if not isinstance(data, str):
            data = data.decode('utf-8')

        payload = json.loads(data)

    except (TypeError, ValueError, UnicodeError) as exc:
        _log(
            'Invalid IntroDB response: {}'.format(exc),
            utils.LOGWARNING
        )
        return None

    outro_time = _get_outro_start(payload)

    if outro_time is None:
        _log(
            'IntroDB: no outro found for {} S{:02d}E{:02d}'.format(
                imdb_id,
                season,
                episode,
            ),
            utils.LOGDEBUG
        )
        return None

    _log(
        'IntroDB: outro at {:.2f}s for {} S{:02d}E{:02d}'.format(
            outro_time,
            imdb_id,
            season,
            episode,
        ),
        utils.LOGINFO
    )

    return outro_time


def get_outro_start(item, total_time, media_context=None):
    """
    Resolve IntroDB outro for the current episode.

    AniBridge-mapped TVDB season/episode are authoritative when available.
    Otherwise UpNext/Player.GetItem season and episode are used.
    """

    if not isinstance(item, dict):
        return None

    if item.get('type') != 'episode':
        return None

    details = item.get('details') or {}

    if not isinstance(details, dict):
        return None

    season = _parse_int(details.get('season'))
    episode = _parse_int(details.get('episode'))
	
    mapped = bool(
        media_context
        and media_context.get('tvdb_season') is not None
        and media_context.get('tvdb_episode') is not None
    )
	
    if mapped:
        season = _parse_int(
            media_context.get('tvdb_season')
        )
        episode = _parse_int(
            media_context.get('tvdb_episode')
        )

    current_item = _get_current_playback_item()

    # Player.GetItem is only a fallback when AniBridge
    # did not provide a mapped episode.
    if current_item and not mapped:
        playback_season = _parse_int(
            current_item.get('season')
        )
        playback_episode = _parse_int(
            current_item.get('episode')
        )

    if playback_season is not None and playback_season >= 0:
        season = playback_season

    if playback_episode is not None and playback_episode >= 0:
        episode = playback_episode

    if season is None or season < 0:
        _log(
            'IntroDB: invalid season: {}'.format(season),
            utils.LOGWARNING
        )
        return None

    if episode is None or episode < 0:
        _log(
            'IntroDB: invalid episode: {}'.format(episode),
            utils.LOGWARNING
        )
        return None

    current_episode = current_item or {}

    if not current_episode.get('tvshowid'):
        current_episode = details.copy()

        if current_item:
            current_episode.update({
                key: value
                for key, value in current_item.items()
                if value not in (None, '', -1, '-1')
            })

    show_imdb_id = None
	
    if media_context:
        show_imdb_id = _normalize_imdb_id(
            media_context.get('show_imdb_id')
        )

    if not show_imdb_id:
        show_imdb_id = _get_playback_show_imdb_id(
            current_item,
            current_episode,
        )
		
    if not show_imdb_id:
        show_imdb_id = _get_playback_imdb_id(
            current_item,
            current_episode,
		)
		
    if not show_imdb_id:
        _log(
            'IntroDB: show IMDb unavailable for S{:02d}E{:02d}'.format(
                season,
                episode,
            ),
            utils.LOGWARNING
        )
        return None

    cache_key = (
        show_imdb_id,
        season,
        episode,
    )

    if cache_key in _CACHE:
        return _CACHE[cache_key]

    result = _request(
        show_imdb_id,
        season,
        episode,
    )

    if result is not None:
        if total_time <= 0:
            result = None
        elif result <= 0:
            result = None
        elif result >= total_time:
            _log(
                'IntroDB: outro {:.2f}s outside video duration {:.2f}s'.format(
                    result,
                    total_time,
                ),
                utils.LOGWARNING
            )
            result = None

    _CACHE[cache_key] = result

    return result


def clear_cache():
    """Clear IntroDB caches."""

    _CACHE.clear()
    _EPISODE_CACHE.clear()
    _SHOW_CACHE.clear()