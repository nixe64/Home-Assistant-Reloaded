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

# pylint: disable=unused-variable

import asyncio
import bisect
import collections.abc
import concurrent
import contextlib
import datetime
import functools
import json
import logging
import numbers
import os
import random
import re
import string
import tempfile
import threading
import time
import traceback
import typing
import zoneinfo
from http import client

import atomicwrites
import ciso8601
import slugify as unicode_slug
import typing_extensions
import voluptuous as vol
import yaml

from .const import Const
from .input import Input
from .node_list_class import NodeListClass
from .serialization_error import SerializationError
from .smart_home_controller_error import SmartHomeControllerError
from .write_error import WriteError

_T = typing.TypeVar("_T")
_U = typing.TypeVar("_U")
_R = typing.TypeVar("_R")
_P = typing_extensions.ParamSpec("_P")

_RE_SANITIZE_FILENAME: typing.Final = re.compile(r"(~|\.\.|/|\\)")
_RE_SANITIZE_PATH: typing.Final = re.compile(r"(~|\.(\.)+)")
_VALID_ENTITY_ID: typing.Final = re.compile(
    r"^(?!.+__)(?!_)[\da-z_]+(?<!_)\.(?!_)[\da-z_]+(?<!_)$"
)

_SHUTDOWN_RUN_CALLBACK_THREADSAFE: typing.Final = "_shutdown_run_callback_threadsafe"

_LOGGER: typing.Final = logging.getLogger(__name__)


@typing.overload
class Event:
    ...


@typing.overload
class State:
    ...


def raise_if_invalid_filename(filename: str) -> None:
    """
    Check if a filename is valid.

    Raises a ValueError if the filename is invalid.
    """
    if _RE_SANITIZE_FILENAME.sub("", filename) != filename:
        raise ValueError(f"{filename} is not a safe filename")


def raise_if_invalid_path(path: str) -> None:
    """
    Check if a path is valid.

    Raises a ValueError if the path is invalid.
    """
    if _RE_SANITIZE_PATH.sub("", path) != path:
        raise ValueError(f"{path} is not a safe path")


def slugify(text: str | None, *, separator: str = "_") -> str:
    """Slugify a given text."""
    if text == "" or text is None:
        return ""
    # pylint: disable=unexpected-keyword-arg
    slug = unicode_slug.slugify(text, separator=separator)
    return "unknown" if slug == "" else slug


def repr_helper(inp: typing.Any) -> str:
    """Help creating a more readable string representation of objects."""
    if isinstance(inp, collections.abc.Mapping):
        return ", ".join(
            f"{repr_helper(key)}={repr_helper(item)}" for key, item in inp.items()
        )
    if isinstance(inp, datetime.datetime):
        return as_local(inp).isoformat()

    return str(inp)


def convert(
    value: _T | None, to_type: typing.Callable[[_T], _U], default: _U | None = None
) -> _U | None:
    """Convert value to to_type, returns default if fails."""
    try:
        return default if value is None else to_type(value)
    except (ValueError, TypeError):
        # If value could not be converted
        return default


def ensure_unique_string(
    preferred_string: str,
    current_strings: collections.abc.Iterable[str] | collections.abc.KeysView[str],
) -> str:
    """Return a string that is not present in current_strings.

    If preferred string exists will append _2, _3, ..
    """
    test_string = preferred_string
    current_strings_set = set(current_strings)

    tries = 1

    while test_string in current_strings_set:
        tries += 1
        test_string = f"{preferred_string}_{tries}"

    return test_string


# Taken from http://stackoverflow.com/a/23728630
def get_random_string(length: int = 10) -> str:
    """Return a random string with letters and digits."""
    generator = random.SystemRandom()
    source_chars = string.ascii_letters + string.digits

    return "".join(generator.choice(source_chars) for _ in range(length))


@functools.lru_cache(Const.TNG_MAX_EXPECTED_ENTITY_IDS)
def split_entity_id(entity_id: str) -> tuple[str, str]:
    """Split a state entity ID into domain and object ID."""
    domain, _, object_id = entity_id.partition(".")
    if not domain or not object_id:
        raise ValueError(f"Invalid entity ID {entity_id}")
    return domain, object_id


def valid_entity_id(entity_id: str) -> bool:
    """Test if an entity ID is a valid format.

    Format: <domain>.<entity> where both are slugs.
    """
    return _VALID_ENTITY_ID.match(entity_id) is not None


def ulid_hex() -> str:
    """Generate a ULID in lowercase hex that will work for a UUID.

    This ulid should not be used for cryptographically secure
    operations.

    This string can be converted with https://github.com/ahawker/ulid

    ulid.from_uuid(uuid.UUID(ulid_hex))
    """
    return f"{int(time.time()*1000):012x}{random.getrandbits(80):020x}"


