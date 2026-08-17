import os
import json
import time
import threading
import socket
import getpass
from typing import Any, Callable, Optional
from flask import Flask, jsonify, request, Response
from flask_cors import CORS

import cv2



API_HOST = "0.0.0.0"
API_PORT = 5000


def start_api_server(gui_app, host=API_HOST, port=API_PORT):
    """
    Start HTTP API server for Windows lockscreen app integration.
    gui_app = instance of FaceRecognitionApp from gui.py
    """

    if getattr(gui_app, "_api_server_started", False):
        return True

    gui_app._api_server_started = True

    def run_server():
        try:
            api_app = create_api_app(gui_app)

            try:
                gui_app.log(f"API server started: http://{host}:{port}", "success")
            except Exception:
                print(f"[API] Server started: http://{host}:{port}")

            api_app.run(
                host=host,
                port=port,
                threaded=True,
                use_reloader=False
            )

        except Exception as e:
            try:
                gui_app._api_last_error = str(e)
                gui_app.log(f"API server error: {e}", "error")
            except Exception:
                print(f"[API ERROR] {e}")

    threading.Thread(target=run_server, daemon=True).start()
    return True

def create_api_app(gui_app):
    api_app = Flask(__name__)
    CORS(api_app)

    def ok(message="", **kwargs):
        data = {
            "ok": True,
            "message": message
        }
        data.update(kwargs)
        return jsonify(data)

    def fail(message="", status=400, **kwargs):
        data = {
            "ok": False,
            "message": message
        }
        data.update(kwargs)
        return jsonify(data), status

    def has_method(name: str) -> bool:
        return hasattr(gui_app, name) and callable(getattr(gui_app, name))

    def call_gui_method(name: str, *args, **kwargs):
        if not has_method(name):
            return False, f"Method not implemented in GUI: {name}", {}

        try:
            method = getattr(gui_app, name)
            result = method(*args, **kwargs)

            # Support helper format: (ok_state, message, extra)
            if isinstance(result, tuple):
                if len(result) == 3:
                    return result
                if len(result) == 2:
                    return result[0], result[1], {}

            return True, "Success", {"result": result}

        except Exception as e:
            gui_app._api_last_error = str(e)
            return False, str(e), {}

    def run_on_tk_thread(func: Callable, wait=False, timeout=10):
        """
        Safely call Tkinter GUI methods from Flask thread.
        """
        result = {
            "done": False,
            "value": None,
            "error": None
        }

        def wrapper():
            try:
                result["value"] = func()
            except Exception as e:
                result["error"] = str(e)
            finally:
                result["done"] = True

        try:
            gui_app.root.after(0, wrapper)
        except Exception as e:
            result["error"] = str(e)
            result["done"] = True

        if not wait:
            return True, "Request submitted.", {}

        start = time.time()
        while not result["done"] and time.time() - start < timeout:
            time.sleep(0.05)

        if result["error"]:
            return False, result["error"], {}

        return True, "Success", {"result": result["value"]}

    # --------------------------------------------------------
    # SYSTEM
    # --------------------------------------------------------
    @api_app.route("/health", methods=["GET"])
    def api_health():
        return ok("Healthy")

    @api_app.route("/system/storage", methods=["GET"])
    def api_system_storage():
        """Expose the Pi SD-card/root-filesystem usage to Windows SAS."""
        try:
            if not has_method("get_system_storage"):
                return fail("System storage service not implemented.", status=501)

            storage = gui_app.get_system_storage()
            if not isinstance(storage, dict):
                return fail("Invalid storage service response.", status=500)

            return jsonify({"ok": True, **storage})
        except Exception as e:
            return fail(f"Failed to read Pi storage: {e}", status=500)

    @api_app.route("/status", methods=["GET"])
    def api_status():
        users = []

        if has_method("_api_get_users_list"):
            try:
                users = gui_app._api_get_users_list()
            except Exception:
                users = []

        return ok(
            "API running",
            recognition_running=getattr(gui_app, "_recognition_running", False),
            capture_running=getattr(gui_app, "_capture_running", False),
            training_running=getattr(gui_app, "_api_training_running", False),
            training_state=getattr(gui_app, "_api_training_state", "idle"),
            last_training_id=getattr(gui_app, "_api_last_training_id", ""),
            last_training_new_faces=getattr(gui_app, "_api_last_training_new_faces", 0),
            last_training_error=getattr(gui_app, "_api_last_training_error", None),
            training_processed=getattr(gui_app, "_api_training_processed", 0),
            training_total=getattr(gui_app, "_api_training_total", 0),
            training_percent=getattr(gui_app, "_api_training_percent", 0),
            training_phase=getattr(gui_app, "_api_training_phase", "idle"),
            training_message=getattr(gui_app, "_api_training_message", ""),
            training_dataset_total=getattr(gui_app, "_api_training_dataset_total", 0),
            training_already_trained=getattr(gui_app, "_api_training_already_trained", 0),
            training_valid_images=getattr(gui_app, "_api_training_valid_images", 0),
            training_skipped_images=getattr(gui_app, "_api_training_skipped_images", 0),
            recognition_resume_pending=bool(
                getattr(gui_app, "_resume_recognition_after_training", False)
                or getattr(gui_app, "_resume_recognition_after_capture", False)
                or getattr(gui_app, "_recognition_resume_pending", False)
            ),
            api_started=getattr(gui_app, "_api_server_started", False),
            hostname=socket.gethostname(),
            device_name=socket.gethostname(),
            system_user=getpass.getuser(),
            ssh_username=getpass.getuser(),
            current_user=getattr(gui_app, "current_user", None),
            auto_capture=getattr(gui_app, "auto_capture_enabled", False),
            users=len(users),
            last_error=getattr(gui_app, "_api_last_error", None)
        )

    # --------------------------------------------------------
    # RECOGNITION
    # --------------------------------------------------------
    @api_app.route("/start-recognition", methods=["POST"])
    def api_start_recognition():
        if has_method("_api_start_recognition_request"):
            ok_state, message, extra = call_gui_method("_api_start_recognition_request")
            return ok(message, **extra) if ok_state else fail(message)

        def start():
            return gui_app.start_recognition_thread()

        ok_state, message, extra = run_on_tk_thread(start, wait=False)
        return ok("Recognition start requested.", **extra) if ok_state else fail(message)

    @api_app.route("/stop-recognition", methods=["POST"])
    def api_stop_recognition():
        """Stop only recognition for an SAS camera transition.

        This intentionally differs from ``/stop``.  A full /stop is a manual
        Pi stop and cancels automatic recognition recovery; SAS training needs
        the camera to resume afterwards.
        """
        if has_method("_api_stop_recognition_request"):
            ok_state, message, extra = call_gui_method("_api_stop_recognition_request")
            return ok(message, **extra) if ok_state else fail(message)

        def stop_recognition():
            gui_app.stop_flag = True
            return True

        ok_state, message, extra = run_on_tk_thread(stop_recognition, wait=False)
        return ok("Recognition stop requested.", **extra) if ok_state else fail(message)

    @api_app.route("/stop", methods=["POST"])
    def api_stop_all():
        """Full manual Pi stop: stop camera work and cancel auto-recovery."""
        if has_method("_api_stop_request"):
            ok_state, message, extra = call_gui_method("_api_stop_request")
            return ok(message, **extra) if ok_state else fail(message)

        def stop_all():
            return gui_app.stop_all()

        ok_state, message, extra = run_on_tk_thread(stop_all, wait=False)
        return ok("Stop requested.", **extra) if ok_state else fail(message)

    @api_app.route("/recognition-result", methods=["GET"])
    def api_recognition_result():
        if has_method("_api_read_recognition_result"):
            try:
                data = gui_app._api_read_recognition_result()
                data["ok"] = True
                return jsonify(data)
            except Exception as e:
                return fail(f"Failed to read recognition result: {e}", status=500)

        result_file = "recognition_result.json"

        if not os.path.exists(result_file):
            return jsonify({
                "ok": True,
                "detected": False,
                "user_id": None,
                "confidence": 0,
                "timestamp": None
            })

        try:
            with open(result_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["ok"] = True
            return jsonify(data)
        except Exception as e:
            return fail(f"Failed to read recognition_result.json: {e}", status=500)

    @api_app.route("/video-feed", methods=["GET"])
    def api_video_feed():
        def generate():
            try:
                while True:
                    frame = None

                    try:
                        with gui_app._api_frame_lock:
                            if gui_app._api_latest_frame is not None:
                                frame = gui_app._api_latest_frame.copy()
                    except Exception:
                        frame = None

                    if frame is None:
                        time.sleep(0.1)
                        continue

                    try:
                        if len(frame.shape) == 3 and frame.shape[2] == 4:
                            frame = frame[:, :, :3]

                        ok_encode, buffer = cv2.imencode(".jpg", frame)

                        if not ok_encode:
                            time.sleep(0.03)
                            continue

                        jpg = buffer.tobytes()

                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                        )

                    except (GeneratorExit, BrokenPipeError, ConnectionResetError):
                        break

                    except Exception as e:
                        gui_app._api_last_error = str(e)
                        time.sleep(0.1)

                    time.sleep(0.03)

            except (GeneratorExit, BrokenPipeError, ConnectionResetError):
                pass

            finally:
                print("[API VIDEO] Client disconnected.")

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )

    # --------------------------------------------------------
    # USERS / FACE DATASET
    # --------------------------------------------------------
    @api_app.route("/users", methods=["GET"])
    def api_users():
        if has_method("_api_get_users_list"):
            try:
                return jsonify({
                    "ok": True,
                    "users": gui_app._api_get_users_list()
                })
            except Exception as e:
                return fail(f"Failed to get users: {e}", status=500)

        return fail("User list API helper not implemented.", status=501)

    @api_app.route("/users/<user_id>", methods=["GET"])
    def api_user_detail(user_id):
        if not has_method("_api_get_users_list"):
            return fail("User list API helper not implemented.", status=501)

        users = gui_app._api_get_users_list()

        for user in users:
            if str(user.get("id", "")).lower() == str(user_id).lower():
                return jsonify({
                    "ok": True,
                    "user": user
                })

        return fail("User not found.", status=404)

    @api_app.route("/capture-user", methods=["POST"])
    def api_capture_user():
        payload = request.get_json(silent=True) or {}

        user_id = str(payload.get("user_id", "")).strip()
        mode = str(payload.get("mode", "add")).strip()

        if not user_id:
            return fail("Missing user_id.")

        auto_capture = payload.get("auto_capture", None)

        if has_method("_api_capture_user_request"):
            ok_state, message, extra = call_gui_method(
                "_api_capture_user_request",
                user_id,
                mode,
                auto_capture
            )
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Capture API helper not implemented.", status=501)

    @api_app.route("/capture-photo", methods=["POST"])
    def api_capture_photo():
        if has_method("_api_manual_capture_request"):
            ok_state, message, extra = call_gui_method("_api_manual_capture_request")
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Manual capture API helper not implemented.", status=501)

    @api_app.route("/stop-capture", methods=["POST"])
    def api_stop_capture():
        if has_method("_api_stop_capture_request"):
            ok_state, message, extra = call_gui_method("_api_stop_capture_request")
            return ok(message, **extra) if ok_state else fail(message)

        try:
            gui_app._stop_capture_event.set()
            return ok("Capture stop requested.")
        except Exception as e:
            return fail(f"Failed to stop capture: {e}", status=500)

    @api_app.route("/train", methods=["POST"])
    def api_train():
        if has_method("_api_train_request"):
            ok_state, message, extra = call_gui_method("_api_train_request")
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Train API helper not implemented.", status=501)

    @api_app.route("/delete-user", methods=["POST"])
    def api_delete_user():
        payload = request.get_json(silent=True) or {}
        user_id = str(payload.get("user_id", "")).strip()

        if not user_id:
            return fail("Missing user_id.")

        if has_method("_api_delete_user_request"):
            ok_state, message, extra = call_gui_method(
                "_api_delete_user_request",
                user_id
            )
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Delete API helper not implemented.", status=501)

    # --------------------------------------------------------
    # SETTINGS / SERVER PATH
    # --------------------------------------------------------
    @api_app.route("/settings", methods=["GET"])
    def api_get_settings():
        try:
            include_password = str(request.args.get("include_password", "false")).strip().lower() in (
                "1", "true", "yes", "y", "on"
            )

            if has_method("get_settings"):
                data = gui_app.get_settings(include_password=include_password)
                return jsonify({
                    "ok": True,
                    **data
                })

            return fail("Settings service not implemented.", status=501)

        except Exception as e:
            return fail(f"Failed to load settings: {e}", status=500)

    @api_app.route("/settings", methods=["POST"])
    def api_save_settings():
        """
        Body example:
        {
            "username": "4372447",
            "password": "plain_password",
            "pc_save_path": "//server/path",
            "auto_capture": true
        }
        """
        if has_method("_api_save_settings_request"):
            payload = request.get_json(silent=True) or {}
            ok_state, message, extra = call_gui_method(
                "_api_save_settings_request",
                payload
            )
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Settings save API helper not implemented yet.", status=501)

    @api_app.route("/server/mount", methods=["POST"])
    def api_mount_server():
        payload = request.get_json(silent=True) or {}

        username = str(payload.get("username", "")).strip() or None
        password = str(payload.get("password", "")).strip() or None
        pc_save_path = str(payload.get("pc_save_path", "")).strip() or None
        save = bool(payload.get("save", False))

        if has_method("mount_server"):
            ok_state, message, extra = gui_app.mount_server(
                username=username,
                password=password,
                unc_path=pc_save_path,
                save=save
            )
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Mount server API not implemented.", status=501)

    # --------------------------------------------------------
    # ADMINS
    # --------------------------------------------------------
    @api_app.route("/admins", methods=["GET"])
    def api_get_admins():
        try:
            return jsonify({
                "ok": True,
                "admins": getattr(gui_app, "admin_list", []),
                "current_user": getattr(gui_app, "current_user", None)
            })
        except Exception as e:
            return fail(f"Failed to get admins: {e}", status=500)

    @api_app.route("/admins/validate", methods=["POST"])
    def api_validate_admin():
        payload = request.get_json(silent=True) or {}
        ntid = str(payload.get("ntid", "")).strip()

        if not ntid:
            return fail("Missing ntid.")

        try:
            valid = gui_app._validate_ntid_in_ad(ntid)
            return ok("Validation completed.", ntid=ntid, valid=valid)
        except Exception as e:
            return fail(f"Validation failed: {e}", status=500)

    @api_app.route("/admins/add", methods=["POST"])
    def api_add_admin():
        payload = request.get_json(silent=True) or {}
        ntid = str(payload.get("ntid", "")).strip()

        if not ntid:
            return fail("Missing ntid.")

        if has_method("add_admin"):
            ok_state, message, extra = gui_app.add_admin(ntid, validate=True)
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Admin add service not implemented.", status=501)

    @api_app.route("/admins/remove", methods=["POST"])
    def api_remove_admin():
        payload = request.get_json(silent=True) or {}
        ntid = str(payload.get("ntid", "")).strip()

        if not ntid:
            return fail("Missing ntid.")

        if has_method("remove_admin"):
            ok_state, message, extra = gui_app.remove_admin(ntid)
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Admin remove service not implemented.", status=501)

    # --------------------------------------------------------
    # LOGS
    # --------------------------------------------------------
    @api_app.route("/logs", methods=["GET"])
    def api_get_logs():
        try:
            if has_method("get_logs"):
                return jsonify({
                    "ok": True,
                    "logs": gui_app.get_logs(limit=200)
                })

            return jsonify({
                "ok": True,
                "logs": []
            })

        except Exception as e:
            return fail(f"Failed to read logs: {e}", status=500)

    @api_app.route("/logs/clear", methods=["POST"])
    def api_clear_logs():
        if has_method("clear_logs"):
            ok_state, message, extra = gui_app.clear_logs()
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Clear logs service not implemented.", status=501)

    # --------------------------------------------------------
    # FACE DATA TRANSFER - SMB / LOCAL
    # --------------------------------------------------------
    @api_app.route("/face-data/export", methods=["POST"])
    def api_export_face_data():
        try:
            payload = request.get_json(silent=True) or {}
            target_folder = payload.get("target_folder")

            if has_method("export_face_data_to_folder"):
                ok_state, message, extra = gui_app.export_face_data_to_folder(
                    target_folder=target_folder,
                    username=payload.get("username"),
                    password=payload.get("password"),
                    pc_save_path=payload.get("pc_save_path"),
                )
                return ok(message, **extra) if ok_state else fail(message)

            return fail("Export service not implemented.", status=501)
        except Exception as e:
            return fail(f"Export API error: {e}", status=500)

    @api_app.route("/face-data/list-server-zips", methods=["POST"])
    def api_list_server_zips():
        try:
            payload = request.get_json(silent=True) or {}

            if has_method("list_server_face_data_zips"):
                ok_state, message, extra = gui_app.list_server_face_data_zips(
                    username=payload.get("username"),
                    password=payload.get("password"),
                    pc_save_path=payload.get("pc_save_path"),
                )
                return ok(message, **extra) if ok_state else fail(message)

            return fail("Server ZIP list service not implemented.", status=501)
        except Exception as e:
            return fail(f"List server ZIP API error: {e}", status=500)

    @api_app.route("/face-data/import", methods=["POST"])
    def api_import_face_data():
        payload = request.get_json(silent=True) or {}
        zip_path = str(payload.get("zip_path", "")).strip()

        if not zip_path:
            return fail("Missing zip_path.")

        if has_method("import_face_data_from_zip"):
            ok_state, message, extra = gui_app.import_face_data_from_zip(zip_path)
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Import service not implemented.", status=501)

    # --------------------------------------------------------
    # FACE DATA TRANSFER - SFTP IMPORT TARGET
    # --------------------------------------------------------
    @api_app.route("/face-data/sftp-import-target", methods=["POST"])
    def api_sftp_import_target():
        try:
            if has_method("get_sftp_import_target"):
                ok_state, message, extra = gui_app.get_sftp_import_target()
                return ok(message, **extra) if ok_state else fail(message)

            return fail("SFTP import target service not implemented.", status=501)
        except Exception as e:
            return fail(f"SFTP import target API error: {e}", status=500)


    # --------------------------------------------------------
    # FACE DATA TRANSFER - SFTP DOWNLOAD PREPARE
    # --------------------------------------------------------
    @api_app.route("/face-data/sftp-prepare-download", methods=["POST"])
    def api_sftp_prepare_download():
        try:
            if has_method("prepare_sftp_download_package"):
                ok_state, message, extra = gui_app.prepare_sftp_download_package()
                return ok(message, **extra) if ok_state else fail(message)

            return fail("SFTP download package service not implemented.", status=501)
        except Exception as e:
            return fail(f"SFTP download package API error: {e}", status=500)

    # --------------------------------------------------------
    # FACE DATA TRANSFER - SFTP
    # --------------------------------------------------------
    @api_app.route("/face-data/sftp-send", methods=["POST"])
    def api_sftp_send():
        payload = request.get_json(silent=True) or {}
    
        host = str(payload.get("host", "")).strip()
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", "")).strip()
        remote_dir = str(payload.get("remote_dir", "")).strip()
        port = int(payload.get("port", 22))
    
        if not host or not username or not password or not remote_dir:
            return fail("Missing host, username, password or remote_dir.")
    
        if has_method("sftp_send_face_data"):
            ok_state, message, extra = gui_app.sftp_send_face_data(
                host=host,
                username=username,
                password=password,
                remote_dir=remote_dir,
                port=port
            )
            return ok(message, **extra) if ok_state else fail(message)
    
        return fail("SFTP send service not implemented.", status=501)


    # --------------------------------------------------------
    # FACE DATA TRANSFER - MULTI-PI SFTP TARGETS / BATCHES
    # --------------------------------------------------------
    def _multi_sftp_manager_or_error():
        try:
            # Imported only when the SAS/Pi multi-transfer feature is used.
            # A failure here must not stop the face-recognition API startup.
            from multi_sftp_transfer import get_multi_sftp_manager
            return get_multi_sftp_manager(gui_app), None
        except Exception as exc:
            return None, f"Multi-Pi SFTP feature is unavailable: {exc}"

    @api_app.route("/face-data/sftp-targets", methods=["GET"])
    def api_multi_sftp_targets_list():
        manager, error = _multi_sftp_manager_or_error()
        if error:
            return fail(error, status=501)
        return ok(
            "SFTP targets loaded.",
            targets=manager.list_targets(),
            config=manager.get_transfer_config(),
        )

    @api_app.route("/face-data/sftp-targets", methods=["POST"])
    def api_multi_sftp_targets_add():
        manager, error = _multi_sftp_manager_or_error()
        if error:
            return fail(error, status=501)
        payload = request.get_json(silent=True) or {}
        hostname = str(payload.get("hostname", "")).strip()
        success, message, targets = manager.add_target(hostname)
        return ok(message, targets=targets) if success else fail(message)

    @api_app.route("/face-data/sftp-targets/<path:hostname>", methods=["DELETE"])
    def api_multi_sftp_targets_remove(hostname):
        manager, error = _multi_sftp_manager_or_error()
        if error:
            return fail(error, status=501)
        success, message, targets = manager.remove_target(hostname)
        return ok(message, targets=targets) if success else fail(message, status=404)

    @api_app.route("/face-data/sftp-multi-config", methods=["GET"])
    def api_multi_sftp_config():
        manager, error = _multi_sftp_manager_or_error()
        if error:
            return fail(error, status=501)
        return ok("Multi-Pi SFTP configuration loaded.", config=manager.get_transfer_config())

    @api_app.route("/face-data/sftp-multi-send", methods=["POST"])
    def api_multi_sftp_send():
        manager, error = _multi_sftp_manager_or_error()
        if error:
            return fail(error, status=501)
        payload = request.get_json(silent=True) or {}
        targets = payload.get("targets", None)
        if targets is None:
            targets = manager.list_targets()
        if not isinstance(targets, list):
            return fail("targets must be an array of hostnames or IP addresses.")
        success, message, snapshot = manager.start_batch(targets)
        return ok(message, batch=snapshot) if success else fail(message)

    @api_app.route("/face-data/sftp-multi-send/<batch_id>", methods=["GET"])
    def api_multi_sftp_status(batch_id):
        manager, error = _multi_sftp_manager_or_error()
        if error:
            return fail(error, status=501)
        snapshot = manager.get_batch_snapshot(batch_id)
        if snapshot is None:
            return fail("Transfer batch was not found.", status=404)
        return ok("Transfer status loaded.", batch=snapshot)

    @api_app.route("/face-data/sftp-multi-send/<batch_id>/retry-failed", methods=["POST"])
    def api_multi_sftp_retry_failed(batch_id):
        manager, error = _multi_sftp_manager_or_error()
        if error:
            return fail(error, status=501)
        success, message, snapshot = manager.retry_failed(batch_id)
        return ok(message, batch=snapshot) if success else fail(message)

    @api_app.route("/face-data/sftp-multi-send/<batch_id>/cancel", methods=["POST"])
    def api_multi_sftp_cancel(batch_id):
        manager, error = _multi_sftp_manager_or_error()
        if error:
            return fail(error, status=501)
        success, message, snapshot = manager.cancel_batch(batch_id)
        return ok(message, batch=snapshot) if success else fail(message)

    @api_app.route("/face-data/sftp-multi-send/<batch_id>/cleanup", methods=["POST"])
    def api_multi_sftp_cleanup(batch_id):
        manager, error = _multi_sftp_manager_or_error()
        if error:
            return fail(error, status=501)
        success, message, snapshot = manager.cleanup_batch(batch_id)
        return ok(message, batch=snapshot) if success else fail(message)

    @api_app.route("/face-data/received", methods=["GET"])
    def api_received_face_data():
        try:
            if has_method("list_received_face_data"):
                return jsonify({
                    "ok": True,
                    "pending": gui_app.list_received_face_data()
                })

            return fail("Received face data service not implemented.", status=501)

        except Exception as e:
            return fail(f"Failed to list received data: {e}", status=500)
        
    @api_app.route("/face-data/received/accept", methods=["POST"])
    def api_accept_received():
        payload = request.get_json(silent=True) or {}
        filename = str(payload.get("filename", "")).strip()

        if not filename:
            return fail("Missing filename.")

        if has_method("accept_received_face_data"):
            ok_state, message, extra = gui_app.accept_received_face_data(filename)
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Accept received service not implemented.", status=501)


    @api_app.route("/face-data/received/reject", methods=["POST"])
    def api_reject_received():
        payload = request.get_json(silent=True) or {}
        filename = str(payload.get("filename", "")).strip()

        if not filename:
            return fail("Missing filename.")

        if has_method("reject_received_face_data"):
            ok_state, message, extra = gui_app.reject_received_face_data(filename)
            return ok(message, **extra) if ok_state else fail(message)

        return fail("Reject received service not implemented.", status=501)

    return api_app
