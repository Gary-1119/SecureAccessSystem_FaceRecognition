from __future__ import annotations

from app_config import Theme


def apply_dashboard_styles(self) -> None:
        time_font = 92 if not self.compact_mode else 64
        brand_font = 23 if not self.compact_mode else 18
        nav_font = 14 if not self.compact_mode else 12
        date_font = 14 if not self.compact_mode else 11
        card_radius = 28 if not self.compact_mode else 22
        title_font = 25 if not self.compact_mode else 18
        icon_font = 52 if not self.compact_mode else 36
        countdown_font = 28 if not self.compact_mode else 22

        self.setStyleSheet(f"""
            QMainWindow, #Root, #MainContent, #MainScroll, #Page, #PageStack {{
                background: {Theme.BG};
                color: {Theme.TEXT};
            }}

            QWidget {{
                background-color: transparent;
            }}

            QScrollArea {{
                border: none;
                background: transparent;
            }}

            QLabel, QPushButton {{
                font-family: Inter, Segoe UI, Arial;
            }}

            #Header {{
                background: {Theme.SURFACE};
                border-bottom: 1px solid {Theme.BORDER};
            }}

            #BrandRow {{
                background: transparent;
            }}

            #HeaderLogo {{
                background: transparent;
            }}

            #Brand {{
                color: {Theme.PRIMARY};
                font-size: {brand_font}px;
                font-weight: 800;
                letter-spacing: -0.02em;
            }}

            #GuidelinesHelpButton {{
                background: #ffffff;
                color: #000000;
                border: 1px solid #c4c7c7;
                border-radius: {14 if not self.compact_mode else 12}px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 800;
                padding: 0px;
            }}

            #GuidelinesHelpButton:hover {{
                background: #e8e8e8;
                border-color: #747878;
            }}

            #GuidelinesHelpButton:pressed {{
                background: #dadada;
                padding-top: 1px;
            }}

            #TopNav, #TopNavActive {{
                background: transparent;
                border: none;
                color: {Theme.SECONDARY};
                font-size: {nav_font}px;
                font-weight: 600;
                padding: 16px 0px 12px 0px;
                border-bottom: 2px solid transparent;
            }}

            #TopNav:hover {{ color: {Theme.PRIMARY}; }}

            #TopNavActive {{
                color: {Theme.PRIMARY};
                border-bottom: 2px solid transparent;
            }}

            #TabIndicator {{
                background: {Theme.PRIMARY};
                border: none;
                border-radius: 1px;
            }}



            #AccountDropdown {{
                background: {Theme.PRIMARY};
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 18px;
            }}

            #AccountDropdownTitle {{
                color: rgba(255, 255, 255, 0.52);
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 700;
                letter-spacing: 2px;
                padding-left: 8px;
                padding-top: 4px;
            }}

            #AccountDropdownUser {{
                color: white;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                padding-left: 8px;
                padding-bottom: 4px;
            }}

            #AccountDropdownButton {{
                background: rgba(255, 255, 255, 0.08);
                color: white;
                border: none;
                border-radius: 11px;
                min-height: 34px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                text-align: left;
                padding-left: 12px;
            }}

            #AccountDropdownButton:hover {{
                background: rgba(255, 255, 255, 0.16);
            }}

            #AccountDropdownDangerButton {{
                background: rgba(255, 255, 255, 0.06);
                color: #FCA5A5;
                border: none;
                border-radius: 11px;
                min-height: 34px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                text-align: left;
                padding-left: 12px;
            }}

            #AccountDropdownDangerButton:hover {{
                background: rgba(220, 38, 38, 0.20);
                color: white;
            }}


            #LoginButtonLoggedIn {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: {17 if not self.compact_mode else 15}px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                padding: 0 18px;
            }}

            #LoginButtonLoggedIn:hover {{
                background: #2F3131;
            }}


            #LoginButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: {17 if not self.compact_mode else 15}px;
                font-size: {12 if not self.compact_mode else 11}px;
                font-weight: 700;
            }}

            #LoginButton:hover {{
                background: #1F1F1F;
            }}

            #LoginButton:pressed {{
                background: #333333;
                padding-top: 2px;
            }}

            #TerminalTime {{
                color: {Theme.PRIMARY};
                font-size: {time_font}px;
                font-weight: 900;
                letter-spacing: -4px;
            }}

            #TerminalDate {{
                color: {Theme.SECONDARY};
                font-size: {date_font}px;
                font-weight: 600;
                letter-spacing: {2 if not self.compact_mode else 1}px;
            }}

            #GlassCard, #GlassCardGreen {{
                background: rgba(255, 255, 255, 0.72);
                border-radius: {card_radius}px;
            }}

            #GlassCard {{
                border: 1px solid rgba(196, 199, 199, 0.60);
            }}

            #GlassCardGreen {{
                border: 2px solid rgba(22, 163, 74, 0.18);
            }}

            #UnlockedCard {{
                background: #3F9468;
                border: none;
                border-radius: {card_radius}px;
            }}

            #CardEyebrowWhite {{
                color: rgba(255, 255, 255, 0.65);
                font-size: {11 if not self.compact_mode else 9}px;
                font-weight: 700;
                letter-spacing: {1.6 if not self.compact_mode else 1.2}px;
            }}

            #UnlockedTitleWhite {{
                color: white;
                font-size: {max(22, int(title_font * 0.72))}px;
                font-weight: 900;
                letter-spacing: -0.03em;
            }}

            #WhiteLockIcon {{
                color: white;
                font-size: {icon_font}px;
                font-weight: 900;
            }}

            #FadeLockBgWhite {{
                color: rgba(255, 255, 255, 0.10);
                font-size: {120 if not self.compact_mode else 90}px;
            }}

            #EncryptedWhite {{
                color: white;
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 800;
            }}

            #UnlockedPillGreen {{
                background: rgba(255, 255, 255, 0.22);
                color: white;
                border-radius: {17 if not self.compact_mode else 14}px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #LockedPillRed {{
                background: rgba(255, 255, 255, 0.22);
                color: white;
                border-radius: {17 if not self.compact_mode else 14}px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #Divider, #VerticalLine {{
                background: {Theme.BORDER};
                border: none;
            }}

            #DividerWhite {{
                background: rgba(255, 255, 255, 0.16);
                border: none;
            }}

            #ManualLockButtonWhite {{
                background: white;
                color: #10B981;
                border: none;
                border-radius: 12px;
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 900;
                letter-spacing: 1.3px;
            }}

            #ManualLockButtonWhite:hover {{
                background: rgba(255, 255, 255, 0.88);
            }}

            #ManualLockButtonWhite[lockState="unlocked"] {{
                color: #3F9468;
            }}

            #ManualLockButtonWhite[lockState="locked"] {{
                color: #B23A3A;
            }}

            #CountdownText {{
                color: #FFFFFF;
                font-size: {countdown_font}px;
                font-weight: 900;
            }}

            #RemainingText {{
                color: rgba(255, 255, 255, 0.78);
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
                letter-spacing: 1px;
            }}

            #CountdownTitle {{
                color: rgba(255, 255, 255, 0.78);
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 800;
            }}

            #CountdownDesc {{
                color: rgba(255, 255, 255, 0.90);
                font-size: {18 if not self.compact_mode else 14}px;
                font-weight: 900;
            }}


            #CircleFlipContainer, #CircleStack, #CircleFace {{
                background: transparent;
                border: none;
            }}

            #FaceDetectedCircle {{
                background: rgba(255, 255, 255, 0.16);
                border: 3px solid rgba(255, 255, 255, 0.32);
                border-radius: {95 if not self.compact_mode else 70}px;
            }}

            #FaceDetectedIcon {{
                color: white;
                background: transparent;
                border: none;
                font-size: {48 if not self.compact_mode else 36}px;
                font-weight: 900;
            }}

            #FaceDetectedCircleText {{
                color: white;
                background: transparent;
                border: none;
                font-size: {13 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 0.5px;
                padding: 3px 8px;
            }}

            #FaceDetectedState {{
                color: #FFFFFF;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}


            #UsersTitle {{
                color: {Theme.PRIMARY};
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }}

            #UsersStatus {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
            }}

            #UsersDivider {{
                background: rgba(196, 199, 199, 0.65);
                border: none;
            }}

            #UserName {{
                color: {Theme.PRIMARY};
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 700;
            }}

            #UserDetail {{
                color: {Theme.SECONDARY};
                font-size: {11 if not self.compact_mode else 9}px;
            }}

            #GreenDot {{
                color: {Theme.GREEN};
                font-size: {16 if not self.compact_mode else 12}px;
            }}

            #IdleText {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
            }}

            #ManageAccessButton {{
                background: transparent;
                color: {Theme.PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}

            #ManageAccessButton:hover {{
                background: {Theme.PRIMARY};
                color: white;
            }}

            #ManageAccessButton:pressed {{
                background: #333333;
                padding-top: 2px;
            }}

            #AuthorizedUsersDashboardIconButton {{
                background: rgba(255, 255, 255, 0.18);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.30);
                border-radius: {24 if not self.compact_mode else 20}px;
                font-size: {18 if not self.compact_mode else 15}px;
                font-weight: 900;
                padding-bottom: 2px;
            }}

            #AuthorizedUsersDashboardIconButton:hover {{
                background: rgba(255, 255, 255, 0.30);
            }}

            #AuthorizedUsersDashboardIconButton:pressed {{
                background: rgba(255, 255, 255, 0.38);
                padding-top: 2px;
            }}

            #AuthorizedUsersDashboardButton {{
                background: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.24);
                border-radius: 12px;
                font-size: {14 if not self.compact_mode else 11}px;
                font-weight: 900;
                letter-spacing: 1.3px;
            }}

            #AuthorizedUsersDashboardButton:hover {{
                background: rgba(255, 255, 255, 0.26);
            }}

            #FooterArea {{
                background: transparent;
                border: none;
            }}

            #FooterStrip {{
                background: rgba(243, 243, 243, 0.88);
                border: 1px solid {Theme.BORDER};
                border-radius: {29 if not self.compact_mode else 26}px;
            }}

            #Copyright {{
                color: {Theme.MUTED};
                font-size: {11 if not self.compact_mode else 9}px;
            }}




            #LoginFailedDialog {{
                background: transparent;
            }}

            #FailedGlassPanel {{
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.70);
                border-radius: 30px;
            }}

            #FailedCircle {{
                background: #B23A3A;
                color: white;
                border-radius: {39 if not self.compact_mode else 33}px;
                font-size: {38 if not self.compact_mode else 30}px;
                font-weight: 900;
            }}

            #FailedTitle {{
                color: {Theme.PRIMARY};
                font-size: {28 if not self.compact_mode else 24}px;
                font-weight: 800;
                letter-spacing: -0.8px;
            }}

            #FailedReason {{
                color: {Theme.SECONDARY};
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 600;
                line-height: 1.5;
            }}

            #FailedDebugBox {{
                background: #F3F3F3;
                border: 1px solid {Theme.BORDER};
                border-radius: 12px;
            }}

            #FailedDebugTitle {{
                color: rgba(0, 0, 0, 0.48);
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #FailedDebugText {{
                color: #2F2F2F;
                font-family: Consolas;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 600;
                line-height: 1.45;
            }}

            #FailedPrimaryButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 12px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 800;
            }}

            #FailedPrimaryButton:hover {{
                background: #2F3131;
            }}


            #LoginSuccessDialog {{
                background: transparent;
            }}

            #SuccessGlassPanel {{
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.70);
                border-radius: 32px;
            }}

            #SuccessBrand {{
                color: {Theme.PRIMARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 6px;
            }}

            #SuccessOuterRing {{
                background: rgba(0, 0, 0, 0.03);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: {45 if not self.compact_mode else 39}px;
            }}

            #SuccessCheckCircle {{
                background: {Theme.PRIMARY};
                color: white;
                border-radius: {31 if not self.compact_mode else 27}px;
                font-size: {30 if not self.compact_mode else 26}px;
                font-weight: 300;
            }}

            #SuccessTitle {{
                color: {Theme.PRIMARY};
                font-size: {26 if not self.compact_mode else 22}px;
                font-weight: 700;
                letter-spacing: -1px;
            }}

            #SuccessBadge {{
                background: rgba(255, 255, 255, 0.65);
                color: rgba(0, 0, 0, 0.70);
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 13px;
                padding: 5px 18px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.6px;
            }}

            #IdentityCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #FFFFFF,
                    stop:0.52 #F3F3F3,
                    stop:1 #E8E8E8
                );
                border: 1px solid rgba(255, 255, 255, 0.95);
                border-radius: 18px;
            }}

            #IdentityMeta {{
                color: rgba(94, 94, 94, 0.70);
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #IdentityNtid {{
                color: {Theme.PRIMARY};
                font-size: {16 if not self.compact_mode else 14}px;
                font-weight: 800;
                letter-spacing: -0.4px;
            }}

            #IdentityShield {{
                background: rgba(0, 0, 0, 0.05);
                color: rgba(0, 0, 0, 0.42);
                border-radius: 10px;
                font-size: 18px;
                font-weight: 900;
            }}

            #IdentityDivider {{
                background: rgba(0, 0, 0, 0.06);
                border: none;
            }}

            #IdentityAccess {{
                color: {Theme.PRIMARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
            }}

            #IdentitySession {{
                color: rgba(94, 94, 94, 0.65);
                font-family: Consolas;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 700;
            }}

            #SuccessPrimaryButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 18px;
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 800;
            }}

            #SuccessPrimaryButton:hover {{
                background: #2F3131;
            }}

            #SuccessPrimaryButton:pressed {{
                background: #444748;
                padding-top: 2px;
            }}

            #SuccessSmallLine {{
                background: rgba(0, 0, 0, 0.07);
                border: none;
            }}

            #SuccessRedirect {{
                color: rgba(94, 94, 94, 0.70);
                font-size: {12 if not self.compact_mode else 11}px;
                font-weight: 600;
            }}

            #SuccessFooterText {{
                color: rgba(0, 0, 0, 0.42);
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.4px;
            }}



            #InlineDebugBox {{
                background: #F3F3F3;
                border: 1px solid {Theme.BORDER};
                border-radius: 12px;
            }}

            #InlineDebugTitle {{
                color: rgba(0, 0, 0, 0.48);
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #InlineDebugText {{
                color: #2F2F2F;
                font-family: Consolas;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 600;
                line-height: 1.45;
            }}

            #MissingCredentialsSetupDialog {{
                background: transparent;
            }}

            #MissingCredentialsPanel {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.95);
                border-radius: 30px;
            }}

            #MissingCredentialsIcon {{
                background: #FFDAD6;
                color: #93000A;
                border: 1px solid rgba(186, 26, 26, 0.20);
                border-radius: {36 if not self.compact_mode else 31}px;
                font-size: {36 if not self.compact_mode else 30}px;
                font-weight: 900;
            }}

            #MissingCredentialsTitle {{
                color: {Theme.PRIMARY};
                font-size: {24 if not self.compact_mode else 21}px;
                font-weight: 900;
                letter-spacing: -0.6px;
            }}

            #MissingCredentialsMessage {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 500;
                line-height: 1.45;
            }}

            #MissingCredentialsPrimaryButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 14px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
                letter-spacing: 1.1px;
            }}

            #MissingCredentialsPrimaryButton:hover {{
                background: #1F1F1F;
            }}

            #MissingCredentialsPrimaryButton:pressed {{
                background: #333333;
                padding-top: 2px;
            }}

            #MissingCredentialsWatermark {{
                color: rgba(0, 0, 0, 0.035);
                font-size: {96 if not self.compact_mode else 76}px;
                font-weight: 900;
            }}


            #SettingsConnectionDialog {{
                background: transparent;
            }}

            #SettingsSuccessPanel {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.95);
                border-radius: 30px;
            }}

            #SettingsFailPanel {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.95);
                border-radius: 26px;
            }}

            #SettingsSuccessIcon {{
                background: #E8F5E9;
                color: #2E7D32;
                border: 1px solid rgba(46, 125, 50, 0.18);
                border-radius: {32 if not self.compact_mode else 28}px;
                font-size: {32 if not self.compact_mode else 28}px;
                font-weight: 900;
            }}

            #SettingsFailIcon {{
                background: #FFDAD6;
                color: #BA1A1A;
                border: 1px solid rgba(186, 26, 26, 0.20);
                border-radius: {32 if not self.compact_mode else 28}px;
                font-size: {34 if not self.compact_mode else 30}px;
                font-weight: 900;
            }}

            #SettingsConnectTitle {{
                color: {Theme.PRIMARY};
                font-size: {26 if not self.compact_mode else 22}px;
                font-weight: 800;
                letter-spacing: -0.8px;
            }}

            #SettingsConnectSubtitle {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 500;
            }}

            #SettingsMetaCard {{
                background: #FFFFFF;
                border: 1px solid {Theme.BORDER};
                border-radius: 12px;
            }}

            #SettingsMetaLabel {{
                color: {Theme.MUTED};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.4px;
            }}

            #SettingsMetaValue {{
                color: {Theme.PRIMARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
                font-family: Consolas;
            }}

            #SettingsMetaSuccessValue {{
                color: #2E7D32;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
            }}

            #SettingsDiagnosticCard {{
                background: #F3F3F3;
                border: 1px solid {Theme.BORDER};
                border-radius: 12px;
            }}

            #SettingsDiagnosticHeader {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.8px;
            }}

            #SettingsIssueMark {{
                color: #BA1A1A;
                font-size: {18 if not self.compact_mode else 16}px;
                font-weight: 900;
            }}

            #SettingsIssueTitle {{
                color: {Theme.PRIMARY};
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #SettingsIssueDesc {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}


            #SmallIconButton {{
                background: #F3F3F3;
                color: {Theme.PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #SmallIconButton:hover {{
                background: #E8E8E8;
            }}




            #ExportStateEyebrow {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 2.2px;
            }}

            #ExportStateActive {{
                color: #000000;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
            }}

            #ExportStateShield {{
                color: #000000;
                font-size: {22 if not self.compact_mode else 18}px;
                font-weight: 900;
            }}


            #ExportCircleSpinner {{
                background: transparent;
                border: none;
            }}


            #ExportSpinnerWrap {{
                background: #FFFFFF;
                border: 1px solid #C4C7C7;
                border-radius: {52 if not self.compact_mode else 46}px;
            }}

            #ExportSpinner {{
                color: #000000;
                font-size: {34 if not self.compact_mode else 30}px;
                font-weight: 900;
            }}

            #ExportSpinnerInner {{
                background: #000000;
                color: #FFFFFF;
                border-radius: {17 if not self.compact_mode else 15}px;
                padding: 0px;
                font-size: {18 if not self.compact_mode else 15}px;
                font-weight: 900;
            }}

            #ExportStateTitle {{
                color: #000000;
                font-size: {19 if not self.compact_mode else 16}px;
                font-weight: 900;
                letter-spacing: 0.6px;
            }}

            #ExportStateSubtitle {{
                color: #5E5E5E;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #ExportProgressOuter {{
                background: #EEEEEE;
                border: none;
                border-radius: 3px;
            }}

            #ExportProgressFill {{
                background: #000000;
                border: none;
                border-radius: 3px;
            }}

            #ExportMetricLabel {{
                color: #747878;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
                letter-spacing: 1.4px;
            }}

            #ExportMetricValue {{
                color: #000000;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
            }}

            #ExportPercentage {{
                color: #000000;
                font-size: {24 if not self.compact_mode else 20}px;
                font-weight: 900;
            }}

            #ExportSuccessIcon {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: {34 if not self.compact_mode else 29}px;
                font-size: {44 if not self.compact_mode else 36}px;
                font-weight: 900;
            }}

            #ExportFailedIcon {{
                background: #BA1A1A;
                color: #FFFFFF;
                border: none;
                border-radius: {34 if not self.compact_mode else 29}px;
                font-size: {44 if not self.compact_mode else 36}px;
                font-weight: 900;
            }}

            #ExportSuccessTitle {{
                color: #000000;
                font-size: {26 if not self.compact_mode else 21}px;
                font-weight: 700;
                letter-spacing: -0.3px;
            }}

            #ExportSuccessSubtitle {{
                color: #5E5E5E;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 600;
            }}

            #ExportDetailBlock {{
                background: #EEEEEE;
                border: 1px solid #C4C7C7;
                border-radius: 10px;
            }}

            #ExportDetailCode {{
                background: rgba(255,255,255,0.65);
                color: #000000;
                border: 1px solid rgba(196,199,199,0.45);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}


            #ImportSourceFile {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }}

            #ImportInfoIcon {{
                background: #E8E8E8;
                color: #000000;
                border: 1px solid #C4C7C7;
                border-radius: {34 if not self.compact_mode else 29}px;
                font-size: {32 if not self.compact_mode else 26}px;
                font-weight: 900;
            }}


            #ExportReturnButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 1.3px;
            }}

            #ExportReturnButton:hover {{
                background: #2F3131;
            }}



            #TransferDialog {{
                background: transparent;
            }}

            #TransferCard {{
                background: rgba(255, 255, 255, 0.96);
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 22px;
            }}

            #TransferTopLine {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 transparent, stop:0.5 rgba(0,0,0,0.14), stop:1 transparent);
            }}

            #TransferHeaderIcon {{
                background: #FFFFFF;
                color: #000000;
                border: 1px solid #C4C7C7;
                border-radius: {28 if not self.compact_mode else 24}px;
                font-size: {20 if not self.compact_mode else 18}px;
                font-weight: 900;
            }}

            #TransferTitle {{
                color: #1A1C1C;
                font-size: {19 if not self.compact_mode else 16}px;
                font-weight: 400;
                letter-spacing: 2.5px;
                text-transform: uppercase;
            }}

            #TransferSubtitle {{
                color: #444748;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 1.6px;
                text-transform: uppercase;
            }}

            #TransferHint {{
                color: #5E5E5E;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 600;
            }}


            #TransferFieldLabel {{
                color: #444748;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.8px;
                text-transform: uppercase;
            }}

            #TransferTabButton {{
                background: #FFFFFF;
                color: #444748;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
                padding: 7px 12px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.4px;
                text-transform: uppercase;
            }}

            #TransferTabButton:hover {{
                background: #F3F3F3;
                color: #000000;
            }}

            #TransferTabButton[selected="true"] {{
                background: #000000;
                color: #FFFFFF;
                border: 1px solid #000000;
            }}

            #TransferInputBox {{
                background: #FFFFFF;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
            }}

            #TransferInputBox:hover {{
                border: 1px solid #747878;
            }}

            #TransferInput {{
                background: transparent;
                color: #1A1C1C;
                border: none;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 600;
                padding-left: 0px;
            }}

            #TransferIconButton {{
                background: transparent;
                color: #747878;
                border: none;
                border-radius: 8px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
            }}

            #TransferIconButton:hover {{
                background: #E8E8E8;
                color: #000000;
            }}

            #TransferInfo {{
                background: #F3F3F3;
                color: #444748;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #TransferStatus {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 600;
            }}

            #TransferStatusSuccess {{
                color: #047857;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
            }}

            #TransferStatusError {{
                color: #BA1A1A;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
            }}

            #TransferCancelButton {{
                background: transparent;
                color: #5E5E5E;
                border: none;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 2px;
                text-transform: uppercase;
            }}

            #TransferCancelButton:hover {{
                color: #000000;
            }}


            #TransferSecondaryActionButton {{
                background: #FFFFFF;
                color: #000000;
                border: 1px solid #C4C7C7;
                border-radius: 12px;
                padding: 12px 24px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 1.8px;
                text-transform: uppercase;
            }}

            #TransferSecondaryActionButton:hover {{
                background: #BA1A1A;
                color: #FFFFFF;
                border: 1px solid #BA1A1A;
            }}

            #TransferPrimaryButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 1.8px;
                text-transform: uppercase;
            }}

            #TransferPrimaryButton:hover {{
                background: #2F3131;
            }}

            #TransferPrimaryButton:disabled {{
                background: #C7C6C6;
                color: #747878;
            }}

            #TransferSearchIcon {{
                color: #747878;
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 900;
            }}

            #TransferZipList {{
                background: #F3F3F3;
                border: 1px solid #C4C7C7;
                border-radius: 8px;
            }}

            #TransferZipRow {{
                background: transparent;
                border-bottom: 1px solid rgba(196,199,199,0.55);
                border-radius: 6px;
            }}

            #TransferZipRow:hover {{
                background: rgba(16, 185, 129, 0.08);
            }}

            #TransferZipRow[selected="true"] {{
                background: #D1FAE5;
                border: 1px solid #10B981;
            }}

            #TransferZipIcon {{
                color: #747878;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
            }}

            #TransferZipName {{
                color: #1A1C1C;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #TransferZipRow[selected="true"] #TransferZipName {{
                color: #065F46;
                font-weight: 900;
            }}

            #TransferReadyBadge {{
                background: #ECFDF5;
                color: #047857;
                border: 1px solid #A7F3D0;
                border-radius: 6px;
                padding: 3px 7px;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 900;
            }}


            #CameraConnectionDialog {{
                background: transparent;
            }}

            #CameraConnectionCard {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.78);
                border-radius: 32px;
            }}

            #CameraConnectionVisualLoading {{
                background: #111111;
                border-top-left-radius: 32px;
                border-bottom-left-radius: 32px;
            }}

            #CameraConnectionVisualSuccess {{
                background: #008F53;
                border-top-left-radius: 32px;
                border-bottom-left-radius: 32px;
            }}

            #CameraConnectionVisualFailed {{
                background: #BA1A1A;
                border-top-left-radius: 32px;
                border-bottom-left-radius: 32px;
            }}

            #CameraConnectionLargeIcon {{
                color: #FFFFFF;
                font-size: {72 if not self.compact_mode else 58}px;
                font-weight: 400;
            }}

            #CameraConnectionVisualCaption {{
                color: #FFFFFF;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 3px;
            }}

            #CameraConnectionContent {{
                background: #F9F9F9;
                border-top-right-radius: 32px;
                border-bottom-right-radius: 32px;
            }}

            #CameraConnectionTitle {{
                color: #000000;
                font-size: {30 if not self.compact_mode else 24}px;
                font-weight: 800;
                letter-spacing: 1.4px;
            }}

            #CameraConnectionSubtitle {{
                color: #5E5E5E;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
                letter-spacing: 2px;
                text-transform: uppercase;
            }}

            #CameraConnectionInfoBlock {{
                border-left: 2px solid rgba(0, 0, 0, 0.10);
                background: transparent;
            }}

            #CameraConnectionInfoLabel {{
                color: #5E5E5E;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 1.8px;
            }}

            #CameraConnectionInfoValue {{
                color: #000000;
                font-size: {16 if not self.compact_mode else 13}px;
                font-weight: 800;
            }}

            #CameraConnectionFooter {{
                color: #5E5E5E;
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 800;
                letter-spacing: 1.6px;
            }}

            #CameraConnectionActionButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 1.6px;
                text-transform: uppercase;
            }}

            #CameraConnectionActionButton:hover {{
                background: #2F3131;
            }}


            #AuthorizedUsersDialog {{
                background: transparent;
            }}

            #AuthorizedUsersCard {{
                background: #FFFFFF;
                border: 1px solid rgba(196, 199, 199, 0.82);
                border-radius: 18px;
            }}

            #AuthorizedUsersEyebrow {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 2.2px;
            }}

            #AuthorizedUsersTitle {{
                color: {Theme.PRIMARY};
                font-size: {28 if not self.compact_mode else 24}px;
                font-weight: 500;
                letter-spacing: 1px;
            }}

            #AuthorizedUsersCount {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 1.8px;
            }}

            #AuthorizedRoundCloseButton {{
                background: #F1F1F1;
                color: #5E5E5E;
                border: 1px solid #C4C7C7;
                border-radius: {22 if not self.compact_mode else 19}px;
                font-size: {22 if not self.compact_mode else 18}px;
                font-weight: 700;
            }}

            #AuthorizedRoundCloseButton:hover {{
                background: #000000;
                color: #FFFFFF;
                border: 1px solid #000000;
            }}

            #AuthorizedSearchBox {{
                background: rgba(0, 0, 0, 0.05);
                border: 1px solid transparent;
                border-radius: 12px;
            }}

            #AuthorizedSearchBox:hover {{
                background: rgba(0, 0, 0, 0.065);
                border: 1px solid #C4C7C7;
            }}

            #AuthorizedSearchIcon {{
                color: {Theme.SECONDARY};
                font-size: {18 if not self.compact_mode else 15}px;
                font-weight: 800;
            }}

            #AuthorizedSearchInput {{
                background: transparent;
                color: {Theme.TEXT};
                border: none;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 400;
                padding-left: 4px;
            }}

            #AuthorizedPopupRow {{
                background: transparent;
                border-bottom: 1px solid rgba(0, 0, 0, 0.045);
                border-radius: 10px;
            }}

            #AuthorizedPopupRow:hover {{
                background: rgba(16, 185, 129, 0.04);
            }}

            #AuthorizedUserAvatar {{
                background: #F3F4F6;
                color: #2F3131;
                border: 1px solid rgba(196, 199, 199, 0.75);
                border-radius: {19 if not self.compact_mode else 17}px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #AuthorizedPopupName {{
                background: transparent;
                color: {Theme.PRIMARY};
                font-size: {16 if not self.compact_mode else 14}px;
                font-weight: 600;
            }}

            #AuthorizedPopupDetail {{
                background: transparent;
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 500;
            }}

            #AuthorizedPopupEmpty {{
                color: {Theme.SECONDARY};
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 600;
                padding: 18px 6px;
            }}

            #AuthorizedCloseButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}

            #AuthorizedCloseButton:hover {{
                background: #2F3131;
            }}


            #SettingsConnectPrimaryButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 13px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #SettingsConnectPrimaryButton:hover {{
                background: #2F3131;
            }}

            #SettingsConnectSecondaryButton {{
                background: #E1DFDF;
                color: #464747;
                border: 1px solid {Theme.BORDER};
                border-radius: 13px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #SettingsConnectSecondaryButton:hover {{
                background: #E8E8E8;
            }}





            #DeleteCompleteDialog {{
                background: transparent;
            }}

            #DeleteCompleteCard {{
                background: #FFFFFF;
                border: 1px solid {Theme.BORDER};
                border-radius: 22px;
            }}

            #DeleteIconWrap {{
                background: #ECFDF5;
                border: 1px solid #D1FAE5;
                border-radius: {41 if not self.compact_mode else 35}px;
            }}

            #DeleteIconCheck {{
                color: #059669;
                font-size: {44 if not self.compact_mode else 36}px;
                font-weight: 900;
            }}

            #DeleteTitle {{
                color: {Theme.PRIMARY};
                font-size: {28 if not self.compact_mode else 24}px;
                font-weight: 900;
                letter-spacing: -0.8px;
            }}

            #DeleteDesc {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 500;
                line-height: 1.5;
            }}

            #DeleteTrace {{
                color: {Theme.MUTED};
                background: {Theme.SURFACE_LOW};
                border: 1px solid {Theme.BORDER};
                border-radius: 12px;
                padding: 8px 10px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1px;
            }}

            #DeleteReturnButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 13px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 900;
            }}

            #DeleteReturnButton:hover {{
                background: #2F3131;
            }}


            QPushButton:disabled {{
                background: #E5E7EB;
                color: #9CA3AF;
                border-color: #D1D5DB;
            }}


            #LoginPopupDialog {{
                background: transparent;
            }}

            #LoginPopupCard {{
                background: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 18px;
            }}

            #LoginCloseButton {{
                background: {Theme.SURFACE_LOW};
                color: {Theme.SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 15px;
                font-size: 18px;
                font-weight: 800;
            }}

            #LoginCloseButton:hover {{
                background: {Theme.PRIMARY};
                color: white;
                border: 1px solid {Theme.PRIMARY};
            }}


            #LoginMainContent {{
                background: {Theme.BG};
            }}

            #LoginCard {{
                background: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 18px;
            }}

            #LoginShieldIcon {{
                background: {Theme.PRIMARY};
                color: white;
                border-radius: 14px;
                font-size: {28 if not self.compact_mode else 22}px;
                font-weight: 900;
            }}

            #LoginTitle {{
                color: {Theme.PRIMARY};
                font-size: {22 if not self.compact_mode else 18}px;
                font-weight: 900;
                letter-spacing: -0.02em;
            }}

            #LoginSubtitle {{
                color: {Theme.SECONDARY};
                font-size: {13 if not self.compact_mode else 11}px;
            }}

            #LoginFieldLabel {{
                color: {Theme.PRIMARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #LoginForgot {{
                color: {Theme.SECONDARY};
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #LoginInput {{
                background: {Theme.SURFACE};
                color: {Theme.PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
                padding: 0px 14px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 600;
                selection-background-color: {Theme.PRIMARY};
                selection-color: white;
            }}

            #LoginInput:hover {{
                border: 1px solid #747878;
                background: white;
            }}

            #LoginInput:focus {{
                border: 1px solid {Theme.PRIMARY};
                background: white;
            }}

            #LoginToggleButton {{
                background: {Theme.SURFACE_LOW};
                color: {Theme.SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #LoginToggleButton:hover {{
                background: #E2E2E2;
                color: {Theme.PRIMARY};
            }}

            #LoginSubmitButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
            }}

            #LoginSubmitButton:hover {{
                background: #2F3131;
            }}

            #LoginSubmitButton:pressed {{
                background: #444748;
                padding-top: 2px;
            }}

            #LoginDivider {{
                background: rgba(196, 199, 199, 0.50);
                border: none;
            }}

            #LoginStatus {{
                color: rgba(94, 94, 94, 0.75);
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 600;
            }}


            #SettingsTitle {{
                color: {Theme.PRIMARY};
                font-size: {28 if not self.compact_mode else 22}px;
                font-weight: 900;
            }}

            #SettingsDesc {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
            }}


            #SystemLogCard {{
                background: #dcdcdc;
                border: none;
                border-radius: {card_radius}px;
            }}

            #SystemLogCard #FaceSectionTitle {{
                color: #3F3F3F;
            }}

            #SystemLogCard #GreenDot {{
                color: #22C55E;
            }}


            #SettingsTitle {{
                color: {Theme.PRIMARY};
                font-size: {34 if not self.compact_mode else 24}px;
                font-weight: 900;
                letter-spacing: -0.02em;
            }}

            #SettingsDesc {{
                color: {Theme.SECONDARY};
                font-size: {15 if not self.compact_mode else 12}px;
            }}

            #SettingsCardTitle {{
                color: {Theme.PRIMARY};
                font-size: {18 if not self.compact_mode else 15}px;
                font-weight: 800;
            }}

            #SettingsCardIcon {{
                color: {Theme.PRIMARY};
                font-size: {22 if not self.compact_mode else 18}px;
                font-weight: 800;
            }}

            #SettingsDivider {{
                background: {Theme.BORDER};
                border: none;
            }}

            #SettingsLabel {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #SettingsInput {{
                background: white;
                color: {Theme.PRIMARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
                padding: 0px 12px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 400;
                selection-background-color: {Theme.PRIMARY};
                selection-color: white;
            }}

            #SettingsInput:hover {{
                border: 1px solid #747878;
            }}

            #SettingsInput:focus {{
                border: 1px solid {Theme.PRIMARY};
            }}

            #SettingsInput:disabled {{
                background: #E5E7EB;
                color: {Theme.MUTED};
                border: 1px solid #D1D5DB;
            }}

            #SettingsReadonlyBox {{
                background: {Theme.SURFACE_LOW};
                color: {Theme.SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
                padding: 10px 12px;
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 400;
            }}

            #SettingsPrimaryButton {{
                background: {Theme.PRIMARY};
                color: white;
                border: none;
                border-radius: 9px;
                padding: 0px 16px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #SettingsPrimaryButton:hover {{
                background: #2F3131;
            }}

            #SettingsPrimaryButton:pressed {{
                background: #444748;
                padding-top: 2px;
            }}

            #SettingsDangerButton {{
                background: {Theme.RED};
                color: white;
                border: none;
                border-radius: 9px;
                padding: 0px 16px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #SettingsDangerButton:hover {{
                background: #B91C1C;
            }}

            #SettingsDangerButton:pressed {{
                background: #991B1B;
                padding-top: 2px;
            }}

            #SettingsSecondaryButton {{
                background: {Theme.SURFACE_LOW};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
                padding: 0px 16px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #SettingsSecondaryButton:hover {{
                background: #E2E2E2;
            }}

            #SettingsSquareButton {{
                background: {Theme.SURFACE_LOW};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
                padding: 0px;
            }}

            #SettingsSquareButton:hover {{
                background: #E2E2E2;
            }}

            #SettingsInnerPanel {{
                background: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
            }}

            #SettingsMiniTitle {{
                color: {Theme.PRIMARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
            }}

            #SettingsMiniDesc {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
            }}

            #SettingsOptionText {{
                color: {Theme.SECONDARY};
                font-size: {13 if not self.compact_mode else 11}px;
            }}


            #SettingsCheckBoxButton {{
                background: white;
                color: transparent;
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                font-size: 14px;
                font-weight: 900;
            }}

            #SettingsCheckBoxButton:hover {{
                border: 1px solid {Theme.PRIMARY};
                background: #F3F3F3;
            }}

            #SettingsCheckBoxButton:checked {{
                background: {Theme.PRIMARY};
                color: white;
                border: 1px solid {Theme.PRIMARY};
            }}

            #SettingsCheckBoxButton:pressed {{
                background: #333333;
            }}


            #SettingsCheckBox {{
                color: white;
                font-size: 12px;
                font-weight: 900;
                spacing: 0px;
            }}

            #SettingsCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 5px;
                border: 1px solid {Theme.BORDER};
                background: white;
            }}

            #SettingsCheckBox::indicator:hover {{
                border: 1px solid {Theme.PRIMARY};
                background: #F3F3F3;
            }}

            #SettingsCheckBox::indicator:checked {{
                background: {Theme.PRIMARY};
                border: 1px solid {Theme.PRIMARY};
            }}

            #SettingsCheckBox::indicator:unchecked {{
                background: white;
                border: 1px solid {Theme.BORDER};
            }}

            


            #SegmentedToggle {{
                background: {Theme.SURFACE_LOW};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
            }}

            #SegmentSnakeIndicator {{
                background: {Theme.PRIMARY};
                border: none;
                border-radius: 7px;
            }}

            #SegmentButtonActive {{
                background: transparent;
                color: white;
                border: none;
                border-radius: 7px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 900;
            }}

            #SegmentButtonInactive {{
                background: transparent;
                color: {Theme.SECONDARY};
                border: none;
                border-radius: 7px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #SegmentButtonInactive:hover {{
                background: rgba(255, 255, 255, 0.45);
                color: {Theme.PRIMARY};
            }}

            #SegmentButtonActive:hover {{
                color: white;
            }}


            #SettingsConnected {{
                color: #16A34A;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #SettingsDisconnected {{
                color: {Theme.RED};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #AdminListScroll {{
                background: transparent;
                border: none;
            }}

            #AdminListScroll QWidget {{
                background: transparent;
            }}

            #AdminListBox {{
                background: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
            }}

            #AdminRow {{
                border-bottom: 1px solid {Theme.BORDER};
                background: transparent;
            }}

            #AdminName {{
                color: {Theme.PRIMARY};
                font-size: {13 if not self.compact_mode else 11}px;
                font-weight: 700;
            }}

            #RemoveButton {{
                background: transparent;
                border: none;
                color: {Theme.RED};
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #RemoveButton:hover {{
                text-decoration: underline;
            }}

            #SettingsActionBar {{
                background: transparent;
                border: none;
            }}




            #CameraPreviewStoppedLabel {{
                background: #020617;
                color: #CBD5E1;
                border-radius: 12px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }}

            #CameraStateStopBadge {{
                background: #DC2626;
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 7px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.8px;
                padding: 0 10px;
            }}


            #CameraStateLiveBadge {{
                background: #3F9468;
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 7px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.8px;
                padding: 0 10px;
            }}

            #CameraStateEndBadge {{
                background: #20242C;
                color: #B8BEC7;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 7px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.8px;
                padding: 0 10px;
            }}


            #CameraFeedCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #111827,
                    stop:0.5 #334155,
                    stop:1 #0F172A);
                border-radius: {card_radius}px;
            }}

            #LiveBadge, #QualityBadge {{
                background: rgba(0, 0, 0, 0.38);
                color: white;
                border-radius: 14px;
                padding: 6px 12px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 1.5px;
            }}

            #LiveBadge {{
                color: white;
            }}

            #QualityBadge {{
                background: rgba(63, 148, 104, 0.80);
            }}

            #ScanBox {{
                color: rgba(255, 255, 255, 0.72);
                font-family: Consolas;
                font-size: {18 if not self.compact_mode else 14}px;
                font-weight: 700;
            }}

            #CameraPreviewLabel {{
                background: #111827;
                color: rgba(255, 255, 255, 0.72);
                border-radius: 18px;
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 700;
            }}

            #CameraMeta {{
                color: rgba(255, 255, 255, 0.45);
                font-family: Consolas;
                font-size: {10 if not self.compact_mode else 9}px;
            }}

            #FaceSectionTitle {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 2px;
            }}


            #NtidInputError {{
                background: #FFF5F5;
                color: {Theme.TEXT};
                border: 2px solid #DC2626;
                border-radius: 12px;
                padding-left: 14px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #NtidInputError::placeholder {{
                color: #DC2626;
            }}


            #NtidInput {{
                background: rgba(255, 255, 255, 0.74);
                color: {Theme.PRIMARY};
                border: 1px solid rgba(26, 28, 28, 0.26);
                border-radius: 10px;
                padding: 0px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 600;
                selection-background-color: {Theme.GREEN_CARD};
                selection-color: white;
            }}

            #NtidInput:hover {{
                border: 1px solid rgba(26, 28, 28, 0.45);
                background: white;
            }}

            #NtidInput:focus {{
                border: 1px solid {Theme.PRIMARY};
                background: white;
            }}

            #OutlineActionButton {{
                background: rgba(255, 255, 255, 0.52);
                color: {Theme.PRIMARY};
                border: 1px solid rgba(26, 28, 28, 0.65);
                border-radius: 10px;
                min-height: 32px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 800;
                letter-spacing: 0.7px;
                padding: 0px 8px;
            }}

            #OutlineActionButton:hover {{
                background: {Theme.PRIMARY};
                color: white;
                border: 1px solid {Theme.PRIMARY};
            }}

            #OutlineActionButton:pressed {{
                background: #333333;
                color: white;
                padding-top: 1px;
            }}

            #GreenActionButton {{
                background: {Theme.GREEN_CARD};
                color: white;
                border: 1px solid {Theme.GREEN_CARD};
                border-radius: 10px;
                min-height: 32px;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 850;
                letter-spacing: 0.8px;
                padding: 0px 8px;
            }}

            #GreenActionButton:hover {{
                background: #327A53;
                border: 1px solid #327A53;
            }}

            #GreenActionButton:pressed {{
                background: #276342;
                padding-top: 1px;
            }}

            /* Make disabled recognition visibly grey during Capture. */
            #GreenActionButton:disabled {{
                background: #D1D5DB;
                color: #6B7280;
                border: 1px solid #B8C0CC;
            }}

            #StopButton {{
                background: rgba(220, 38, 38, 0.04);
                color: {Theme.RED};
                border: 1px solid rgba(220, 38, 38, 0.35);
                border-radius: 9px;
                min-height: 30px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 850;
                letter-spacing: 0.4px;
            }}

            #StopButton:hover {{
                background: {Theme.RED};
                color: white;
                border: 1px solid {Theme.RED};
            }}

            #StopButton:pressed {{
                background: #B91C1C;
                padding-top: 1px;
            }}

            #DeleteButton {{
                background: rgba(255, 255, 255, 0.52);
                color: {Theme.SECONDARY};
                border: 1px solid {Theme.BORDER};
                border-radius: 9px;
                min-height: 30px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 850;
                letter-spacing: 0.4px;
            }}

            #DeleteButton:hover {{
                background: {Theme.PRIMARY};
                color: white;
                border: 1px solid {Theme.PRIMARY};
            }}

            #DeleteButton:pressed {{
                background: #333333;
                padding-top: 1px;
            }}

            #FaceSystemLogScroll {{
                background: transparent;
                border: none;
            }}

            #FaceSystemLogBody {{
                background: transparent;
            }}

            #LogText {{
                color: #2F2F2F;
                font-family: Consolas;
                font-size: {11 if not self.compact_mode else 10}px;
                line-height: 1.8;
            }}

            #FaceUsersScroll {{
                background: transparent;
                border: none;
            }}

            #FaceUsersBody {{
                background: transparent;
            }}

            #FaceUserSearchBox {{
                background: rgba(255, 255, 255, 0.62);
                border: 1px solid rgba(196, 199, 199, 0.75);
                border-radius: 14px;
            }}

            #FaceUserSearchBox:hover {{
                background: rgba(255, 255, 255, 0.86);
                border: 1px solid rgba(0, 0, 0, 0.18);
            }}

            #FaceUserSearchIcon {{
                color: {Theme.SECONDARY};
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 700;
            }}

            #FaceUserSearchInput {{
                background: transparent;
                color: {Theme.TEXT};
                border: none;
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 400;
            }}

            #FaceUserExpandCard {{
                background: rgba(255, 255, 255, 0.18);
                border: 1px solid transparent;
                border-radius: 12px;
            }}

            #FaceUserExpandCard:hover {{
                background: rgba(243, 243, 243, 0.92);
                border: 1px solid transparent;
            }}

            #FaceUserExpandCard[expanded="true"] {{
                background: rgba(243, 243, 243, 0.96);
                border: 1px solid transparent;
            }}

            #FaceUserCardLabel {{
                background: transparent;
                color: {Theme.SECONDARY};
                font-size: {9 if not self.compact_mode else 8}px;
                font-weight: 700;
                letter-spacing: 1.1px;
            }}

            #FaceUserCardNtid {{
                background: transparent;
                color: {Theme.PRIMARY};
                font-size: {15 if not self.compact_mode else 13}px;
                font-weight: 800;
            }}

            #FaceUserFramesIcon {{
                background: transparent;
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 700;
            }}

            #FaceUserCardDetail {{
                background: transparent;
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 500;
            }}

            #FaceUserCardActions {{
                background: transparent;
                border: none;
            }}

            #FaceUserCardCaptureButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.4px;
                padding: 0px 8px;
            }}

            #FaceUserCardCaptureButton:hover {{
                background: #2F3131;
            }}

            #FaceUserCardDeleteButton {{
                background: rgba(255, 255, 255, 0.78);
                color: #1F2933;
                border: 1px solid rgba(116, 120, 120, 0.72);
                border-radius: 10px;
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 900;
                letter-spacing: 0.2px;
                padding: 0px 8px;
            }}

            #FaceUserCardDeleteButton:hover {{
                background: rgba(186, 26, 26, 0.08);
                color: #BA1A1A;
                border: 1px solid rgba(186, 26, 26, 0.42);
            }}

            #FaceUserEmptyMessage {{
                color: {Theme.SECONDARY};
                font-size: {12 if not self.compact_mode else 10}px;
                font-weight: 500;
                padding: 10px;
            }}


            #FaceUserRowWrapper {{
                background: transparent;
                border: none;
            }}

            #FaceUserRowWrapper[menuOpen="true"] #FaceUserRow {{
                background: #FFFFFF;
                border: 1px solid rgba(16, 185, 129, 0.22);
            }}

            #FaceUserRow {{
                background: rgba(255, 255, 255, 0.45);
                border: 1px solid transparent;
                border-radius: 18px;
            }}

            #FaceUserRow:hover {{
                background: white;
                border: 1px solid rgba(0, 0, 0, 0.05);
            }}

            #FaceUserMenuChevron {{
                color: {Theme.SECONDARY};
                font-size: {14 if not self.compact_mode else 12}px;
                font-weight: 900;
                background: transparent;
            }}

            #FaceUserQuickMenu {{
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(196, 199, 199, 0.75);
                border-radius: 12px;
                margin-left: 6px;
                margin-right: 6px;
            }}

            #FaceUserMenuTitle {{
                color: {Theme.SECONDARY};
                font-size: {10 if not self.compact_mode else 9}px;
                font-weight: 800;
                letter-spacing: 1.4px;
            }}

            #FaceUserMenuNtid {{
                color: {Theme.PRIMARY};
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #FaceUserCaptureButton {{
                background: #000000;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                padding: 0px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #FaceUserCaptureButton:hover {{
                background: #2F3131;
            }}

            #FaceUserDeleteButton {{
                background: rgba(255, 255, 255, 0.72);
                color: #BA1A1A;
                border: 1px solid rgba(186, 26, 26, 0.32);
                border-radius: 10px;
                padding: 0px 12px;
                font-size: {11 if not self.compact_mode else 10}px;
                font-weight: 800;
            }}

            #FaceUserDeleteButton:hover {{
                background: rgba(186, 26, 26, 0.08);
                border: 1px solid rgba(186, 26, 26, 0.55);
            }}
        """)
