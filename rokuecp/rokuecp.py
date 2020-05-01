"""Asynchronous Python client for Roku."""
import asyncio
from socket import gaierror as SocketGIAEroor
from typing import Any, Mapping, Optional

import aiohttp
import async_timeout
from yarl import URL

from .__version__ import __version__
from .const import VALID_REMOTE_KEYS
from .exceptions import RokuConnectionError, RokuError
from .models import Device, Channel, State


class Roku:
    """Main class for handling connections with Roku."""

    _device: Optional[Device] = None

    def __init__(
        self,
        host: str,
        base_path: str = "/",
        port: int = 8080,
        request_timeout: int = 8,
        session: aiohttp.client.ClientSession = None,
        user_agent: str = None,
    ) -> None:
        """Initialize connection with receiver."""
        self._session = session
        self._close_session = False

        self.base_path = base_path
        self.host = host
        self.port = port
        self.request_timeout = request_timeout
        self.user_agent = user_agent

        if user_agent is None:
            self.user_agent = f"PythonRokuECP/{__version__}"

    async def _request(
        self,
        uri: str = "",
        method: str = "GET",
        data: Optional[Any] = None,
        params: Optional[Mapping[str, str]] = None,
    ) -> Any:
        """Handle a request to a receiver."""
        scheme = "http"

        url = URL.build(
            scheme=scheme, host=self.host, port=self.port, path=self.base_path
        ).join(URL(uri))

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/xml, text/plain, */*",
        }

        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True

        try:
            with async_timeout.timeout(self.request_timeout):
                response = await self._session.request(
                    method, url, data=data, params=params, headers=headers,
                )
        except asyncio.TimeoutError as exception:
            raise RokuConnectionError(
                "Timeout occurred while connecting to device"
            ) from exception
        except (aiohttp.ClientError, SocketGIAEroor) as exception:
            raise RokuConnectionError(
                "Error occurred while communicating with device"
            ) from exception

        content_type = response.headers.get("Content-Type")

        if (response.status // 100) in [4, 5]:
            content = await response.read()
            response.close()

            raise RokuError(
                f"HTTP {response.status}",
                {
                    "content-type": content_type,
                    "message": content.decode("utf8"),
                    "status-code": response.status,
                },
            )

        if "application/xml" in content_type:
            data = await response.read()
            
            return data

        return await response.text()

    @property
    def device(self) -> Optional[Device]:
        """Return the cached Device object."""
        return self._device

    async def update(self, full_update: bool = False) -> Device:
        """Get all information about the device in a single call."""
        if self._device is None or full_update:
            info = await self._request("/query/device-info")
            if info is None:
                raise RokuError("Roku device returned an empty API response")

            apps = await self._request("/query/apps")
            if apps is None or "apps" not in apps:
                raise RokuError("Roku device returned an empty API response")

            self._device = Device({"info": info, "apps": apps["apps"]})
            return self._device

        self._device.update_from_dict({})
        return self._device

    async def remote(self, key: str) -> None:
        """Emulate pressing a key on the remote."""
        if not key.lower() in VALID_REMOTE_KEYS:
            raise RokuError(f"Remote key is invalid: {key}")

        await self._request("keypress/{key}", method="POST")

    async def close(self) -> None:
        """Close open client session."""
        if self._session and self._close_session:
            await self._session.close()

    async def __aenter__(self) -> "Roku":
        """Async enter."""
        return self

    async def __aexit__(self, *exc_info) -> None:
        """Async exit."""
        await self.close()