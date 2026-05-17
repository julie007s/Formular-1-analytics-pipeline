from __future__ import annotations

import io
import logging
import time
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

from .config import PipelineConfig


logger = logging.getLogger(__name__)


class OpenF1Client:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.base_url = config.base_url

    def build_url(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        endpoint = endpoint.strip("/")
        url = f"{self.base_url}/{endpoint}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    def request_text(self, endpoint: str, params: dict[str, Any] | None = None) -> str | None:
        url = self.build_url(endpoint, params)
        wait = self.config.retry_wait_seconds

        for attempt in range(1, self.config.max_retries + 1):
            logger.info("GET %s", url)
            try:
                response = requests.get(url, timeout=self.config.timeout_seconds)
            except requests.RequestException as exc:
                logger.warning("Request failed on attempt %s/%s: %s", attempt, self.config.max_retries, exc)
                if attempt == self.config.max_retries:
                    return None
                time.sleep(wait)
                wait *= 2
                continue

            if response.status_code == 200:
                return response.text
            if response.status_code == 404:
                logger.info("No data for %s", url)
                return None
            if response.status_code == 429:
                logger.warning("Rate limited on attempt %s/%s. Waiting %.1fs", attempt, self.config.max_retries, wait)
                time.sleep(wait)
                wait *= 2
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                logger.warning("HTTP error on attempt %s/%s: %s", attempt, self.config.max_retries, exc)
                if attempt == self.config.max_retries:
                    return None
                time.sleep(wait)
                wait *= 2

        return None

    def get_csv(self, endpoint: str, params: dict[str, Any] | None = None) -> pd.DataFrame | None:
        text = self.request_text(endpoint, params)
        if text is None:
            return None
        try:
            return pd.read_csv(io.StringIO(text))
        except pd.errors.EmptyDataError:
            logger.info("Empty CSV response for endpoint=%s params=%s", endpoint, params)
            return None

    def get_json(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
        url = self.build_url(endpoint, params)
        wait = self.config.retry_wait_seconds

        for attempt in range(1, self.config.max_retries + 1):
            logger.info("GET %s", url)
            try:
                response = requests.get(url, timeout=self.config.timeout_seconds)
            except requests.RequestException as exc:
                logger.warning("Request failed on attempt %s/%s: %s", attempt, self.config.max_retries, exc)
                if attempt == self.config.max_retries:
                    return None
                time.sleep(wait)
                wait *= 2
                continue

            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                logger.info("No data for %s", url)
                return None
            if response.status_code == 429:
                logger.warning("Rate limited on attempt %s/%s. Waiting %.1fs", attempt, self.config.max_retries, wait)
                time.sleep(wait)
                wait *= 2
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                logger.warning("HTTP error on attempt %s/%s: %s", attempt, self.config.max_retries, exc)
                if attempt == self.config.max_retries:
                    return None
                time.sleep(wait)
                wait *= 2

        return None

    def sleep(self) -> None:
        time.sleep(self.config.sleep_seconds)