def ulid(timestamp: float | None = None) -> str:
    """Generate a ULID.

    This ulid should not be used for cryptographically secure
    operations.

     01AN4Z07BY      79KA1307SR9X4MV3
    |----------|    |----------------|
     Timestamp          Randomness
       48bits             80bits

    This string can be loaded directly with https://github.com/ahawker/ulid

    import homeassistant.util.ulid as ulid_util
    import ulid
    ulid.parse(ulid_util.ulid())
    """
    ulid_bytes = int((timestamp or time.time()) * 1000).to_bytes(
        6, byteorder="big"
    ) + int(random.getrandbits(80)).to_bytes(10, byteorder="big")

    # This is base32 crockford encoding with the loop unrolled for performance
    #
    # This code is adapted from:
    # https://github.com/ahawker/ulid/blob/06289583e9de4286b4d80b4ad000d137816502ca/ulid/base32.py#L102
    #
    enc = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    return (
        enc[(ulid_bytes[0] & 224) >> 5]
        + enc[ulid_bytes[0] & 31]
        + enc[(ulid_bytes[1] & 248) >> 3]
        + enc[((ulid_bytes[1] & 7) << 2) | ((ulid_bytes[2] & 192) >> 6)]
        + enc[((ulid_bytes[2] & 62) >> 1)]
        + enc[((ulid_bytes[2] & 1) << 4) | ((ulid_bytes[3] & 240) >> 4)]
        + enc[((ulid_bytes[3] & 15) << 1) | ((ulid_bytes[4] & 128) >> 7)]
        + enc[(ulid_bytes[4] & 124) >> 2]
        + enc[((ulid_bytes[4] & 3) << 3) | ((ulid_bytes[5] & 224) >> 5)]
        + enc[ulid_bytes[5] & 31]
        + enc[(ulid_bytes[6] & 248) >> 3]
        + enc[((ulid_bytes[6] & 7) << 2) | ((ulid_bytes[7] & 192) >> 6)]
        + enc[(ulid_bytes[7] & 62) >> 1]
        + enc[((ulid_bytes[7] & 1) << 4) | ((ulid_bytes[8] & 240) >> 4)]
        + enc[((ulid_bytes[8] & 15) << 1) | ((ulid_bytes[9] & 128) >> 7)]
        + enc[(ulid_bytes[9] & 124) >> 2]
        + enc[((ulid_bytes[9] & 3) << 3) | ((ulid_bytes[10] & 224) >> 5)]
        + enc[ulid_bytes[10] & 31]
        + enc[(ulid_bytes[11] & 248) >> 3]
        + enc[((ulid_bytes[11] & 7) << 2) | ((ulid_bytes[12] & 192) >> 6)]
        + enc[(ulid_bytes[12] & 62) >> 1]
        + enc[((ulid_bytes[12] & 1) << 4) | ((ulid_bytes[13] & 240) >> 4)]
        + enc[((ulid_bytes[13] & 15) << 1) | ((ulid_bytes[14] & 128) >> 7)]
        + enc[(ulid_bytes[14] & 124) >> 2]
        + enc[((ulid_bytes[14] & 3) << 3) | ((ulid_bytes[15] & 224) >> 5)]
        + enc[ulid_bytes[15] & 31]
    )


# --------------- File Functions ------------------


def write_utf8_file_atomic(
    filename: str,
    utf8_data: str,
    private: bool = False,
) -> None:
    """Write a file and rename it into place using atomicwrites.

    Writes all or nothing.

    This function uses fsync under the hood. It should
    only be used to write mission critical files as
    fsync can block for a few seconds or longer if the
    disk is busy.

    Using this function frequently will significantly
    negatively impact performance.
    """
    try:
        with atomicwrites.AtomicWriter(filename, overwrite=True).open() as fdesc:
            if not private:
                os.fchmod(fdesc.fileno(), 0o644)
            fdesc.write(utf8_data)
    except OSError as error:
        _LOGGER.exception(f"Saving file failed: {filename}")
        raise WriteError(error) from error


def write_utf8_file(
    filename: str,
    utf8_data: str,
    private: bool = False,
) -> None:
    """Write a file and rename it into place.

    Writes all or nothing.
    """

    tmp_filename = ""
    tmp_path = os.path.split(filename)[0]
    try:
        # Modern versions of Python tempfile create this file with mode 0o600
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=tmp_path, delete=False
        ) as fdesc:
            fdesc.write(utf8_data)
            tmp_filename = fdesc.name
            if not private:
                os.fchmod(fdesc.fileno(), 0o644)
        os.replace(tmp_filename, filename)
    except OSError as error:
        _LOGGER.exception(f"Saving file failed: {filename}")
        raise WriteError(error) from error
    finally:
        if os.path.exists(tmp_filename):
            try:
                os.remove(tmp_filename)
            except OSError as err:
                # If we are cleaning up then something else went wrong, so
                # we should suppress likely follow-on errors in the cleanup
                _LOGGER.error(
                    f"File replacement cleanup failed for {tmp_filename} while "
                    + f"saving {filename}: {err}"
                )


# ---------------- JSON Helper Functions ---------------------------


