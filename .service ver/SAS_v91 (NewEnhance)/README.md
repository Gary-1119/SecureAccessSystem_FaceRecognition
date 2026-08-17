## Latest patch: SAS v105 — Square Locked Camera Panel

### Changed
- Changed the locked desktop notification camera preview from a wide rectangle to a centred, fixed **1:1 square** scan viewport.
- Standard notification mode uses a 224 × 224 px square preview; compact mode uses a 204 × 204 px square preview.
- The Pi frame is centre-cropped with the existing `KeepAspectRatioByExpanding` scaling so the square panel is fully filled without distortion.
- Kept the same read-only `GET /video-feed` viewer, scan corners, scan line, LIVE / CONNECTING status, desktop-visible lock behavior, and SAS minimized state.

### Files changed
```text
Modified: sas_dashboard_modular/dialogs.py
- Updated SystemLockedNotification sizing and converted the camera panel to a centred fixed square viewport.

Modified: README.md
- Added SAS v105 release notes and the changed-file list.
```

### Not changed
```text
- sas_dashboard_modular/dashboard.py
- sas_dashboard_modular/services/runtime_lock_service.py
- Pi face-recognition code / pi_app_patch
- Pi camera capture, recognition, training, API behavior, SFTP, import/export, login, and admin logic
```

---

## Latest patch: SAS v104 — Locked Desktop Live Camera Panel

### Changed
- Expanded the small bottom-right **SYSTEM LOCKED** desktop notification with the requested live Pi camera panel.
- The card keeps the desktop-visible lock design: SAS remains minimized, the normal Windows desktop stays visible, and no blur/darken overlay is restored.
- While locked, the notification opens a dedicated **read-only** visual subscription to the Raspberry Pi API endpoint:
  - `GET /video-feed`
- The new panel displays a compact live MJPEG camera preview, biometric-style red corner markers, a scan line, and a connection/live indicator.
- It does **not** start or stop recognition, capture a photo, train a model, alter Pi settings, or control the physical camera. It only views the existing Pi stream.
- The notification stops and releases this second preview connection automatically when the user unlocks by face recognition, emergency hotkey, or other normal unlock flow.
- The existing locked-state keyboard/mouse blocking behavior and emergency hotkey remain unchanged.

### Files changed
```text
Modified: sas_dashboard_modular/dialogs.py
- Expanded SystemLockedNotification with a read-only Pi /video-feed camera viewer.
- Added background MJPEG reading, Qt-safe frame rendering, live/reconnecting/unavailable statuses, and automatic stream cleanup.
- Added the compact scan-frame visual panel matching the supplied design.

Modified: sas_dashboard_modular/dashboard.py
- Passes the configured Pi /video-feed URL to the locked desktop notification without restoring or activating SAS.

Modified: README.md
- Added SAS v104 release notes and the changed-file list.
```

### Not changed
```text
- sas_dashboard_modular/services/runtime_lock_service.py
- Pi face-recognition code / pi_app_patch
- Pi camera capture, recognition, training, API behavior, SFTP, import/export, login, and admin logic
```

---

## Latest patch: SAS v103 — Mouse Click Lock Fix

### Fixed
- Fixed the desktop-visible lock mode where the cursor was held in place but left/right mouse clicks could still reach Windows applications.
- Replaced the earlier mouse-hook implementation with a dedicated Windows low-level mouse-hook thread. The hook is now installed and pumped on the same thread, which is required for reliable `WH_MOUSE_LL` callback delivery.
- While **Disable Mouse When Locked** is enabled, SAS now suppresses mouse movement, left/right/middle/X clicks, double-clicks, vertical/horizontal wheel actions, and keeps the cursor constrained.
- The emergency keyboard hotkey remains separate from the mouse lock and continues to be available.
- A standard user desktop should no longer accept mouse clicks while SAS is locked. Windows protected paths such as Ctrl+Alt+Del, UAC secure desktop, or other higher-privilege security screens remain controlled by Windows.

### Files changed
```text
Modified: sas_dashboard_modular/services/runtime_lock_service.py
- Reworked global mouse-click suppression to use one dedicated hook/message-loop thread.
- Added correct 64-bit Win32 function signatures and clean hook shutdown logic.
- Kept cursor clipping and the existing emergency-hotkey logic.

Modified: README.md
- Added SAS v103 release notes and the changed-file list.
```

### Not changed
```text
- sas_dashboard_modular/dashboard.py
- sas_dashboard_modular/dialogs.py
- Raspberry Pi code / pi_app_patch
- Face-recognition API, SFTP, import/export, login, and admin logic
```

---

## Latest patch: SAS v102 — Desktop-Preserving Lock Notification

### Changed
- Removed the old full-screen **System Locked** modal overlay. SAS no longer darkens or blurs the dashboard during a lock.
- When an inactivity or manual lock occurs, SAS is minimized to the Windows taskbar instead of being restored or maximized.
- Added a small non-modal, bottom-right **SYSTEM LOCKED** desktop notification matching the requested dark notification-card design:
  - title: **SYSTEM LOCKED**
  - message: **Access Suspended. Scan Face To Unlock**
  - red lock/status visual
- The notification is top-level, always-on-top, and configured not to take keyboard focus. It does not open or activate the SAS dashboard.
- The normal Windows desktop and existing applications remain visible while locked. Existing SAS keyboard/mouse blocking and the emergency hotkey continue to operate according to the saved security settings.
- Replaced the lock emoji with a QPainter-drawn lock icon in the notification so older Windows systems do not depend on emoji font rendering.
- Removed the obsolete overlay-specific blur, dim background, manual override button, and old lock-dialog styles.

### Files updated
```text
sas_dashboard_modular/dashboard.py
sas_dashboard_modular/dialogs.py
sas_dashboard_modular/services/runtime_lock_service.py
README.md
```

`pi_app_patch` was not changed.

---

# Secure Access System Patch README

## Latest patch: SAS v101 — Train Automatically Ends Active SAS Capture

### Changed
- Clicking **Train** in the SAS Face Recognition tab now works even while a Pi capture is running.
- SAS automatically sends a capture-stop request, waits until the Raspberry Pi reports that capture has ended and the camera is released, then starts the Pi training job.
- This applies to both **manual capture** and **auto-capture** sessions started from SAS.
- The SAS video preview closes during the transition. The existing Pi recovery flow returns background recognition after the capture/training workflow, so the workstation can still unlock by face recognition.
- When Train ends an auto-capture session, SAS suppresses the separate Capture Complete popup and continues directly to the training popup instead.
- If capture cannot stop in time, training is not started and SAS shows a training failure rather than attempting two Pi camera processes at once.

### Files Updated
```text
sas_dashboard_modular/dashboard.py
README.md
```

`pi_app_patch` was **not** changed.

---

## Latest patch: SAS v100 — Training Modal Layout Restore

### Changed
- Restored the **Training in Progress** modal to the centred v98 layout and original in-progress height.
- Completion now expands only after training finishes. The green **DONE** ring is placed with equal space between the green recognition-status block and the **PROCESSING DATASET** card.
- Removed the geometry-based completion flip animation that could override the Qt layout and make the DONE ring overlap the dataset card.

### Files Updated
```text
sas_dashboard_modular/dialogs.py
README.md
```

`pi_app_patch` was **not** changed.

---

## Latest patch: SAS v99 — Training Completion and Import Card Positioning

### Changed
- Increased the Training popup height and adjusted its content alignment so the completed green **DONE** ring sits higher with clear space above the **PROCESSING DATASET** card.
- Moved the **Import Face Data** transfer card upward by 24 pixels without changing Export or other card dialogs. This keeps the taller import ZIP-list layout more visible on typical laptop screens.

### Files Updated
```text
sas_dashboard_modular/dialogs.py
sas_dashboard_modular/dashboard.py
README.md
```

`pi_app_patch` was **not** changed.

---

## Latest patch: SAS v98 — Training Dialog Launch Fix

### Fixed
- Fixed the SAS **Train** button opening no dialog. `TrainingProgressDialog` created `self.title_label` but then attempted to add an undefined `title` variable to its layout. This raised a runtime `NameError` before the Pi training API was called.
- The training modal now opens correctly, shows the indeterminate loading spinner, and proceeds to call the Pi `/train` endpoint.

### Files Updated
```text
sas_dashboard_modular/dialogs.py
README.md
```

`pi_app_patch` was **not** changed.

---

## Latest patch: SAS v97 — Login Popup Restore and Blur Safety Fix

### Fixed
- Restored the Login popup title widget in `sas_dashboard_modular/dialogs.py`. A v96 training-popup UI edit accidentally referenced a training-dialog title variable inside `LoginPopupDialog`, causing the login dialog to fail during construction.
- Fixed the restricted **Face Recognition** and **Settings** flow: clicking either tab now opens the Login popup instead of leaving the dashboard blurred.
- Made `open_login_popup()` build the dialog before applying the blur effect. If a future dialog construction error occurs, the dashboard remains usable and logs `LOGIN_POPUP_ERROR` instead of staying blurred.

### Files Updated
```text
sas_dashboard_modular/dialogs.py
sas_dashboard_modular/dashboard.py
README.md
```

`pi_app_patch` was **not** changed.

---

## Latest patch: SAS v95 — Training Spinner + Clear Image Results

### Changed
- Replaced the SAS Training popup percentage ring with an **indeterminate loading spinner**. The modal no longer shows a percentage that can look stuck while the Pi is processing images.
- The Pi still sends real training status: SAS now shows useful text such as **images checked**, **skipped images**, and the current training stage.
- Training now reports separate results instead of treating every captured file as a successful trained face:
  - total dataset images scanned
  - new images checked
  - valid face images added to the model
  - already-trained images not reprocessed
  - images skipped because they did not produce exactly one usable face encoding
- Example: if 10 captured images are new but one image has no clear single face, SAS now reports **10 checked, 9 valid trained, 1 skipped**. This explains why the former popup could show 9 even after capturing 10 photos.
- New-image detection remains path-based: `trained_files` stores values such as `ntid/image_0.jpg`. Existing paths are skipped without loading/encoding their image data. If someone replaces an image while keeping the exact same file name, it is still treated as already trained; a later hash/modified-time enhancement would be needed to detect replacements.

### Files changed
```text
sas_dashboard_modular/dashboard.py
sas_dashboard_modular/dialogs.py
pi_app_patch/gui.py
pi_app_patch/face_api.py
pi_app_patch/train.py
README.md
```

### Raspberry Pi deployment
Replace these Pi files together, then restart the Pi Face Recognition application/API:
```text
pi_app_patch/gui.py
pi_app_patch/face_api.py
pi_app_patch/train.py
```

---

## Latest patch: SAS v94 — Background Recognition During Training + Real Progress

### Changed
- **Training no longer stops the Raspberry Pi recognition camera.** Training reads stored dataset images and rebuilds `encodings.pickle`; it does not use Picamera2.
- **Pi-local Train and SAS Train now use the same behavior:** existing face recognition remains active while training runs, so workstation unlock is still available.
- **Newly trained faces become available without reopening the camera.** `train.py` writes the updated encoding file atomically, and `recog.py` detects the completed replacement and reloads the model in memory while recognition continues.
- **Capture behavior remains different by design:** Capture must stop recognition because both workflows need the same Pi camera. After capture completes or is stopped through SAS, recognition resumes as before.
- The SAS Training modal now receives **real progress** from the Pi: processed image count, total new-image count, current stage, and a percentage that reaches 100% only after the updated model is saved successfully.
- Removed the old decorative training timer that advanced to 92% regardless of real Pi progress.
- During Pi-local training, Capture/Train/Delete are disabled and the Stop button is temporarily disabled so a user cannot interrupt recognition halfway through the training operation.

### Files changed
```text
sas_dashboard_modular/dashboard.py
sas_dashboard_modular/dialogs.py
pi_app_patch/gui.py
pi_app_patch/face_api.py
pi_app_patch/train.py
pi_app_patch/recog.py
README.md
```

### Raspberry Pi deployment
Replace these Pi files together, then restart the Pi Face Recognition application/API:
```text
pi_app_patch/gui.py
pi_app_patch/face_api.py
pi_app_patch/train.py
pi_app_patch/recog.py
```

---

## Latest patch: SAS v93 — Unified Pi Camera Workflow

### Fixed
- **Train from Pi or SAS now follows the same Pi-controlled workflow:** stop recognition, wait for PiCamera2 to release, train the dataset, then restart background recognition automatically.
- **Capture from Pi or SAS now follows the same workflow:** stop recognition, start capture, then restart background recognition after auto-capture completes or a capture STOP ends the capture session.
- SAS now asks the Pi `/train` endpoint to manage its own camera transition instead of performing a separate competing stop sequence first.
- The Pi API now exposes asynchronous training state (`training_state`, `last_training_id`, result/error fields) from the actual FaceService used by Flask, so SAS can detect real completion instead of leaving the training dialog in progress.
- SAS waits for Pi recognition to be running again after automatic capture before showing a completed capture result.
- Capture and training remain mutually exclusive; neither can start while the other is active.
- A full/manual Pi stop remains available through the full `/stop` endpoint and cancels planned recognition recovery.

