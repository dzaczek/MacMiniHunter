"""Matrix (Element) notification service - sends deal alerts to a Matrix room."""

import logging
import json
from typing import Optional

import requests

from src.config import settings

logger = logging.getLogger(__name__)


class MatrixNotifier:
    """Sends notifications to a Matrix room via the Matrix Client-Server API.

    Required env vars:
        MATRIX_HOMESERVER: e.g. "https://matrix.org"
        MATRIX_ACCESS_TOKEN: bot user's access token
        MATRIX_ROOM_ID: e.g. "!abc123:matrix.org"
    """

    def __init__(
        self,
        homeserver: Optional[str] = None,
        access_token: Optional[str] = None,
        room_id: Optional[str] = None,
    ):
        self.homeserver = (homeserver or settings.matrix_homeserver).rstrip("/")
        self.access_token = access_token or settings.matrix_access_token
        self.room_id = room_id or settings.matrix_room_id
        self._txn_id = 0

    def send_deal_alert(self, deal: dict) -> bool:
        """Send a formatted deal notification to the Matrix room.

        Args:
            deal: Dict with keys: product_name, store, current_price, avg_price, drop_pct, url
        """
        is_absolute = deal.get("absolute_deal", False)

        if is_absolute:
            plain = (
                f"🔥 ABSOLUTE DEAL: {deal['product_name']}\n"
                f"Store: {deal['store']}\n"
                f"Price: {deal['current_price']:.2f} CHF (threshold: {deal['avg_price']:.2f} CHF)\n"
                f"Link: {deal['url']}"
            )
            html = (
                f"<h3>🔥 ABSOLUTE DEAL: {deal['product_name']}</h3>"
                f"<p><b>Store:</b> {deal['store']}<br/>"
                f"<b>Price:</b> <span style='color:green'>{deal['current_price']:.2f} CHF</span> "
                f"(threshold: {deal['avg_price']:.2f} CHF)<br/>"
                f"<a href='{deal['url']}'>Go to offer →</a></p>"
            )
        else:
            plain = (
                f"📉 Price Drop: {deal['product_name']}\n"
                f"Store: {deal['store']}\n"
                f"Now: {deal['current_price']:.2f} CHF (was avg {deal['avg_price']:.2f} CHF, -{deal['drop_pct']}%)\n"
                f"Link: {deal['url']}"
            )
            html = (
                f"<h3>📉 Price Drop: {deal['product_name']}</h3>"
                f"<p><b>Store:</b> {deal['store']}<br/>"
                f"<b>Price:</b> <span style='color:green'>{deal['current_price']:.2f} CHF</span> "
                f"(avg: {deal['avg_price']:.2f} CHF, <b>-{deal['drop_pct']}%</b>)<br/>"
                f"<a href='{deal['url']}'>Go to offer →</a></p>"
            )

        return self._send_message(plain, html)

    def send_scrape_summary(self, store_counts: dict[str, int]) -> bool:
        """Send a summary after a scraping run."""
        total = sum(store_counts.values())
        lines = [f"Scraping complete: {total} prices recorded"]
        for store, count in store_counts.items():
            lines.append(f"  - {store}: {count}")

        plain = "\n".join(lines)
        html = f"<p><b>Scraping complete:</b> {total} prices recorded</p><ul>"
        for store, count in store_counts.items():
            html += f"<li>{store}: {count}</li>"
        html += "</ul>"

        return self._send_message(plain, html)

    def _send_message(self, plain_text: str, html_body: str) -> bool:
        """Send a message to the configured Matrix room."""
        if not all([self.homeserver, self.access_token, self.room_id]):
            logger.warning("[Matrix] Not configured - skipping notification")
            return False

        self._txn_id += 1
        url = (
            f"{self.homeserver}/_matrix/client/r0/rooms/"
            f"{self.room_id}/send/m.room.message/{self._txn_id}"
        )

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "msgtype": "m.text",
            "body": plain_text,
            "format": "org.matrix.custom.html",
            "formatted_body": html_body,
        }

        try:
            resp = requests.put(url, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            logger.info(f"[Matrix] Message sent to {self.room_id}")
            return True
        except requests.RequestException as e:
            logger.error(f"[Matrix] Failed to send message: {e}")
            return False
