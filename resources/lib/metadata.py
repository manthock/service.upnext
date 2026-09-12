# -*- coding: utf-8 -*-
# GNU General Public License v2.0

from __future__ import absolute_import, division, unicode_literals

import re

import xbmc

import utils
from anibridge import AniBridge


class MediaMetadata(object):
    """Resolve identifiers for the currently playing Kodi item."""

    def __init__(self, cache=None):
        self.cache = cache if cache is not None else {}

        self.anibridge = AniBridge(
            logger=self._log,
            cache=self.cache,
        )

    @staticmethod
    def _log(message):
        utils.log(
            message,
            name="MediaMetadata",
            level=utils.LOGDEBUG,
        )

    @staticmethod
    def normalize_numeric_id(value):
        if value in (None, ""):
            return None

        match = re.search(
            r"(\d+)",
            str(value),
        )

        if not match:
            return None

        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def normalize_imdb_id(value):
        if value in (None, ""):
            return None

        match = re.search(
            r"(tt\d{7,8})",
            str(value),
        )

        if not match:
            return None

        return match.group(1)

    @staticmethod
    def parse_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first_label(labels):
        for label in labels:
            value = xbmc.getInfoLabel(label)

            if value:
                return value

        return ""

    def _get_active_player_id(self):
        result = utils.jsonrpc(
            "Player.GetActivePlayers"
        )

        players = result.get("result", [])

        for player in players:
            if player.get("type") == "video":
                return player.get("playerid")

        return None

    def _get_episode_details(self, episode_id):
        if episode_id is None:
            return {}

        cache_key = (
            "metadata_episode",
            int(episode_id),
        )

        if cache_key in self.cache:
            return self.cache[cache_key]

        result = utils.jsonrpc(
            "VideoLibrary.GetEpisodeDetails",
            {
                "episodeid": int(episode_id),
                "properties": [
                    "imdbnumber",
                    "uniqueid",
                    "tvshowid",
                ],
            },
            log_errors=False,
        )

        details = (
            result
            .get("result", {})
            .get("episodedetails", {})
            or {}
        )

        self.cache[cache_key] = details

        return details

    def _get_show_details(self, tvshow_id):
        if tvshow_id is None:
            return {}

        cache_key = (
            "metadata_show",
            int(tvshow_id),
        )

        if cache_key in self.cache:
            return self.cache[cache_key]

        result = utils.jsonrpc(
            "VideoLibrary.GetTVShowDetails",
            {
                "tvshowid": int(tvshow_id),
                "properties": [
                    "imdbnumber",
                    "uniqueid",
                ],
            },
            log_errors=False,
        )

        details = (
            result
            .get("result", {})
            .get("tvshowdetails", {})
            or {}
        )

        self.cache[cache_key] = details

        return details

    def _get_item_unique_ids(self, item):
        return item.get("uniqueid", {}) or {}

    def get_tmdb_id(self, item):
        unique_ids = self._get_item_unique_ids(item)

        value = self.normalize_numeric_id(
            unique_ids.get("tmdb")
        )

        if value is not None:
            return value

        tvshow_id = self.normalize_numeric_id(
            item.get("tvshowid")
        )

        if tvshow_id is not None:
            details = self._get_show_details(
                tvshow_id
            )

            value = self.normalize_numeric_id(
                (details.get("uniqueid", {}) or {}).get(
                    "tmdb"
                )
            )

            if value is not None:
                return value

        episode_id = (
            item.get("id")
            or item.get("episodeid")
        )

        if episode_id is not None:
            details = self._get_episode_details(
                episode_id
            )

            value = self.normalize_numeric_id(
                (details.get("uniqueid", {}) or {}).get(
                    "tmdb"
                )
            )

            if value is not None:
                return value

        value = self.normalize_numeric_id(
            self._first_label(
                [
                    "ListItem.UniqueID(tmdb)",
                    "VideoPlayer.UniqueID(tmdb)",
                    "VideoPlayer.Property(tmdb_id)",
                    "VideoPlayer.Property(tmdb)",
                ]
            )
        )

        if value is not None:
            return value

        # Trakt property fallback.
        prop = utils.get_property(
            "script.trakt.ids"
        )

        if prop:
            try:
                trakt_ids, _ = utils.decode_data(
                    serialised_json=prop
                )

                if trakt_ids:
                    value = self.normalize_numeric_id(
                        trakt_ids.get("tmdb")
                    )

                    if value is not None:
                        return value

            except Exception:
                pass

        return None

    def get_tvdb_id(self, item):
        unique_ids = self._get_item_unique_ids(item)

        value = self.normalize_numeric_id(
            unique_ids.get("tvdb")
        )

        if value is not None:
            return value

        tvshow_id = self.normalize_numeric_id(
            item.get("tvshowid")
        )

        if tvshow_id is not None:
            details = self._get_show_details(
                tvshow_id
            )

            value = self.normalize_numeric_id(
                (details.get("uniqueid", {}) or {}).get(
                    "tvdb"
                )
            )

            if value is not None:
                return value

        episode_id = (
            item.get("id")
            or item.get("episodeid")
        )

        if episode_id is not None:
            details = self._get_episode_details(
                episode_id
            )

            value = self.normalize_numeric_id(
                (details.get("uniqueid", {}) or {}).get(
                    "tvdb"
                )
            )

            if value is not None:
                return value

        return self.normalize_numeric_id(
            self._first_label(
                [
                    "ListItem.UniqueID(tvdb)",
                    "VideoPlayer.UniqueID(tvdb)",
                    "VideoPlayer.Property(tvdb_id)",
                    "VideoPlayer.Property(tvdb)",
                ]
            )
        )

    def get_imdb_id(self, item):
        imdb_id = self.normalize_imdb_id(
            item.get("imdbnumber")
        )

        if imdb_id:
            return imdb_id

        unique_ids = self._get_item_unique_ids(item)

        imdb_id = self.normalize_imdb_id(
            unique_ids.get("imdb")
        )

        if imdb_id:
            return imdb_id

        tvshow_id = self.normalize_numeric_id(
            item.get("tvshowid")
        )

        if tvshow_id is not None:
            details = self._get_show_details(
                tvshow_id
            )

            imdb_id = self.normalize_imdb_id(
                details.get("imdbnumber")
            )

            if imdb_id:
                return imdb_id

            imdb_id = self.normalize_imdb_id(
                (details.get("uniqueid", {}) or {}).get(
                    "imdb"
                )
            )

            if imdb_id:
                return imdb_id

        episode_id = (
            item.get("id")
            or item.get("episodeid")
        )

        if episode_id is not None:
            details = self._get_episode_details(
                episode_id
            )

            imdb_id = self.normalize_imdb_id(
                details.get("imdbnumber")
            )

            if imdb_id:
                return imdb_id

            imdb_id = self.normalize_imdb_id(
                (details.get("uniqueid", {}) or {}).get(
                    "imdb"
                )
            )

            if imdb_id:
                return imdb_id

        return self.normalize_imdb_id(
            self._first_label(
                [
                    "VideoPlayer.IMDBNumber",
                    "ListItem.IMDBNumber",
                    "ListItem.UniqueID(imdb)",
                    "VideoPlayer.UniqueID(imdb)",
                ]
            )
        )

    def get_show_imdb_id(self, item):
        tvshow_id = self.normalize_numeric_id(
            item.get("tvshowid")
        )

        if tvshow_id is not None:
            details = self._get_show_details(
                tvshow_id
            )

            imdb_id = self.normalize_imdb_id(
                details.get("imdbnumber")
            )

            if imdb_id:
                return imdb_id

            imdb_id = self.normalize_imdb_id(
                (details.get("uniqueid", {}) or {}).get(
                    "imdb"
                )
            )

            if imdb_id:
                return imdb_id

        return self.normalize_imdb_id(
            self._first_label(
                [
                    "VideoPlayer.TVshowIMDBNumber",
                    "Container.ListItem.TVShowIMDBNumber",
                    "ListItem.TVShowIMDBNumber",
                ]
            )
        )

    def resolve(self, item):
        """
        Resolve the current item's metadata.

        Returns a stable context consumed by IntroDB,
        TheIntroDB, Skip Intro and future providers.
        """
        if not item:
            return None

        season = self.parse_int(
            item.get("season")
        )

        episode = self.parse_int(
            item.get("episode")
        )

        context = {
            "type": item.get("type"),

            "title": (
                item.get("showtitle")
                or item.get("title")
                or item.get("label")
                or ""
            ),

            "season": season,
            "episode": episode,

            "tmdb_id": self.get_tmdb_id(item),
            "tvdb_id": self.get_tvdb_id(item),

            "imdb_id": self.get_imdb_id(item),
            "show_imdb_id": self.get_show_imdb_id(item),

            "tvdb_season": None,
            "tvdb_episode": None,
            "anilist_id": None,
        }

        # AniBridge is relevant only when we have
        # the identifiers needed for an anime mapping.
        if (
            season is not None
            and episode is not None
            and context["tmdb_id"] is not None
            and context["tvdb_id"] is not None
        ):
            mapping = self.anibridge.resolve_tmdb_to_tvdb_episode(
                context["tmdb_id"],
                context["tvdb_id"],
                episode,
            )

            if mapping:
                context["tvdb_season"] = mapping.get(
                    "season"
                )
                context["tvdb_episode"] = mapping.get(
                    "episode"
                )
                context["anilist_id"] = mapping.get(
                    "anilist_id"
                )

        self._log_context(context)

        return context

    def _log_context(self, context):
        self._log(
            "Media context -> "
            "TMDB=%s S%sE%s / "
            "TVDB=%s S%sE%s / "
            "IMDb=%s / AniList=%s"
            % (
                context.get("tmdb_id") or "?",
                context.get("season") or "?",
                context.get("episode") or "?",
                context.get("tvdb_id") or "?",
                context.get("tvdb_season") or "?",
                context.get("tvdb_episode") or "?",
                context.get("show_imdb_id")
                or context.get("imdb_id")
                or "?",
                context.get("anilist_id") or "?",
            )
        )