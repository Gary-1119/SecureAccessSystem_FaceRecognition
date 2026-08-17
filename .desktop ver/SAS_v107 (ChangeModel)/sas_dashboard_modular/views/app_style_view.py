from __future__ import annotations

from dashboard_typing import DashboardMixinBase
from styles.app_stylesheet import build_app_stylesheet


class AppStyleViewMixin(DashboardMixinBase):
    def apply_styles(self):
        self.setStyleSheet(build_app_stylesheet(self))

