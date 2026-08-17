import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon

from dashboard import SecureAccessDashboard


def app_resource_path(*parts: str) -> str:
    module_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(module_dir, *parts)]
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(os.path.join(bundle_dir, *parts))
        candidates.append(os.path.join(bundle_dir, "sas_dashboard_modular", *parts))
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return os.path.join(module_dir, *parts)


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SAS.SecureAccessSystem.v2")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Secure Access System")
    app.setApplicationDisplayName("Secure Access System")
    app.setOrganizationName("Secure Access System")
    app.setFont(QFont("Inter", 10))
    logo_icon_path = app_resource_path("assets", "sas_logo.ico")
    if os.path.exists(logo_icon_path):
        app.setWindowIcon(QIcon(logo_icon_path))

    window = SecureAccessDashboard()
    window.show()

    sys.exit(app.exec())