### Files changed
```text
sas_dashboard_modular/dashboard.py
pi_app_patch/gui.py
pi_app_patch/face_service.py
pi_app_patch/face_api.py
README.md
```

### Raspberry Pi deployment
Replace these Pi files together, then restart the Pi Face Recognition app/API:
```text
pi_app_patch/gui.py
pi_app_patch/face_service.py
pi_app_patch/face_api.py
```

---

## Latest patch: SAS v90 — Stable Pi UI + SAS-Managed Capture Recovery

### Fixed
- Restored the Raspberry Pi `gui.py`, `face_api.py`, and `face_service.py` files to the known-working v88 set after the v89 Pi-side recovery change caused the Pi GUI not to appear in deployment.
- SAS STOP during normal recognition closes only the SAS Windows preview. The Pi recognition process continues for workstation unlock.
- SAS STOP during capture sends `POST /stop-capture`, waits for capture to end, then retries `POST /start-recognition` until the Pi reports background recognition is running.
- The SAS preview remains closed after stopping a capture. Recognition returns on the Pi automatically for unlock; the user presses Recognize only when they want to reopen the Windows preview.
- The Recognize button remains disabled during capture as introduced in v87/v88.

### Files changed
```text
sas_dashboard_modular/dashboard.py
pi_app_patch/gui.py              (restored to stable v88 version)
pi_app_patch/face_api.py         (restored to stable v88 version)
pi_app_patch/face_service.py     (restored to stable v88 version)
README.md
```

### Raspberry Pi deployment
Replace the three files below together on the Pi, then restart the Pi Face Recognition app:
```text
pi_app_patch/gui.py
pi_app_patch/face_api.py
pi_app_patch/face_service.py
```

---


## Latest patch: SAS v89 — SAS Preview Stop + Automatic Pi Recognition Recovery

### Changed
- **STOP in SAS during normal recognition now closes only the SAS Windows video preview.** The Raspberry Pi continues recognizing faces in the background, so the workstation can still unlock.
- **STOP in SAS during capture now stops the Pi capture process only** and waits for the Pi camera to release safely. The Pi then restarts recognition automatically in the background.
- The SAS video preview stays closed after capture stop/completion. Users press **Recognize** only when they want to view the Pi camera feed again.
- Capture and recognition remain mutually exclusive: the SAS **Recognize** button stays disabled while capture is active.
- Added Pi API endpoint: `POST /stop-capture-resume-recognition`. This endpoint is used only by SAS during a capture; Pi-local Stop remains a true stop and does not auto-restart recognition.
- Fixed a SAS status-refresh callback that referenced an unset `status` variable after an action error.

### Files changed
```text
sas_dashboard_modular/dashboard.py
pi_app_patch/face_api.py
pi_app_patch/face_service.py
pi_app_patch/gui.py
README.md
```

### Raspberry Pi patch
`pi_app_patch` was updated. Deploy `face_api.py`, `face_service.py`, and `gui.py` to the Raspberry Pi together, then restart the Pi Face Recognition application/API.

---

## Latest patch: SAS v88 — Disabled Recognize Button Visibility

### Changed
- The **Recognize** button now uses a clear grey background, grey text, and grey border whenever it is disabled during capture or while capture is stopping.
- This makes the disabled state visibly different from the normal green Recognize button.

### Files changed
```text
sas_dashboard_modular/dashboard.py
README.md
```

### Raspberry Pi patch
No Raspberry Pi file was changed in v88.

---

## Latest patch: SAS v87 — Capture / Recognition Safety

### Fixed
- Pressing **STOP** in the SAS Face Recognition tab now sends all compatible Pi stop requests (`/stop-capture`, `/stop-recognition`, and `/stop`) and waits for Pi `/status` to confirm that both capture and recognition have ended.
- Fixed the Pi received-data watcher: it previously scheduled the boot auto-recognition routine every 15 seconds, which could restart the Pi camera after the user pressed Stop. Recognition is now scheduled only once during Pi startup, and a Stop request cancels any delayed boot auto-start.
- A user-initiated Stop no longer starts recognition automatically after a manual capture. The Pi camera remains stopped until the user explicitly presses **Recognize**.
- The SAS **Recognize** button is greyed out immediately when capture starts and remains disabled while capture is active or stopping.
- Added a second safety guard so a queued Recognize click is rejected while capture is still active.
- Recognition-start errors caused by a busy Pi camera are now checked against Pi `/status` instead of being incorrectly treated as a Pi disconnection.
- Automatic capture completion now leaves the camera stopped and asks the user to press **Recognize** manually when ready.

### Files changed
```text
sas_dashboard_modular/dashboard.py
pi_app_patch/gui.py
README.md
```

### Raspberry Pi patch
`pi_app_patch/gui.py` was updated. The Pi now schedules boot recognition only once and does not restart recognition from the repeating received-data watcher after a user presses Stop.

---


## Current version: v175

### Main changes in v175

Fixed received ZIP Accept/Reject behaviour and refined the SAS pending received card.

Changes:
- Pi Check Received Accept now delegates to the FaceService accept logic, which merges the ZIP using the same add-new-only import behaviour and then moves the ZIP into `received_face_data/accepted`.
- Pi Check Received Reject now delegates to the FaceService reject logic and moves the ZIP into `received_face_data/rejected`.
- Pi Check Received badge refreshes after Accept or Reject.
- SAS Pending Received popup keeps the in-app card behaviour and uses blur behind the card.
- SAS received ZIP list now shows filename rows only, with a cleaner blue row style and admin-management-style thin scrollbar.
- SAS Accept/Reject still calls the Pi received-data API so the final merge/reject action is handled by the Pi app service.

Files changed in v175:

```text
sas_dashboard_modular/dashboard.py
pi_app_patch/gui.py
README.md
```

`pi_app_patch` was updated in v175.

---

### Main changes in v149

Fixed temporary "Not Responding" after pressing Save Connect.

Cause:
- Save Connect validation already ran in a worker thread.
- But after validation succeeded, SAS called Pi `/settings` sync on the UI thread.
- If the Pi was slow/offline, the Windows UI could freeze until the HTTP request finished or timed out.

Fix:
- Pi settings sync now runs asynchronously in a worker thread.
- UI is updated through `qt_after(...)`.
- Save Connect button temporarily shows `Saving...` and is disabled during validation.
- After local server credentials are saved, the success popup appears without waiting for slow Pi sync.
- Pi sync status updates separately:
  - `Pi sync: Syncing...`
  - `Pi sync: Enabled/Disabled`
  - or `Pi sync: Failed`

Files changed in v149:

```text
sas_dashboard_modular/dashboard.py
```

No Raspberry Pi file changes are needed for v149.

---

## Previous patch notes

consolidated


### README_v100_smooth_user_card_actions.txt

SAS v100 Smooth User Card Actions

Fixes:
- Expanded user card no longer clips the Delete button.
- Removed "Secure Biometric Verification Active" footer.
- Expand/collapse animation now animates both minimumHeight and maximumHeight.
- This makes it smoother in both minimised and maximised windows.
- Capture/Delete still work and still log QUICK_CAPTURE / QUICK_DELETE.
- Expanding a card still does not write USER_CARD into System Log.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v101_user_card_border_text_cleanup.txt

SAS v101 User Card Border + Text Cleanup

Changes:
- User card border changed to lighter grey.
- Expanded/hover border is lighter and less harsh.
- Delete button border made visually consistent with the upper card border.
- Removed small icons beside Capture and Delete.
- "DELETE ACCOUNT" changed to "DELETE USER".

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v102_face_user_scroll_paint_fix.txt

SAS v102 Face User Scroll/Paint Fix

Fixes:
- After pressing Recognize and scrolling the Authorized Users panel,
  user cards no longer become blank/ghost blocks.
- Removed row opacity fade effects from the Face Recognition user panel.
- User rows now use fixed vertical size policy so they do not stretch into large blanks.
- Refresh after Recognize preserves current scroll position instead of forcing list to top.
- Expand/collapse card animation remains.
- No Pi file changes needed.

File changed:
- sas_dashboard_modular/dashboard.py

---

### README_v103_delete_button_bottom_border_fix.txt

SAS v103 Delete Button Bottom Border Fix

Fix:
- In minimised window, the DELETE USER button bottom border was clipped/eaten.
- Increased expanded user card height slightly.
- Added bottom breathing space in the actions area.
- Slightly increased DELETE USER button height.
- Kept the expanded card smooth animation and existing behaviour.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v104_user_card_hover_fill_no_border.txt

SAS v104 User Card Hover Fill No Border

Changes:
- User cards have no visible border initially.
- Hover changes the card colour to a soft text-field-like grey.
- Expanded/selected card uses the same soft grey colour.
- Transparent border is kept only to prevent layout shift, but it is not visible.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v105_import_add_on_mode.txt

SAS v105 Import Add-On Mode

Change:
- Import no longer skips existing users.
- Existing IDs are updated in add-on mode:
  - additional dataset images are copied into the existing user folder
  - filename conflicts are safely renamed
  - incoming encodings are appended to encodings.pickle
  - new users are still created normally
- Windows SAS import UI wording changed:
  - removed skip/no-new-user wording
  - success screen shows merged users
  - loading text says merging/adding encodings
- Pi GUI import wording changed:
  - existing IDs are updated instead of skipped

Files changed:
- sas_dashboard_modular/dashboard.py
- pi_app_patch/face_service.py
- pi_app_patch/gui.py

Pi update required:
- face_service.py
- gui.py
Then restart the Pi app/API.

No face_api.py change required.

---

### README_v106_admin_management_absolute_path_fix.txt

SAS v106 Admin Management Fix

Encoding import note:
- v105 add-on import already appends incoming encodings into encodings.pickle.
- Existing users are not skipped; their new images and encodings are added.

Admin Management fix:
- ADMIN_FILE now points to sas_dashboard_modular/admins.txt using an absolute path.
- This fixes the issue where the app was launched from another working directory and read a different/empty admins.txt.
- AdminService now creates the parent folder if needed and reads UTF-8-SIG to handle BOM.
- Settings tab refreshes Admin Management whenever opened.
- Admin list scroll remains.

Files changed:
- sas_dashboard_modular/app_config.py
- sas_dashboard_modular/services/admin_service.py
- sas_dashboard_modular/dashboard.py

No Pi file changes for admin management.
Pi import add-on changes from v105 still require:
- pi_app_patch/face_service.py
- pi_app_patch/gui.py

---

### README_v107_import_add_new_only_dedupe.txt

SAS v107 Import Add-New-Only Dedupe

Change:
- Existing users are not skipped.
- But identical pictures are not imported again.
- Import now uses SHA256 image hashing per user:
  if the imported image content already exists in that user's dataset, it is ignored.
- New images are copied safely; filename conflicts are renamed.
- Encodings are also deduplicated:
  - if trained_files aligns with encodings, only encodings for newly copied images are added
  - encoding vectors are also hashed to prevent duplicates
- Result:
  importing the same 60 pictures again will NOT become 120 duplicate pictures.
  only truly new pictures and their corresponding encodings are added.

Files changed:
- pi_app_patch/face_service.py
- pi_app_patch/gui.py
- sas_dashboard_modular/dashboard.py

Pi update required:
- face_service.py
- gui.py
Then restart the Pi app/API.

No face_api.py change required.

---

### README_v108_admin_row_fixed_height.txt

SAS v108 Admin Row Fixed Height

Fix:
- Admin Management rows no longer stretch when there are only 1-2 admins.
- Row height stays fixed whether there are 2 admins or 10 admins.
- Added bottom stretch after admin rows so empty space stays below the rows.
- Admin list scrollbar geometry is stable and still invisible.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v109_unlock_recognition_saslog_fix.txt

SAS v109 Unlock + recognition_result.json + SAS_LOG Fix

Critical fix:
- v106 changed RECOGNITION_RESULT_FILE to an absolute local app path.
- That caused SAS to read:
    sas_dashboard_modular/recognition_result.json
  instead of:
    <configured server path>/recognition_result.json
- v109 fixes this. recognition_result.json is again read from the configured server path.

Recognition reader improved:
- Always joins server_path + basename("recognition_result.json")
- Supports UTF-8-SIG JSON
- Supports timestamp formats:
  YYYY-MM-DD HH:MM:SS
  YYYY-MM-DDTHH:MM:SS
  fractional seconds / ISO
- Supports confidence as number or "78.5%"

SAS_LOG fixed:
- Face unlock writes local and server SAS_LOG.
- Emergency unlock now also writes SAS_LOG:
    UNLOCKED | USER=EMERGENCY | METHOD=EMERGENCY_HOTKEY | CONFIDENCE=N/A
- Manual unlock now also writes SAS_LOG.
- Server SAS_LOG uses current self.server_path and falls back to credential.txt server path.

Files changed:
- sas_dashboard_modular/app_config.py
- sas_dashboard_modular/services/recognition_state_service.py
- sas_dashboard_modular/services/runtime_lock_service.py
- sas_dashboard_modular/dashboard.py

No Pi file changes needed for this fix.

---

### README_v110_pi_settings_hostname_ip.txt

SAS v110 Pi Settings Hostname/IP Display

Change:
- Pi app Settings popup now shows a new card above Server Credentials:
  Pi Network Identity
