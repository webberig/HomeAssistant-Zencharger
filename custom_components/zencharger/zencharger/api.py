"""API client for Zencharger Dashboard."""

import logging

import httpx
from requests import get
import json

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import CONF_CREDENTIALS, CONF_DATA, CONF_HOST, CONF_PASSWORD
from .websocket import ZenchargerWebSocket
from .const import ATTR_DATA, ATTR_FAIL_CODE

_LOGGER = logging.getLogger(__name__)


class ZenchargerApi:
    """Api class."""

    @property
    def websocket(self):
        return self._websocket

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self._sessionId = None
        self.cookies = None
        if isinstance(entry, dict):
            self._host = entry[CONF_DATA][CONF_CREDENTIALS][CONF_HOST]
            self._password = entry[CONF_DATA][CONF_CREDENTIALS][CONF_PASSWORD]
        else:
            self._host = entry.data[CONF_CREDENTIALS][CONF_HOST]
            self._password = entry.data[CONF_CREDENTIALS][CONF_PASSWORD]

        self._websocket = ZenchargerWebSocket(hass, entry)

    async def ws_connect(self):
        if self._sessionId is None:
            self.login()
        await self._websocket.ws_connect(self._sessionId)

    def login(self) -> str:
        """Login to api to get Session id."""

        url = self._host + "/api/v1/auth/login"
        headers = {
            "accept": "application/json",
        }
        body = {
            "Password": self._password,
            "PersistentSession": True,
        }
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=1.5)
            response.raise_for_status()

            if "Set-Cookie" in response.headers:
                self._sessionId = response.headers["Set-Cookie"]
                self.cookies = response.cookies
                return response.headers.get("Set-Cookie")

            raise ZenchargerApiError("Could not login with given credentials")
        except Exception as error:
            raise ZenchargerApiError("Could not login with given credentials")

    def status(self) -> str:
        return self.__get("auth/status")

    def getSchedules(self):
        return self.__get("config/scheduledcharging/schedules")

    def updateScheduledCharging(self, chargingSchedule):
        return self.__request("post", "config/scheduledcharging/schedules", chargingSchedule)

    def updateUserConfig(self, config: any):
        return self.__request("patch", "config/user", config)


    def updateCurrentLimit(self, new_value):
        data = self.getSchedules()

        for day, entries in data.items():
            for entry in entries:
                if entry["CurrentLimit"] != 0:
                    entry["CurrentLimit"] = new_value

        self.updateScheduledCharging(data);
        self.updateUserConfig({
            "ScheduledChargingEnable": True
        })

    def __request(self, method: str, path: str, body: dict):
        """Perform POST or PATCH call to API"""
        if self._sessionId is None:
            self.login()

        url = self._host + "/api/v1/" + path

        headers = {
            "accept": "application/json"
        }

        try:
            response = httpx.request(method, url, headers=headers, cookies=self.cookies, json=body, timeout=5)
            response.raise_for_status()
            if not 'application/json' in response.headers.get('Content-Type', ''):
                return None

            json_data = response.json()

            # Session Expired code?
            if ATTR_FAIL_CODE in json_data and json_data[ATTR_FAIL_CODE] == 305:
                # token expired
                self._sessionId = None
                return self._do_call(url, body)

            if ATTR_FAIL_CODE in json_data and json_data[ATTR_FAIL_CODE] != 0:
                raise ZenchargerApiError(
                    f"Retrieving the data for {url} failed with failCode: {json_data[ATTR_FAIL_CODE]}, message: {json_data[ATTR_DATA]}"
                )

            return json_data

        except KeyError as error:
            _LOGGER.error(error)
            _LOGGER.error(response.text)

    def __get(self, path: str):
        """Perform GET call to API"""
        if self._sessionId is None:
            self.login()

        url = self._host + "/api/v1/" + path

        headers = {
            "accept": "application/json"
        }

        try:
            response = get(url, headers=headers, cookies=self.cookies, timeout=1.5)
            response.raise_for_status()
            json_data = response.json()

            # Session Expired code?
            if ATTR_FAIL_CODE in json_data and json_data[ATTR_FAIL_CODE] == 305:
                # token expired
                self._sessionId = None
                return self._do_call(url, body)

            if ATTR_FAIL_CODE in json_data and json_data[ATTR_FAIL_CODE] != 0:
                raise ZenchargerApiError(
                    f"Retrieving the data for {url} failed with failCode: {json_data[ATTR_FAIL_CODE]}, message: {json_data[ATTR_DATA]}"
                )

            return json_data

        except KeyError as error:
            _LOGGER.error(error)
            _LOGGER.error(response.text)


class ZenchargerApiError(Exception):
    """Generic Zencharger Api error."""


class ZenchargerApiAccessFrequencyTooHighError(ZenchargerApiError):
    pass


class ZenchargerApiErrorInvalidAccessToCurrentInterfaceError(ZenchargerApiError):
    pass