def load_json(filename: str, default: list | dict | None = None) -> list | dict:
    """Load JSON data from a file and return as dict or list.

    Defaults to returning empty dict if file is not found.
    """
    try:
        with open(filename, encoding="utf-8") as fdesc:
            return json.loads(fdesc.read())  # type: ignore[no-any-return]
    except FileNotFoundError:
        # This is not a fatal error
        _LOGGER.debug(f"JSON file not found: {filename}")
    except ValueError as error:
        _LOGGER.exception(f"Could not parse JSON content: {filename}")
        raise SmartHomeControllerError(error) from error
    except OSError as error:
        _LOGGER.exception(f"JSON file reading failed: {filename}")
        raise SmartHomeControllerError(error) from error
    return {} if default is None else default


def save_json(
    filename: str,
    data: list | dict,
    private: bool = False,
    *,
    encoder: type[json.JSONEncoder] | None = None,
    atomic_writes: bool = False,
) -> None:
    """Save JSON data to a file.

    Returns True on success.
    """
    try:
        json_data = json.dumps(data, indent=4, cls=encoder)
    except TypeError as error:
        msg = (
            f"Failed to serialize to JSON: {filename}. Bad data at "
            + f"{_format_unserializable_data(_find_paths_unserializable_data(data))}"
        )
        _LOGGER.error(msg)
        raise SerializationError(msg) from error

    if atomic_writes:
        write_utf8_file_atomic(filename, json_data, private)
    else:
        write_utf8_file(filename, json_data, private)


def _format_unserializable_data(data: dict[str, typing.Any]) -> str:
    """Format output of find_paths in a friendly way.

    Format is comma separated: <path>=<value>(<type>)
    """
    return ", ".join(f"{path}={value}({type(value)}" for path, value in data.items())


def _find_paths_unserializable_data(
    bad_data: typing.Any, *, dump_func: typing.Callable[[typing.Any], str] = json.dumps
) -> dict[str, typing.Any]:
    """Find the paths to unserializable data.

    This method is slow! Only use for error handling.
    """
    to_process = collections.deque([(bad_data, "$")])
    invalid = {}

    while to_process:
        obj, obj_path = to_process.popleft()

        try:
            dump_func(obj)
            continue
        except (ValueError, TypeError):
            pass

        # We convert objects with as_dict to their dict values so we can find bad data inside it
        if hasattr(obj, "as_dict"):
            desc = obj.__class__.__name__
            if isinstance(obj, State):
                desc += f": {obj.entity_id}"
            elif isinstance(obj, Event):
                desc += f": {obj.event_type}"

            obj_path += f"({desc})"
            obj = obj.as_dict()

        if isinstance(obj, dict):
            for key, value in obj.items():
                try:
                    # Is key valid?
                    dump_func({key: None})
                except TypeError:
                    invalid[f"{obj_path}<key: {key}>"] = key
                else:
                    # Process value
                    to_process.append((value, f"{obj_path}.{key}"))
        elif isinstance(obj, list):
            for idx, value in enumerate(obj):
                to_process.append((value, f"{obj_path}[{idx}]"))
        else:
            invalid[obj_path] = obj

    return invalid


# ------------------- Async IO Helper Functions -------------------------


def fire_coroutine_threadsafe(
    coro: asyncio.coroutines.Coroutine[typing.Any, typing.Any, typing.Any],
    loop: asyncio.events.AbstractEventLoop,
) -> None:
    """Submit a coroutine object to a given event loop.

    This method does not provide a way to retrieve the result and
    is intended for fire-and-forget use. This reduces the
    work involved to fire the function on the loop.
    """
    ident = loop.__dict__.get("_thread_ident")
    if ident is not None and ident == threading.get_ident():
        raise RuntimeError("Cannot be called from within the event loop")

    if not asyncio.coroutines.iscoroutine(coro):
        raise TypeError(f"A coroutine object is required: {coro}")

    def callback() -> None:
        """Handle the firing of a coroutine."""
        asyncio.ensure_future(coro, loop=loop)

    loop.call_soon_threadsafe(callback)


def run_callback_threadsafe(
    loop: asyncio.events.AbstractEventLoop,
    callback: typing.Callable[..., _T],
    *args: typing.Any,
) -> concurrent.futures.Future[_T]:
    """Submit a callback object to a given event loop.

    Return a concurrent.futures.Future to access the result.
    """
    ident = loop.__dict__.get("_thread_ident")
    if ident is not None and ident == threading.get_ident():
        raise RuntimeError("Cannot be called from within the event loop")

    future: concurrent.futures.Future[_T] = concurrent.futures.Future()

    def run_callback() -> None:
        """Run callback and store result."""
        try:
            future.set_result(callback(*args))
        except Exception as exc:  # pylint: disable=broad-except
            if future.set_running_or_notify_cancel():
                future.set_exception(exc)
            else:
                _LOGGER.warning("Exception on lost future: ", exc_info=True)

    loop.call_soon_threadsafe(run_callback)

    if hasattr(loop, _SHUTDOWN_RUN_CALLBACK_THREADSAFE):
        #
        # If the final `TheNextGeneration.async_block_till_done` in
        # `TheNextGeneration.async_stop` has already been called, the callback
        # will never run and, `future.result()` will block forever which
        # will prevent the thread running this code from shutting down which
        # will result in a deadlock when the main thread attempts to shutdown
        # the executor and `.join()` the thread running this code.
        #
        # To prevent this deadlock we do the following on shutdown:
        #
        # 1. Set the _SHUTDOWN_RUN_CALLBACK_THREADSAFE attr on this function
        #    by calling `shutdown_run_callback_threadsafe`
        # 2. Call `hass.async_block_till_done` at least once after shutdown
        #    to ensure all callbacks have run
        # 3. Raise an exception here to ensure `future.result()` can never be
        #    called and hit the deadlock since once `shutdown_run_callback_threadsafe`
        #    we cannot promise the callback will be executed.
        #
        raise RuntimeError("The event loop is in the process of shutting down.")

    return future