- It displays:
  - Hostname
  - IP Address
  - API URL
  - API Port 5000
- Each important value has a Copy button.
- This helps Windows SAS users know what to enter for Pi Hostname/IP.
- The app gets IP using hostname -I first, then socket fallback.

File changed:
- pi_app_patch/gui.py

Pi update required:
- gui.py

No Windows SAS file changes needed.

---

### README_v111_startup_pi_status_sync.txt

SAS v111 Startup Pi Status Sync

Fix:
- When the app starts and Pi is already reachable, the Settings > Pi Connectivity status now updates to Connected automatically.
- Background /users refresh now also updates:
  - pi_connected = True
  - pi_connection_checked = True
  - Status: Connected
- If background refresh fails, status becomes Disconnected.
- If Settings page is opened after connection is already true, it initially shows Connected instead of Disconnected/Checking.
- Connect button still works as manual retry.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v112_pi_auto_start_recognition.txt

SAS v112 Pi Auto Start Recognition

Change:
- When the Pi GUI starts, it automatically triggers the same logic as pressing the Recognise button.
- This works with Raspberry Pi desktop autostart:
  1. Pi powers on
  2. Desktop autostarts gui.py
  3. GUI waits about 2.5 seconds
  4. Recognition starts automatically

File changed:
- pi_app_patch/gui.py

Pi update required:
- gui.py

No Windows SAS file changes needed.

Note:
- The delay is intentional so the GUI, camera, and API have time to initialise after boot.
- If recognition is already running or capture is running, it will not start another recognition process.

---

### README_v113_sas_pi_disconnect_freeze_fix.txt

SAS v113 Pi Disconnect Freeze Fix

Problem fixed:
- When SAS is connected to Pi and recognition/video-feed is running, powering off the Pi could make the whole SAS app freeze / Not Responding.
- Cause: OpenCV VideoCapture.read() for the MJPEG stream was running in the Qt UI thread and could block when the Pi disappeared.

Changes:
- Moved Pi camera MJPEG reading into a background worker thread.
- UI thread only renders frames; it no longer blocks on VideoCapture.read().
- If Pi camera feed is lost:
  - preview stops
  - Pi status becomes Disconnected
  - Face Recognition controls are disabled
  - authorised users list is cleared
  - popup prompts user: Pi disconnected, please check Pi
  - returns user to Settings after popup closes
- Recognize start failure also triggers the disconnect popup.
- Background user refresh failure can also trigger disconnect handling if the Pi was previously connected.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v114_camera_feed_not_api_disconnect.txt

SAS v114 Camera Feed Not API Disconnect Fix

Problem:
- After Settings showed Pi Connected, opening Face Recognition could mark the Pi as Disconnected.
- Authorised users could still appear in Face Recognition, but Dashboard showed Disconnected/empty.
- Cause: v113 treated /video-feed failure as full Pi disconnection.
  But /video-feed can be unavailable/stopped even when the Pi API is online.

Fix:
- Added handle_camera_feed_unavailable().
- If /video-feed fails, SAS now checks /status first:
  - If /status works:
      Pi remains Connected
      Face controls stay enabled
      user list/dashboard refreshes
      camera panel shows stopped/unavailable
  - If /status fails:
      Pi is treated as truly disconnected
      popup asks user to check Pi
      user returns to Settings
- Opening Face Recognition no longer clears Dashboard users just because camera feed is stopped.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v115_camera_feed_time_import_fix.txt

SAS v115 Camera Feed time import fix

Fix:
- v113/v114 moved camera feed reading into a background thread.
- That new camera worker uses time.sleep().
- dashboard.py was missing import time.
- This caused:
    CAMERA_FEED_UNAVAILABLE: Pi camera feed error: name 'time' is not defined | API online
- Added import time to dashboard.py.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v116_login_placeholder_generic.txt

SAS v116 Login Placeholder Generic

Change:
- Login NTID placeholder changed from:
    e.g. 4372447
  to:
    e.g. 1234567

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v117_login_placeholder_full_fix.txt

SAS v117 Login Placeholder Full Fix

Fix:
- v116 changed the placeholder in dashboard.py only.
- The login popup also uses sas_dashboard_modular/dialogs.py, which still had:
    e.g. 4372447
- v117 changes both locations to:
    e.g. 1234567

Files changed:
- sas_dashboard_modular/dashboard.py
- sas_dashboard_modular/dialogs.py

No Pi file changes needed.

---

### README_v118_connect_success_camera_state_reset.txt

SAS v118 Connect Success Camera State Reset

Problem:
- Settings could connect successfully, but when opening Face Recognition,
  the camera panel still showed the old "Pi disconnected" message.
- This happened because a previous disconnect state was not cleared after reconnect.
- Face Recognition tab also did not always refresh the camera state on entry.

Fix:
- On successful Settings connection:
  - pi_connected remains True
  - _camera_user_stopped is reset
  - old disconnect handling flag is reset
  - camera panel is updated immediately:
      if Pi recognition/capture running -> show video feed
      else -> show normal "Camera stopped" prompt
- When opening Face Recognition tab:
  - refresh authorised users
  - check /status
  - show video feed if recognition is running
  - otherwise show "Camera stopped", not "Pi disconnected"
- Preserves v115 import time fix.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v119_camera_feed_retry_stable.txt

SAS v119 Camera Feed Retry Stability Fix

Problem:
- SAS connected to /video-feed, then immediately showed:
    CAMERA_FEED_UNAVAILABLE: Pi camera feed lost. | API online
- Pressing Recognize again fixed it.
- Cause:
  The new background camera worker was too strict. A few failed OpenCV reads
  during Pi camera/video-feed warm-up were treated as feed unavailable.

Fix:
- Camera worker now retries longer before declaring feed unavailable.
- It attempts to reconnect the MJPEG stream up to 3 times.
- It waits briefly before opening /video-feed after Recognize or /status says recognition is running.
- This preserves the no-freeze protection while avoiding false camera-feed failures.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v120_unified_dashboard_ui.txt

SAS v120 Unified Dashboard UI

Changes:
- Dashboard now uses one large unified status card instead of three separate cards.
- Uses uploaded locked/unlocked UI concept:
  - large central card
  - green unlocked state
  - red locked state
  - circle countdown remains
  - face-detected flip animation remains
- Manual Lock button keeps existing toggle_lock_state() function.
- Authorised Users button opens the existing View All authorised users popup.
- Dashboard removed the separate Authorised Users card.
- Menu title changed from SECURE ACCESS to SECURE ACCESS SYSTEM.
- Clock date removed GLOBAL NODE 01.
- Footer behaviour:
  - Dashboard: server path only
  - Face Recognition: footer hidden
  - Settings: server path, state file, lock time interval
  - removed © 2026 SECURE ACCESS SYSTEM text from footer.

Files changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v121_unified_dashboard_wide_card_flip_fix.txt

SAS v121 Unified Dashboard Wide Card + Flip Fix

Fixes after v120:
- Dashboard unified card changed from tall/square card to long landscape card.
- Restored circle size to the previous 168px/126px behaviour so the flip stays smooth and round.
- Added direct circular stylesheet for face-detected circle to avoid square-to-circle flip artefact.
- Reduced spacing and button widths to match the provided long-card concept.
- Fixed menu title clipping by giving SECURE ACCESS SYSTEM enough width and reducing font size.
- Date still has GLOBAL NODE 01 removed.
- Footer rules from v120 preserved:
  Dashboard = server path only
  Face Recognition = hidden footer
  Settings = full footer without copyright text.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v122_fullscreen_dashboard_responsive.txt

SAS v122 Fullscreen Startup + Responsive Dashboard

Changes:
- App now opens maximized automatically at startup.
- Dashboard uses more available fullscreen space.
- Unified dashboard card becomes wider and taller on laptop/monitor fullscreen.
- Reduced top dashboard padding so the card sits closer to the clock.
- Content maximum width now scales with window width.
- Dashboard footer server-path strip widened slightly.
- Menu title width increased and font reduced slightly so SECURE ACCESS SYSTEM does not clip.

Notes:
- Uses showMaximized(), not borderless showFullScreen(), so Windows title bar remains available.
- Existing functions remain unchanged:
  Manual Lock, Authorised Users popup, countdown, flip animation, recognition polling.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v123_dynamic_fill_dashboard.txt

SAS v123 Dynamic Fullscreen Dashboard Fill

Fixes:
- Dashboard now dynamically enlarges to fill more fullscreen space on both laptop and external monitor.
- Card width/height now scale based on current window size instead of small fixed caps.
- Clock scales larger on large monitors.
- Reduced wasted empty space between dashboard card and footer.
- App still opens maximized on startup, but minimise/restore behaviour is kept.
- Fixed header title clipping:
  SECURE ACCESS SYSTEM now has a wider left header zone and smaller stable title font.
- Footer behaviour preserved:
  Dashboard: server path only
  Face Recognition: footer hidden
  Settings: server path, state file, lock time interval.

Files changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v124_scaled_dashboard_content.txt

SAS v124 Scaled Dashboard Content

Changes:
- Dashboard card continues filling fullscreen space dynamically.
- Content inside the green/red card now scales with card size:
  - countdown circle grows with the card
  - countdown number grows with the circle
  - title and protocol label grow with the card
  - action buttons grow with the card
  - description text grows with the card
- Clock/time zone scales larger on external monitors.
- Progress ring stroke now scales with circle size and uses white/translucent-white ring styling.
- Header title SECURE ACCESS SYSTEM still preserved with wider brand area.

Files changed:
- sas_dashboard_modular/dashboard.py
- sas_dashboard_modular/ui_components.py

No Pi file changes needed.

---

### README_v125_dashboard_overlap_face_circle_fix.txt

SAS v125 Dashboard Overlap + Face Circle Fix

Fixes:
- Increased the Dashboard clock/date section height and spacing.
- Added top padding for the date text to prevent overlap under large clock sizes.
- Slightly reduced largest clock sizes only to avoid text collision while keeping monitor view large.
- Face-detected circle content now scales with the Dashboard card:
  - face icon enlarges with the circle
  - FACE DETECTED label enlarges with the circle
- Removed the dark green border line from the face-detected circle.
- Face-detected circle now uses a soft translucent fill only.

Files changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v126_face_detected_block_color_fix.txt

SAS v126 Face Detected Block Colour Fix

Fix:
- The block behind the face icon and FACE DETECTED text now uses the same translucent colour as the face circle background.
- Removed the visually different rectangle colour effect.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v127_face_detected_transparent_blocks_border.txt

SAS v127 Face Detected Transparent Blocks + Border

Fix:
- Removed the different colour blocks behind the face icon and FACE DETECTED text.
- The icon and text backgrounds are now transparent, so they match the circle background.
- Added a light border line around the face-detected circle.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v128_dashboard_clock_spacing_fix.txt

SAS v128 Dashboard Clock Spacing Fix

Fix:
- Increased Dashboard time section height on fullscreen/monitor view.
- Added more spacing between the clock/date and the green Dashboard card.
- Slightly reduced only the largest monitor clock size to prevent bottom clipping.
- Added safe bottom padding to the clock label.
- Date now has more top padding below the clock.

Result:
- Clock bottom should show completely.
- Dashboard card is moved down slightly.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v129_clock_clipping_real_fix.txt

SAS v129 Clock Clipping Real Fix

Fix:
- v128 made the clock/date area worse because padding was used on the large clock label.
- This version removes the padding method and gives the clock QLabel a real dynamic height.
- Time section height now adjusts based on the actual clock/date font size.
- The large monitor clock size is slightly reduced only enough to prevent bottom clipping.
- The extra gap between clock and card is reduced again.
- Dashboard card remains large and dynamic.
- Time/date labels have transparent background and no border.

Files changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v130_face_recognition_2x2_layout.txt

SAS v130 Face Recognition 2 x 2 Layout

Change:
- Redesigned Face Recognition tab layout to 2 x 2:
    [ Camera Panel     ][ System Log       ]
    [ Primary Controls ][ Authorised Users ]

Function preserved:
- Camera preview / Recognize flow unchanged.
- System Log function unchanged.
- Capture / Train / Recognize / Stop / Delete buttons unchanged.
- Authorised Users search, refresh, scroll, expand, Capture/Delete functions unchanged.
- Only layout and responsive sizing changed.

Files changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v131_face_recognition_equal_2x2.txt

SAS v131 Face Recognition Equal 2 x 2 Layout

Change:
- Face Recognition tab remains 2 x 2:
    [ Camera Panel     ][ System Log       ]
    [ Primary Controls ][ Authorised Users ]

- All four cards are now equal size.
- Camera panel is no longer longer/taller than the others.
- Grid rows and columns now use equal stretch.
- Camera preview height is constrained to fit inside the equal card.

Function preserved:
- Camera preview / Recognize flow unchanged.
- System Log unchanged.
- Primary Controls unchanged.
- Authorised Users unchanged.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v132_camera_view_fit_panel.txt

SAS v132 Camera View Fit Panel

Change:
- Face Recognition remains equal 2 x 2.
- Camera preview now uses more of the camera panel space.
- Reduced camera panel internal padding and badge row space.
- Camera image still keeps aspect ratio:
  - no stretching
  - no distortion
  - no ratio modification
