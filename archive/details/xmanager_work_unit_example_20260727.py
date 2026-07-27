# Historical one-off diagnostic preserved for provenance.
# The ids are stale; do not use this as an active shared utility.

from absl import app
from google3.learning.deepmind.xmanager2.client import xmanager_api

def main(argv):
    c = xmanager_api.XManagerApi()
    wu = c.get_work_unit(274477069, 1)
    print(f"Status: {wu.status_name} / Msg: {getattr(wu, 'status_message', 'No message')}")
    print(getattr(wu, 'error_message', 'No error_message'))
    print(getattr(wu, 'failure_reason', 'No failure reason'))
    print("\n--- Logs ---")
    try:
        urls = wu.get_log_urls()  # type: ignore
        print("Log URLs:", list(urls))
    except Exception as e:
        print("Could not get log URLs:", e)

    print("\n--- History ---")
    try:
        for ev in wu.get_history():  # type: ignore
            print(ev)
    except Exception as e:
        print("Could not get history:", e)

if __name__ == '__main__':
    app.run(main)