def check_loop(
    func: typing.Callable[..., typing.Any],
    strict: bool = True,
    advise_msg: str | None = None,
) -> None:
    """Warn if called inside the event loop. Raise if `strict` is True.

    The default advisory message is 'Use `await hass.async_add_executor_job()'
    Set `advise_msg` to an alternate message if the the solution differs.
    """
    try:
        asyncio.get_running_loop()
        in_loop = True
    except RuntimeError:
        in_loop = False

    if not in_loop:
        return

    found_frame = None

    stack = traceback.extract_stack()

    if (
        func.__name__ == "sleep"
        and len(stack) >= 3
        and stack[-3].filename.endswith("pydevd.py")
    ):
        # Don't report `time.sleep` injected by the debugger (pydevd.py)
        # stack[-1] is us, stack[-2] is protected_loop_func, stack[-3] is the offender
        return

    for frame in reversed(stack):
        for path in ("custom_components/", "smart_home_tng/components/"):
            try:
                index = frame.filename.index(path)
                found_frame = frame
                break
            except ValueError:
                continue

        if found_frame is not None:
            break

    # Did not source from integration? Hard error.
    if found_frame is None:
        raise RuntimeError(
            f"Detected blocking call to {func.__name__} inside the event loop. "
            + f"{advise_msg or 'Use `await hass.async_add_executor_job()`'}; "
            + "This is causing stability issues. Please report issue"
        )

    start = index + len(path)
    end = found_frame.filename.index("/", start)

    integration = found_frame.filename[start:end]

    if path == "custom_components/":
        extra = " to the custom component author"
    else:
        extra = ""
    line = (found_frame.line or "?").strip()
    _LOGGER.warning(
        f"Detected blocking call to {func.__name__} inside the event loop. "
        + f"This is causing stability issues. Please report issue {extra} "
        + f"for {integration} doing blocking calls at {found_frame.filename[index:]}, "
        + f"line {found_frame.lineno}: {line}"
    )
    if strict:
        raise RuntimeError(
            "Blocking calls must be done in the executor or a separate thread; "
            + f"{advise_msg or 'Use `await hass.async_add_executor_job()`'}; "
            + f"at {found_frame.filename[index:]}, line {found_frame.lineno}: "
            + f"{(found_frame.line or '?').strip()}"
        )


def protect_loop(
    func: typing.Callable[_P, _R], strict: bool = True
) -> typing.Callable[_P, _R]:
    """Protect function from running in event loop."""

    @functools.wraps(func)
    def protected_loop_func(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        check_loop(func, strict=strict)
        return func(*args, **kwargs)

    return protected_loop_func


async def gather_with_concurrency(
    limit: int, *tasks: typing.Any, return_exceptions: bool = False
) -> typing.Any:
    """Wrap asyncio.gather to limit the number of concurrent tasks.

    From: https://stackoverflow.com/a/61478547/9127614
    """
    semaphore = asyncio.Semaphore(limit)

    async def sem_task(task: collections.abc.Awaitable[typing.Any]) -> typing.Any:
        async with semaphore:
            return await task

    return await asyncio.gather(
        *(sem_task(task) for task in tasks), return_exceptions=return_exceptions
    )


def shutdown_run_callback_threadsafe(loop: asyncio.events.AbstractEventLoop) -> None:
    """Call when run_callback_threadsafe should prevent creating new futures.

    We must finish all callbacks before the executor is shutdown
    or we can end up in a deadlock state where:

    `executor.result()` is waiting for its `._condition`
    and the executor shutdown is trying to `.join()` the
    executor thread.

    This function is considered irreversible and should only ever
    be called when Home Assistant is going to shutdown and
    python is going to exit.
    """
    setattr(loop, _SHUTDOWN_RUN_CALLBACK_THREADSAFE, True)


# ------------ Datetime Helper Functions --------------------------

_DATE_STR_FORMAT: typing.Final = "%Y-%m-%d"
_UTC: typing.Final = datetime.timezone.utc

# EPOCHORDINAL is not exposed as a constant
# https://github.com/python/cpython/blob/3.10/Lib/zoneinfo/_zoneinfo.py#L12
_EPOCHORDINAL = datetime.datetime(1970, 1, 1).toordinal()

# Copyright (c) Django Software Foundation and individual contributors.
# All rights reserved.
# https://github.com/django/django/blob/master/LICENSE
_DATETIME_RE: typing.Final = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    + r"[T ](?P<hour>\d{1,2}):(?P<minute>\d{1,2})"
    + r"(?::(?P<second>\d{1,2})(?:\.(?P<microsecond>\d{1,6})\d{0,6})?)?"
    + r"(?P<tzinfo>Z|[+-]\d{2}(?::?\d{2})?)?$"
)