- Scaling quality changed to SmoothTransformation.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v133_face_camera_taller_controls_shorter.txt

SAS v133 Face Recognition Camera Taller / Controls Shorter

Change:
- Face Recognition remains 2 x 2:
    [ Camera Panel     ][ System Log       ]
    [ Primary Controls ][ Authorised Users ]

- Top row is now taller:
    Camera Panel and System Log have more height.

- Bottom row is now shorter:
    Primary Controls and Authorised Users no longer waste large empty vertical space.

- Camera preview uses more of the taller camera panel while keeping aspect ratio.
- Primary Controls internal spacing reduced and empty bottom stretch removed.

Functions preserved:
- Camera preview / Recognize flow unchanged.
- System Log unchanged.
- Capture / Train / Recognize / Stop / Delete unchanged.
- Authorised Users unchanged.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v134_face_layout_swap_reduce_space.txt

SAS v134 Face Recognition Layout Swap + Reduced Space

Change:
- Face Recognition tab layout changed to:
    [ Camera Panel     ][ Authorised Users ]
    [ Primary Controls ][ System Log       ]

- Reduced large empty space under the menu bar.
- Grid spacing reduced slightly.
- Uses more available vertical screen space.
- Top row is taller for Camera and Authorised Users.
- Bottom row is shorter for Primary Controls and System Log.
- System Log padding reduced slightly to fit better in bottom-right panel.

Functions preserved:
- Camera preview / Recognize flow unchanged.
- Capture / Train / Recognize / Stop / Delete unchanged.
- Authorised Users search, refresh, scroll, expand, Capture/Delete unchanged.
- System Log behaviour unchanged.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v34_manual_capture.txt

SAS v34 Manual Capture Update

Windows SAS:
- Use sas_dashboard_modular/ as the updated Windows app.

Raspberry Pi:
- Copy files from pi_app_patch/ into the Raspberry Pi FaceRecognition folder:
  capture.py
  face_api.py
  face_service.py
  gui.py
  recog.py
  train.py

Important new API:
- POST /capture-user with auto_capture=true/false
- POST /capture-photo for one manual photo when auto_capture=false

Behaviour:
- Auto-Capture Enabled:
  Capture starts and Pi automatically captures photos.
  When complete, SAS shows Capture Complete and starts Recognize.

- Auto-Capture Disabled:
  Capture starts manual mode.
  Capture button changes to TAKE PHOTO.
  Each TAKE PHOTO click requests one photo.
  Press STOP when finished.
  SAS shows Capture Complete and starts Recognize.

---

### README_v36_auto_capture_logic_fix.txt

SAS v36 Auto-Capture Logic Fix

Main fixes:
1. Removed the Auto-Capture 'Pi sync:' UI line.
2. Fixed Pi bool parsing bug:
   bool("False") is True in Python, so string false could still run auto-capture.
3. Pi reloads settings.json before capture, so changes apply immediately without Pi restart.
4. SAS pulls /settings from Pi when entering Face Recognition/Settings and before capture.
5. If user changes Auto-Capture directly on Pi, SAS toggle updates to match Pi state.

Manual mode:
- Auto-Capture Disabled
- Press Capture
- Button changes to TAKE PHOTO
- Click TAKE PHOTO for each image
- Press Stop when finished

---

### README_v37_disconnect_and_pi_settings_reload.txt

SAS v37 fixes

Windows SAS fixes:
1. Fixed NameError when Pi is offline:
   cannot access free variable 'e'
2. Pi Connectivity now changes to Disconnected when /status fails.
3. Camera panel stops/blackens when Pi is offline.

Raspberry Pi fixes:
1. Pi Settings popup now reloads settings.json every time it is opened.
2. If Windows SAS changes auto_capture through /settings, Pi runtime state updates immediately.
3. When Pi Settings is opened after SAS changed auto_capture, the checkbox reflects the latest settings.json.
4. /settings GET reloads settings.json before returning, so SAS gets the latest state.

