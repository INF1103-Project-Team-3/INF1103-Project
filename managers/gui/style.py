# The admin window's look, taken from the compact wireframes (one place to change it).

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette

INK = "#1C1C1A"
INK_SOFT = "#3A3A37"
MUTED = "#5F5F5A"
PAGE = "#F5F5F3"
CARD = "#FFFFFF"
BORDER = "#D9D9D6"
BORDER_SOFT = "#ECECEA"
FIELD_BORDER = "#BDBDB8"
BLUE = "#2F5BEA"
BLUE_DARK = "#1E3FB0"
BLUE_SOFT = "#E8EEFD"
ORANGE = "#C2551B"
ORANGE_DARK = "#9A4512"
ORANGE_SOFT = "#FBE9DD"
ORANGE_TINT = "#FFF6F0"
LOG_TEXT = "#E8E8E3"
LOG_WARN = "#FFD08A"
LOG_ERROR = "#FFB4A0"

FONT_FAMILIES = ["Inter", "Segoe UI", "Arial"]
ASSETS = Path(__file__).resolve().parent / "assets"
ARROW = (ASSETS / "chevron-down.png").as_posix()
ARROW_DISABLED = (ASSETS / "chevron-down-disabled.png").as_posix()
CHECK = (ASSETS / "check.png").as_posix()