# Copyright (c) Django Software Foundation and individual contributors.
# All rights reserved.
# https://github.com/django/django/blob/master/LICENSE
_STANDARD_DURATION_RE: typing.Final = re.compile(
    r"^"
    + r"(?:(?P<days>-?\d+) (days?, )?)?"
    + r"(?P<sign>-?)"
    + r"((?:(?P<hours>\d+):)(?=\d+:\d+))?"
    + r"(?:(?P<minutes>\d+):)?"
    + r"(?P<seconds>\d+)"
    + r"(?:[\.,](?P<microseconds>\d{1,6})\d{0,6})?"
    + r"$"
)

# Copyright (c) Django Software Foundation and individual contributors.
# All rights reserved.
# https://github.com/django/django/blob/master/LICENSE
_ISO8601_DURATION_RE: typing.Final = re.compile(
    r"^(?P<sign>[-+]?)"
    + r"P"
    + r"(?:(?P<days>\d+([\.,]\d+)?)D)?"
    + r"(?:T"
    + r"(?:(?P<hours>\d+([\.,]\d+)?)H)?"
    + r"(?:(?P<minutes>\d+([\.,]\d+)?)M)?"
    + r"(?:(?P<seconds>\d+([\.,]\d+)?)S)?"
    + r")?"
    + r"$"
)

# Copyright (c) Django Software Foundation and individual contributors.
# All rights reserved.
# https://github.com/django/django/blob/master/LICENSE
_POSTGRES_INTERVAL_RE: typing.Final = re.compile(
    r"^"
    + r"(?:(?P<days>-?\d+) (days? ?))?"
    + r"(?:(?P<sign>[-+])?"
    + r"(?P<hours>\d+):"
    + r"(?P<minutes>\d\d):"
    + r"(?P<seconds>\d\d)"
    + r"(?:\.(?P<microseconds>\d{1,6}))?"
    + r")?$"
)


class _TimeZoneSettings:
    """Store the default time zone information."""

    default_time_zone = datetime.timezone.utc


def set_default_time_zone(time_zone: datetime.tzinfo) -> None:
    """Set a default time zone to be used when none is specified.

    Async friendly.
    """
    assert isinstance(time_zone, datetime.tzinfo)

    _TimeZoneSettings.default_time_zone = time_zone


def get_time_zone(time_zone_str: str) -> datetime.tzinfo | None:
    """Get time zone from string. Return None if unable to determine.

    Async friendly.
    """
    try:
        return zoneinfo.ZoneInfo(time_zone_str)
    except zoneinfo.ZoneInfoNotFoundError:
        return None


def utcnow() -> datetime.datetime:
    """Get now in UTC time."""
    return datetime.datetime.now(_UTC)


def now(time_zone: datetime.tzinfo | None = None) -> datetime.datetime:
    """Get now in specified time zone."""
    return datetime.datetime.now(time_zone or _TimeZoneSettings.default_time_zone)


def as_utc(dattim: datetime.datetime) -> datetime.datetime:
    """Return a datetime as UTC time.

    Assumes datetime without tzinfo to be in the DEFAULT_TIME_ZONE.
    """
    if dattim.tzinfo == _UTC:
        return dattim
    if dattim.tzinfo is None:
        dattim = dattim.replace(tzinfo=_TimeZoneSettings.default_time_zone)

    return dattim.astimezone(_UTC)


def as_timestamp(dt_value: datetime.datetime | str) -> float:
    """Convert a date/time into a unix time (seconds since 1970)."""
    parsed_dt: datetime.datetime | None
    if isinstance(dt_value, datetime.datetime):
        parsed_dt = dt_value
    else:
        parsed_dt = parse_datetime(str(dt_value))
    if parsed_dt is None:
        raise ValueError("not a valid date/time.")
    return parsed_dt.timestamp()


def as_local(dattim: datetime.datetime) -> datetime.datetime:
    """Convert a UTC datetime object to local time zone."""
    if dattim.tzinfo == _TimeZoneSettings.default_time_zone:
        return dattim
    if dattim.tzinfo is None:
        dattim = dattim.replace(tzinfo=_TimeZoneSettings.default_time_zone)

    return dattim.astimezone(_TimeZoneSettings.default_time_zone)


def utc_from_timestamp(timestamp: float) -> datetime.datetime:
    """Return a UTC time from a timestamp."""
    return datetime.datetime.utcfromtimestamp(timestamp).replace(tzinfo=_UTC)


