# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Python Youtube API  v1.0.0
# ---------------------------------------------------------------------------
# License: GPL (http://www.gnu.org/licenses/gpl-3.0.html)
# Based on code from php-youtube-api, https://github.com/madcoda/php-youtube-api
# Author:
# Ronen Hayun
# ronen.hayun@gmail.com
# ---------------------------------------------------------------------------

# Modified by CantSayIHave

import json
from urllib.parse import urlparse
import urllib.request
import aiohttp
import asyncio


class YoutubeAPI:
    youtube_key = ""

    apis = {
        'videos.list': 'https://www.googleapis.com/youtube/v3/videos',
        'search.list': 'https://www.googleapis.com/youtube/v3/search',
        'channels.list': 'https://www.googleapis.com/youtube/v3/channels',
        'playlists.list': 'https://www.googleapis.com/youtube/v3/playlists',
        'playlistItems.list': 'https://www.googleapis.com/youtube/v3/playlistItems',
        'activities': 'https://www.googleapis.com/youtube/v3/activities',
    }

    page_info = {}

    def __init__(self, key:str):
        self.youtube_key = key

    async def get_video_info(self, video_id):

        api_url = self.get_api('videos.list')
        params = {
            'id': video_id,
            'key': self.youtube_key,
            'part': 'id, snippet, contentDetails, player, statistics, status'
        }
        apiData = await self.api_get(api_url, params)

        return self.decode_single(apiData)

    async def get_videos_info(self, video_ids):

        ids = video_ids
        if not isinstance(video_ids, basestring):
            ids = video_ids.join(',')

        api_url = self.get_api('videos.list')
        params = {
            'id': ids,
            'part': 'id, snippet, contentDetails, player, statistics, status'
        }
        api_data = await self.api_get(api_url, params)

        return self.decode_list(api_data)

    async def search(self, q, max_results=10):

        params = {
            'q': q,
            'part': 'id, snippet',
            'maxResults': max_results
        }

        return await self.search_advanced(params)

    async def search_videos(self, q, max_results=10, order=None):

        params = {
            'q': q,
            'type': 'video',
            'part': 'id, snippet',
            'maxResults': max_results
        }
        if order is not None:
            params['order'] = order

        s = await self.search_advanced(params)
        return s

    async def search_channel_videos(self, q, channel_id, max_results=10, order=None):

        params = {
            'q': q,
            'type': 'video',
            'channelId': channel_id,
            'part': 'id, snippet',
            'maxResults': max_results
        }
        if order is not None:
            params['order'] = order

        return await self.search_advanced(params)

    async def get_channel_videos(self, channel_id, max_results=10):
        params = {
            'type': 'video',
            'channelId': channel_id,
            'part': 'id, snippet',
            'maxResults': max_results,
            'order': 'date'
        }
        return await self.search_advanced(params)

    async def search_advanced(self, params, page_info=False):

        api_url = self.get_api('search.list')
        if params is None:
            raise ValueError('at least the Search query must be supplied')

        api_data = await self.api_get(api_url, params)
        if page_info:
            return {
                'results': self.decode_list(api_data),
                'info': self.page_info
            }
        else:
            return self.decode_list(api_data)

    async def paginate_results(self, params, token=None):

        if token is not None:
            params['pageToken'] = token
        if params:
            return await self.search_advanced(params, True)

    async def get_channel_by_name(self, username, optional_params=False):

        api_url = self.get_api('channels.list')
        params = {
            'forUsername': username,
            'part': 'id,snippet,contentDetails,statistics,invideoPromotion'
        }
        if optional_params:
            params += optional_params

        api_data = await self.api_get(api_url, params)
        return self.decode_single(api_data)

    async def get_channel_by_id(self, id, optional_params=False):

        api_url = self.get_api('channels.list')
        params = {
            'id': id,
            'part': 'id,snippet,contentDetails,statistics,invideoPromotion'
        }
        if optional_params:
            params += optional_params

        api_data = await self.api_get(api_url, params)
        return self.decode_single(api_data)

    async def get_playlists_by_channel_id(self, channel_id, optional_params={}):

        api_url = self.get_api('playlists.list')
        params = {
            'channelId': channel_id,
            'part': 'id, snippet, status'
        }
        if optional_params:
            params += optional_params

        api_data = await self.api_get(api_url, params)
        return self.decode_list(api_data)

    async def get_playlist_by_id(self, id):

        api_url = self.get_api('playlists.list')
        params = {
            'id': id,
            'part': 'id, snippet, status'
        }
        api_data = await self.api_get(api_url, params)
        return self.decode_single(api_data)

    async def get_playlist_items_by_playlist_id(self, playlist_id, max_results=50):

        api_url = self.get_api('playlistItems.list')
        params = {
            'playlistId': playlist_id,
            'part': 'id, snippet, contentDetails, status',
            'maxResults': max_results
        }
        api_data = await self.api_get(api_url, params)
        return self.decode_list(api_data)

    async def get_activities_by_channel_id(self, channel_id):

        if channel_id is None:
            raise ValueError('ChannelId must be supplied')

        api_url = self.get_api('activities')
        params = {
            'channelId': channel_id,
            'part': 'id, snippet, contentDetails'
        }
        api_data = await self.api_get(api_url, params)
        return self.decode_list(api_data)

    def parse_vid_from_url(self, youtube_url):

        if 'youtube.com' in youtube_url:
            params = self._parse_url_query(youtube_url)
            return params['v']
        elif 'youtu.be' in youtube_url:
            path = self._parse_url_path(youtube_url)
            vid = path[1:]
            return vid
        else:
            raise Exception('The supplied URL does not look like a Youtube URL')

    def get_channel_from_url(self, youtube_url):

        if 'youtube.com' not in youtube_url:
            raise Exception('The supplied URL does not look like a Youtube URL')
        path = self._parse_url_path(youtube_url)
        if '/channel' in path:
            segments = path.split('/')
            channel_id = segments[len(segments) - 1]
            channel = self.get_channel_by_id(channel_id)
        elif '/user' in path:
            segments = path.split('/')
            username = segments[len(segments) - 1]
            channel = self.get_channel_by_name(username)
        else:
            raise Exception('The supplied URL does not look like a Youtube Channel URL')

        return channel

    def get_api(self, name):
        return self.apis[name]

    def decode_single(self, api_data):

        res_obj = json.loads(api_data.decode('utf-8'))
        if 'error' in res_obj:
            msg = "Error {} {}".format(res_obj['error']['code'], res_obj['error']['message'])
            if res_obj['error']['errors'][0]:
                msg = msg + " : " + res_obj['error']['errors'][0]['reason']
            raise Exception(msg)
        else:
            items_array = res_obj['items']
            if isinstance(items_array, dict) or len(items_array) == 0:
                return False
            else:
                return items_array[0]

    def decode_list(self, api_data):

        res_obj = json.loads(api_data.decode('utf-8'))
        if 'error' in res_obj:
            msg = "Error " + res_obj['error']['code'] + " " + res_obj['error']['message']
            if res_obj['error']['errors'][0]:
                msg = msg + " : " + res_obj['error']['errors'][0]['reason']
            raise Exception(msg)
        else:
            self.page_info = {
                'resultsPerPage': res_obj['pageInfo']['resultsPerPage'],
                'totalResults': res_obj['pageInfo']['totalResults'],
                'kind': res_obj['kind'],
                'etag': res_obj['etag'],
                'prevPageToken': None,
                'nextPageToken': None
            }
            if 'prevPageToken' in res_obj:
                self.page_info['prevPageToken'] = res_obj['prevPageToken']
            if 'nextPageToken' in res_obj:
                self.page_info['nextPageToken'] = res_obj['nextPageToken']

            items_array = res_obj['items']
            if isinstance(items_array, dict) or len(items_array) == 0:
                return False
            else:
                return items_array

    async def api_get(self, url, params):

        params['key'] = self.youtube_key

        url = url + "?" + urllib.parse.urlencode(params)

        resp = await self._single_get_request(url)

        data = await resp.read()

        return data

    def _parse_url_path(self, url):

        array = urlparse(url)
        return array['path']

    def _parse_url_query(self, url):

        array = urlparse(url)._asdict()
        query = array['query']
        query_parts = query.split('&')
        params = {}
        for param in query_parts:
            item = param.split('=')
            if not item[1]:
                params[item[0]] = ''
            else:
                params[item[0]] = item[1]

        return params

    @staticmethod
    async def _single_post_request(url: str, **kwargs):
        with aiohttp.ClientSession() as session:
            async with session.post(url, **kwargs) as resp:
                return resp

    @staticmethod
    async def _single_get_request(url: str):
        with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return resp