Update instructions:
- Use sas_dashboard_modular/ for Windows SAS.
- Copy pi_app_patch/*.py into the Pi FaceRecognition folder if you want the Pi-side fixes.

---

### README_v51_import_export_cards.txt

SAS v51 Import/Export Cards

Windows SAS:
- Export and Import buttons now open card-style popups.
- Server path copy icon copies the path to clipboard.
- Export uses Pi API /face-data/export.
- Import uses Pi API /face-data/list-server-zips to load server ZIP files, supports search, then calls /face-data/import.

Pi changes are included in pi_app_patch:
- face_api.py adds POST /face-data/list-server-zips
- gui.py adds API helper methods:
  export_face_data_to_folder
  list_server_face_data_zips
  import_face_data_from_zip

You need to copy the updated pi_app_patch files to the Raspberry Pi manually for the new import list function to work.

---

### README_v52_import_export_validation.txt

SAS v52 Import/Export Validation Fix

Windows SAS changes:
- Import/Export NTID field is editable.
- Password and Server Path are editable.
- Server Path icon now opens a folder picker and writes selected path into the field.
- Export validates NTID/password/server path before running.
- Import Connect validates NTID/password/server path before loading ZIP files.
- Import list fetches only valid SAS export ZIP files.

Pi changes:
- face_api.py: /face-data/export and /face-data/list-server-zips now accept username/password/pc_save_path payload.
- gui.py: API helpers now use payload credentials instead of only stored settings.json.
- gui.py: list_server_face_data_zips filters only face_data_backup_*.zip and validates encodings.pickle inside ZIP.

IMPORTANT:
If Pi still returns 501 NOT IMPLEMENTED for /face-data/list-server-zips, it means the Pi is still using the old face_api.py.
Copy pi_app_patch/face_api.py and pi_app_patch/gui.py to the Pi and restart the Pi app/API.

---

### README_v53_FACE_SERVICE_IMPORT_EXPORT_FIX.txt

SAS v53 Pi FaceService import/export fix

Reason for previous 500 error:
- The Pi API is started with self.face_service, not the Tkinter GUI object.
- v52 added export/list helper methods to gui.py, but /face-data/export calls methods on face_service.py.
- Therefore /face-data/export could throw INTERNAL SERVER ERROR or the list route could be unavailable/not implemented.

Files to update on Raspberry Pi:
1. face_api.py
2. face_service.py

gui.py does not need to be updated for this specific fix if you already updated it before, but copying the whole pi_app_patch is also safe.

After copying, restart the Pi Face Recognition app/API.

New/changed API:
- POST /face-data/export accepts username/password/pc_save_path
- POST /face-data/list-server-zips accepts username/password/pc_save_path
- face_service.py now implements export_face_data_to_folder and list_server_face_data_zips

---

### README_v67_import_loading_success_users.txt

SAS v67 Import Loading/Success Card

Windows SAS:
- Import button now changes the same popup into a loading card.
- Loading uses the same circular spinner style as Pi Connectivity / Export.
- Import success uses the provided success-card style.
- Success displays imported users:
  - shows all if <= 5
  - shows first 5 + count if many users
  - shows "No New Users Imported" if backup contains only existing users.

Pi changes:
- pi_app_patch/gui.py changed.
- import_face_data_from_zip now returns imported_users, skipped_users_count, and previews.
- Copy gui.py to the Pi and restart the Pi app/API to see imported user names in the SAS popup.

---

### README_v70_import_deleted_user_fix.txt

SAS v70 Import Deleted User Fix

Problem:
- If a user was deleted from the Pi UI/dataset folder but the old ID still existed in encodings.pickle,
  import could wrongly show "No New Users Imported".

Fix:
- Pi import now treats dataset folders as the main source of truth for whether a user exists.
- If a deleted user still exists inside encodings.pickle, stale encodings/trained_files for that ID are removed before re-importing.
- Re-importing a deleted user from backup should now work.

Pi file changed:
- pi_app_patch/gui.py

Copy gui.py to the Pi and restart the Pi app/API.

---

### README_v71_import_face_service_fix.txt

SAS v71 Import FaceService Fix

Problem:
- The Pi API may call FaceService.import_face_data_from_zip(), not GUI.import_face_data_from_zip().
- FaceService previously returned added_ids, but Windows SAS only looked for imported_users.
- This could make SAS show "No New Users Imported" even when FaceService imported a deleted user.

Fix:
Windows SAS:
- Import success now accepts imported_users, added_ids, or imported_ids list.

Pi FaceService:
- Import uses dataset folders as source of truth.
- Stale encodings for re-imported deleted users are removed first.
- Returns imported_users/add_ids/skipped counts to SAS.

Update required:
1. Windows SAS: use this package version.
2. Pi: copy pi_app_patch/face_service.py to Raspberry Pi.
3. Recommended also copy pi_app_patch/gui.py.
4. Restart the Pi app/API.

---

### README_v82_full_pi_settings_sync.txt

SAS v82 Full Pi Settings Sync

Windows SAS:
- Save & Connect sends username, password, pc_save_path, auto_capture and recognition_result metadata to Pi /settings.
- Logs PI_SETTINGS_SYNC with state file name.

Pi FaceService:
- POST /settings now mounts the SMB path first.
- If mount succeeds, it writes settings.json with:
  username, encrypted password, pc_save_path, auto_capture, recognition_result_file, server_mount_point, last_synced_from, last_synced_at.
- Updates runtime FaceService + GUI auto_capture/path state without restarting.
- Resets recognition_result.json locally and at /mnt/pcshare/recognition_result.json so Windows SAS does not read stale unlock data.

Pi GUI:
- Opening Settings reloads settings.json each time.
- Auto-Capture toggle and server credentials/path display follow latest settings.json.
- Pi GUI Save also writes the same metadata keys.

Update required on Pi:
- pi_app_patch/face_service.py
- pi_app_patch/gui.py

Windows:
- Use this SAS package version.

---

### README_v83_bidirectional_settings_sync.txt

SAS v83 Bidirectional Pi Settings Sync

Fix:
- Previously SAS Save & Connect pushed settings to Pi correctly.
- But Pi Settings changes only updated Pi settings.json and SAS only pulled auto_capture.
- Now SAS pulls full Pi settings back into its Settings UI.

Windows SAS:
- New pull_pi_settings_to_sas().
- When Settings tab opens, SAS calls GET /settings?include_password=true.
- Updates SAS Settings fields:
  NTID, password, server path, auto_capture.
- Saves pulled values into Windows credential.txt too.
- Connect success also pulls full Pi settings.

Pi API:
- GET /settings supports include_password=true.

Pi FaceService:
- get_settings(include_password=True) decrypts password for Windows SAS pull.
- Default GET /settings still hides password.

Update required on Pi:
- pi_app_patch/face_api.py
- pi_app_patch/face_service.py

Windows:
- Use this SAS package version.

---

### README_v84_pi_log_folder.txt

SAS v84 Pi Log Folder

Change:
- Pi recognition server logs are no longer written directly to the root server path.
- They are written to:
    <server path>/Pi_LOG/YYYY-MM-DD.log

Example:
    //mypenm0vdspc16/internship/Gary LIm/Pi_LOG/2026-05-26.log

If Pi_LOG does not exist, recog.py creates it automatically.

Pi file changed:
- pi_app_patch/recog.py

Update this file on the Pi and restart recognition/Pi app.

---

### README_v85_sas_log_local_and_server.txt

SAS v85 SAS_LOG Local + Server

Change:
- Windows SAS unlock log now writes to both:
  1. Local app folder:
     sas_dashboard_modular/SAS_LOG/YYYY-MM-DD.txt
  2. Configured server path:
     <server path>/SAS_LOG/YYYY-MM-DD.txt

Rule preserved:
- SAS_LOG only stores UNLOCKED events.
- Dashboard/settings/system messages are not stored in SAS_LOG.

Existing related Pi log behaviour:
- Pi recognition logs are written to:
  <server path>/Pi_LOG/YYYY-MM-DD.log

Files changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed for this update.

---

### README_v86_settings_textfield_thin_font.txt

SAS v86 Settings Text Field Thin Font

Change:
- Settings page QLineEdit text fields now use thinner font weight.
- Settings readonly box text also uses thinner font weight.
- Buttons are not changed.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v87_authorized_users_popup_ux_animation.txt

SAS v87 Authorized Users Popup UX Animation

Changes:
- View All popup now fades in smoothly.
- Card gently slides/lifts into position.
- User rows animate in one by one.
- Search result count updates live, e.g. "2 / 5 MATCHED".
- Search box has built-in clear button.
- Added small avatar circle for each user row.
- Row hover now highlights subtly in green.
- Close round button hover improved.
- Buttons outside this popup are not changed.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v88_fix_authorized_popup_and_transfer_fonts.txt

SAS v88 Fix Authorized Popup + Transfer Field Fonts

Fix:
- Removed the unstable row height/slide animation from Authorized Users popup.
- Kept safe fade animation only.
- Rows now render normally from the top again.
- Popup fade-in remains smooth.

Also:
- Import/Export popup text-field content uses thinner font.
- SFTP text-field content also uses thinner font.
- Buttons are not changed.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v89_authorized_popup_hover_disappear_fix.txt

SAS v89 Authorized Users Popup Hover Disappear Fix

Problem:
- User rows could disappear or jump when hovering/searching inside the View All popup.
- Cause: row-level QGraphicsOpacityEffect animation conflicted with QScrollArea hover repaint/layout.

Fix:
- Removed row opacity/height animations completely.
- Kept popup fade-in only.
- Rows now render normally and remain visible on hover.
- Hover is now a safe subtle background only.
- Text labels use transparent background.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v90_authorized_popup_search_scroll_sequence.txt

SAS v90 Authorized Users Popup Search/Scroll/Sequence Fix

Fixes:
- Search results no longer leave old stale rows behind.
- The count now matches the visible result list.
- The round number on the left is now the row sequence number:
  1, 2, 3, 4, 5...
  instead of the first digit of the NTID.
- The popup scroll area supports large user lists, including 100+ users.
- After searching/filtering, the scroll position resets to the top.

Cause:
- deleteLater() is deferred in Qt, so old rows could visually remain briefly
  after filtering. The popup now hides and detaches old rows immediately.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v91_authorized_popup_stale_row_fix.txt

SAS v91 Authorized Users Popup Stale Row Fix

Problem:
- During search, old rows could remain visible until clicking again.
- Cause: Qt deleteLater() is deferred, so the old row could still be painted in the scroll viewport.

Fix:
- On every search render, the popup now replaces the whole QScrollArea widget/body.
- Old body is hidden and detached immediately before deleteLater().
- Viewport is explicitly refreshed.
- Scroll resets to top after every search.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v92_authorized_popup_scroll_six_fix.txt

SAS v92 Authorized Users Popup Stable Scroll Fix

Fix:
- View All popup opens again.
- Popup size is fixed; it will not enlarge.
- The visible list area shows up to 6 users.
- If there are more than 6 users, the list scrolls inside the popup.
- Search no longer leaves stale users visible.
- Left number uses visible sequence 1,2,3... after filtering.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v93_face_system_log_scroll_all_actions.txt

SAS v93 Face Recognition System Log Scroll + Action Status

Fix:
- Face Recognition SYSTEM LOG is now a scrollable area.
- Keeps up to 120 Face Recognition log lines.
- Automatically scrolls to the latest action/status.
- Shows action status for capture, train, recognise, stop, delete, users refresh,
  connection, camera feed, import/export, SFTP, received data and errors.
- Added explicit log messages when user presses Capture, Train, Recognize, Stop and Delete.
- Dashboard/settings/general logs remain terminal-only; the visible section focuses on Face Recognition.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v94_face_user_quick_actions.txt

SAS v94 Face User Row Quick Actions

Change:
- In Face Recognition authorised users panel, each user row is clickable.
- Clicking a user opens a submenu directly under the row.
- Submenu contains:
  - Capture
  - Delete
- Capture/Delete automatically fill the NTID into Primary Controls first,
  then run the existing capture/delete logic.
- Only one submenu stays open at a time.
- Face System Log records USER_MENU, QUICK_CAPTURE and QUICK_DELETE events.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v95_face_users_expanding_cards.txt

SAS v95 Face Recognition User Panel Expanding Cards

Change:
- Face Recognition authorised users panel now uses expandable cards.
- Click a user card to enlarge it.
- Capture/Delete buttons appear inside the enlarged card.
- Added search bar inside the panel.
- User list is scrollable for large lists, including 100+ users.
- Search works with expandable cards.
- After search, clicking a user still expands and shows Capture/Delete.
- User rows fade in safely like the View All popup style, without popup.
- Capture/Delete actions still reuse existing NTID validation and Pi API logic.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v96_fit_layout_user_cards.txt

SAS v96 Fit Layout + User Card Colour Fix

Changes:
- Reduced camera panel height.
- Reduced Primary Controls and System Log lower card height.
- Right Authorized Users panel has tighter padding.
- User cards are smaller so Capture/Delete fit inside the panel.
- User list still scrolls for 100+ users.
- User cards are no longer blue-tinted:
  default = same white/panel feel
  selected/expanded = slight grey
- Shortened card detail text to avoid clipping, e.g. "52 frames".
- Buttons inside expanded user card are smaller.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v97_responsive_face_layout_fit.txt

SAS v97 Responsive Face Layout Fit

Fixes:
- Authorised Users panel is wider.
- Left camera/primary/system-log section is reduced to help the user panel fit.
- Camera panel height reduced.
- Primary Controls and System Log height adjusted so buttons no longer overlap in minimised window.
- User cards are more compact and use a width-friendly layout.
- User card colour:
  default = same white/panel tone
  expanded = slight grey
- Capture/Delete inside expanded user card are shorter and fit within the panel.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v98_maximize_camera_height.txt

SAS v98 Maximize Camera Height

Change:
- In maximised / large screen mode, camera panel height is increased again.
- Normal/minimised mode keeps compact layout so Primary Controls buttons do not overlap.
- Authorised Users panel width changes from v97 remain.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_v99_user_card_ui_no_expand_log.txt

SAS v99 User Card UI + No Expand Log

Changes:
- Face Recognition user expanded card now follows the uploaded UI concept:
  - NTID Identifier style
  - soft TRAINED/PENDING status badge
  - capture frame line
  - full-width + Capture button
  - full-width Delete Account button
  - small secure verification footer
- Expand/collapse animation is smoother.
- Expanding a user card no longer writes USER_CARD into System Log.
- Capture/Delete still log QUICK_CAPTURE / QUICK_DELETE and reuse existing Pi API logic.

File changed:
- sas_dashboard_modular/dashboard.py

No Pi file changes needed.

---

### README_START_HERE.md

# Start Here - SAS Dashboard Modular Version

## 1. Folder structure

```text
sas_dashboard_modular/
│
├── main.py
├── dashboard.py
├── dialogs.py
├── ui_components.py
├── app_config.py
└── services/
    ├── admin_service.py
    ├── credential_service.py
    ├── ad_service.py
    ├── face_api_service.py
    ├── recognition_state_service.py
    └── runtime_lock_service.py
```

## 2. How to run

Open PowerShell inside this folder:

```powershell
cd "sas_dashboard_modular"
python main.py
```

If `python` is not recognised, use your full Python path:

```powershell
C:\Users\4372447\AppData\Local\Programs\Python\Python314\python.exe main.py
```

## 3. Where to edit now

### UI / Layout
Edit:

```text
dashboard.py
dialogs.py
ui_components.py
```

### Logic copied from lockapp.py
Edit:

```text
services/
```

## 4. What has already been moved from lockapp.py

### Admin logic
`services/admin_service.py`

- ensure admins.txt exists
- load admins
- save admin
- first login becomes admin
- check admin login

### Credential logic
`services/credential_service.py`

- read credential.txt
- save credential.txt

### Active Directory / SOAP logic
`services/ad_service.py`

- validate NTID exists
- encrypt password
- validate NTID + password
- validation with debug steps

### Raspberry Pi API logic
`services/face_api_service.py`

- test connection
- capture user
- train
- get result
- stop recognition
- delete user
- refresh users

### Recognition result JSON logic
`services/recognition_state_service.py`

- read recognition_result.json
- check detected/user_id/confidence/timestamp
- validate scan freshness

### Runtime lock logic
`services/runtime_lock_service.py`

- grant access
- lock system
- update face detected state from recognition result

## 5. Next function to migrate from lockapp.py

The next major logic to move is:

```text
_start_auto_scan()
_auto_scan_loop()
_get_idle_secs()
_poll_system_idle()
_apply_lock_controls()
_register_emergency_hotkey()
_disable_keyboard()
_enable_keyboard()
_disable_mouse()
_enable_mouse()
```

These should be added to:

```text
services/runtime_lock_service.py
```

Do not put new backend logic directly inside `dashboard.py` anymore.


## Basic runtime functions added in this version

- Settings Server Credentials now validates NTID + password before saving.
- Browse button now opens a folder picker for the server path.
- Security Options are loaded/saved to `credential.txt`.
- Inactivity lock time is loaded/saved and applied to the countdown timer.
- Server path is used for `recognition_result.json`.
- Server path is used to write logs under `SAS_LOG/YYYY-MM-DD.txt`.
- If `recognition_result.json` is valid/detected, the dashboard unlocks green and the countdown circle flips to Face Detected.
- If the face is no longer detected, the UI stays unlocked while countdown runs.
- If countdown reaches `00:00`, the dashboard locks red and stays at `00:00` until a valid face is detected again.

---
---

## v153_face_tab_spacing_readme

Date: 2026-06-05

### Update summary

- Adjusted the Face Recognition tab responsive width calculation.
- Added a safer right-side padding clamp so the camera panel and System Log stay inside the page spacing.
- Reduced the maximum right-column width on wide screens to prevent the camera/log area from touching or exceeding the right edge.
- Kept the existing Face Recognition functions and animations unchanged.

### Changed files

```text
sas_dashboard_modular/dashboard.py
README.md
```

### Raspberry Pi app patch status

```text
pi_app_patch was not updated in this version.
```

---

## v154_dashboard_status_card_footer_ui

Date: 2026-06-05

### Update summary

- Removed the `PROTOCOL STATUS` label from the Dashboard status card.
- Changed the Dashboard `AUTHORIZED USERS` action from a large rectangular button into a small floating round icon button at the bottom-left of the green/red status card.
- Kept the existing Authorised Users popup function connected to the new icon button.
- Made the `Active session expires soon` message larger and bold for better visibility.
- Updated the footer strip sizing so its width follows the visible footer content instead of staying at a large fixed length.

### Changed files

```text
sas_dashboard_modular/dashboard.py
README.md
```

### Raspberry Pi app patch status

```text
pi_app_patch was not updated in this version.
```

---

## v155_transfer_to_windows_sftp_pull

Date: 2026-06-05

### Update summary

- Added a new `Transfer to Windows` action under the Face Data Transfer SFTP section.
- Kept the existing `Send to Another Pi` SFTP push function unchanged for Pi-to-Pi transfer.
- Added a new card-style SFTP popup using the same visual style as the existing transfer popup.
- Implemented Windows transfer as SFTP pull mode: SAS on Windows connects to the Raspberry Pi SSH/SFTP server, downloads the prepared face-data ZIP, and saves it into the selected Windows folder.
- Windows does not need OpenSSH Server for this new pull mode; the Raspberry Pi must have SSH Server enabled.
- Added a Raspberry Pi API route to prepare a temporary ZIP package for SFTP download.

### Changed files

```text
sas_dashboard_modular/dashboard.py
pi_app_patch/face_api.py
pi_app_patch/face_service.py
README.md
```

### Raspberry Pi app patch status

```text
pi_app_patch was updated in this version.
```



## v156_transfer_to_windows_backend_pi_credentials

- Updated the Transfer to Windows popup so users no longer enter Raspberry Pi SSH credentials.
- Pi SFTP username/password are treated as backend/build configuration (`SAS_PI_SFTP_USERNAME`, `SAS_PI_SFTP_PASSWORD`, `SAS_PI_SFTP_PORT`).
- Transfer to Windows remains SFTP pull mode: SAS downloads the prepared ZIP from the connected Pi SSH/SFTP server.
- The popup now asks for Windows username/password and a Windows save folder only.
- Windows save folder supports local paths such as `C:\JE_SFTP` and SMB/UNC paths such as `\\server\share\folder`.
- For SMB/UNC paths, SAS attempts a `net use` session with the supplied Windows credentials before saving.
- `pi_app_patch` was not changed in v156; the Pi-side prepare-download API added in v155 remains the same.
- The Windows SAS build still needs the `paramiko` package included because SAS performs the SFTP pull download.

---

## v157_transfer_to_windows_hostname_password

Date: 2026-06-05

### Update summary

- Updated `Transfer to Windows` SFTP pull mode so SAS uses the currently connected Pi automatically.
- SAS now uses the connected Pi hostname/IP from Settings as the SFTP host.
- Pi SFTP username remains backend-configured with default `jbl_facerec` or `SAS_PI_SFTP_USERNAME`.
- Pi SFTP password is now derived from the connected Pi hostname, based on the project rule: `hostname = password`.
- SAS first attempts to fetch the Pi hostname from the connected Pi `/status` API, then falls back to reverse DNS, then the host/IP entered in Settings.
- Removed the previous requirement for backend `SAS_PI_SFTP_PASSWORD` for Transfer to Windows.
- The user still only enters Windows Username/NTID, Windows Password, and Windows Save Folder in the popup.
- Added `hostname` and `device_name` fields to the Pi `/status` API response so SAS can resolve the correct hostname even when the user connects by IP.

### Changed files

```text
sas_dashboard_modular/dashboard.py
sas_dashboard_modular/app_config.py
pi_app_patch/face_api.py
README.md
```

### Raspberry Pi app patch status

```text
pi_app_patch was updated in this version.
```


## v158 - Transfer to Windows uses fetched Pi username

- Added Pi `/status` fields for `system_user` and `ssh_username`.
- Pi Connectivity now displays Hostname, IP/Host, and Username after connection.
- Transfer to Windows no longer uses hostname as the Pi SFTP password.
- SAS now fetches the connected Pi username from `/status` and uses `username = password` for the SFTP pull login.
- User still only enters Windows Username/NTID, Windows Password, and Windows Save Folder.
- `pi_app_patch` was updated in this version.

---

## v159 - Pi Settings username display and setup scroll fix

- Updated the Raspberry Pi app Settings popup to show the Linux/SFTP username in the Pi Network Identity section.
- Pi Network Identity now displays Hostname, Username, IP Address, API URL, and API Port with copy buttons.
- The displayed Username is fetched from the Linux user running the Pi app and is intended for SAS Transfer to Windows SFTP pull logic.
- Fixed the Settings popup scroll binding so the popup can scroll even when the user has not logged in yet.
- `pi_app_patch` was updated in this version.

## v160 - Pi Settings Transfer to Windows Section
- Added a logged-in Pi Settings section/button for **Transfer to Windows**.
- Pi GUI now shows a same-style popup explaining Windows SAS SFTP pull mode.
- Popup displays Pi Hostname, IP Address, SFTP Username, password rule, and API URL.
- Added **Prepare ZIP** action in the Pi popup for manual verification of the Windows download package.
- Added **Copy Info** action for copying Pi transfer information.
- Existing Send to Another Pi and Check Received functions are unchanged.

## v161 - Remove Pi Settings Transfer to Windows Button

- Removed the **Transfer to Windows** button from the Raspberry Pi app Settings screen.
- Removed the Pi-side Transfer to Windows information popup and related UI function from `pi_app_patch/gui.py`.
- Kept the SAS Dashboard **Transfer to Windows** SFTP pull feature unchanged.
- `pi_app_patch` was updated in this version.

## v162 - Hide SAS Pi Connectivity Identity Summary Line

- Removed the visible connected Pi identity summary line from the SAS Dashboard Pi Connectivity card.
- The Pi Connectivity card now keeps only the input field, Connect button, and connection status message.
- Internal Pi hostname/IP/username values are still retained for Transfer to Windows SFTP pull logic.
- `pi_app_patch` was not updated in this version.


## v163 - Windows-style inactivity lock countdown

- Updated SAS auto-lock behaviour to follow Windows screen-saver style inactivity logic.
- The countdown now starts/reduces only when there is no keyboard or mouse activity.
- Mouse movement, mouse clicks, wheel scrolling, keyboard typing, and touch events reset the countdown while SAS is unlocked.
- Face not detected no longer starts the countdown.
- SAS now polls `recognition_result.json` only after the system is already locked.
- After a valid recognition result is found while locked, SAS unlocks and resets the inactivity countdown.
- Auto-lock log message now says the system locked because keyboard and mouse were inactive.
- `pi_app_patch` was not updated in this version.

## v164 - Remove startup and logout forced lock

- SAS no longer starts in locked mode when the application opens.
- Logging out no longer immediately locks the dashboard.
- After logout, SAS returns to the normal Dashboard screen in an unlocked state.
- Auto-lock still works later through the inactivity countdown only.
- Manual Lock button behaviour is unchanged.
- `pi_app_patch` was not updated in this version.


## v165 - Built-in hardcoded admin login

- Added a built-in local admin login account for SAS.
- Login ID: `admin`
- Password: `penAteam`
- This account bypasses Active Directory validation and logs in directly as Admin.
- Existing AD login and first-valid-AD-login-becomes-admin logic remain unchanged for normal users.
- The hardcoded account can also be overridden by environment variables `SAS_HARDCODED_ADMIN_ID` and `SAS_HARDCODED_ADMIN_PASSWORD` if needed.
- `pi_app_patch` was not updated in this version.


## v166 - Match Transfer to Windows ZIP filename with server export

- Updated the Raspberry Pi SFTP download preparation package name used by SAS **Transfer to Windows**.
- Transfer to Windows now creates ZIP files using the same naming pattern as **Export to Server Path**: `face_data_backup_YYYYMMDD_HHMMSS.zip`.
- The transfer method remains SFTP pull from the connected Raspberry Pi to the Windows SAS laptop.
- `pi_app_patch` was updated in this version.

## v167 - Import/Export tab restructure and local ZIP import

- Renamed the Server Path panel title to `Import and Export Data`.
- Updated Export popup to include two tabs:
  - `Server Path` for existing export-to-server-path flow.
  - `Download Dataset (SFTP)` for Windows SFTP pull download.
- Removed the visible `Transfer to Windows` button from the separate SFTP transfer panel.
- Kept `Send to Another Pi` and `Check Received` in the SFTP panel.
- Updated Import popup to include two tabs:
  - `Server Path` for existing server ZIP list/import flow.
  - `Local ZIP` for importing a ZIP that was downloaded to Windows by SFTP.
- Added local ZIP import flow: SAS validates Windows credentials, uploads the selected ZIP to the connected Pi by SFTP, then calls the Pi import API.
- Added Pi API endpoint `/face-data/sftp-import-target` so SAS can upload local ZIP files to the correct Pi temp import folder.
- `pi_app_patch` was updated in this version because the Pi API and service now expose the SFTP import target folder.


## v168_runtime_stylesheet_fix
- Fixed SAS startup crash caused by malformed stylesheet braces in the new Import/Export tab button CSS.
- Resolved `NameError: name 'background' is not defined` during `apply_styles()`.
- No Pi app logic changes were made in this version.

## v169 - Snake animation tabs for Import and Export popups

- Updated the Export Face Data popup tab control to use the same Auto-Capture-style snake sliding animation.
- Updated the Import Face Data popup tab control to use the same Auto-Capture-style snake sliding animation.
- Replaced the previous static tab buttons with a reusable `TransferSnakeTabs` control.
- Existing export/import/server path/SFTP/local ZIP functions are unchanged.
- `pi_app_patch` was not updated in this version.

## v170 - Safe worker callback shutdown fix

- Fixed a runtime crash where a background Pi status worker could call `qt_after()` after the SAS dashboard Qt signal bridge had already been deleted.
- The guard now skips late worker callbacks during application close/shutdown instead of raising `RuntimeError: Signal source has been deleted`.
- Existing Pi connectivity, Import/Export, SFTP, and snake-tab UI behaviour are unchanged.
- `pi_app_patch` was not updated in this version.

## v171 - Pi import wording and received pending list fix

- Updated Pi app import wording so it no longer says existing users are skipped.
- Import confirmation now explains the actual merge behaviour:
  - Existing users receive only new images/encodings.
  - Duplicate images/encodings are ignored.
  - No current user is deleted or replaced.
- Updated received dataset accept logic to use the same add-new-only merge import function.
- Fixed `Check Received` in the Pi app so manual checking shows all pending ZIP files in `received_face_data/pending`.
- The background received-data watcher still avoids repeated popups for the same file.
- `pi_app_patch` was updated in this version.

## v172 - Pi Check Received badge and desktop notification

- Added a red notification badge on the Pi app `Check Received` button.
- The badge shows the number of pending ZIP files in `received_face_data/pending`.
- The badge automatically hides when no pending ZIP files exist.
- The background received-data watcher now updates the badge count every scan.
- When new pending ZIP files are detected, the Pi app triggers a best-effort desktop/system notification and alert sound.
- Manual `Check Received` still opens the pending ZIP list for review, accept, or reject.
- Accepting or rejecting a received ZIP refreshes the badge count immediately.
- `pi_app_patch` was updated in this version.

## v173 - Received ZIP badge and SAS notification workflow

- Updated the Pi app `Check Received` behaviour:
  - Kept the red pending-count badge on the `Check Received` button.
  - Removed Pi-side sound and desktop/system notification for pending received ZIP files.
  - Updated the pending ZIP list popup to include direct `Accept`, `Reject`, and `Close` buttons.
- Updated the SAS Dashboard received-data workflow:
  - Added a red pending-count badge on the SAS `Check Received` button.
  - SAS polls the connected Pi `/face-data/received` endpoint for pending ZIP files.
  - SAS shows a desktop/system notification when new pending ZIP files are detected, where supported by the OS.
  - SAS opens a non-blocking popup when new pending ZIP files are detected.
  - The popup includes `Accept`, `Reject`, and `Close` buttons so users can decide later.
  - SAS accept/reject actions call the Pi API endpoints and refresh the badge count.
- `pi_app_patch` was updated in this version.

## v174 - Received ZIP accept/reject and notification UI fix

- Fixed SAS received-ZIP accept/reject API calls by sending the filename payload through the existing `payload` parameter instead of an unsupported `json` keyword.
- Fixed SAS pending ZIP parsing so only the ZIP filename is shown in the received-data list instead of the full metadata dictionary.
- Restyled the SAS pending received-data popup as a frameless in-app card based on the provided UI reference.
- Added a best-effort Windows toast notification path for new pending ZIP detection, with the existing tray message as fallback.
- Updated Pi reject behaviour so rejected received ZIP files are moved to `received_face_data/rejected` instead of being deleted.
- Pi Check Received badge refreshes after accept/reject actions.
- `pi_app_patch` was updated in this version.

## v176 - SAS received popup selection and import flow fix

- Updated the SAS pending received face data popup so normal ZIP rows are neutral and only the selected row is highlighted blue.
- Reduced received ZIP row height and limited the visible list to five files before scrolling.
- Updated the received ZIP list scrollbar to a thinner Admin Management-style scrollbar.
- When SAS accepts a pending received ZIP, the popup now switches into the same import progress/success UI used by the normal Import flow.
- Reject still moves the selected ZIP through the Pi API and refreshes the pending count/list.
- Added a slightly darker overlay behind card popups while preserving the blur effect so users can focus on the card.
- `pi_app_patch` was not updated in this version.

## v178 - Check Received Badge Alignment

- Aligned the SAS Check Received red badge vertically with the button label.
- Badge now stays on the right side of the button but no longer floats above the top edge.
- pi_app_patch was not updated in this version.

## v177 - SAS received popup search and manual selection fix

- Updated the SAS pending received face data popup so no ZIP file is selected by default when the popup opens.
- ZIP rows now become blue only after the user manually selects a file.
- Added a search bar to the SAS pending received popup, matching the Import popup search behaviour.
- Search filters pending ZIP filenames while keeping the clean in-card list style.
- The list remains fixed to five visible rows before scrolling when more files are available.
- Accept and Reject buttons are disabled until a ZIP file is selected.
- `pi_app_patch` was not updated in this version.

## v179 - Check Received badge startup position and circle fix

- Fixed the SAS `Check Received` badge starting on the left side during initial layout.
- Badge is now repositioned after the Qt layout pass and on button resize/show events.
- Single and double digit badge counts now use a true circular 22x22 badge.
- `99+` remains a small pill for readability.
- `pi_app_patch` was not updated in this version.


## v180 - Pylance warning cleanup for SAS dashboard
- Cleaned remaining SAS Dashboard Pylance issues shown in the diagnostics file.
- Cast QGraphicsBlurEffect before reading blurRadius.
- Guarded status-card style refresh so only QWidget instances are polished/unpolished.
- Guarded optional Dashboard user-status label before calling setText.
- Cast paramiko usage after availability checks so Transport/SFTPClient warnings are removed.
- Cast QApplication.instance() before using alert().
- pi_app_patch was not updated in this version.

SAS v181 Settings Tab Width/Padding Refinement
- Settings tab now uses a slightly narrower maximum content width than Dashboard/Face Recognition.
- Increased left/right page padding inside Settings so the cards and fields do not look too stretched on wide screens.
- Change is limited to the SAS Settings tab layout.
- pi_app_patch was not updated in this version.

## v182 - SAS notification identity and popup overlay cleanup

- Updated SAS received-file notification logic to avoid duplicate notifications where one appears as Python.
- SAS now sets the Windows AppUserModelID/application name to Secure Access System before showing notifications.
- Windows toast notification is preferred and Qt tray notification is only used as fallback.
- Fixed received-card popup cleanup so blur/dark overlay and disabled dashboard state are always cleared after Close, Accept, Reject, or window destruction.
- pi_app_patch was not updated in this version.

## v183 - Overlapping card overlay and notification cleanup

- Fixed the remaining dark/blur overlay issue when multiple card popups overlap.
- Card popups now use a shared overlay open-count so the dashboard is only cleared after the last active card closes.
- This specifically fixes the flow where Send via SFTP succeeds, Pending Received appears before the SFTP popup is closed, and the dashboard remains dark after closing both popups.
- Removed Qt tray notification fallback for SAS received-file alerts to prevent Windows notifications from appearing as Python during source/Python runs.
- SAS now only attempts the Windows toast notification path for received-file alerts.
- pi_app_patch was not updated in this version.

## v184 - SAS Logo / Window Icon Update
- Added uploaded SAS logo asset under `sas_dashboard_modular/assets/`.
- Applied SAS logo to the Qt application/window icon for the title bar and Windows taskbar.
- Updated Windows toast notification script to use the SAS logo as the app-logo image when supported.
- Removed `Enterprise Dashboard` from the native Windows title bar; title now shows `Secure Access System`.
- `pi_app_patch` was not updated in this version.


## v185 - Transparent SAS Logo Update
- Replaced the SAS logo assets with the new transparent-background logo provided by the user.
- Updated `sas_dashboard_modular/assets/sas_logo.png` and `sas_dashboard_modular/assets/sas_logo.ico`.
- Window title bar icon, taskbar icon, and notification icon sources now use the transparent logo asset.

## v186 - Pending Received Popup Close Button Cleanup
- Removed the bottom `CLOSE` button from the SAS Pending Received Face Data popup.
- The popup now uses only the top-right `X` close button.
- Accept and Reject behaviour is unchanged.


## v187 - Header Brand Logo
- Added the SAS transparent logo to the left side of the `SECURE ACCESS SYSTEM` text in the top navigation bar.
- Existing window/taskbar/notification logo assets are unchanged.
- `pi_app_patch` was not updated.

## v188 - Startup Taskbar Background Mode
- Added SAS background-running startup behaviour for configured workstations.
- If server credentials are configured and the Raspberry Pi API is connected, SAS automatically minimizes into the Windows taskbar after startup.
- If this is the first launch, configuration is missing, or the Pi is disconnected, SAS stays maximized and guides the user to Settings.
- Whenever SAS locks the workstation, the main window is restored/maximized automatically.
- After SAS unlocks from a valid `recognition_result.json` face result, the window minimizes back to the taskbar.
- Users can still click the Windows taskbar icon to restore the app manually for operation.
- `pi_app_patch` was not updated.

## v189 - SFTP Transfer Enter Key Fix
- Updated the SFTP Transfer popup so pressing Enter in Host, Port, Username, Password, or Receiver Project Folder triggers the `Transfer` button.
- Prevented the Cancel button from becoming the default Enter action.
- Mouse-click transfer behaviour is unchanged.
- `pi_app_patch` was not updated.

## v190 - SFTP Enter Key Uses Full Transfer Flow
- Pressing Enter in the SFTP Transfer popup now calls the same transfer handler as the `Transfer` button.
- The popup now shows the same sending/loading status when Enter is pressed.
- Enter no longer only closes the popup or skips the visual transfer progress.
- `pi_app_patch` was not updated.

## v191 - SFTP Enter Key Keeps Popup Open
- Fixed the SFTP Transfer popup closing when Enter is pressed.
- Enter is now intercepted by an event filter and routed to the same transfer workflow as the `Transfer` button.
- The popup remains open and shows the normal loading, success, or failure message.
- The Cancel button and top-right X still close the popup normally.
- `pi_app_patch` was not updated.

## v192 - Taskbar Icon Restore
- Fixed SAS disappearing from the Windows taskbar after automatic background minimize.
- The main SAS window is now forced to remain a normal Windows taskbar application window.
- Auto-background mode now minimizes to the taskbar, not to a hidden/tool-window state.
- Users can restore SAS by clicking the normal Windows taskbar icon.
- `pi_app_patch` was not updated.

## v193 - External SAS_Data Runtime Folder
- Added a user-facing `SAS_Data` folder beside `SAS.exe` when running as a PyInstaller EXE.
- Runtime files are no longer stored inside PyInstaller `_internal`.
- EXE mode now reads/writes these files outside `_internal`:
  - `SAS_Data/admins.txt`
  - `SAS_Data/users.txt`
  - `SAS_Data/credential.txt`
  - `SAS_Data/unlock_log.txt`
  - `SAS_Data/SAS_LOG/`
- Source-code mode keeps the existing project-folder behaviour for developer testing.
- `pi_app_patch` was not updated.

## v196 - Pi Disconnect No Auto-Lock and Retry Warning
- When the Raspberry Pi is disconnected, SAS now suspends inactivity auto-lock.
- This prevents a user from being locked when `recognition_result.json` cannot be updated by the Pi.
- SAS keeps retrying the Pi API connection automatically while disconnected.
- If the admin/user closes the Pi disconnected popup while the Pi is still offline, the popup will show again.
- When the Pi reconnects, SAS resumes normal inactivity lock behaviour.
- `pi_app_patch` was not updated.

## v197 - Context-Aware Pi Disconnected Popup
- Improved the Pi disconnected popup behaviour.
- If the user is already in the Settings tab, automatic retry checks will not keep opening popups and blocking typing.
- In Settings, the popup/result is shown only when the user manually presses Connect.
- If SAS is minimized/background or the user is on another tab/application, Pi disconnect will restore/maximize SAS and show the disconnected warning.
- Duplicate disconnected popups are prevented when one is already visible.
- If the user closes the disconnected popup, SAS switches to Settings and continues retrying in the background without immediately reopening the popup.
- Inactivity auto-lock remains suspended while Pi is disconnected.
- `pi_app_patch` was not updated.

## v198 - Pi Disconnect Popup Return-to-Settings Flow
- Removed the close/cross button from the Pi disconnected popup.
- User should use `Return to Settings` as the only popup action.
- `Return to Settings` restores/maximizes SAS and opens the Settings tab.
- SAS no longer repeatedly maximizes itself when it is already maximized.
- If SAS is already visible, the disconnected popup appears without unnecessary maximize calls.
- If SAS is minimized/background, the warning flow still allows the user to return to Settings.
- Inactivity auto-lock remains suspended while Pi is disconnected.
- `pi_app_patch` was not updated.

## v199 - Return to Settings Restore Fix
- Fixed Pi disconnected popup `Return to Settings` action when SAS is minimized/background.
- Clicking `Return to Settings` now force-restores the main SAS window, maximizes it, brings it forward, and switches to Settings.
- The popup action button is now wired by scanning the dialog buttons, so it works even if the internal button attribute name is different.
- After the main window is restored and Settings is opened, the disconnected popup closes.
- `pi_app_patch` was not updated.

## v200 - Single Pi Disconnect Popup
- Removed the duplicate/old Pi disconnect failed-dialog path that could still show a close button.
- Pi disconnect now uses only one no-close popup with `Return to Settings`.
- Any old connection dialog is closed before the no-close disconnect popup is created.
- Close, Cancel, and X buttons inside the disconnect dialog are hidden/disabled.
- `Return to Settings` remains the only user action for the Pi disconnect warning.
- `pi_app_patch` was not updated.

## v201 - Pi Disconnect Popup No Auto-Maximize / No Blur
- Fixed Pi disconnected popup automatically maximizing SAS before the user presses `Return to Settings`.
- Fixed disconnect popup leaving SAS blurred/blocked so the user could not operate the app.
- Disconnect warning no longer steals focus or maximizes SAS automatically.
- SAS restores/maximizes and switches to Settings only after the user clicks `Return to Settings`.
- The disconnect popup remains no-close/no-X; `Return to Settings` is the intended action.
- Inactivity auto-lock remains suspended while Pi is disconnected.
- `pi_app_patch` was not updated.

## v202 - Final Pi Disconnect Popup Flow
- Rebuilt the Pi disconnected popup as a simple no-close, non-modal warning.
- Removed use of the old connection dialog for automatic Pi-disconnect warnings, preventing duplicate popups, blur overlay, and unexpected maximize behaviour.
- When SAS is minimized/background and Pi disconnects, the disconnect popup appears but SAS does not maximize automatically.
- SAS maximizes and switches to Settings only when the user clicks `Return to Settings`.
- When SAS is already visible/maximized, the popup behaves normally like the Face Recognition disconnected warning.
- Inactivity auto-lock remains suspended while Pi is disconnected.
- `pi_app_patch` was not updated.

## v203 - Restore Pi Disconnect Popup Visibility
- Fixed Pi disconnected popup not appearing after the v202 popup rewrite.
- Face Recognition tab disconnect warning is restored.
- If SAS is minimized/background, the disconnect popup is now created as a top-level window so it can appear.
- If SAS is already visible/maximized, the popup appears normally over SAS.
- Stale popup flags are now cleared when the previous dialog is no longer visible.
- The popup still has no X/Close button; `Return to Settings` is the intended action.
- Inactivity auto-lock remains suspended while Pi is disconnected.
- `pi_app_patch` was not updated.

## v204 - Restore Pi Disconnect Popup UI
- Restored the Pi disconnected popup to use the original working connection-dialog layout.
- Fixed the broken white-bar popup display from v202/v203.
- Kept the no-close behaviour by hiding/disable X, Close, and Cancel controls.
- `Return to Settings` remains the only visible action.
- SAS does not auto-maximize when Pi disconnects.
- SAS maximizes and opens Settings only after the user clicks `Return to Settings`.
- Startup background/minimize logic is unchanged.
- Inactivity auto-lock remains suspended while Pi is disconnected.
- `pi_app_patch` was not updated.

## v205 - Restore Startup Minimize and Suppress Settings Disconnect Popup
- Restored the startup background behaviour: if configuration is complete and Pi connection succeeds, SAS minimizes to the Windows taskbar/background.
- Automatic Pi-disconnect retry popups are now suppressed while the user is already in the Settings tab.
- This prevents the popup from blocking typing while the user edits the Pi hostname/IP.
- Manual Connect in Settings can still show a connection result when the user presses Connect.
- If the user is outside Settings or SAS is in background, the Pi disconnected warning can still appear.
- Inactivity auto-lock remains suspended while Pi is disconnected.
- `pi_app_patch` was not updated.

## v206 - Startup Minimize Even When Pi Disconnected + Settings Silent Retry
- Updated startup behaviour to match the requested flow:
  - If SAS configuration is complete, SAS minimizes/runs in background after startup even if the Pi is disconnected.
  - If the Pi is disconnected, the disconnect popup is still shown as the visible warning/action path.
  - First-launch or missing configuration still keeps SAS visible.
- Fixed Settings tab interruption:
  - Automatic retry popups are suppressed while the user is already in the Settings tab.
  - This allows the user to type/edit the Pi hostname/IP without repeated popups.
  - Manual Connect in Settings can still show a result once when the user presses Connect.
- Inactivity auto-lock remains suspended while Pi is disconnected.
- `pi_app_patch` was not updated.

## v207 - Restore v193 Startup Minimize Once Logic
- Restored the v193-style startup behaviour.
- SAS will only auto-minimize once during startup/background initialization.
- After the user manually restores/maximizes SAS, later Pi status checks, retry success, or Settings Connect actions will not minimize it again.
- Face-unlock behaviour is unchanged: after a valid unlock from `recognition_result.json`, SAS can minimize back to the taskbar.
- First launch or missing configuration still keeps SAS visible.
- Pi disconnect retry and Settings silent-popup logic from the recent versions is preserved.
- `pi_app_patch` was not updated.

## v208 - Config-Only Startup Minimize and Reliable Settings Popup Suppression
- Startup background mode now depends only on completed SAS configuration.
- SAS minimizes at startup once the app is configured; it no longer waits for the Pi connection result.
- If the Pi is disconnected, the disconnect popup/retry flow handles it separately.
- Improved Settings-tab detection using:
  - current tab name
  - active page widget
  - settings page dictionary fallback
  - focused Settings input widgets
  - visible Pi hostname input fallback
- Automatic Pi-disconnect retry popups are now suppressed while the user is in Settings, so typing hostname/IP is not interrupted.
- Manual Connect in Settings can still show one connection result popup.
- `pi_app_patch` was not updated.

## v209 - Restore Face Recognition Tab Disconnect Popup
- Fixed Face Recognition tab click not showing the Pi disconnected popup.
- Clicking Face Recognition while Pi is disconnected now bypasses automatic retry-popup suppression and shows the disconnect warning like before.
- Settings-tab automatic retry suppression remains unchanged.
- Startup config-only minimize logic remains unchanged.
- `pi_app_patch` was not updated.

## v210 - Single Startup Disconnect Popup
- Fixed duplicate Pi disconnected popups during startup.
- Added a strong duplicate guard so startup check and retry loop cannot open two popups at the same time.
- Startup disconnect popup is shown once; retry continues in the background.
- Settings-tab popup suppression remains unchanged.
- Config-only startup minimize logic remains unchanged.
- Face Recognition tab manual disconnect popup remains available.
- `pi_app_patch` was not updated.

## v211 - Show Disconnect Popup When Settings Was Minimized
- Updated Settings-tab suppression logic:
  - If SAS is visible and user is in Settings, automatic disconnect popups are still suppressed so typing is not interrupted.
  - If SAS is minimized/background, the disconnect popup is allowed even if the last active tab was Settings.
- When SAS is minimized/background, the disconnect popup is made top-level so it can appear without maximizing the SAS main window.
- Startup config-only minimize logic remains unchanged.
- Single startup disconnect popup guard remains unchanged.
- `pi_app_patch` was not updated.

## v212 - Disconnect Popup Card UI Fix
- Fixed Pi disconnected popup appearing as floating text over a blurred screen.
- Rebuilt the disconnect popup as a self-contained white card dialog with proper background, spacing, icon, details, and Return to Settings button.
- Kept existing logic unchanged:
  - visible Settings tab suppresses automatic popups
  - minimized/background Settings still allows the disconnect popup
  - no X/Close/Cancel button
  - Return to Settings is the only action
  - single startup popup guard remains active
- `pi_app_patch` was not updated.

## v213 - Restore Previous Disconnect Popup Card UI
- Restored the previous disconnect popup/card UI.
- Removed the custom v212 disconnect popup design.
- Removed the minimized-mode top-level/new-window popup behaviour.
- Disconnect popup again uses the existing connection-card style.
- No X/Close/Cancel button remains.
- Return to Settings remains the only action.
- Existing logic is preserved:
  - visible Settings tab suppresses automatic retry popups
  - startup config-only minimize logic
  - single startup popup guard
  - Face Recognition tab disconnect popup
- `pi_app_patch` was not updated.

## v214 - Settings Connect Failed Dialog Fix
- Fixed Settings tab Connect popup staying stuck at `Connecting...` when Pi connection fails.
- Manual Settings Connect now updates the existing progress dialog into the failed state instead of closing/replacing it.
- Failed Settings Connect shows the same no-close disconnect card with `Return to Settings`.
- Automatic Settings-tab retry popup suppression remains unchanged.
- Startup config-only minimize logic remains unchanged.
- `pi_app_patch` was not updated.

## v215 - Settings Connect Manual Failure Fix
- Fixed Settings `Connect` button calling the connection test without the manual failure-popup flag.
- Pressing `Connect` in Settings now uses `show_disconnect_popup=True`, `show_progress=True`, and `origin="settings"`.
- If Pi connection fails, the existing `Connecting...` popup changes to failed state with `Return to Settings`.
- Added a 10-second Settings Connect timeout guard so the popup cannot stay on `Connecting...` forever.
- Existing startup/config minimize and Settings automatic retry suppression logic remains unchanged.
- `pi_app_patch` was not updated.

## v216 - Stronger Mouse Disable During Lock
- Enhanced `Disable Mouse When Locked`.
- Cursor is now confined using Windows `ClipCursor` to a 1x1 point, making it feel more like the mouse is actually disabled.
- Cursor enforcement loop is faster, reducing the visible pull-back effect.
- Added a low-level Windows mouse hook to block mouse movement, click, double-click, wheel, and extra mouse button events while SAS is locked.
- Mouse hook and cursor clipping are released automatically when SAS unlocks.
- Existing startup, disconnect popup, Settings suppression, and Face Recognition logic remain unchanged.
- `pi_app_patch` was not updated.

## v217 - Pylance Cleanup and Origin Callback Runtime Fix
- Fixed runtime crash: `NameError: origin is not defined` inside the queued Pi connection callback.
- `_face_api_test_connection()` now stores `origin_safe` before worker callbacks use it.
- Cleaned overlay helper to avoid direct unknown-method Pylance warnings.
- Cleaned `setGraphicsEffect(None)` typing with `cast(QGraphicsEffect, None)`.
- Replaced direct dynamic dialog attribute assignment for `_sftp_enter_filter` with `setattr`.
- Added fallback for unbound SFTP status label references.
- Kept existing startup, disconnect popup, Settings suppression, Face Recognition, and stronger mouse-disable logic unchanged.
- `pi_app_patch` was not updated.

## v218 - User Testing Fixes
- Removed hardcoded/default personal NTID and server path from first-time Settings UI.
- Server Credentials now start blank for new users; saved values only appear after a valid save.
- Strengthened first-time Save Connect validation:
  - NTID must validate in AD.
  - Password must validate in AD.
  - Server path must exist and pass write-test.
  - `credential.txt` cannot be written unless the same Save Connect attempt passed validation.
- Fixed manual Settings Connect failure duplicate-popup behavior.
- Updated SFTP/Pi hostname example text away from `facerecognition`; neutral IP example is used instead.
- Existing startup, disconnect, Settings suppression, Face Recognition, and mouse-disable logic remain unchanged.
- `pi_app_patch` was not updated.

## v219 - Secure Server Credentials Display
- Security fix: SAS no longer auto-fills Server Credentials from the Pi API.
- Pi settings pull now uses `/settings` only and does not request `include_password=true`.
- NTID and password fields are cleared on Settings load.
- Pi API pull can still sync non-sensitive settings such as Auto Capture, but it will not display another user's NTID/password/server path.
- Server Credentials fields are blank for users unless they type their own values.
- First-time Save Connect validation from v218 remains active.
- Existing startup, disconnect popup, Settings suppression, Face Recognition, and mouse-disable logic remain unchanged.
- `pi_app_patch` was not updated.

## v220 - Block Transfer Popups When Pi Disconnected
- Import, Export, and SFTP transfer popups now require Pi API connection before opening.
- If Pi is disconnected, SAS shows the normal Pi disconnected popup instead of opening the Import/Export/SFTP card.
- This prevents users from opening SFTP-related popups when the Pi is offline.
- If the Pi disconnects while the Export popup is already open and the user clicks Download, the popup closes and the disconnect warning appears.
- Existing secure credentials display, startup, Settings suppression, Face Recognition, and mouse-disable logic remain unchanged.
- `pi_app_patch` was not updated.

## v221 - Allow Transfer Popups When Pi Disconnected
- Reverted the v220 pre-blocking behavior.
- Import, Export, and SFTP popups can open even when the Pi is disconnected.
- Users can click the transfer/connect action inside the popup; the existing fail prompt handles disconnected/failed connection cases.
- Existing secure credentials display, startup, Settings suppression, Face Recognition, and mouse-disable logic remain unchanged.
- `pi_app_patch` was not updated.

## v222 - Secure Transfer Credentials and Session Settings Convenience
- Import / Export / SFTP popups now open with blank NTID and password fields every time.
- Transfer popups may still show the server path for convenience, but they do not expose saved NTID/password.
- Pi sync/pull and Settings load clear only NTID and password; server path remains visible.
- After a successful Save Connect in the current login session, NTID/password/server path remain visible in Settings so the same user can make small changes and press Save Connect again without retyping.
- On logout/restart, NTID and password are cleared again for security.
- Existing startup, disconnect popup, Settings suppression, Face Recognition, and mouse-disable logic remain unchanged.
- `pi_app_patch` was not updated.

## v223 - Blank Transfer Popup Fields and Clear Credentials on Logout
- Fixed Import / Export / SFTP popups still showing saved NTID/password/path.
- The following popup fields now open blank every time:
  - Export Server Path: NTID, Password, Server Path
  - Export Download Dataset (SFTP): Windows Username, Windows Password, Windows Save Folder
  - Import Server Path: NTID, Password, Server Path
  - Import Local ZIP: Windows Username, Windows Password, Local ZIP remains blank
- Main Settings Server Credentials behavior:
  - Pi sync/pull clears only NTID and password.
  - Server path remains visible for convenience.
  - After successful Save Connect, NTID/password/server path stay visible only for the same logged-in session.
  - Logout, Switch Account, or different user/admin login clears previous NTID/password.
- Existing startup, disconnect popup, Settings suppression, Face Recognition, and mouse-disable logic remain unchanged.
- `pi_app_patch` was not updated.

## v224 - Import / Export Card Text UI Update
- Export popup tab text changed from `Download Dataset (SFTP)` to `Local Path`.
- Import popup tab text changed from `Local ZIP` to `Local Path`.
- Export download tab button text changed from `Download` to `Export`.
- Import local ZIP tab button text changed from `Import Local ZIP` to `Import`.
- Removed the subtitle line under `EXPORT FACE DATA`.
- Removed the subtitle line under `IMPORT FACE DATA`.
- No backend transfer/import/export logic was changed.
- `pi_app_patch` was not updated.

## v225 - Remove Remaining Import / Export Popup Labels
- Removed the remaining subtitle under `EXPORT FACE DATA`.
- Removed the remaining subtitle under `IMPORT FACE DATA`.
- Removed the highlighted description/help labels in the Import / Export popup cards.
- Fixed the local import button text from `Import Local Path` to `Import`.
- Kept tab labels as `Local Path`.
- Kept backend import/export/SFTP logic unchanged.
- `pi_app_patch` was not updated.

## v226 - Import / Export Card Open and Spacing Fix
- Fixed Import Face Data popup not opening because of an incorrect `info.hide()` reference.
- Removed the remaining empty grey info boxes after description labels were removed.
- Removed extra stretch spacers that created large blank areas in the card.
- Reduced Export card height after removing subtitle/help text.
- Reduced Import card height after removing subtitle/help text.
- Kept backend import/export/SFTP logic unchanged.
- `pi_app_patch` was not updated.

## v227 - Main Footer Compact and Dashboard Hidden
- Updated the main bottom footer, not the Import/Export popup footer.
- Dashboard tab no longer shows the footer.
- Face Recognition tab remains footer-free.
- Settings tab keeps the footer but with reduced height.
- Footer strip height, padding, spacing, divider height, and label text size were reduced.
- Backend logic was not changed.
- `pi_app_patch` was not updated.

## v228 - Transfer Placeholders and Rounded Footer Restore
- Added example placeholders inside Import / Export popup text fields:
  - NTID / Username fields show an NTID example.
  - Server Path shows a server path example.
  - Windows Save Folder shows a local folder example.
  - Local ZIP File shows a selection hint.
- Password fields remain blank without placeholder examples.
- Restored the main footer to the previous rounded pill shape.
- Footer remains compact and Dashboard tab footer remains hidden.
- Backend logic was not changed.
- `pi_app_patch` was not updated.

## v229 - Runtime Origin and Placeholder Fix
- Fixed runtime crash: `NameError: origin is not defined` inside Pi connection callback.
- Fixed Import / Export popup crash: `transfer_input_row()` now supports the `placeholder` parameter.
- Updated placeholder examples to use generic values:
  - NTID example: `1234567`
  - Server path example: `//server/share/SAS_folder`
  - Windows folder example: `C:\Users\Public\Documents`
- Password fields remain blank without example placeholders.
- Backend logic was not changed.
- `pi_app_patch` was not updated.

## v230 - Settings Card Row Order Update
- Rearranged the Settings page card order:
  - Row 1: Pi Connectivity | Auto-Capture
  - Row 2: Server Credentials | Security Options
  - Row 3 remains: Face Data Transfer | Admin Management
- Existing card content, validation, credential security, Pi connection, and backend logic were not changed.
- `pi_app_patch` was not updated.

## v231 - Footer Rounded Pill Shape Fix
- Fixed the main footer appearing rectangular.
- Restored explicit rounded pill styling on `FooterStrip`.
- Rounded left and right ends are restored using border-radius matching the compact footer height.
- Footer remains compact on Settings and hidden on Dashboard.
- Settings card order from v230 remains unchanged.
- `pi_app_patch` was not updated.

## v232 - Origin Pylance Warning Fix
- Fixed remaining Pylance warning: `origin` is not defined inside `_face_api_test_connection`.
- The function now uses `origin_safe` inside queued callbacks and conditional branches.
- This also prevents the runtime `NameError: origin is not defined`.
- Footer rounded pill fix from v231 remains unchanged.
- Settings card order, Import/Export placeholders, credential security, and lock logic remain unchanged.
- `pi_app_patch` was not updated.

## v233 - Direct Origin Runtime Fix
- Fixed the remaining runtime crash where a queued callback still referenced `origin` directly.
- Patched all method blocks that use `origin` conditions to use `origin_safe`.
- Added a defensive fallback for any remaining direct `origin` condition.
- This prevents `NameError: origin is not defined` during Pi status/settings callbacks.
- Existing footer, Settings card order, Import/Export placeholders, credential security, and lock logic remain unchanged.
- `pi_app_patch` was not updated.

## v234 - Pi Import Backup Pending and Reject Delete
- Updated Pi-side face data transfer behavior.
- Export no longer creates or keeps an extra local backup copy just for export.
- Temporary export staging ZIPs in `temp_export/` are cleaned before new export staging is prepared to reduce wasted Pi storage.
- Import still creates a safety backup before changing `dataset/` and `encodings.pickle`.
- The import safety backup is now stored in:
  - `received_face_data/pending/backup_before_import_YYYYMMDD_HHMMSS.zip`
- Because the backup is in `pending`, the user can select it again from Check Received if needed.
- Reject now deletes the pending ZIP directly instead of moving it to `received_face_data/rejected/`.
- `received_face_data/rejected/` is no longer created by the Pi transfer folder setup.
- Windows dashboard logic was not changed.
- `pi_app_patch` was updated.

## v235 - Accepted Keep Latest 3 and Export Filename Rename
- Updated Pi-side accepted-folder storage control:
  - `received_face_data/accepted/` now keeps only the latest 3 accepted ZIP files.
  - When more than 3 accepted ZIPs exist, the oldest accepted ZIPs are deleted automatically.
- Renamed new export ZIP filename pattern:
  - Old: `face_data_backup_YYYYMMDD_HHMMSS.zip`
  - New: `face_data_YYYYMMDD_HHMMSS.zip`
- Existing legacy `face_data_backup_*.zip` files are still accepted by the server ZIP listing/import flow for compatibility.
- `backup_before_import_*.zip` remains only for import safety backups and is stored in `received_face_data/pending/`.
- Reject behavior from v234 remains: rejected pending ZIPs are deleted directly.
- `pi_app_patch` was updated.

## SAS v92 – Training Completion and Recognition Recovery Fix

- Fixed a deferred Qt error callback that could leave the SAS **Training in Progress** dialog open after the Pi had already completed training.
- Added a Pi training request ID/state handshake so SAS waits for the exact training job it started.
- Split Pi API stop actions into targeted capture/recognition stops and a separate full manual stop. Training no longer accidentally cancels its own post-training camera recovery.
- Pi now retries recognition restart after training while the camera is released.
- SAS verifies Pi recognition after training and safely requests a restart as a fallback.
- SAS preview remains closed after training; Pi recognition runs in the background for workstation unlock.

Updated files:
- `sas_dashboard_modular/dashboard.py`
- `pi_app_patch/face_api.py`
- `pi_app_patch/gui.py`

