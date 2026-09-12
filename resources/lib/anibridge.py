# -*- coding: utf-8 -*-
# GNU General Public License v2.0

from __future__ import absolute_import, division, unicode_literals

import json
from contextlib import closing
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ANIBRIDGE_MAPPINGS_URL = (
    "https://mappings.anibridge.eliasbenb.dev/api/v3/mappings"
)

REMOTE_LOOKUP_TIMEOUT = 5


class AniBridge(object):
    """Resolve anime episode mappings through AniBridge."""

    def __init__(self, logger=None, cache=None):
        self.logger = logger
        self.cache = cache if cache is not None else {}

    def log(self, message):
        if self.logger:
            self.logger(message)

    @staticmethod
    def parse_range(value):
        """
        Parse an AniBridge episode range.

        Examples:

            1
            1-12
            14-
            1-6,8-13
            14-|2

        Returns:
            ([(start, end), ...], ratio)
        """
        if not isinstance(value, str):
            return [], 1

        value = value.strip()

        if not value:
            return [], 1

        ratio = 1

        if "|" in value:
            value, ratio_text = value.rsplit("|", 1)

            try:
                ratio = int(ratio_text)
            except (TypeError, ValueError):
                ratio = 1

        ranges = []

        for part in value.split(","):
            part = part.strip()

            if not part:
                continue

            if "-" in part:
                start_text, end_text = part.split("-", 1)
            else:
                start_text = part
                end_text = part

            try:
                start = int(start_text)
            except (TypeError, ValueError):
                continue

            if end_text == "":
                end = None
            else:
                try:
                    end = int(end_text)
                except (TypeError, ValueError):
                    continue

            ranges.append((start, end))

        return ranges, ratio

    @classmethod
    def episode_offset(cls, episode, range_text):
        """
        Return the zero-based offset of an episode inside a source range.
        """
        ranges, _ = cls.parse_range(range_text)

        if not ranges:
            return None

        for start, end in ranges:
            if episode < start:
                continue

            if end is not None and episode > end:
                continue

            return episode - start

        return None

    @classmethod
    def target_episode(cls, target_range, source_offset):
        """
        Resolve a source episode offset against an AniBridge target range.

        Positive ratio:
            source E1 -> target E1, E2, E3...

        Negative ratio:
            every N source episodes -> one target episode.
        """
        ranges, ratio = cls.parse_range(target_range)

        if not ranges:
            return None

        target_episodes = []

        for start, end in ranges:
            if end is None:
                end = start + source_offset + abs(ratio or 1) + 2

            if end < start:
                continue

            target_episodes.extend(range(start, end + 1))

        if not target_episodes:
            return None

        if ratio == 0:
            ratio = 1

        if ratio > 0:
            target_index = source_offset * ratio

            if target_index >= len(target_episodes):
                return None

            return target_episodes[target_index]

        target_index = source_offset // abs(ratio)

        if target_index >= len(target_episodes):
            return None

        return target_episodes[target_index]

    @classmethod
    def resolve_episode_range(
        cls,
        source_episode,
        source_range,
        target_range,
    ):
        offset = cls.episode_offset(
            source_episode,
            source_range,
        )

        if offset is None:
            return None

        return cls.target_episode(
            target_range,
            offset,
        )

    def _fetch_json(self, url):
        request = Request(
            url,
            headers={
                "User-Agent": "service.upnext/AniBridge",
                "Accept": "application/json",
            },
        )

        try:
            with closing(
                urlopen(
                    request,
                    timeout=REMOTE_LOOKUP_TIMEOUT,
                )
            ) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            self.log(
                "AniBridge HTTP error %s for %s"
                % (exc.code, url)
            )
            return None
        except URLError as exc:
            self.log(
                "AniBridge network error: %s"
                % exc
            )
            return None
        except Exception as exc:
            self.log(
                "AniBridge request failed: %s"
                % exc
            )
            return None

        try:
            return json.loads(body)
        except (TypeError, ValueError) as exc:
            self.log(
                "AniBridge returned invalid JSON: %s"
                % exc
            )
            return None

    def fetch_mappings(
        self,
        provider,
        media_id,
        scope=None,
    ):
        """
        Fetch AniBridge v3 mappings.

        Example:

            provider="tmdb_show"
            media_id=46298
            scope="s2"
        """
        if media_id is None:
            return None

        params = {
            "provider": provider,
            "id": str(media_id),
            "limit": "1000",
        }

        if scope:
            params["scope"] = scope

        url = "%s?%s" % (
            ANIBRIDGE_MAPPINGS_URL,
            urlencode(params),
        )

        cache_key = (
            "anibridge",
            provider,
            int(media_id),
            scope or "",
        )

        if cache_key in self.cache:
            return self.cache[cache_key]

        payload = self._fetch_json(url)

        if not isinstance(payload, dict):
            self.cache[cache_key] = None
            return None

        data = payload.get("data")

        if not isinstance(data, dict):
            self.cache[cache_key] = None
            return None

        self.cache[cache_key] = data

        return data

    def resolve_tmdb_to_tvdb_episode(
        self,
        tmdb_id,
        tvdb_id,
        tmdb_season,
        tmdb_episode,
    ):
        """
        Resolve:

            TMDB show + season + episode
                ->
            AniList ID + episode
                ->
            TVDB show + season + episode

        TMDB/TVDB use season-scoped descriptors.
        AniList does not use seasons.

        Returns:
            {
                "tvdb_id": 123,
                "season": 1,
                "episode": 12,
                "anilist_id": 456
            }

        or None.
        """

        if (
            tmdb_id is None
            or tvdb_id is None
            or tmdb_season is None
            or tmdb_episode is None
        ):
           return None

        try:
            tmdb_id = int(tmdb_id)
            tvdb_id = int(tvdb_id)
            tmdb_season = int(tmdb_season)
            tmdb_episode = int(tmdb_episode)
        except (TypeError, ValueError):
            return None

        # ---------------------------------------------------------
        # 1. TMDB season -> AniList ID + AniList episode
        # ---------------------------------------------------------

        tmdb_data = self.fetch_mappings(
            "tmdb_show",
            tmdb_id,
            "s%d" % tmdb_season,
        )

        if not tmdb_data:
            self.log(
                "AniBridge: no TMDB mapping for %s S%02d"
                % (
                    tmdb_id,
                    tmdb_season,
                )
            )
            return None

        tmdb_source = "tmdb_show:%d:s%d" % (
            tmdb_id,
            tmdb_season,
        )

        tmdb_targets = tmdb_data.get(
            tmdb_source
        )

        if not isinstance(tmdb_targets, dict):
            self.log(
                "AniBridge: no source descriptor %s"
                % tmdb_source
            )
            return None

        # There can theoretically be more than one AniList
        # target. Resolve the episode against the TMDB->AniList
        # episode ranges before continuing.
        anilist_candidates = []

        for target_descriptor, edges in tmdb_targets.items():

            if not target_descriptor.startswith(
                "anilist:"
            ):
                continue

            try:
                anilist_id = int(
                    target_descriptor.split(
                        ":",
                        1,
                    )[1]
                )
            except (TypeError, ValueError):
                continue

            if not isinstance(edges, dict):
                continue

            for source_range, target_range in edges.items():

                anilist_episode = self.resolve_episode_range(
                    tmdb_episode,
                    source_range,
                    target_range,
                )

                if anilist_episode is None:
                    continue

                anilist_candidates.append(
                    (
                        anilist_id,
                        anilist_episode,
                    )
                )

        if not anilist_candidates:
            self.log(
                "AniBridge: no AniList episode mapping for "
                "TMDB %s S%02dE%02d"
                % (
                    tmdb_id,
                    tmdb_season,
                    tmdb_episode,
                )
            )
            return None

        # ---------------------------------------------------------
        # 2. AniList episode -> TVDB season + episode
        # ---------------------------------------------------------

        for anilist_id, anilist_episode in anilist_candidates:

            anilist_data = self.fetch_mappings(
                "anilist",
                anilist_id,
            )

            if not anilist_data:
                continue

            anilist_source = "anilist:%d" % anilist_id

            anilist_targets = anilist_data.get(
                anilist_source
            )

            if not isinstance(anilist_targets, dict):
                continue

            for target_descriptor, edges in (
                anilist_targets.items()
            ):

                if not target_descriptor.startswith(
                    "tvdb_show:"
                ):
                    continue

                target_parts = target_descriptor.split(
                    ":"
                )

                if len(target_parts) != 3:
                    continue

                try:
                    mapped_tvdb_id = int(
                        target_parts[1]
                    )
                except (TypeError, ValueError):
                    continue

                if mapped_tvdb_id != tvdb_id:
                    continue

                tvdb_scope = target_parts[2]

                if not tvdb_scope.startswith("s"):
                    continue

                try:
                    tvdb_season = int(
                        tvdb_scope[1:]
                    )
                except (TypeError, ValueError):
                    continue

                if not isinstance(edges, dict):
                    continue

                for source_range, target_range in (
                    edges.items()
                ):

                    tvdb_episode = self.resolve_episode_range(
                        anilist_episode,
                        source_range,
                        target_range,
                    )

                    if tvdb_episode is None:
                        continue

                    result = {
                        "tvdb_id": tvdb_id,
                        "season": tvdb_season,
                        "episode": tvdb_episode,
                        "anilist_id": anilist_id,
                        "anilist_episode": anilist_episode,
                    }

                    self.log(
                        "AniBridge: TMDB %s S%02dE%02d -> "
                        "AniList %s E%d -> "
                        "TVDB %s S%02dE%02d"
                        % (
                            tmdb_id,
                            tmdb_season,
                            tmdb_episode,
                            anilist_id,
                            anilist_episode,
                            tvdb_id,
                            tvdb_season,
                            tvdb_episode,
                        )
                    )

                    return result

        self.log(
            "AniBridge: no TVDB mapping for "
            "TMDB %s S%02dE%02d"
            % (
                tmdb_id,
                tmdb_season,
                tmdb_episode,
            )
        )

        return None
