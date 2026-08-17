import time

from insightface_engine import get_engine


def _emit_text(callback, message):
    if callback is None:
        return
    try:
        callback(str(message))
    except Exception:
        pass


def _emit_state(callback, **state):
    if callback is None:
        return
    try:
        callback(state)
    except Exception:
        pass


def train_model(progress_callback=None, progress_state_callback=None):
    """v106-compatible train hook for InsightFace.

    InsightFace creates embeddings during capture/registration, so there is no
    separate dlib-style training pass.  Returning 0 preserves the old caller
    contract: zero new images needed training.
    """
    users = get_engine().list_users()
    message = (
        "No training required. InsightFace embeddings are saved during registration. "
        f"{len(users)} registered user(s) are ready."
    )
    _emit_text(progress_callback, message)
    _emit_state(
        progress_state_callback,
        processed=0,
        total=0,
        percent=100,
        phase="completed",
        message=message,
        complete=True,
        dataset_total=sum(int(user.get("samples") or user.get("photos") or 0) for user in users),
        already_trained=sum(int(user.get("samples") or user.get("photos") or 0) for user in users),
        valid_images=0,
        skipped_images=0,
    )
    time.sleep(0.05)
    return 0


if __name__ == "__main__":
    train_model(print)
