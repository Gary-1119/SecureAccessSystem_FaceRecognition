import os

from services.atomic_file import atomic_write_text


class AdminService:
    """Admin list logic migrated from lockapp.py.

    First valid AD login becomes the root/admin user when admins.txt is empty.
    After that, only NTIDs inside admins.txt are admin.
    """

    def __init__(self, admin_file: str):
        self.admin_file = admin_file

    def ensure_admin_file(self):
        folder = os.path.dirname(os.path.abspath(self.admin_file))
        if folder:
            os.makedirs(folder, exist_ok=True)

        if not os.path.exists(self.admin_file):
            atomic_write_text(self.admin_file, "", encoding="utf-8", keep_backup=False)

    def has_admins(self):
        return len(self.load_admins()) > 0

    def load_admins(self):
        self.ensure_admin_file()
        try:
            admins = []
            with open(self.admin_file, "r", encoding="utf-8-sig") as f:
                for line in f:
                    ntid = str(line).strip().replace("\ufeff", "").lower()
                    if ntid and ntid not in admins:
                        admins.append(ntid)
            return admins
        except Exception:
            return []

    def save_admin(self, ntid: str):
        ntid = str(ntid).strip().lower()
        if not ntid:
            return

        admins = self.load_admins()
        if ntid not in admins:
            admins.append(ntid)

        atomic_write_text(self.admin_file, "".join(f"{admin}\n" for admin in admins), encoding="utf-8", keep_backup=True)

    def remove_admin(self, ntid: str):
        """Remove an admin NTID.

        The first admin is protected and cannot be removed here.
        Returns (success, message).
        """
        target = str(ntid).strip().lower()
        if not target:
            return False, "Missing admin NTID."

        admins = self.load_admins()
        if target not in admins:
            return False, "Admin not found."

        if admins and target == admins[0]:
            return False, "The first/root admin cannot be removed."

        admins = [admin for admin in admins if admin != target]
        atomic_write_text(self.admin_file, "".join(f"{admin}\n" for admin in admins), encoding="utf-8", keep_backup=True)

        return True, "Admin removed."

    def check_admin_login(self, ntid: str):
        ntid = str(ntid).strip().lower()
        admins = self.load_admins()

        if not admins:
            self.save_admin(ntid)
            return True, "First login registered as Admin."

        if ntid in admins:
            return True, "Admin login successful."

        return False, "Normal user login successful."