import json
import secrets
import string
import threading
from os import environ
from os.path import exists
from typing import Optional, Tuple

from dotenv import load_dotenv
from line_works.client import LineWorks
from line_works.mqtt.enums.packet_type import PacketType
from line_works.mqtt.models.packet import MQTTPacket
from line_works.mqtt.models.payload.message import MessagePayload
from line_works.tracer import LineWorksTracer

from flask import Flask, jsonify, request

JSON_FILE = "notify.json"


class NotifySettings(dict):
    def __init__(self, json_path: str = JSON_FILE) -> None:
        super().__init__()
        self.json_path = json_path
        if exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                self.update(json.load(f))

    def __generate_random_token(self) -> str:
        return "".join(
            secrets.choice(string.ascii_letters + string.digits)
            for _ in range(48)
        )

    def get_notify_token(
        self, channel_no: str, user_id: str
    ) -> Tuple[str, bool]:
        user_settings: dict[str, str] = self.get(user_id, {})
        if t := user_settings.get(channel_no):
            return t, False
        return self.add_notify_token(channel_no, user_id), True

    def add_notify_token(self, channel_no: str, user_id: str) -> str:
        token = self.__generate_random_token()

        if not (user_settings := self.get(user_id, {})):
            self[user_id] = user_settings
        user_settings[channel_no] = token

        self.save()

        return token

    def find_channel_no_by_notify_token(
        self, notify_token: str
    ) -> Optional[str]:
        user_settings: dict[str, str]
        for user_settings in self.values():
            for channel_no, token in user_settings.items():
                if token == notify_token:
                    return channel_no
        return None

    def save(self) -> None:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(self, f, ensure_ascii=False, indent=2)


settings = NotifySettings()


def receive_publish_packet(w: LineWorks, p: MQTTPacket) -> None:
    payload = p.payload

    if not isinstance(payload, MessagePayload):
        return

    if not payload.channel_no or not payload.from_user_no:
        return

    user_id = str(payload.from_user_no)
    channel_no = str(payload.channel_no)

    if payload.loc_args1 == "test":
        w.send_text_message(payload.channel_no, "ok")

    elif payload.loc_args1 == "/id":
        w.send_text_message(payload.channel_no, user_id)

    elif payload.loc_args1 == "/notify":
        token, is_new = settings.get_notify_token(channel_no, user_id)
        if is_new:
            w.send_text_message(
                payload.channel_no,
                f"Generated notify token: {token}",
            )
        else:
            w.send_text_message(
                payload.channel_no,
                "You have already registered a notify token.\n"
                f"notify token: {token}",
            )

    elif payload.loc_args1.startswith("/find:"):
        notify_token = payload.loc_args1.split(":")[1].strip()
        channel_no = settings.find_channel_no_by_notify_token(notify_token)
        if channel_no:
            w.send_text_message(
                payload.channel_no,
                f"Channel no: {channel_no}",
            )
        else:
            w.send_text_message(
                payload.channel_no,
                "Notify token not found.",
            )


load_dotenv(".env", verbose=True)

works = LineWorks(works_id=environ["WORKS_ID"], password=environ["PASSWORD"])

tracer = LineWorksTracer(works=works)
tracer.add_trace_func(PacketType.PUBLISH, receive_publish_packet)

app = Flask(__name__)


@app.route("/notify", methods=["POST"])
def notify():
    token = request.json.get("token", "")

    channel_no = settings.find_channel_no_by_notify_token(token)
    if not channel_no:
        return jsonify({"error": "Invalid token"}), 404

    message = request.json.get("message", "")
    if not message:
        return jsonify({"error": "No message provided"}), 400

    works.send_text_message(int(channel_no), message)
    return jsonify({"success": True, "message": "Notification sent"}), 200


def run_flask():
    app.run(host="0.0.0.0", port=3333)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    tracer.trace()