def utc_to_timestamp(utc_dt: datetime.datetime) -> float:
    """Fast conversion of a datetime in UTC to a timestamp."""
    # Taken from
    # https://github.com/python/cpython/blob/3.10/Lib/zoneinfo/_zoneinfo.py#L185
    return (
        (utc_dt.toordinal() - _EPOCHORDINAL) * 86400
        + utc_dt.hour * 3600
        + utc_dt.minute * 60
        + utc_dt.second
        + (utc_dt.microsecond / 1000000)
    )


def start_of_local_day(
    dt_or_d: datetime.date | datetime.datetime | None = None,
) -> datetime.datetime:
    """Return local datetime object of start of day from date or datetime."""
    if dt_or_d is None:
        date: datetime.date = now().date()
    elif isinstance(dt_or_d, datetime.datetime):
        date = dt_or_d.date()
    else:
        date = dt_or_d

    return datetime.datetime.combine(
        date, datetime.time(), tzinfo=_TimeZoneSettings.default_time_zone
    )


# Copyright (c) Django Software Foundation and individual contributors.
# All rights reserved.
# https://github.com/django/django/blob/master/LICENSE
def parse_datetime(dt_str: str) -> datetime.datetime | None:
    """Parse a string and return a datetime.datetime.

    This function supports time zone offsets. When the input contains one,
    the output uses a timezone with a fixed offset from UTC.
    Raises ValueError if the input is well formatted but not a valid datetime.
    Returns None if the input isn't well formatted.
    """
    with contextlib.suppress(ValueError, IndexError):
        return ciso8601.parse_datetime(dt_str)

    if not (match := _DATETIME_RE.match(dt_str)):
        return None
    kws: dict[str, typing.Any] = match.groupdict()
    if kws["microsecond"]:
        kws["microsecond"] = kws["microsecond"].ljust(6, "0")
    tzinfo_str = kws.pop("tzinfo")

    tzinfo: datetime.tzinfo | None = None
    if tzinfo_str == "Z":
        tzinfo = _UTC
    elif tzinfo_str is not None:
        offset_mins = int(tzinfo_str[-2:]) if len(tzinfo_str) > 3 else 0
        offset_hours = int(tzinfo_str[1:3])
        offset = datetime.timedelta(hours=offset_hours, minutes=offset_mins)
        if tzinfo_str[0] == "-":
            offset = -offset
        tzinfo = datetime.timezone(offset)
    kws = {k: int(v) for k, v in kws.items() if v is not None}
    kws["tzinfo"] = tzinfo
    return datetime.datetime(**kws)


def parse_date(dt_str: str) -> datetime.date | None:
    """Convert a date string to a date object."""
    try:
        return datetime.datetime.strptime(dt_str, _DATE_STR_FORMAT).date()
    except ValueError:  # If dt_str did not match our format
        return None


# Copyright (c) Django Software Foundation and individual contributors.
# All rights reserved.
# https://github.com/django/django/blob/master/LICENSE
def parse_duration(value: str) -> datetime.timedelta | None:
    """Parse a duration string and return a datetime.timedelta.

    Also supports ISO 8601 representation and PostgreSQL's day-time interval
    format.
    """
    match = (
        _STANDARD_DURATION_RE.match(value)
        or _ISO8601_DURATION_RE.match(value)
        or _POSTGRES_INTERVAL_RE.match(value)
    )
    if match:
        kws = match.groupdict()
        sign = -1 if kws.pop("sign", "+") == "-" else 1
        if kws.get("microseconds"):
            kws["microseconds"] = kws["microseconds"].ljust(6, "0")
        time_delta_args: dict[str, float] = {
            k: float(v.replace(",", ".")) for k, v in kws.items() if v is not None
        }
        days = datetime.timedelta(float(time_delta_args.pop("days", 0.0) or 0.0))
        if match.re == _ISO8601_DURATION_RE:
            days *= sign
        return days + sign * datetime.timedelta(**time_delta_args)
    return None


def parse_time(time_str: str) -> datetime.time | None:
    """Parse a time string (00:20:00) into Time object.

    Return None if invalid.
    """
    parts = str(time_str).split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) > 2 else 0
        return datetime.time(hour, minute, second)
    except ValueError:
        # ValueError if value cannot be converted to an int or not in range
        return None


def get_age(date: datetime.datetime) -> str:
    """
    Take a datetime and return its "age" as a string.

    The age can be in second, minute, hour, day, month or year. Only the
    biggest unit is considered, e.g. if it's 2 days and 3 hours, "2 days" will
    be returned.
    Make sure date is not in the future, or else it won't work.
    """

    def formatn(number: int, unit: str) -> str:
        """Add "unit" if it's plural."""
        if number == 1:
            return f"1 {unit}"
        return f"{number:d} {unit}s"

    delta = (now() - date).total_seconds()
    rounded_delta = round(delta)

    units = ["second", "minute", "hour", "day", "month"]
    factors = [60, 60, 24, 30, 12]
    selected_unit = "year"

    for i, next_factor in enumerate(factors):
        if rounded_delta < next_factor:
            selected_unit = units[i]
            break
        delta /= next_factor
        rounded_delta = round(delta)

    return formatn(rounded_delta, selected_unit)


