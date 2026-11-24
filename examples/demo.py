"""Offline protocol simulation, NOT an AI comprehension benchmark."""
import json
import tempfile
from pathlib import Path

from continuity.core import Store


def main():
    examples = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory() as temp:
        store = Store(Path(temp) / "demo.sqlite3")
        try:
            store.import_file("demo", examples / "conversations.json")
            snapshot = store.snapshot("demo", ["demo-room-1", "demo-room-2"])["snapshot"]
            checks = json.loads((examples / "checks.json").read_text(encoding="utf-8"))
            store.add_checks(snapshot, checks)
            first = store.new_session(snapshot)["session"]

            def simulate_reader(session):
                while True:
                    chunk = store.read_next(session)
                    if chunk["done"]:
                        break
                    store.acknowledge(session, chunk["position"], chunk["sha"], chunk["receipt_token"])
                # Hard-coded expected answers simulate protocol behavior only.
                for c in checks:
                    store.answer(session, c["id"], c["expected"], c["position"], c["quote"])

            simulate_reader(first)
            store.activate(first)
            prepared = store.prepare_handoff(first, snapshot, 10000, 9500)
            second = prepared["target_session"]
            before = store.status(second)
            simulate_reader(second)
            store.activate(second)
            print(json.dumps({"kind": "offline_protocol_simulation", "paid_api_calls": 0,
                              "threshold": prepared["budget"], "new_reader_before_reading": before,
                              "new_reader_after_checks": store.status(second),
                              "old_session_state": store.status(first)["state"],
                              "native_chatgpt_room_created": False, "ai_comprehension_tested": False}, ensure_ascii=False, indent=2))
        finally:
            store.close()


if __name__ == "__main__":
    main()
