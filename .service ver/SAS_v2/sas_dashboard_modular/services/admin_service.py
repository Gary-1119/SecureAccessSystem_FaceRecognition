import os


class AdminService:
    """Admin list logic migrated from lockapp.py.

    First valid login becomes admin.
    After that, only NTIDs inside admins.txt are admin.
    """

    def __init__(self, admin_file: str):
        self.admin_file = admin_file

    def ensure_admin_file(self):
        if not os.path.exists(self.admin_file):
            with open(self.admin_file, "w", encoding="utf-8") as f:
                f.write("")

    def load_admins(self):
        self.ensure_admin_file()
        try:
            with open(self.admin_file, "r", encoding="utf-8") as f:
                return [line.strip().lower() for line in f if line.strip()]
        except Exception:
            return []

    def save_admin(self, ntid: str):
        ntid = str(ntid).strip().lower()
        if not ntid:
            return

        admins = self.load_admins()
        if ntid not in admins:
            admins.append(ntid)

        with open(self.admin_file, "w", encoding="utf-8") as f:
            for admin in admins:
                f.write(admin + "\n")

    def check_admin_login(self, ntid: str):
        ntid = str(ntid).strip().lower()
        admins = self.load_admins()

        if not admins:
            self.save_admin(ntid)
            return True, "First login registered as Admin."

        if ntid in admins:
            return True, "Admin login successful."

        return False, "Normal user login successful."
