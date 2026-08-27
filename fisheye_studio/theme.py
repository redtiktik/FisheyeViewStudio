from __future__ import annotations


APP_STYLE = r"""
* {
    font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
    font-size: 10pt;
    color: #E8EEF7;
}

QMainWindow, QWidget#AppRoot {
    background: #07111F;
}

QScrollArea, QAbstractScrollArea, QViewport {
    background: transparent;
    border: none;
}

QFrame#HeaderCard, QFrame#Card, QFrame#RenderBar {
    background: #0D1A2B;
    border: 1px solid #1B2B40;
    border-radius: 14px;
}

QFrame#HeaderCard {
    background: #0B1727;
}

QLabel#AppTitle {
    font-size: 20pt;
    font-weight: 700;
    color: #F8FAFC;
}

QLabel#SectionTitle {
    font-size: 13pt;
    font-weight: 700;
    color: #F5F8FC;
}

QLabel#Subtitle, QLabel#MutedLabel {
    color: #94A7BE;
}

QLabel#FilePath {
    background: #081321;
    border: 1px solid #1B2B40;
    border-radius: 9px;
    padding: 8px 10px;
    color: #C9D6E6;
}

QPushButton {
    background: #17263A;
    border: 1px solid #29405C;
    border-radius: 9px;
    padding: 8px 13px;
    font-weight: 600;
}

QPushButton:hover {
    background: #203550;
    border-color: #3A5A7D;
}

QPushButton:pressed {
    background: #122237;
}

QPushButton:disabled {
    color: #5F7188;
    background: #101B2A;
    border-color: #1B2A3D;
}

QPushButton#PrimaryButton {
    background: #0E7490;
    border-color: #22B8D6;
    color: white;
    padding: 10px 18px;
}

QPushButton#PrimaryButton:hover {
    background: #0F88A7;
}

QPushButton#DangerButton {
    background: #3A1821;
    border-color: #703044;
    color: #FBC6D1;
}

QPushButton#DangerButton:hover {
    background: #4A1D29;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTimeEdit {
    background: #081321;
    border: 1px solid #23364D;
    border-radius: 8px;
    padding: 7px 9px;
    selection-background-color: #0E7490;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTimeEdit:focus {
    border-color: #22B8D6;
}

QComboBox::drop-down {
    border: none;
    width: 26px;
}

QComboBox QAbstractItemView {
    background: #0E1B2D;
    border: 1px solid #29405C;
    selection-background-color: #164E63;
    outline: none;
}

QCheckBox {
    spacing: 7px;
}

QCheckBox::indicator {
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid #46627F;
    background: #091422;
}

QCheckBox::indicator:checked {
    background: #0E7490;
    border-color: #22B8D6;
}

QSlider::groove:horizontal {
    height: 5px;
    border-radius: 2px;
    background: #21344A;
}

QSlider::sub-page:horizontal {
    background: #22B8D6;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: #E7F7FB;
    border: 2px solid #0E7490;
}

QListWidget {
    background: #081321;
    border: 1px solid #1F3249;
    border-radius: 9px;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    padding: 8px 9px;
    border-radius: 7px;
}

QListWidget::item:selected {
    background: #164E63;
    color: white;
}

QFrame#PreviewCard {
    background: #0A1626;
    border: 1px solid #1D3148;
    border-radius: 12px;
}

QFrame#PreviewCard:hover {
    border-color: #345777;
    background: #0C1B2D;
}

QFrame#PreviewCard[selected="true"] {
    border: 2px solid #22B8D6;
    background: #0D2032;
}

QFrame#PreviewCard[disabledView="true"] {
    background: #0A121D;
    border-color: #172535;
}

QLabel#PreviewImage {
    background: #040A12;
    border: 1px solid #18283A;
    border-radius: 9px;
    color: #71869E;
}

QLabel#PreviewName {
    font-weight: 700;
    color: #EDF4FC;
}

QLabel#StatusPill {
    border-radius: 10px;
    padding: 5px 10px;
    font-size: 9pt;
    font-weight: 700;
}

QLabel#StatusPill[status="good"] {
    background: #113B31;
    border: 1px solid #23775F;
    color: #A7F3D0;
}

QLabel#StatusPill[status="warning"] {
    background: #3A2C11;
    border: 1px solid #775B23;
    color: #FDE68A;
}

QLabel#StatusPill[status="bad"] {
    background: #3B1820;
    border: 1px solid #7A3041;
    color: #FECACA;
}

QLabel#StatusPill[status="neutral"] {
    background: #142337;
    border: 1px solid #2B4564;
    color: #BED0E4;
}

QProgressBar {
    background: #091422;
    border: 1px solid #20334A;
    border-radius: 8px;
    text-align: center;
    min-height: 18px;
}

QProgressBar::chunk {
    background: #0E7490;
    border-radius: 7px;
}

QPlainTextEdit {
    background: #050B13;
    border: 1px solid #1D2E43;
    border-radius: 9px;
    color: #B8C6D8;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 9pt;
}

QToolButton {
    background: transparent;
    border: none;
    color: #9FB2C9;
    font-weight: 600;
    padding: 5px;
}

QToolButton:hover {
    color: #E7F7FB;
}

QSplitter::handle {
    background: transparent;
}

QScrollBar:vertical {
    background: transparent;
    width: 11px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #2A3E56;
    min-height: 28px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #3B5774;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    height: 0;
    background: none;
}

QToolTip {
    background: #0B1727;
    color: #E8EEF7;
    border: 1px solid #29405C;
    padding: 6px;
}
"""
