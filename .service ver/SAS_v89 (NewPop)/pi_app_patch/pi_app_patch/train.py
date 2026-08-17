import os
import pickle
import tempfile

import cv2
import face_recognition

DATASET_DIR = "dataset"
ENCODINGS_FILE = "encodings.pickle"


def load_existing_encodings():
    """Load existing encodings and trained file list from pickle."""
    if not os.path.exists(ENCODINGS_FILE):
        return [], [], set()

    try:
        with open(ENCODINGS_FILE, "rb") as f:
            data = pickle.load(f)
        encodings = data.get("encodings", [])
        names = data.get("names", [])
        trained_files = set(data.get("trained_files", []))
        return encodings, names, trained_files
    except Exception as e:
        print(f"[WARN] Could not load existing encodings: {e}")
        return [], [], set()


def _emit_text(callback, message: str) -> None:
    if callback is None:
        return
    try:
        callback(str(message))
    except Exception:
        pass


def _emit_state(
    callback,
    *,
    processed: int,
    total: int,
    phase: str,
    message: str,
    complete: bool = False,
    **extra,
) -> None:
    """Send structured, real training progress to the Pi GUI/API layer.

    There is one final work unit for atomically writing ``encodings.pickle``.
    This keeps 100% reserved for the point at which the new model is fully
    saved and safe for recognition to reload.
    """
    if callback is None:
        return

    safe_processed = max(0, int(processed or 0))
    safe_total = max(0, int(total or 0))

    if complete:
        percent = 100
    elif safe_total <= 0:
        percent = 0
    else:
        percent = int(round((safe_processed / (safe_total + 1)) * 100))
        percent = max(0, min(99, percent))

    state = {
        "processed": safe_processed,
        "total": safe_total,
        "percent": percent,
        "phase": str(phase),
        "message": str(message),
    }
    # Extra counters let the Windows SAS UI distinguish between images that
    # were examined, valid face images added to the model, already-trained
    # images, and images skipped because they could not provide one encoding.
    state.update(extra)

    try:
        callback(state)
    except Exception:
        pass


def _atomic_write_encodings(data: dict) -> None:
    """Write the trained model without exposing a half-written pickle file.

    Recognition can keep using its current in-memory model while training runs.
    Once this atomic replacement completes, recognition detects the new file
    and reloads it safely.
    """
    directory = os.path.dirname(os.path.abspath(ENCODINGS_FILE)) or "."
    fd, temp_path = tempfile.mkstemp(prefix="encodings_", suffix=".tmp", dir=directory)

    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, ENCODINGS_FILE)
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        raise


