"""
Core components of Smart Home - The Next Generation.

Smart Home - TNG is a Home Automation framework for observing the state
of entities and react to changes. It is based on Home Assistant from
home-assistant.io and the Home Assistant Community.

Copyright (c) 2022, Andreas Nixdorf

This program is free software: you can redistribute it and/or
modify it under the terms of the GNU General Public License as
published by the Free Software Foundation, either version 3 of
the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public
License along with this program.  If not, see
http://www.gnu.org/licenses/.
"""

import asyncio
import collections.abc
import http
import json
import logging
import typing

import voluptuous as vol
from aiohttp import typedefs, web, web_urldispatcher

from .json_encoder import JSONEncoder
from .callback import is_callback
from .const import Const
from .context import Context
from .service_not_found import ServiceNotFound
from .unauthorized import Unauthorized

_LOGGER: typing.Final = logging.getLogger(__name__)


# pylint: disable=unused-variable
@typing.overload
class SmartHomeControllerView:
    ...


class SmartHomeControllerView:
    """Base view for all views."""

    url: str | None = None
    extra_urls: list[str] = []
    # Views inheriting from this class can override this
    requires_auth = True
    cors_allowed = False

    @staticmethod
    def context(request: web.Request) -> Context:
        """Generate a context from a request."""
        if (user := request.get(Const.KEY_TNG_USER)) is None:
            return Context()

        return Context(user_id=user.id)

    @staticmethod
    def json(
        result: typing.Any,
        status_code: http.HTTPStatus | int = http.HTTPStatus.OK,
        headers: typedefs.LooseHeaders | None = None,
    ) -> web.Response:
        """Return a JSON response."""
        try:
            msg = json.dumps(result, cls=JSONEncoder, allow_nan=False).encode("UTF-8")
        except (ValueError, TypeError) as err:
            _LOGGER.error(f"Unable to serialize to JSON: {err}\n{result}")
            raise web.HTTPInternalServerError from err
        response = web.Response(
            body=msg,
            content_type=Const.CONTENT_TYPE_JSON,
            status=int(status_code),
            headers=headers,
        )
        response.enable_compression()
        return response

    def json_message(
        self,
        message: str,
        status_code: http.HTTPStatus | int = http.HTTPStatus.OK,
        message_code: str | None = None,
        headers: typedefs.LooseHeaders | None = None,
    ) -> web.Response:
        """Return a JSON message response."""
        data = {"message": message}
        if message_code is not None:
            data["code"] = message_code
        return self.json(data, status_code, headers=headers)

    def register(self, app: web.Application, router: web.UrlDispatcher) -> None:
        """Register the view with a router."""
        assert self.url is not None, "No url set for view"
        urls = [self.url] + self.extra_urls
        routes: list[web_urldispatcher.AbstractRoute] = []

        for method in ("get", "post", "delete", "put", "patch", "head", "options"):
            if not (handler := getattr(self, method, None)):
                continue

            handler = self._request_handler_factory(handler)

            for url in urls:
                routes.append(router.add_route(method, url, handler))

        # Use `get` because CORS middleware is not be loaded in emulated_hue
        if self.cors_allowed:
            allow_cors = app.get("allow_all_cors")
        else:
            allow_cors = app.get("allow_configured_cors")

        if allow_cors:
            for route in routes:
                allow_cors(route)

    def _request_handler_factory(
        self, handler: typing.Callable
    ) -> typing.Callable[[web.Request], collections.abc.Awaitable[web.StreamResponse]]:
        """Wrap the handler classes."""
        assert asyncio.iscoroutinefunction(handler) or is_callback(
            handler
        ), "Handler should be a coroutine or a callback."

        async def handle(request: web.Request) -> web.StreamResponse:
            """Handle incoming request."""
            if request.app[Const.KEY_TNG].is_stopping:
                return web.Response(status=http.HTTPStatus.SERVICE_UNAVAILABLE)

            authenticated = request.get(Const.KEY_AUTHENTICATED, False)

            if self.requires_auth and not authenticated:
                raise web.HTTPUnauthorized()

            _LOGGER.debug(
                f"Serving {request.path} to {request.remote} (auth: {authenticated})"
            )

            try:
                result = handler(request, **request.match_info)

                if asyncio.iscoroutine(result):
                    result = await result
            except vol.Invalid as err:
                raise web.HTTPBadRequest() from err
            except ServiceNotFound as err:
                # pylint: disable=bad-exception-context
                raise web.HTTPInternalServerError() from err
            except Unauthorized as err:
                # pylint: disable=bad-exception-context
                raise web.HTTPUnauthorized() from err

            if isinstance(result, web.StreamResponse):
                # The method handler returned a ready-made Response, how nice of it
                return result

            status_code = http.HTTPStatus.OK

            if isinstance(result, tuple):
                result, status_code = result

            if isinstance(result, bytes):
                bresult = result
            elif isinstance(result, str):
                bresult = result.encode("utf-8")
            elif result is None:
                bresult = b""
            else:
                assert (
                    False
                ), f"Result should be None, string, bytes or StreamResponse. Got: {result}"

            return web.Response(body=bresult, status=status_code)

        return handle