def parse_time_expression(
    parameter: typing.Any, min_value: int, max_value: int
) -> list[int]:
    """Parse the time expression part and return a list of times to match."""
    if parameter is None or parameter == "*":
        res = list(range(min_value, max_value + 1))
    elif isinstance(parameter, str):
        if parameter.startswith("/"):
            parameter = int(parameter[1:])
            res = [x for x in range(min_value, max_value + 1) if x % parameter == 0]
        else:
            res = [int(parameter)]

    elif not hasattr(parameter, "__iter__"):
        res = [int(parameter)]
    else:
        res = sorted(int(x) for x in parameter)

    for val in res:
        if val < min_value or val > max_value:
            raise ValueError(
                f"Time expression '{parameter}': parameter {val} out of range "
                f"({min_value} to {max_value})"
            )

    return res


def _dst_offset_diff(dattim: datetime.datetime) -> datetime.timedelta:
    """Return the offset when crossing the DST barrier."""
    delta = datetime.timedelta(hours=24)
    return (dattim + delta).utcoffset() - (dattim - delta).utcoffset()


def _lower_bound(arr: list[int], cmp: int) -> int | None:
    """Return the first value in arr greater or equal to cmp.

    Return None if no such value exists.
    """
    if (left := bisect.bisect_left(arr, cmp)) == len(arr):
        return None
    return arr[left]


def find_next_time_expression_time(
    dt_now: datetime.datetime,
    seconds: list[int],
    minutes: list[int],
    hours: list[int],
) -> datetime.datetime:
    """Find the next datetime from now for which the time expression matches.

    The algorithm looks at each time unit separately and tries to find the
    next one that matches for each. If any of them would roll over, all
    time units below that are reset to the first matching value.

    Timezones are also handled (the tzinfo of the now object is used),
    including daylight saving time.
    """
    if not seconds or not minutes or not hours:
        raise ValueError("Cannot find a next time: Time expression never matches!")

    while True:
        # Reset microseconds and fold; fold (for ambiguous DST times) will be handled later
        result = dt_now.replace(microsecond=0, fold=0)

        # Match next second
        if (next_second := _lower_bound(seconds, result.second)) is None:
            # No second to match in this minute. Roll-over to next minute.
            next_second = seconds[0]
            result += datetime.timedelta(minutes=1)

        result = result.replace(second=next_second)

        # Match next minute
        next_minute = _lower_bound(minutes, result.minute)
        if next_minute != result.minute:
            # We're in the next minute. Seconds needs to be reset.
            result = result.replace(second=seconds[0])

        if next_minute is None:
            # No minute to match in this hour. Roll-over to next hour.
            next_minute = minutes[0]
            result += datetime.timedelta(hours=1)

        result = result.replace(minute=next_minute)

        # Match next hour
        next_hour = _lower_bound(hours, result.hour)
        if next_hour != result.hour:
            # We're in the next hour. Seconds+minutes needs to be reset.
            result = result.replace(second=seconds[0], minute=minutes[0])

        if next_hour is None:
            # No minute to match in this day. Roll-over to next day.
            next_hour = hours[0]
            result += datetime.timedelta(days=1)

        result = result.replace(hour=next_hour)

        if result.tzinfo in (None, _UTC):
            # Using UTC, no DST checking needed
            return result

        if not _datetime_exists(result):
            # When entering DST and clocks are turned forward.
            # There are wall clock times that don't "exist" (an hour is skipped).

            # -> trigger on the next time that 1. matches the pattern and 2. does exist
            # for example:
            #   on 2021.03.28 02:00:00 in CET timezone clocks are turned forward an hour
            #   with pattern "02:30", don't run on 28 mar (such a wall time does not
            #   exist on this day instead run at 02:30 the next day

            # We solve this edge case by just iterating one second until the result exists
            # (max. 3600 operations, which should be fine for an edge case that happens once a year)
            dt_now += datetime.timedelta(seconds=1)
            continue

        if not _datetime_ambiguous(now):
            return result

        # When leaving DST and clocks are turned backward.
        # Then there are wall clock times that are ambiguous i.e. exist with DST and without DST
        # The logic above does not take into account if a given pattern matches _twice_
        # in a day.
        # Example: on 2021.10.31 02:00:00 in CET timezone clocks are turned backward an hour

        if _datetime_ambiguous(result):
            # `now` and `result` are both ambiguous, so the next match happens
            # _within_ the current fold.

            # Examples:
            #  1. 2021.10.31 02:00:00+02:00 with pattern 02:30 -> 2021.10.31 02:30:00+02:00
            #  2. 2021.10.31 02:00:00+01:00 with pattern 02:30 -> 2021.10.31 02:30:00+01:00
            return result.replace(fold=dt_now.fold)

        if dt_now.fold == 0:
            # `now` is in the first fold, but result is not ambiguous (meaning it no longer matches
            # within the fold).
            # -> Check if result matches in the next fold. If so, emit that match

            # Turn back the time by the DST offset, effectively run the algorithm on the first fold
            # If it matches on the first fold, that means it will also match on the second one.

            # Example: 2021.10.31 02:45:00+02:00 with pattern 02:30 -> 2021.10.31 02:30:00+01:00

            check_result = find_next_time_expression_time(
                dt_now + _dst_offset_diff(dt_now), seconds, minutes, hours
            )
            if _datetime_ambiguous(check_result):
                return check_result.replace(fold=1)

        return result


