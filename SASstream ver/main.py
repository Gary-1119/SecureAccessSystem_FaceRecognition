import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon

from dashboard import SecureAccessDashboard
from services.resource_service import app_resource_path



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