STYLE = f"""
QWidget {{ font-size: 14px; color: {INK}; }}
QMainWindow, QStackedWidget, QStackedWidget > QWidget {{ background: {PAGE}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QStatusBar {{ background: {CARD}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px 4px 0; border: none; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0 4px 2px 4px; border: none; }}
QScrollBar::handle:vertical {{ background: #C9C9C4; border-radius: 4px; min-height: 40px; margin: 0 2px; }}
QScrollBar::handle:horizontal {{ background: #C9C9C4; border-radius: 4px; min-width: 40px; margin: 2px 0; }}
QScrollBar::handle:hover {{ background: #A8A8A3; }}
QScrollBar::handle:pressed {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QToolTip {{ background: {INK}; color: #FFFFFF; border: none; padding: 4px 8px; }}

#sidebar {{ background: {CARD}; border-right: 1px solid {BORDER}; }}
#appName {{ font-size: 20px; font-weight: 700; padding: 4px 12px 20px 12px; }}
#navButton {{ border: none; border-radius: 8px; background: transparent; min-height: 44px; }}
#navButton:hover:!checked {{ background: #F2F2EF; }}
#navButton:checked {{ background: {BLUE_SOFT}; }}
#navText {{ font-size: 16px; color: {INK_SOFT}; background: transparent; }}
#navText[active="true"] {{ color: {BLUE_DARK}; font-weight: 600; }}

#pageTitle {{ font-size: 28px; font-weight: 700; }}
#pageSubtitle, #mutedText {{ color: {MUTED}; }}
#smallNote {{ font-size: 12px; color: {MUTED}; }}
#cardTitle {{ font-size: 18px; font-weight: 600; }}
#fieldLabel {{ font-size: 14px; font-weight: 600; }}
#errorText {{ color: {ORANGE_DARK}; font-weight: 600; }}

#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
#card[tone="critical"] {{ background: {ORANGE_TINT}; border-color: #EFC7AE; }}
#statLabel {{ font-size: 13px; color: {MUTED}; background: transparent; }}
#statValue {{ font-size: 32px; font-weight: 700; background: transparent; }}
#statFoot {{ font-size: 12px; color: {MUTED}; background: transparent; }}
#card[tone="critical"] #statLabel, #card[tone="critical"] #statValue,
#card[tone="critical"] #statFoot {{ color: {ORANGE_DARK}; }}
#placeholder {{ background: {CARD}; border: 1px dashed {FIELD_BORDER}; border-radius: 12px;
                padding: 20px; color: {MUTED}; }}

QPushButton {{ background: {CARD}; color: {INK}; border: 1px solid {BORDER}; border-radius: 8px;
               min-height: 44px; padding: 0 16px; font-size: 15px; }}
QPushButton:hover {{ background: #F7F7F5; }}
QPushButton:disabled {{ color: #A8A8A3; background: #FAFAF8; }}
#primaryButton {{ background: {BLUE}; color: #FFFFFF; border: none; font-weight: 600; padding: 0 18px; }}
#primaryButton:hover {{ background: #2850D4; }}
#primaryButton:disabled {{ background: #9DB0EE; color: #FFFFFF; }}
#bigPrimaryButton {{ background: {BLUE}; color: #FFFFFF; border: none; border-radius: 10px;
                     font-weight: 600; min-height: 48px; padding: 0 24px; font-size: 16px; }}
#bigPrimaryButton:hover {{ background: #2850D4; }}
#bigPrimaryButton:disabled {{ background: #9DB0EE; }}
#dangerButton {{ color: {ORANGE_DARK}; border-color: #E3B9A0; }}
#dangerButton:hover {{ background: {ORANGE_TINT}; }}
#segment {{ border: none; border-radius: 0; background: {CARD}; color: {INK_SOFT}; font-size: 14px; }}
#segment[side="left"] {{ border-top-left-radius: 9px; border-bottom-left-radius: 9px; }}
#segment[side="right"] {{ border-top-right-radius: 9px; border-bottom-right-radius: 9px; }}
#segment:checked {{ background: {INK}; color: #FFFFFF; font-weight: 600; }}
#segmentGroup {{ border: 1px solid {BORDER}; border-radius: 10px; background: {CARD}; }}

QLineEdit, QComboBox, QDateEdit {{ background: {CARD}; color: {INK}; border: 1px solid {BORDER};
                                   border-radius: 8px; min-height: 40px; padding: 0 10px; }}
QComboBox, QDateEdit {{ padding-right: 32px; combobox-popup: 0; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{ border-color: {BLUE}; }}
QComboBox:disabled, QDateEdit:disabled {{ color: #A8A8A3; background: #FAFAF8; }}
QComboBox[mismatch="true"] {{ border-color: {ORANGE}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
                                              width: 30px; border: none; background: transparent; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{ARROW}"); width: 12px; height: 12px; }}
QComboBox::down-arrow:disabled, QDateEdit::down-arrow:disabled {{ image: url("{ARROW_DISABLED}"); }}
QComboBox QAbstractItemView {{ background: {CARD}; color: {INK}; border: 1px solid {BORDER};
                               padding: 4px; outline: 0; }}
QComboBox QAbstractItemView::item {{ min-height: 32px; padding: 0 10px; border-radius: 6px; }}
QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {{
    background: {BLUE_SOFT}; color: {BLUE_DARK}; }}
#searchBox {{ border-color: {FIELD_BORDER}; border-radius: 10px; min-height: 44px; padding: 0 14px; font-size: 15px; }}
QWidget[dialogField="true"] {{ border-color: {FIELD_BORDER}; min-height: 44px; }}
QAbstractItemView {{ background: {CARD}; color: {INK}; selection-background-color: {BLUE_SOFT};
                     selection-color: {BLUE_DARK}; }}
QCalendarWidget QWidget {{ background: {CARD}; color: {INK}; }}

#pill {{ font-size: 12px; font-weight: 600; border-radius: 9px; padding: 2px 8px; }}
#pill[kind="critical"] {{ background: {ORANGE}; color: #FFFFFF; }}
#pill[kind="warn"]     {{ background: {ORANGE_SOFT}; color: {ORANGE_DARK}; }}
#pill[kind="info"]     {{ background: {BLUE_SOFT}; color: {BLUE_DARK}; }}
#pill[kind="caution"]  {{ background: #FFF3D6; color: #7A5300; }}
#pill[kind="good"]     {{ background: #E3F1E6; color: #1E6B34; }}
#pill[kind="neutral"]  {{ background: {BORDER_SOFT}; color: #4A4A46; }}
#pill[kind="running"]  {{ background: transparent; color: {BLUE_DARK}; }}

#entryCard {{ background: {CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 10px; }}
#entryCard:hover {{ border-color: {BORDER}; }}
#entryCard[selected="true"] {{ background: #F5F8FF; border: 2px solid {BLUE}; }}
#entryCard[selected="true"][critical="true"] {{ background: {ORANGE_TINT}; border: 2px solid {ORANGE}; }}
#entryText {{ font-size: 14px; background: transparent; }}
#entryMeta {{ font-size: 12px; color: {MUTED}; background: transparent; }}

#detailId {{ font-size: 18px; font-weight: 600; }}
#detailDate {{ font-size: 13px; color: {MUTED}; }}
#feedbackText {{ background: {PAGE}; border-radius: 8px; padding: 16px; font-size: 15px; }}
#reasonList {{ color: {INK_SOFT}; }}
#gridHeader {{ font-size: 12px; font-weight: 600; color: {MUTED}; }}
#fieldRow {{ border-top: 1px solid {BORDER_SOFT}; background: transparent; }}
#fieldRow[mismatch="true"] {{ background: {ORANGE_TINT}; }}
#fieldName {{ font-weight: 600; background: transparent; }}
#fieldValue {{ background: transparent; }}
#fieldValue[mismatch="true"] {{ color: {ORANGE_DARK}; font-weight: 600; }}
#buttonRow {{ border-top: 1px solid {BORDER_SOFT}; background: transparent; }}

#progressCard {{ background: {CARD}; border: 2px solid {BLUE}; border-radius: 12px; }}
#progressCard[idle="true"] {{ border: 1px solid {BORDER}; }}
QProgressBar {{ background: {BORDER_SOFT}; border: none; border-radius: 6px; }}
QProgressBar::chunk {{ background: {BLUE}; border-radius: 6px; }}
#statusLine {{ font-size: 13px; color: {MUTED}; background: transparent; }}
#runLog {{ font-family: "JetBrains Mono", "Consolas", monospace; font-size: 13px; background: {INK};
           color: {LOG_TEXT}; border: none; border-radius: 8px; padding: 10px 12px; }}

#actionRow {{ border-top: 1px solid {BORDER_SOFT}; background: transparent; }}
#actionTitle {{ font-size: 15px; font-weight: 600; background: transparent; }}
#actionMeta {{ font-size: 13px; color: {MUTED}; background: transparent; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; background: {CARD};
                                                 border: 1.5px solid {FIELD_BORDER}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {INK_SOFT}; }}
QCheckBox::indicator:checked {{ background: {BLUE}; border-color: {BLUE}; image: url("{CHECK}"); }}
QRadioButton::indicator:checked {{ background: {CARD}; border: 5px solid {BLUE}; width: 9px; height: 9px; }}
#chartLegendSwatch {{ font-size: 16px; font-weight: 700; background: transparent; }}

#startTitle {{ font-size: 36px; font-weight: 700; }}
#startSubtitle {{ font-size: 16px; color: {MUTED}; }}
#choiceCard {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}
#choiceCard:hover {{ border-color: {FIELD_BORDER}; }}
#choiceCard[selected="true"] {{ background: {BLUE_SOFT}; border: 2px solid {BLUE}; }}
#choiceKicker {{ font-size: 13px; font-weight: 600; color: {MUTED}; background: transparent; }}
#choiceCard[selected="true"] #choiceKicker {{ color: {BLUE_DARK}; }}
#choiceTitle {{ font-size: 20px; font-weight: 700; background: transparent; }}
#choiceText {{ font-size: 14px; color: {MUTED}; background: transparent; }}
#loginCard {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}
#passwordBox {{ min-height: 48px; border: 1px solid {FIELD_BORDER}; border-radius: 10px; padding: 0 14px; font-size: 15px; }}
#passwordBox[error="true"] {{ border: 2px solid {ORANGE}; }}
#largeButton {{ min-height: 48px; border-radius: 10px; padding: 0 20px; }}

#topBar {{ background: {CARD}; border-bottom: 1px solid {BORDER}; }}
#linkButton {{ border: none; background: transparent; color: {BLUE}; font-size: 14px; font-weight: 600;
               min-height: 44px; padding: 0 4px; }}
#linkButton:hover {{ color: {BLUE_DARK}; text-decoration: underline; background: transparent; }}
#formCard {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 16px; }}
#formTitle {{ font-size: 28px; font-weight: 700; }}
#formIntro {{ font-size: 15px; color: {MUTED}; }}
#questionLabel {{ font-size: 15px; font-weight: 600; }}
#feedbackBox {{ background: {CARD}; border: 1px solid {FIELD_BORDER}; border-radius: 10px; padding: 8px;
                font-size: 15px; }}
#feedbackBox:focus, #studentTheme:focus {{ border-color: {BLUE}; }}
#studentTheme {{ min-height: 48px; border: 1px solid {FIELD_BORDER}; border-radius: 10px; padding: 0 14px; font-size: 15px; }}
#chip {{ min-height: 36px; border-radius: 18px; padding: 0 12px; font-size: 13px; }}
#optionCard {{ background: {CARD}; border: 1px solid {FIELD_BORDER}; border-radius: 10px; }}
#optionCard:hover {{ border-color: {INK_SOFT}; }}
#optionCard[selected="true"] {{ background: {BLUE_SOFT}; border: 2px solid {BLUE}; }}
#optionCard[tone="critical"] {{ background: {ORANGE_TINT}; border-color: {ORANGE}; }}
#optionCard[tone="critical"][selected="true"] {{ border: 2px solid {ORANGE}; }}
#optionCard QRadioButton {{ font-size: 15px; font-weight: 600; background: transparent; }}
#optionCard[tone="critical"] QRadioButton {{ color: {ORANGE_DARK}; }}
#optionText {{ font-size: 13px; color: {MUTED}; background: transparent; }}
#helpBox {{ background: {ORANGE_TINT}; border: 1px solid #F0CDB6; border-radius: 10px; }}
#helpTitle {{ font-size: 14px; font-weight: 600; color: {ORANGE_DARK}; background: transparent; }}
#helpText {{ font-size: 14px; background: transparent; }}
#successBanner {{ background: #E3F1E6; border: 1px solid #A9D3B4; border-radius: 12px; }}
#successIcon {{ background: #1E6B34; color: #FFFFFF; border-radius: 16px; font-size: 17px; font-weight: 700; }}
#successTitle {{ font-size: 15px; font-weight: 600; color: #1E6B34; background: transparent; }}
#successText {{ font-size: 14px; color: {INK_SOFT}; background: transparent; }}

QDialog {{ background: {CARD}; }}
QMessageBox {{ background: {CARD}; }}
#dialogTitle {{ font-size: 20px; font-weight: 700; }}
"""


# Inter if it is installed, otherwise Segoe UI (Windows) or Arial.
def app_font() -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(14)
    return font


# A light palette, so Windows dark mode doesn't turn boxes dark under our dark text.
def light_palette() -> QPalette:
    palette = QPalette()
    colours = {
        QPalette.ColorRole.Window: PAGE, QPalette.ColorRole.WindowText: INK,
        QPalette.ColorRole.Base: CARD, QPalette.ColorRole.AlternateBase: PAGE,
        QPalette.ColorRole.Text: INK, QPalette.ColorRole.Button: CARD,
        QPalette.ColorRole.ButtonText: INK, QPalette.ColorRole.Highlight: BLUE_SOFT,
        QPalette.ColorRole.HighlightedText: BLUE_DARK, QPalette.ColorRole.ToolTipBase: INK,
        QPalette.ColorRole.ToolTipText: "#FFFFFF", QPalette.ColorRole.PlaceholderText: "#8A8A85",
        QPalette.ColorRole.Link: BLUE,
    }
    for role, colour in colours.items():
        palette.setColor(role, QColor(colour))
    return palette


# Re-applies the style sheet after a dynamic property (e.g. selected) changes.
def restyle(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