def _datetime_exists(dattim: datetime.datetime) -> bool:
    """Check if a datetime exists."""
    assert dattim.tzinfo is not None
    original_tzinfo = dattim.tzinfo
    # Check if we can round trip to UTC
    return dattim == dattim.astimezone(_UTC).astimezone(original_tzinfo)


def _datetime_ambiguous(dattim: datetime.datetime) -> bool:
    """Check whether a datetime is ambiguous."""
    assert dattim.tzinfo is not None
    opposite_fold = dattim.replace(fold=not dattim.fold)
    return _datetime_exists(dattim) and dattim.utcoffset() != opposite_fold.utcoffset()


# ---------------- Helper für ConfigValidation ------------------------------


def boolean(value: typing.Any) -> bool:
    """Validate and coerce a boolean value."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.lower().strip()
        if value in ("1", "true", "yes", "on", "enable"):
            return True
        if value in ("0", "false", "no", "off", "disable"):
            return False
    elif isinstance(value, numbers.Number):
        # type ignore: https://github.com/python/mypy/issues/3186
        return value != 0
    raise vol.Invalid(f"invalid boolean value {value}")


# ------------------ UUID Helpers --------------------------------------------


def random_uuid_hex() -> str:
    """Generate a random UUID hex.

    This uuid should not be used for cryptographically secure
    operations.
    """
    return f"{random.getrandbits(32 * 4): %032x}"


# ----------------- Block Asnync IO -------------------------------------------


def block_async_io() -> None:
    """Enable the detection of blocking calls in the event loop."""
    # Prevent urllib3 and requests doing I/O in event loop
    client.HTTPConnection.putrequest = protect_loop(client.HTTPConnection.putrequest)

    # Prevent sleeping in event loop. Non-strict since 2022.02
    time.sleep = protect_loop(time.sleep, strict=False)

    # Currently disabled. pytz doing I/O when getting timezone.
    # Prevent files being opened inside the event loop
    # builtins.open = protect_loop(builtins.open)


# -------------- YAML Helpers ---------------------------------------------------


def dump(_dict: dict) -> str:
    """Dump YAML to a string and remove null."""
    return yaml.safe_dump(
        _dict, default_flow_style=False, allow_unicode=True, sort_keys=False
    ).replace(": null\n", ":\n")


def save_yaml(path: str, data: dict) -> None:
    """Save YAML to a file."""
    # Dump before writing to not truncate the file if dumping fails
    str_data = dump(data)
    with open(path, "w", encoding="utf-8") as outfile:
        outfile.write(str_data)


# From: https://gist.github.com/miracle2k/3184458
def represent_odict(
    dumper: yaml.SafeDumper, tag: str, mapping, flow_style=None
) -> yaml.MappingNode:
    """Like BaseRepresenter.represent_mapping but does not issue the sort()."""
    value: list = []
    node = yaml.MappingNode(tag, value, flow_style=flow_style)
    if dumper.alias_key is not None:
        dumper.represented_objects[dumper.alias_key] = node
    best_style = True
    if hasattr(mapping, "items"):
        mapping = mapping.items()
    for item_key, item_value in mapping:
        node_key = dumper.represent_data(item_key)
        node_value = dumper.represent_data(item_value)
        if not (isinstance(node_key, yaml.ScalarNode) and not node_key.style):
            best_style = False
        if not (isinstance(node_value, yaml.ScalarNode) and not node_value.style):
            best_style = False
        value.append((node_key, node_value))
    if flow_style is None:
        if dumper.default_flow_style is not None:
            node.flow_style = dumper.default_flow_style
        else:
            node.flow_style = best_style
    return node


yaml.SafeDumper.add_representer(
    typing.OrderedDict,
    lambda dumper, value: represent_odict(dumper, "tag:yaml.org,2002:map", value),
)

yaml.SafeDumper.add_representer(
    NodeListClass,
    lambda dumper, value: dumper.represent_sequence("tag:yaml.org,2002:seq", value),
)

yaml.SafeDumper.add_representer(
    Input,
    lambda dumper, value: dumper.represent_scalar("!input", value.name),
)

# -------------------- Device Registry Helpers ---------------------------------------


def format_mac(mac: str) -> str:
    """Format the mac address string for entry into dev reg."""
    to_test = mac

    if len(to_test) == 17 and to_test.count(":") == 5:
        return to_test.lower()

    if len(to_test) == 17 and to_test.count("-") == 5:
        to_test = to_test.replace("-", "")
    elif len(to_test) == 14 and to_test.count(".") == 2:
        to_test = to_test.replace(".", "")

    if len(to_test) == 12:
        # no : included
        return ":".join(to_test.lower()[i : i + 2] for i in range(0, 12, 2))

    # Not sure how formatted, return original
    return mac