def train_model(progress_callback=None, progress_state_callback=None):
    """Train only new dataset images and report clear training summary data.

    Newness is determined by the stored ``trained_files`` path list.  Every
    dataset directory is enumerated to find the new files, but only files not
    in that set are opened and face-encoded.  The function continues returning
    an ``int`` (number of valid new face encodings) so existing Pi callers stay
    compatible.
    """
    print("[INFO] Loading existing encodings...")
    _emit_text(progress_callback, "Loading existing encodings...")
    known_encodings, known_names, trained_files = load_existing_encodings()

    if not os.path.exists(DATASET_DIR):
        print("[ERROR] Dataset folder not found.")
        _emit_text(progress_callback, "Dataset folder not found.")
        _emit_state(
            progress_state_callback,
            processed=0,
            total=0,
            phase="failed",
            message="Dataset folder not found.",
            complete=True,
            dataset_total=0,
            already_trained=0,
            valid_images=0,
            skipped_images=0,
        )
        return 0

    persons = [
        d for d in os.listdir(DATASET_DIR)
        if os.path.isdir(os.path.join(DATASET_DIR, d))
    ]

    work_items = []
    dataset_total = 0
    already_trained_count = 0

    # This scans filenames only.  It does not load/encode already-trained files.
    for name in persons:
        person_dir = os.path.join(DATASET_DIR, name)
        images = [
            f for f in os.listdir(person_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]

        for img_name in images:
            dataset_total += 1
            file_key = f"{name}/{img_name}"
            if file_key in trained_files:
                already_trained_count += 1
                continue
            work_items.append((name, img_name, file_key))

    total = len(work_items)
    _emit_state(
        progress_state_callback,
        processed=0,
        total=total,
        phase="preparing",
        message=(
            f"Scanning {dataset_total} dataset image{'s' if dataset_total != 1 else ''}. "
            f"{total} new image{'s' if total != 1 else ''} need training."
            if total > 0
            else f"Scanning {dataset_total} dataset image{'s' if dataset_total != 1 else ''}. No new images need training."
        ),
        dataset_total=dataset_total,
        already_trained=already_trained_count,
        valid_images=0,
        skipped_images=0,
    )

    if total == 0:
        print("[INFO] No new images to train.")
        _emit_text(progress_callback, "No new images to train.")
        _emit_state(
            progress_state_callback,
            processed=0,
            total=0,
            phase="completed",
            message=(
                f"No new images to train. {already_trained_count} existing image"
                f"{'s are' if already_trained_count != 1 else ' is'} already trained."
            ),
            complete=True,
            dataset_total=dataset_total,
            already_trained=already_trained_count,
            valid_images=0,
            skipped_images=0,
        )
        return 0

    new_count = 0
    processed = 0
    skipped_invalid_count = 0

    for name, img_name, file_key in work_items:
        image_path = os.path.join(DATASET_DIR, name, img_name)
        image_trained = False
        message = f"Processing {file_key} ({processed + 1}/{total})"
        _emit_state(
            progress_state_callback,
            processed=processed,
            total=total,
            phase="training",
            message=message,
            dataset_total=dataset_total,
            already_trained=already_trained_count,
            valid_images=new_count,
            skipped_images=skipped_invalid_count,
        )

        try:
            image = cv2.imread(image_path)
            if image is None:
                warning = f"Skipped {file_key}: could not read image"
                print(f"[WARN] {warning}")
                _emit_text(progress_callback, warning)
                continue

            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            boxes = face_recognition.face_locations(rgb, model="hog")

            if len(boxes) != 1:
                warning = f"Skipped {file_key}: expected 1 face, found {len(boxes)}"
                print(f"[SKIP] {warning}")
                _emit_text(progress_callback, warning)
                continue

            image_encodings = face_recognition.face_encodings(rgb, boxes)
            if not image_encodings:
                warning = f"Skipped {file_key}: no usable face encoding was created"
                print(f"[SKIP] {warning}")
                _emit_text(progress_callback, warning)
                continue

            for encoding in image_encodings:
                known_encodings.append(encoding)
                known_names.append(name)
                trained_files.add(file_key)
                new_count += 1

            image_trained = True
            trained_message = f"Trained: {file_key}"
            print(f"[INFO] {trained_message}")
            _emit_text(progress_callback, trained_message)

        except Exception as e:
            warning = f"Skipped {file_key}: {e}"
            print(f"[WARN] {warning}")
            _emit_text(progress_callback, warning)
        finally:
            processed += 1
            if not image_trained:
                skipped_invalid_count += 1
            _emit_state(
                progress_state_callback,
                processed=processed,
                total=total,
                phase="training",
                message=(
                    f"Checked {processed}/{total} new image{'s' if total != 1 else ''}. "
                    f"{new_count} valid, {skipped_invalid_count} skipped."
                ),
                dataset_total=dataset_total,
                already_trained=already_trained_count,
                valid_images=new_count,
                skipped_images=skipped_invalid_count,
            )

    _emit_state(
        progress_state_callback,
        processed=processed,
        total=total,
        phase="saving",
        message="Saving updated face model...",
        dataset_total=dataset_total,
        already_trained=already_trained_count,
        valid_images=new_count,
        skipped_images=skipped_invalid_count,
    )

    if new_count == 0:
        message = (
            f"No valid new faces were added. {processed} new image"
            f"{'s were' if processed != 1 else ' was'} checked and {skipped_invalid_count} skipped."
        )
        print(f"[INFO] {message}")
        _emit_text(progress_callback, message)
        _emit_state(
            progress_state_callback,
            processed=processed,
            total=total,
            phase="completed",
            message=message,
            complete=True,
            dataset_total=dataset_total,
            already_trained=already_trained_count,
            valid_images=0,
            skipped_images=skipped_invalid_count,
        )
        return 0

    data = {
        "encodings": known_encodings,
        "names": known_names,
        "trained_files": list(trained_files),
    }

    _atomic_write_encodings(data)

    complete_message = (
        f"Training complete. {new_count} valid image{'s' if new_count != 1 else ''} trained; "
        f"{skipped_invalid_count} skipped."
    )
    print(f"[INFO] {complete_message}")
    print(f"[INFO] Total faces in database: {len(known_encodings)}")
    _emit_text(progress_callback, complete_message)
    _emit_state(
        progress_state_callback,
        processed=processed,
        total=total,
        phase="completed",
        message=complete_message,
        complete=True,
        dataset_total=dataset_total,
        already_trained=already_trained_count,
        valid_images=new_count,
        skipped_images=skipped_invalid_count,
    )

    return new_count


if __name__ == "__main__":
    train_model()
