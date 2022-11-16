"""
Amazon Alexa Integration for Smart Home - The Next Generation.

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

import logging
import typing

from ... import core
from .alexa_intent_response import AlexaIntentResponse

_alexa: typing.TypeAlias = core.Alexa
_intent: typing.TypeAlias = core.Intent

_LOGGER: typing.Final = logging.getLogger(__name__)

_HANDLERS: typing.Final[
    core.Registry[
        str,
        typing.Callable[
            [core.SmartHomeController, dict], typing.Awaitable[AlexaIntentResponse]
        ],
    ]
] = core.Registry()

_INTENTS_API_ENDPOINT: typing.Final = "/api/alexa"


SPEECH_MAPPINGS = {
    "plain": _alexa.SpeechType.PLAIN_TEXT,
    "ssml": _alexa.SpeechType.SSML,
    core.Intent.SpeechType.PLAIN: _alexa.SpeechType.PLAIN_TEXT,
    core.Intent.SpeechType.SSML: _alexa.SpeechType.SSML,
}


class UnknownRequest(core.SmartHomeControllerError):
    """When an unknown Alexa request is passed in."""


# pylint: disable=unused-variable
class AlexaIntentsView(core.SmartHomeControllerView):
    """Handle Alexa requests."""

    def __init__(self):
        url = _INTENTS_API_ENDPOINT
        name = "api:alexa"
        super().__init__(url, name)

    async def post(self, request):
        """Handle Alexa."""
        controller = request.app[core.Const.KEY_SHC]
        message: dict = await request.json()

        _LOGGER.debug(f"Received Alexa request: {message}")

        try:
            response = await _async_handle_message(controller, message)
            return b"" if response is None else self.json(response)
        except UnknownRequest as err:
            _LOGGER.warning(str(err))
            return self.json(_intent_error_response(message, str(err)))

        except _intent.UnknownIntent as err:
            _LOGGER.warning(str(err))
            return self.json(
                _intent_error_response(
                    message,
                    "This intent is not yet configured within Home Assistant.",
                )
            )

        except _intent.InvalidSlotInfo as err:
            _LOGGER.error(f"Received invalid slot data from Alexa: {err}")
            return self.json(
                _intent_error_response(
                    message, "Invalid slot information received for this intent."
                )
            )

        except _intent.IntentError as err:
            _LOGGER.exception(str(err))
            return self.json(_intent_error_response(message, "Error handling intent."))


def _intent_error_response(message: dict, error: str):
    """Return an Alexa response that will speak the error message."""
    alexa_intent_info = message.get("request").get("intent")
    alexa_response = AlexaIntentResponse(alexa_intent_info)
    alexa_response.add_speech(_alexa.SpeechType.PLAIN_TEXT, error)
    return alexa_response.as_dict()


async def _async_handle_message(owner: core.SmartHomeController, message: dict):
    """Handle an Alexa intent.

    Raises:
     - UnknownRequest
     - intent.UnknownIntent
     - intent.InvalidSlotInfo
     - intent.IntentError

    """
    req = message.get("request")
    req_type = req["type"]

    if not (handler := _HANDLERS.get(req_type)):
        raise UnknownRequest(f"Received unknown request {req_type}")

    return await handler(owner, message)


@_HANDLERS.register("SessionEndedRequest")
@_HANDLERS.register("IntentRequest")
@_HANDLERS.register("LaunchRequest")
async def _async_handle_intent(owner: core.SmartHomeControllerComponent, message: dict):
    """Handle an intent request.

    Raises:
     - intent.UnknownIntent
     - intent.InvalidSlotInfo
     - intent.IntentError

    """
    req = message.get("request")
    alexa_intent_info = req.get("intent")
    alexa_response = AlexaIntentResponse(alexa_intent_info)

    if req["type"] == "LaunchRequest":
        intent_name = (
            message.get("session", {}).get("application", {}).get("applicationId")
        )
    elif req["type"] == "SessionEndedRequest":
        app_id = message.get("session", {}).get("application", {}).get("applicationId")
        intent_name = f"{app_id}.{req['type']}"
        alexa_response.variables["reason"] = req["reason"]
        alexa_response.variables["error"] = req.get("error")
    else:
        intent_name = alexa_intent_info["name"]

    intent_response = await owner.controller.intents.async_handle_intent(
        owner.domain,
        intent_name,
        {key: {"value": value} for key, value in alexa_response.variables.items()},
    )

    for intent_speech, alexa_speech in SPEECH_MAPPINGS.items():
        if intent_speech in intent_response.speech:
            alexa_response.add_speech(
                alexa_speech, intent_response.speech[intent_speech]["speech"]
            )
        if intent_speech in intent_response.reprompt:
            alexa_response.add_reprompt(
                alexa_speech, intent_response.reprompt[intent_speech]["reprompt"]
            )

    if "simple" in intent_response.card:
        alexa_response.add_card(
            _alexa.CardType.SIMPLE,
            intent_response.card["simple"]["title"],
            intent_response.card["simple"]["content"],
        )

    return alexa_response.as_dict()
