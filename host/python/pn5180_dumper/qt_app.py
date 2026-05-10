import json
import sys
import time
from queue import Empty, Queue
from pathlib import Path

import serial
from serial.tools import list_ports

from PyQt5.QtCore import QSettings, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QShortcut,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .capture import DumpCapture, parse_new_metadata, save_capture
from .keys import load_local_mfc_keys


DEFAULT_BAUD = 460800
BRUTE_ATTEMPT_TIMEOUT_MS = 6000
BRUTE_BATCH_TIMEOUT_MS = 60000
BRUTE_BATCH_SIZE = 8
BRUTE_PROGRESS_PATH = Path("captures") / "brute_progress.json"
APP_TITLE = "PNDumper by Magical_Poof"
LOGO_FILE_NAME = "d20.png"


def app_logo_path() -> Path | None:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "assets" / LOGO_FILE_NAME)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / LOGO_FILE_NAME)
    project_root = Path(__file__).resolve().parents[3]
    candidates.extend(
        [
            Path.cwd() / LOGO_FILE_NAME,
            project_root / "scripts" / LOGO_FILE_NAME,
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class HexTableWidget(QTableWidget):
    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.matches(QKeySequence.Copy):
            self.copy_selection_to_clipboard()
            return
        super().keyPressEvent(event)

    def copy_selection_to_clipboard(self) -> None:
        ranges = self.selectedRanges()
        if not ranges:
            return

        selected = ranges[0]
        rows: list[str] = []
        for row in range(selected.topRow(), selected.bottomRow() + 1):
            values: list[str] = []
            for column in range(selected.leftColumn(), selected.rightColumn() + 1):
                item = self.item(row, column)
                values.append(item.text() if item else "")
            rows.append("\t".join(values))

        QApplication.clipboard().setText("\n".join(rows))


class SerialCaptureWorker(QThread):
    line_received = pyqtSignal(str)
    record_saved = pyqtSignal(dict, str)
    status_changed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, port: str, baud: int, out_dir: Path, once: bool) -> None:
        super().__init__()
        self.port = port
        self.baud = baud
        self.out_dir = out_dir
        self.once = once
        self._stop_requested = False
        self._command_queue: Queue[str] = Queue()

    def stop(self) -> None:
        self._stop_requested = True

    def send_command(self, command: str) -> None:
        self._command_queue.put(command)

    def run(self) -> None:
        capture = DumpCapture()
        try:
            with serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=0.25,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                dsrdtr=False,
                rtscts=False,
            ) as ser:
                ser.dtr = False
                ser.rts = False
                self.status_changed.emit(f"Connected to {self.port} @ {self.baud}")
                time.sleep(0.3)

                while not self._stop_requested:
                    while True:
                        try:
                            command = self._command_queue.get_nowait()
                        except Empty:
                            break
                        ser.write((command.strip() + "\n").encode("ascii", errors="ignore"))
                        ser.flush()

                    raw = ser.readline()
                    if not raw:
                        continue

                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue

                    self.line_received.emit(line)
                    try:
                        complete = capture.feed(line)
                    except Exception as exc:
                        self.failed.emit(f"Parser warning: {exc}")
                        capture.reset()
                        continue

                    if complete:
                        target_dir = save_capture(capture, self.out_dir)
                        metadata = capture.metadata
                        payload = {
                            "type": metadata.tag_type if metadata else "-",
                            "uid": metadata.uid if metadata else "-",
                            "rc": metadata.rc if metadata else "-",
                            "block_size": metadata.block_size if metadata else None,
                            "num_blocks": metadata.num_blocks if metadata else None,
                            "has_dump": bool(capture.compact_hex_lines),
                            "byte_length": sum(len(bytes.fromhex(line)) for line in capture.compact_hex_lines),
                            "block_statuses": list(capture.compact_block_statuses),
                        }
                        if metadata:
                            payload.update(metadata.extra)
                        self.record_saved.emit(payload, str(target_dir))
                        capture.reset()
                        if self.once:
                            break

                self.status_changed.emit("Disconnected")
        except serial.SerialException as exc:
            self.failed.emit(f"Serial error: {exc}")
        except Exception as exc:
            self.failed.emit(f"Unexpected error: {exc}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.worker: SerialCaptureWorker | None = None
        self.settings = QSettings("PN5180Dumper", "PN5180Dumper")
        self.current_metadata: dict | None = None
        self.current_folder: Path | None = None
        self.current_dump_bytes = b""
        self.current_block_statuses: list[str] = []
        self.write_bytes = b""
        self.brute_keys: list[str] = []
        self.brute_queue: list[tuple[int, str, str]] = []
        self.brute_total = 0
        self.brute_checked = 0
        self.brute_current_block: int | None = None
        self.brute_current_sector_blocks: list[int] = []
        self.brute_recovered_blocks: set[int] = set()
        self.brute_sector_found = False
        self.brute_pending_blocks: list[int] = []
        self.brute_all_mode = False
        self.brute_total_sectors = 0
        self.brute_done_sectors = 0
        self.brute_current_attempt: tuple[int, str, str] | None = None
        self.brute_current_batch: list[tuple[int, str, str]] = []
        self.brute_batch_counter = 0
        self.brute_active_batch_id: str | None = None
        self.brute_waiting_for_result = False
        self.brute_waiting_for_sector_results = False
        self.brute_running = False
        self.write_queue: list[tuple[int, bytes]] = []
        self.write_total = 0
        self.write_done = 0
        self.write_failures: list[str] = []
        self.write_running = False
        self.write_uid_block_requested = False
        self.write_uid_block_verified = False
        self.read_running = False
        self.last_logged_device_state: str | None = None

        self.setWindowTitle(APP_TITLE)
        self.resize(1080, 720)
        self.logo_path = app_logo_path()
        if self.logo_path:
            self.setWindowIcon(QIcon(str(self.logo_path)))
        self.apply_dark_theme()

        self.reader_indicator = QLabel()
        self.reader_state_label = QLabel("Reader: offline")
        self.port_combo = QComboBox()

        self.refresh_ports_button = QPushButton("Refresh ports")
        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)

        self.scan_button = QPushButton("Scan devices")
        self.scan_button.setEnabled(False)
        self.scan_button.setToolTip("Reserved for firmware command protocol V2")

        self.status_label = QLabel("Idle")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)

        self.tag_indicator = QLabel()
        self.current_device_label = QLabel("Current tag: none")
        self.current_device_refresh_button = QPushButton("Refresh")
        self.current_device_refresh_button.setEnabled(False)
        self.device_field_labels: dict[str, QLabel] = {}

        self.mode_tabs = QTabWidget()
        self.read_export_path_edit = QLineEdit(str(self.settings.value("paths/read_export", "")))
        self.read_export_browse_button = QPushButton("Browse")
        self.read_export_button = QPushButton("Export dump")
        self.read_export_button.setEnabled(False)
        self.read_button = QPushButton("Read")
        self.read_button.setEnabled(False)
        self.hex_table_scale = int(self.settings.value("ui/hex_table_scale", 100))
        self.hex_table_scale = max(70, min(180, self.hex_table_scale))
        self.read_hex_table = self._create_hex_table(action_columns=True)
        self.start_brute_button = QPushButton("Start Brute")
        self.start_brute_button.setEnabled(False)
        self.stop_brute_button = QPushButton("Stop Brute")
        self.stop_brute_button.setEnabled(False)
        self.reset_button = QPushButton("RESET")
        self.brute_progress_bar = QProgressBar()
        self.brute_progress_bar.setRange(0, 1)
        self.brute_progress_bar.setValue(0)
        self.brute_progress_label = QLabel("Brute: idle")

        self.write_address_spin = QSpinBox()
        self.write_address_spin.setRange(0, 65535)
        self.write_import_path_edit = QLineEdit(str(self.settings.value("paths/write_import", "")))
        self.write_import_browse_button = QPushButton("Browse")
        self.write_load_button = QPushButton("Load file")
        self.write_hex_table = self._create_hex_table()
        self.write_verify_check = QCheckBox("Verify after write")
        self.write_verify_check.setChecked(True)
        self.write_uid_block_check = QCheckBox("Write UID block 0 (magic only)")
        self.write_uid_block_check.setToolTip("Dangerous: only for UID-changeable magic cards.")
        self.magic_probe_button = QPushButton("Probe magic UID")
        self.magic_probe_button.setToolTip("Checks whether the current tag answers the Gen1A magic backdoor.")
        self.write_button = QPushButton("Write")
        self.write_button.setEnabled(False)
        self.write_button.setToolTip("Writes safe MIFARE Classic data blocks, skipping UID and trailer blocks")

        self._build_layout()
        self._connect_signals()
        self.scan_timer = QTimer(self)
        self.scan_timer.setInterval(800)
        self.scan_timer.timeout.connect(self.auto_scan_current_device)
        self.brute_attempt_timer = QTimer(self)
        self.brute_attempt_timer.setSingleShot(True)
        self.brute_attempt_timer.setInterval(BRUTE_ATTEMPT_TIMEOUT_MS)
        self.brute_attempt_timer.timeout.connect(self.handle_brute_attempt_timeout)
        self.update_write_verify_dependency(self.write_uid_block_check.isChecked())
        self._set_indicator(self.reader_indicator, False)
        self._set_indicator(self.tag_indicator, False)
        self.refresh_ports()
        self.apply_hex_table_scale(announce=False)

    def _build_layout(self) -> None:
        root = QWidget()
        main_layout = QVBoxLayout(root)

        connection_box = QGroupBox("Connection")
        connection_layout = QGridLayout(connection_box)
        reader_row = QHBoxLayout()
        reader_row.addWidget(self.reader_indicator)
        reader_row.addWidget(self.reader_state_label)
        reader_row.addStretch(1)
        connection_layout.addLayout(reader_row, 0, 0, 1, 6)
        connection_layout.addWidget(QLabel("Port"), 1, 0)
        connection_layout.addWidget(self.port_combo, 1, 1, 1, 5)

        button_row = QHBoxLayout()
        button_row.addWidget(self.refresh_ports_button)
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.disconnect_button)
        button_row.addStretch(1)
        connection_layout.addLayout(button_row, 3, 0, 1, 6)

        devices_box = QGroupBox("Current device")
        devices_layout = QVBoxLayout(devices_box)
        current_row = QHBoxLayout()
        current_row.addWidget(self.tag_indicator)
        current_row.addWidget(self.current_device_label)
        current_row.addStretch(1)
        current_row.addWidget(self.current_device_refresh_button)
        devices_layout.addLayout(current_row)
        details_grid = QGridLayout()
        details_grid.setHorizontalSpacing(18)
        details_grid.setVerticalSpacing(6)
        for index, (key, title) in enumerate(self._device_detail_fields()):
            field_widget = QWidget()
            field_layout = QHBoxLayout(field_widget)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(6)
            field_widget.setFixedWidth(340 if key == "family" else 265)

            title_widget = self._device_title_widget(key, title)
            title_widget.setFixedWidth(95)
            value_label = QLabel("-")
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_label.setMinimumWidth(0)
            value_label.setMaximumWidth(235 if key == "family" else 160)
            value_label.setWordWrap(False)
            self.device_field_labels[key] = value_label

            field_layout.addWidget(title_widget)
            field_layout.addWidget(value_label, 1)
            row = index // 4
            column = index % 4
            details_grid.addWidget(field_widget, row, column)
        details_grid.setColumnStretch(4, 1)
        devices_layout.addLayout(details_grid)

        mode_box = QGroupBox("Mode")
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.addWidget(self.mode_tabs)
        self.mode_tabs.addTab(self._build_read_tab(), "Read")
        self.mode_tabs.addTab(self._build_write_tab(), "Write")

        log_box = QGroupBox("Diagnostic serial log")
        log_layout = QVBoxLayout(log_box)
        log_layout.addWidget(self.log_view)

        main_layout.addWidget(connection_box)
        main_layout.addWidget(devices_box)
        main_layout.addWidget(mode_box, 5)
        main_layout.addWidget(log_box, 2)
        main_layout.addWidget(self.status_label)

        self.setCentralWidget(root)

    def apply_dark_theme(self) -> None:
        QApplication.instance().setStyleSheet("""
            QWidget {
                background: #11151c;
                color: #d8dee9;
                selection-background-color: #2f6f9f;
                selection-color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #263241;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                background: #141a22;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #9fb3c8;
            }
            QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
                background: #0c1016;
                color: #e5e9f0;
                border: 1px solid #2b3646;
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton, QToolButton {
                background: #1f2a36;
                color: #e5e9f0;
                border: 1px solid #3a4a5d;
                border-radius: 4px;
                padding: 4px 10px;
            }
            QPushButton:hover, QToolButton:hover {
                background: #2b3a4a;
                border-color: #5f7fa3;
            }
            QPushButton:disabled {
                color: #667080;
                background: #151b23;
                border-color: #263241;
            }
            QTabWidget::pane {
                border: 1px solid #263241;
                background: #11151c;
            }
            QTabBar::tab {
                background: #17202a;
                color: #aebdcc;
                border: 1px solid #263241;
                padding: 6px 14px;
            }
            QTabBar::tab:selected {
                background: #243142;
                color: #ffffff;
            }
            QTableWidget {
                background: #0b0f14;
                alternate-background-color: #0f141b;
                color: #dbe6f3;
                border: 1px solid #253142;
                gridline-color: #1d2734;
                selection-background-color: #284d6c;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background: #172231;
                color: #9fb3c8;
                border: 0;
                border-right: 1px solid #263241;
                padding: 4px;
                font-weight: 600;
            }
            QToolTip {
                background: #1b2531;
                color: #e5e9f0;
                border: 1px solid #60728a;
                padding: 6px;
            }
            QProgressBar {
                background: #0c1016;
                border: 1px solid #2b3646;
                border-radius: 4px;
                color: #d8dee9;
                text-align: center;
                min-height: 18px;
            }
            QProgressBar::chunk {
                background: #2f6f9f;
                border-radius: 3px;
            }
        """)

    def _build_read_tab(self) -> QWidget:
        tab = QWidget()
        layout = QGridLayout(tab)
        layout.addWidget(self.read_button, 0, 0)
        layout.addWidget(self.start_brute_button, 0, 1)
        layout.addWidget(self.stop_brute_button, 0, 2)
        layout.addWidget(self.reset_button, 0, 3)
        layout.addWidget(QLabel("Raw dump"), 1, 0, 1, 8)
        layout.addWidget(self.read_hex_table, 2, 0, 1, 8)
        layout.addWidget(self._build_read_side_panel(), 2, 8, 2, 2)
        layout.addWidget(QLabel("Export path"), 3, 0)
        layout.addWidget(self.read_export_path_edit, 3, 1, 1, 5)
        layout.addWidget(self.read_export_browse_button, 3, 6)
        layout.addWidget(self.read_export_button, 3, 7)
        return tab

    def _build_read_side_panel(self) -> QWidget:
        panel = QGroupBox("Brute / Legend")
        panel.setMaximumWidth(280)
        layout = QVBoxLayout(panel)
        layout.addWidget(self.brute_progress_label)
        layout.addWidget(self.brute_progress_bar)

        legend = QLabel(
            "OK: block was read successfully\n"
            "MS: Missing Sector key. Sector key is not known yet.\n"
            "NN: Not read. Auth worked, but block read failed.\n\n"
            "Pick: recover this whole MIFARE Classic sector.\n"
            "Start Brute: recover all visible MS/NN sectors."
        )
        legend.setWordWrap(True)
        legend.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(legend)
        layout.addStretch(1)
        return panel

    def _build_write_tab(self) -> QWidget:
        tab = QWidget()
        layout = QGridLayout(tab)
        layout.addWidget(QLabel("Import path"), 0, 0)
        layout.addWidget(self.write_import_path_edit, 0, 1, 1, 3)
        layout.addWidget(self.write_import_browse_button, 0, 4)
        layout.addWidget(self.write_load_button, 0, 5)
        layout.addWidget(QLabel("Target block/page"), 1, 0)
        layout.addWidget(self.write_address_spin, 1, 1)
        layout.addWidget(self.write_verify_check, 1, 2, 1, 2)
        layout.addWidget(self.write_uid_block_check, 1, 4, 1, 2)
        layout.addWidget(self.magic_probe_button, 1, 6)
        layout.addWidget(QLabel("Raw write buffer"), 2, 0, 1, 6)
        layout.addWidget(self.write_hex_table, 3, 0, 1, 6)
        layout.addWidget(self.write_button, 4, 0, 1, 6)
        layout.addWidget(
            QLabel("Safe mode skips sector trailers. UID block 0 is written only when explicitly enabled."),
            5,
            0,
            1,
            6,
        )
        return tab

    def _create_hex_table(self, action_columns: bool = False) -> QTableWidget:
        headers = ["Offset"] + [f"{i:02X}" for i in range(16)]
        if action_columns:
            headers.append("Brute Progress")
        table = HexTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setToolTip("Select cells and press Ctrl+C to copy the visible table text.")
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setFont(QFont("Consolas", 9))
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(22)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.horizontalHeader().setStretchLastSection(False)
        table.setColumnWidth(0, 78)
        for column in range(1, 17):
            table.setColumnWidth(column, 32)
        if action_columns:
            table.setColumnWidth(17, 210)
        return table

    def _connect_signals(self) -> None:
        self.refresh_ports_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.start_connection)
        self.disconnect_button.clicked.connect(self.stop_capture)
        self.current_device_refresh_button.clicked.connect(self.scan_current_device)
        self.read_button.clicked.connect(self.read_once)
        self.start_brute_button.clicked.connect(self.start_brute_all)
        self.read_export_browse_button.clicked.connect(self.choose_read_export_path)
        self.read_export_button.clicked.connect(self.export_current_dump)
        self.write_import_browse_button.clicked.connect(self.choose_write_import_path)
        self.write_load_button.clicked.connect(self.load_write_file)
        self.write_button.clicked.connect(self.start_write_dump)
        self.write_uid_block_check.toggled.connect(self.update_write_verify_dependency)
        self.magic_probe_button.clicked.connect(self.probe_magic_uid)
        self.port_combo.currentIndexChanged.connect(self.save_selected_port)
        self.stop_brute_button.clicked.connect(self.stop_brute)
        self.reset_button.clicked.connect(self.reset_session)
        self._setup_shortcuts()

    def _setup_shortcuts(self) -> None:
        self.shortcuts: list[QShortcut] = []
        zoom_shortcuts = [
            ("+", lambda: self.adjust_hex_table_scale(10)),
            ("=", lambda: self.adjust_hex_table_scale(10)),
            ("Ctrl++", lambda: self.adjust_hex_table_scale(10)),
            ("Ctrl+=", lambda: self.adjust_hex_table_scale(10)),
            ("-", lambda: self.adjust_hex_table_scale(-10)),
            ("Ctrl+-", lambda: self.adjust_hex_table_scale(-10)),
            ("Ctrl+0", lambda: self.set_hex_table_scale(100)),
        ]
        for table in (self.read_hex_table, self.write_hex_table):
            for sequence, callback in zoom_shortcuts:
                shortcut = QShortcut(QKeySequence(sequence), table)
                shortcut.setContext(Qt.WidgetWithChildrenShortcut)
                shortcut.activated.connect(callback)
                self.shortcuts.append(shortcut)

        help_shortcut = QShortcut(QKeySequence("F1"), self)
        help_shortcut.setContext(Qt.ApplicationShortcut)
        help_shortcut.activated.connect(self.show_help)
        self.shortcuts.append(help_shortcut)

    def adjust_hex_table_scale(self, delta: int) -> None:
        self.set_hex_table_scale(self.hex_table_scale + delta)

    def set_hex_table_scale(self, value: int) -> None:
        self.hex_table_scale = max(70, min(180, value))
        self.settings.setValue("ui/hex_table_scale", self.hex_table_scale)
        self.apply_hex_table_scale()

    def apply_hex_table_scale(self, announce: bool = True) -> None:
        font_size = max(7, round(9 * self.hex_table_scale / 100))
        row_height = max(18, round(22 * self.hex_table_scale / 100))
        offset_width = max(62, round(78 * self.hex_table_scale / 100))
        byte_width = max(26, round(32 * self.hex_table_scale / 100))
        brute_width = max(160, round(210 * self.hex_table_scale / 100))

        for table in (self.read_hex_table, self.write_hex_table):
            table.setFont(QFont("Consolas", font_size))
            table.verticalHeader().setDefaultSectionSize(row_height)
            table.setColumnWidth(0, offset_width)
            for column in range(1, 17):
                table.setColumnWidth(column, byte_width)
            if table.columnCount() > 17:
                table.setColumnWidth(17, brute_width)

        if announce:
            self.status_label.setText(f"Table zoom: {self.hex_table_scale}%")

    def show_help(self) -> None:
        QMessageBox.information(
            self,
            "PN5180 Dumper help",
            "Горячие клавиши / Hotkeys:\n"
            "+ / Ctrl++: увеличить масштаб Raw dump table / increase Raw dump table zoom\n"
            "- / Ctrl+-: уменьшить масштаб Raw dump table / decrease Raw dump table zoom\n"
            "Ctrl+0: сбросить масштаб на 100% / reset table zoom to 100%\n"
            "Ctrl+C: копировать выделенные ячейки / copy selected table cells\n"
            "F1: показать эту справку / show this help\n\n"
            "Маркеры Raw dump / Raw dump markers:\n"
            "MS: ключ сектора неизвестен / Missing Sector key; sector key is not known yet.\n"
            "NN: блок не прочитан; аутентификация прошла, но чтение упало / "
            "Not read; authentication worked, but block read failed.\n"
            "Brute: подобрать ключ для всего сектора MIFARE Classic / "
            "starts key search for the whole MIFARE Classic sector.\n\n"
            "Запись / Write note:\n"
            "Безопасная запись пропускает trailer-блоки секторов. Блок UID 0 требует magic-болванку. / "
            "Safe write skips sector trailers. UID block 0 requires a magic UID-changeable blank.",
        )

    def refresh_ports(self) -> None:
        current = self.port_combo.currentData() or self.settings.value("connection/port", "")
        self.port_combo.clear()
        preferred_index = -1
        for port in list_ports.comports():
            label = f"{port.device} - {port.description}"
            self.port_combo.addItem(label, port.device)
            if preferred_index < 0 and port.device.upper() != "COM1":
                preferred_index = self.port_combo.count() - 1
        if current and str(current).upper() != "COM1":
            index = self.port_combo.findData(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
                return
        if preferred_index >= 0:
            self.port_combo.setCurrentIndex(preferred_index)

    def save_selected_port(self) -> None:
        port = self.port_combo.currentData()
        if port:
            self.settings.setValue("connection/port", port)

    def choose_read_export_path(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export raw dump",
            self.read_export_path_edit.text() or "dump.bin",
            "Binary dump (*.bin);;All files (*.*)",
        )
        if selected:
            self.read_export_path_edit.setText(selected)
            self.settings.setValue("paths/read_export", selected)

    def choose_write_import_path(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Load write buffer",
            self.write_import_path_edit.text() or "",
            "Binary dump (*.bin);;Hex files (*.hex *.txt);;All files (*.*)",
        )
        if selected:
            self.write_import_path_edit.setText(selected)
            self.settings.setValue("paths/write_import", selected)
            self.load_write_file()

    def start_connection(self) -> bool:
        if self.worker:
            return True

        self.refresh_ports()
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "No port", "Select a serial port first.")
            return False

        out_dir = Path("captures")
        out_dir.mkdir(parents=True, exist_ok=True)

        self.worker = SerialCaptureWorker(
            port=port,
            baud=DEFAULT_BAUD,
            out_dir=out_dir,
            once=False,
        )
        self.worker.line_received.connect(self.append_log)
        self.worker.record_saved.connect(self.add_record)
        self.worker.status_changed.connect(self.set_status)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

        self.settings.setValue("connection/port", port)
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.read_button.setEnabled(False)
        self.current_device_refresh_button.setEnabled(False)
        self.status_label.setText("Connecting...")
        return True

    def start_capture(self, request_initial_dump: bool = True) -> None:
        if not self.start_connection():
            return
        if request_initial_dump:
            self.read_once()

    def read_once(self) -> None:
        if not self.worker:
            QMessageBox.information(self, "Not connected", "Connect to the reader first, then press Read.")
            return
        self.read_running = True
        self.worker.send_command("PND1 DUMP")
        self.status_label.setText("Read requested...")

    def scan_current_device(self) -> None:
        if not self.worker:
            QMessageBox.information(self, "Not connected", "Connect to the reader first.")
            return
        if self.read_running or self.write_running or self.brute_running:
            self.status_label.setText("Device refresh is paused while another operation is running")
            return
        self.worker.send_command("PND1 SCAN")
        self.status_label.setText("Device refresh requested...")

    def auto_scan_current_device(self) -> None:
        if not self.worker or self.read_running or self.write_running or self.brute_running:
            return
        self.worker.send_command("PND1 SCAN")

    def stop_capture(self) -> None:
        if self.worker:
            self.worker.stop()
            self.status_label.setText("Stopping...")

    def on_worker_finished(self) -> None:
        self.worker = None
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.read_button.setEnabled(False)
        self.current_device_refresh_button.setEnabled(False)
        self.scan_timer.stop()
        self._set_reader_online(False)

    def append_log(self, line: str) -> None:
        self._set_reader_online(True)
        should_log = True
        if line == "INFO no_card":
            self._set_tag_online(False)
            self.read_running = False
            should_log = self.last_logged_device_state != "NO_CARD"
            if should_log:
                self.last_logged_device_state = "NO_CARD"
        elif line.startswith("TAG_DETECTED "):
            payload = line[len("TAG_DETECTED "):]
            state = f"TAG:{self._tag_signature(payload)}"
            should_log = self.last_logged_device_state != state
            if should_log:
                self.last_logged_device_state = state
            self.update_detected_tag(payload, "detected")
        elif line.startswith("META "):
            try:
                metadata = parse_new_metadata(line)
            except ValueError:
                metadata = None
            if metadata:
                payload = {
                    "type": metadata.tag_type,
                    "uid": metadata.uid,
                    "rc": metadata.rc,
                    "block_size": metadata.block_size,
                    "num_blocks": metadata.num_blocks,
                }
                payload.update(metadata.extra)
                self.current_metadata = payload
                self._set_tag_online(True)
                self.update_current_device_details(payload, "capturing")
        elif line == "DUMP_END":
            self.read_running = False
        elif line.startswith("PND1 BRUTE_RESULT"):
            self.handle_brute_result(self._parse_fields(line))
        elif line.startswith("PND1 BRUTE_BATCH_END"):
            self.handle_brute_batch_end(self._parse_fields(line))
        elif line.startswith("PND1 WRITE_RESULT"):
            self.handle_write_result(self._parse_fields(line))
        elif line.startswith("PND1 MAGIC_RESULT"):
            self.handle_magic_result(self._parse_fields(line))
        if should_log:
            self.log_view.appendPlainText(line)

    def _parse_fields(self, line: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for part in line.split():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            fields[key] = value
        return fields

    def _tag_signature(self, payload: str) -> str:
        fields = self._parse_fields(payload)
        return "|".join(
            [
                fields.get("type", "-"),
                fields.get("protocol", "-"),
                fields.get("uid", "-"),
                fields.get("sak", "-"),
                fields.get("family", "-"),
            ]
        )

    def update_detected_tag(self, payload: str, memory_state: str) -> None:
        fields = self._parse_fields(payload)

        scan_metadata = {
            "type": fields.get("type", "-"),
            "protocol": fields.get("protocol", "-"),
            "uid": fields.get("uid", "-"),
            "uid_length": fields.get("uid_length", "-"),
            "memory_read": memory_state,
            "family": fields.get("family", "-"),
            "atqa": fields.get("atqa", "-"),
            "sak": fields.get("sak", "-"),
            "num_blocks": None,
        }

        metadata = scan_metadata
        if self.current_metadata and self.current_metadata.get("uid") == scan_metadata.get("uid"):
            metadata = dict(scan_metadata)
            metadata.update(
                {
                    key: value
                    for key, value in self.current_metadata.items()
                    if value is not None and value != "" and value != "-"
                }
            )
        elif self.current_metadata and self.current_metadata.get("uid") != scan_metadata.get("uid"):
            self.current_folder = None

        self._set_tag_online(True)
        self.current_metadata = metadata
        self.update_current_device_details(metadata, self._current_device_location())

    def _current_device_location(self) -> str:
        if self.current_folder:
            return str(self.current_folder)
        return "detected"

    def add_record(self, metadata: dict, folder: str) -> None:
        self.current_metadata = metadata
        self.current_folder = Path(folder)
        self._set_tag_online(True)
        self.update_current_device_details(metadata, folder)

        dump_path = self.current_folder / "dump.bin"
        if dump_path.exists():
            self.current_dump_bytes = dump_path.read_bytes()
            statuses = metadata.get("block_statuses") if isinstance(metadata.get("block_statuses"), list) else None
            self.current_block_statuses = list(statuses or [])
            self.populate_hex_table(
                self.read_hex_table,
                self.current_dump_bytes,
                self.current_block_statuses,
                enable_brute=True,
            )
            self.read_export_button.setEnabled(True)
            self.read_export_path_edit.setText(str(dump_path))
            self.settings.setValue("paths/read_export", str(dump_path))
            self.sync_write_buffer_from_dump(dump_path)
            self.start_brute_button.setEnabled(bool(self.missing_sector_start_blocks()))
            saved_progress = self.load_brute_progress()
            if saved_progress:
                self.update_global_brute_progress(f"Brute: resume available at #{saved_progress.get('resume_index', 0)}")
            else:
                self.update_global_brute_progress(
                    "Brute: ready" if self.missing_sector_start_blocks() else "Brute: nothing to recover"
                )
        else:
            self.current_dump_bytes = b""
            self.current_block_statuses = []
            self.populate_hex_table(self.read_hex_table, b"")
            self.read_export_button.setEnabled(False)
            self.start_brute_button.setEnabled(False)
            self.update_global_brute_progress("Brute: idle")

        self.status_label.setText(f"Saved record to {folder}")

    def sync_write_buffer_from_dump(self, dump_path: Path | None = None) -> None:
        if dump_path is not None:
            self.write_import_path_edit.setText(str(dump_path))
            self.settings.setValue("paths/write_import", str(dump_path))
        self.write_bytes = self.current_dump_bytes
        self.populate_hex_table(self.write_hex_table, self.write_bytes)
        self.write_button.setEnabled(bool(self.write_bytes) and not self.write_running)

    def start_brute_for_block(self, block: int) -> None:
        if not self.worker:
            self.start_connection()
            if not self.worker:
                QMessageBox.information(self, "Serial is stopped", "Start capture first and keep the port connected.")
                return
        if self.brute_running:
            QMessageBox.information(self, "Brute is running", "Stop the current brute task first.")
            return
        if not self.load_brute_keys():
            return
        self.brute_all_mode = False
        self.brute_pending_blocks = []
        self.brute_total_sectors = 1
        self.brute_done_sectors = 0
        saved = self.load_brute_progress()
        start_index = 0
        if saved and self.same_mifare_sector(int(saved.get("current_block", -1)), block):
            start_index = int(saved.get("resume_index", 0))
        self.start_brute_sector(block, start_index=start_index)

    def start_brute_all(self) -> None:
        if not self.worker:
            self.start_connection()
            if not self.worker:
                QMessageBox.information(self, "Serial is stopped", "Start capture first and keep the port connected.")
                return
        if self.brute_running:
            QMessageBox.information(self, "Brute is running", "Stop the current brute task first.")
            return
        if not self.load_brute_keys():
            return

        targets = self.missing_sector_start_blocks()
        if not targets:
            QMessageBox.information(self, "Nothing to brute", "There are no MS/NN sectors in the current dump.")
            return

        self.brute_all_mode = True
        saved = self.load_brute_progress()
        if saved and saved.get("all_mode"):
            current_block = int(saved.get("current_block", targets[0]))
            self.brute_pending_blocks = [
                int(block)
                for block in saved.get("pending_blocks", [])
                if self.block_still_needs_brute(int(block))
            ]
            self.brute_total_sectors = int(saved.get("total_sectors", len(targets)))
            self.brute_done_sectors = int(saved.get("done_sectors", 0))
            self.start_brute_sector(current_block, start_index=int(saved.get("resume_index", 0)))
        elif saved:
            current_block = int(saved.get("current_block", targets[0]))
            self.brute_pending_blocks = [
                block for block in targets if not self.same_mifare_sector(block, current_block)
            ]
            self.brute_total_sectors = len(self.brute_pending_blocks) + 1
            self.brute_done_sectors = 0
            self.start_brute_sector(current_block, start_index=int(saved.get("resume_index", 0)))
        else:
            self.brute_pending_blocks = targets
            self.brute_total_sectors = len(targets)
            self.brute_done_sectors = 0
            self.start_next_pending_brute_sector()

    def load_brute_keys(self) -> bool:
        try:
            self.brute_keys = load_local_mfc_keys()
        except Exception as exc:
            QMessageBox.warning(self, "Dictionary error", f"Could not load local key dictionary: {exc}")
            return False
        return True

    def start_next_pending_brute_sector(self) -> None:
        if not self.brute_pending_blocks:
            self.brute_running = False
            self.stop_brute_button.setEnabled(False)
            self.start_brute_button.setEnabled(bool(self.missing_sector_start_blocks()))
            self.update_global_brute_progress("Brute: complete")
            self.clear_brute_progress()
            self.status_label.setText("Brute complete")
            return
        self.start_brute_sector(self.brute_pending_blocks.pop(0))

    def start_brute_sector(self, block: int, start_index: int = 0) -> None:
        self.brute_current_sector_blocks = self._mifare_classic_sector_blocks_for_block(block)
        self.brute_recovered_blocks = set()
        self.brute_sector_found = False
        self.brute_total = len(self.brute_keys) * 2
        self.brute_checked = min(max(start_index, 0), self.brute_total)
        self.brute_queue = self.build_brute_queue(block, self.brute_checked)
        self.brute_current_block = block
        self.brute_running = True
        self.brute_current_attempt = None
        self.brute_current_batch = []
        self.brute_active_batch_id = None
        self.brute_waiting_for_result = False
        self.brute_waiting_for_sector_results = False
        self.start_brute_button.setEnabled(False)
        self.stop_brute_button.setEnabled(True)
        self.update_brute_progress_for_sector()
        self.update_global_brute_progress()
        self.send_next_brute_attempt()

    def build_brute_queue(self, block: int, start_index: int) -> list[tuple[int, str, str]]:
        queue: list[tuple[int, str, str]] = []
        for index in range(start_index, len(self.brute_keys) * 2):
            key = self.brute_keys[index // 2]
            key_type = "A" if index % 2 == 0 else "B"
            queue.append((block, key_type, key))
        return queue

    def current_tag_uid(self) -> str:
        if not self.current_metadata:
            return "-"
        return str(self.current_metadata.get("uid", "-"))

    def brute_resume_index(self) -> int:
        if self.brute_waiting_for_result and self.brute_current_batch:
            return max(self.brute_checked - len(self.brute_current_batch), 0)
        if self.brute_waiting_for_result and self.brute_checked > 0:
            return self.brute_checked - 1
        return self.brute_checked

    def save_brute_progress(self) -> None:
        if self.brute_current_block is None or not self.brute_keys:
            return
        BRUTE_PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "uid": self.current_tag_uid(),
            "current_block": self.brute_current_block,
            "resume_index": self.brute_resume_index(),
            "pending_blocks": self.brute_pending_blocks,
            "all_mode": self.brute_all_mode,
            "total_sectors": self.brute_total_sectors,
            "done_sectors": self.brute_done_sectors,
            "key_count": len(self.brute_keys),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        BRUTE_PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_brute_progress(self) -> dict | None:
        if not BRUTE_PROGRESS_PATH.exists():
            return None
        try:
            payload = json.loads(BRUTE_PROGRESS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("uid") != self.current_tag_uid():
            return None
        if self.brute_keys and payload.get("key_count") != len(self.brute_keys):
            return None
        current_block = int(payload.get("current_block", -1))
        if current_block < 0 or not self.block_still_needs_brute(current_block):
            return None
        return payload

    def clear_brute_progress(self) -> None:
        try:
            BRUTE_PROGRESS_PATH.unlink(missing_ok=True)
        except OSError:
            pass

    def block_still_needs_brute(self, block: int) -> bool:
        sector_blocks = self._mifare_classic_sector_blocks_for_block(block)
        return any(
            candidate < len(self.current_block_statuses) and self.current_block_statuses[candidate] in {"NN", "MS"}
            for candidate in sector_blocks
        )

    def same_mifare_sector(self, left: int, right: int) -> bool:
        if left < 0 or right < 0:
            return False
        return self._mifare_classic_sector_first_block(left) == self._mifare_classic_sector_first_block(right)

    def handle_brute_attempt_timeout(self) -> None:
        if not self.brute_running or not (self.brute_waiting_for_result or self.brute_waiting_for_sector_results):
            return
        if self.brute_current_attempt:
            block, key_type, key = self.brute_current_attempt
            if self.brute_current_batch:
                self.update_brute_progress(block, f"timeout batch at {key_type} {key}")
            else:
                self.update_brute_progress(block, f"timeout {key_type} {key}")
        self.save_brute_progress()
        self.brute_waiting_for_result = False
        self.brute_waiting_for_sector_results = False
        self.brute_current_attempt = None
        self.brute_current_batch = []
        self.brute_active_batch_id = None
        self.update_global_brute_progress("Brute: timeout, continuing")
        self.send_next_brute_attempt()

    def stop_brute(self) -> None:
        self.save_brute_progress()
        self.brute_running = False
        self.read_running = False
        self.brute_attempt_timer.stop()
        self.brute_current_attempt = None
        self.brute_current_batch = []
        self.brute_active_batch_id = None
        self.brute_waiting_for_result = False
        self.brute_waiting_for_sector_results = False
        self.brute_queue = []
        self.brute_sector_found = False
        self.brute_pending_blocks = []
        self.brute_all_mode = False
        self.start_brute_button.setEnabled(bool(self.missing_sector_start_blocks()))
        self.stop_brute_button.setEnabled(False)
        if self.brute_current_block is not None:
            self.update_brute_progress_for_sector("stopped")
        self.update_global_brute_progress("Brute: stopped")
        self.status_label.setText("Brute stopped")

    def reset_session(self) -> None:
        self.brute_running = False
        self.brute_queue = []
        self.brute_total = 0
        self.brute_checked = 0
        self.brute_current_block = None
        self.brute_current_sector_blocks = []
        self.brute_recovered_blocks = set()
        self.brute_sector_found = False
        self.brute_pending_blocks = []
        self.brute_all_mode = False
        self.brute_total_sectors = 0
        self.brute_done_sectors = 0
        self.brute_current_attempt = None
        self.brute_current_batch = []
        self.brute_active_batch_id = None
        self.brute_waiting_for_result = False
        self.brute_waiting_for_sector_results = False
        self.brute_attempt_timer.stop()
        self.clear_brute_progress()

        self.current_metadata = None
        self.current_folder = None
        self.current_dump_bytes = b""
        self.current_block_statuses = []
        self.last_logged_device_state = None
        self.write_queue = []
        self.write_total = 0
        self.write_done = 0
        self.write_failures = []
        self.write_running = False
        self.write_uid_block_requested = False
        self.write_uid_block_verified = False
        self.write_bytes = b""
        self.write_import_path_edit.clear()
        self.populate_hex_table(self.write_hex_table, b"")
        self.write_button.setEnabled(False)
        self.populate_hex_table(self.read_hex_table, b"", enable_brute=True)
        self.read_export_button.setEnabled(False)
        self.start_brute_button.setEnabled(False)
        self.stop_brute_button.setEnabled(False)
        self.update_global_brute_progress("Brute: idle")
        self._set_tag_online(False)
        self.log_view.clear()
        self.status_label.setText("Reset")

    def send_next_brute_attempt(self) -> None:
        if not self.brute_running or not self.worker:
            return
        if not self.brute_queue:
            block = self.brute_current_block
            self.brute_running = False
            if block is not None:
                self.update_brute_progress_for_sector("exhausted")
            self.brute_done_sectors += 1
            if self.brute_all_mode:
                self.update_global_brute_progress("Brute: sector exhausted, continuing")
                self.save_brute_progress()
                self.start_next_pending_brute_sector()
            else:
                self.start_brute_button.setEnabled(bool(self.missing_sector_start_blocks()))
                self.stop_brute_button.setEnabled(False)
                self.update_global_brute_progress("Brute: exhausted")
                self.clear_brute_progress()
                self.status_label.setText("Brute exhausted the dictionary")
            return

        batch = self.brute_queue[:BRUTE_BATCH_SIZE]
        del self.brute_queue[:BRUTE_BATCH_SIZE]
        block, key_type, key = batch[-1]
        start_index = self.brute_checked
        self.brute_checked += len(batch)
        self.brute_current_block = block
        self.brute_current_attempt = (block, key_type, key)
        self.brute_current_batch = batch
        self.brute_batch_counter += 1
        self.brute_active_batch_id = str(self.brute_batch_counter)
        self.brute_waiting_for_result = True
        self.brute_waiting_for_sector_results = False
        self.update_brute_progress_for_sector()
        attempts = " ".join(f"{attempt_key_type}{attempt_key}" for _block, attempt_key_type, attempt_key in batch)
        self.worker.send_command(f"PND1 BRUTE_BATCH {block} {start_index} {self.brute_active_batch_id} {attempts}")
        self.save_brute_progress()
        self.brute_attempt_timer.setInterval(BRUTE_BATCH_TIMEOUT_MS)
        self.brute_attempt_timer.start()

    def handle_brute_result(self, fields: dict[str, str]) -> None:
        if not self.brute_running:
            return

        block_text = fields.get("block")
        if block_text is None:
            if self.brute_current_batch:
                return
            self.send_next_brute_attempt()
            return

        block = int(block_text)
        if self.brute_current_sector_blocks and block not in self.brute_current_sector_blocks:
            return

        if self.brute_current_batch and fields.get("key_type") and fields.get("key"):
            found_attempt = any(
                fields.get("key_type") == expected_key_type and fields.get("key") == expected_key
                for _block, expected_key_type, expected_key in self.brute_current_batch
            )
            if not found_attempt:
                return
        elif self.brute_current_attempt and fields.get("key_type") and fields.get("key"):
            _block, expected_key_type, expected_key = self.brute_current_attempt
            if fields.get("key_type") != expected_key_type or fields.get("key") != expected_key:
                return

        self.brute_attempt_timer.stop()
        self.brute_attempt_timer.setInterval(BRUTE_ATTEMPT_TIMEOUT_MS)
        self.brute_waiting_for_result = False

        status = fields.get("status", "")
        if status == "ok" and "data" in fields:
            data = bytes.fromhex(fields["data"])
            start = block * 16
            if len(self.current_dump_bytes) < start + 16:
                self.current_dump_bytes = self.current_dump_bytes.ljust(start + 16, b"\x00")
            buffer = bytearray(self.current_dump_bytes)
            buffer[start:start + 16] = data
            self.current_dump_bytes = bytes(buffer)
            while len(self.current_block_statuses) <= block:
                self.current_block_statuses.append("OK")
            self.current_block_statuses[block] = "OK"
            self.brute_sector_found = True
            self.brute_recovered_blocks.add(block)
            self.brute_waiting_for_sector_results = True
            self.update_brute_progress_for_sector(f"found {fields.get('key_type')} {fields.get('key')}")
            self.populate_hex_table(
                self.read_hex_table,
                self.current_dump_bytes,
                self.current_block_statuses,
                enable_brute=True,
            )
            self.sync_write_buffer_from_dump()
            if self.brute_current_sector_blocks and self.brute_recovered_blocks.issuperset(
                set(self.brute_current_sector_blocks)
            ):
                self.finish_brute_sector(fields)
            elif self.brute_running:
                self.brute_attempt_timer.setInterval(BRUTE_ATTEMPT_TIMEOUT_MS)
                self.brute_attempt_timer.start()
            return

        if self.brute_sector_found and status == "read_failed":
            self.brute_recovered_blocks.add(block)
            if self.brute_current_sector_blocks and self.brute_recovered_blocks.issuperset(
                set(self.brute_current_sector_blocks)
            ):
                self.finish_brute_sector(fields)
            elif self.brute_running:
                self.brute_attempt_timer.setInterval(BRUTE_ATTEMPT_TIMEOUT_MS)
                self.brute_attempt_timer.start()
            return

        self.send_next_brute_attempt()

    def handle_brute_batch_end(self, fields: dict[str, str]) -> None:
        if not self.brute_running or not self.brute_waiting_for_result:
            return
        if self.brute_active_batch_id and fields.get("batch") != self.brute_active_batch_id:
            return
        if fields.get("block") and self.brute_current_block is not None:
            try:
                if int(fields["block"]) != self.brute_current_block:
                    return
            except ValueError:
                return

        self.brute_attempt_timer.stop()
        self.brute_attempt_timer.setInterval(BRUTE_ATTEMPT_TIMEOUT_MS)
        status = fields.get("status", "unknown")
        checked = fields.get("checked", str(len(self.brute_current_batch)))
        if status == "found":
            self.brute_waiting_for_result = False
            self.update_brute_progress_for_sector(f"found, reading sector ({checked} attempts)")
            self.brute_waiting_for_sector_results = True
            self.brute_attempt_timer.start()
            return
        if status in {"bad_key", "bad_command"}:
            retry_batch = list(self.brute_current_batch)
            self.brute_checked = max(self.brute_checked - len(retry_batch), 0)
            self.brute_queue = retry_batch + self.brute_queue
            self.brute_waiting_for_result = False
            self.brute_current_attempt = None
            self.brute_current_batch = []
            self.brute_active_batch_id = None
            self.update_brute_progress_for_sector("batch parse failed, retrying")
            self.save_brute_progress()
            self.send_next_brute_attempt()
            return

        self.brute_waiting_for_result = False
        self.brute_current_attempt = None
        self.brute_current_batch = []
        self.brute_active_batch_id = None
        self.update_brute_progress_for_sector()
        self.save_brute_progress()
        self.send_next_brute_attempt()

    def finish_brute_sector(self, fields: dict[str, str]) -> None:
        self.brute_running = False
        self.brute_queue = []
        self.brute_attempt_timer.stop()
        self.brute_current_attempt = None
        self.brute_current_batch = []
        self.brute_active_batch_id = None
        self.brute_waiting_for_result = False
        self.brute_waiting_for_sector_results = False
        self.update_brute_progress_for_sector(f"found {fields.get('key_type')} {fields.get('key')}")
        recovered = len(self.brute_recovered_blocks)
        total = len(self.brute_current_sector_blocks)
        self.brute_done_sectors += 1
        self.status_label.setText(f"Recovered sector around block {self.brute_current_block}: {recovered}/{total} blocks")
        if self.brute_all_mode:
            self.update_global_brute_progress()
            self.save_brute_progress()
            self.start_next_pending_brute_sector()
        else:
            self.stop_brute_button.setEnabled(False)
            self.start_brute_button.setEnabled(bool(self.missing_sector_start_blocks()))
            self.update_global_brute_progress("Brute: sector recovered")
            self.clear_brute_progress()

    def _mifare_classic_sector_blocks_for_block(self, block: int) -> list[int]:
        if block < 128:
            first = (block // 4) * 4
            count = 4
        else:
            first = 128 + ((block - 128) // 16) * 16
            count = 16
        limit = len(self.current_block_statuses) or ((len(self.current_dump_bytes) + 15) // 16)
        return [candidate for candidate in range(first, first + count) if candidate < max(limit, first + count)]

    def _mifare_classic_sector_first_block(self, block: int) -> int:
        if block < 128:
            return (block // 4) * 4
        return 128 + ((block - 128) // 16) * 16

    def missing_sector_start_blocks(self) -> list[int]:
        starts: list[int] = []
        seen: set[int] = set()
        for block, status in enumerate(self.current_block_statuses):
            if status not in {"NN", "MS"}:
                continue
            start = self._mifare_classic_sector_first_block(block)
            if start not in seen:
                starts.append(block)
                seen.add(start)
        return starts

    def update_brute_progress_for_sector(self, text: str | None = None) -> None:
        blocks = self.brute_current_sector_blocks or (
            [self.brute_current_block] if self.brute_current_block is not None else []
        )
        for block in blocks:
            self.update_brute_progress(block, text)

    def update_global_brute_progress(self, text: str | None = None) -> None:
        if self.brute_total_sectors > 0:
            self.brute_progress_bar.setRange(0, self.brute_total_sectors)
            self.brute_progress_bar.setValue(min(self.brute_done_sectors, self.brute_total_sectors))
        else:
            self.brute_progress_bar.setRange(0, 1)
            self.brute_progress_bar.setValue(0)

        if text:
            self.brute_progress_label.setText(text)
        elif self.brute_running:
            remaining_keys = max(self.brute_total - self.brute_checked, 0)
            self.brute_progress_label.setText(
                f"Brute: sector {self.brute_done_sectors + 1}/{max(self.brute_total_sectors, 1)}, "
                f"keys left {remaining_keys}/{self.brute_total}"
            )
        else:
            self.brute_progress_label.setText("Brute: idle")

    def update_brute_progress(self, block: int, text: str | None = None) -> None:
        if self.read_hex_table.columnCount() < 18:
            return
        remaining = max(self.brute_total - self.brute_checked, 0)
        value = text or f"{remaining}/{self.brute_total}"
        row = self._mifare_classic_sector_first_block(block)
        if row >= self.read_hex_table.rowCount():
            row = block
        if row < 0 or row >= self.read_hex_table.rowCount():
            return

        widget = self.read_hex_table.cellWidget(row, 17)
        label = widget.findChild(QLabel, "bruteStatus") if widget else None
        if label:
            label.setText(value)
        else:
            self._set_brute_progress_widget(self.read_hex_table, row, block, value, False)

    def export_current_dump(self) -> None:
        if not self.current_dump_bytes:
            QMessageBox.information(self, "No dump", "There is no raw dump to export yet.")
            return

        target_text = self.read_export_path_edit.text().strip()
        if not target_text:
            QMessageBox.warning(self, "No export path", "Choose export path first.")
            return

        target = Path(target_text)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.current_dump_bytes)
        self.settings.setValue("paths/read_export", str(target))
        self.status_label.setText(f"Exported {len(self.current_dump_bytes)} bytes to {target}")

    def load_write_file(self) -> None:
        source = Path(self.write_import_path_edit.text().strip())
        if not source.exists():
            QMessageBox.warning(self, "File not found", f"File does not exist: {source}")
            return

        if source.suffix.lower() in {".hex", ".txt"}:
            text = source.read_text(encoding="utf-8", errors="replace")
            compact = "".join(ch for ch in text if ch in "0123456789abcdefABCDEF")
            try:
                self.write_bytes = bytes.fromhex(compact)
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid hex", f"Could not parse hex file: {exc}")
                return
        else:
            self.write_bytes = source.read_bytes()

        self.populate_hex_table(self.write_hex_table, self.write_bytes)
        self.settings.setValue("paths/write_import", str(source))
        self.write_button.setEnabled(bool(self.write_bytes))
        self.status_label.setText(f"Loaded {len(self.write_bytes)} bytes from {source}")

    def start_write_dump(self) -> None:
        if self.write_running:
            QMessageBox.information(self, "Write running", "A write operation is already running.")
            return
        if not self.write_bytes:
            QMessageBox.information(self, "No data", "Load a dump file first.")
            return
        if len(self.write_bytes) % 16 != 0:
            QMessageBox.warning(self, "Invalid dump", "MIFARE Classic writes need a size aligned to 16-byte blocks.")
            return

        start_block = self.write_address_spin.value()
        allow_uid_block = self.write_uid_block_check.isChecked()
        self.write_uid_block_requested = False
        self.write_uid_block_verified = False
        queue: list[tuple[int, bytes]] = []
        skipped: list[int] = []
        for source_block, offset in enumerate(range(0, len(self.write_bytes), 16)):
            target_block = start_block + source_block
            if target_block == 0 and not allow_uid_block:
                skipped.append(target_block)
                continue
            if self._is_mifare_classic_trailer_block(target_block):
                skipped.append(target_block)
                continue
            if target_block == 0:
                self.write_uid_block_requested = True
            queue.append((target_block, self.write_bytes[offset:offset + 16]))

        if not queue:
            QMessageBox.warning(self, "Nothing to write", "All blocks were skipped by safe-write protection.")
            return

        answer = QMessageBox.question(
            self,
            "Confirm write",
            (
                f"Write {len(queue)} data blocks to the tag now?\n\n"
                f"Skipped protected blocks: {len(skipped)}.\n"
                "Only use this on tags you own or are authorized to copy."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        if allow_uid_block and any(block == 0 for block, _data in queue):
            answer = QMessageBox.question(
                self,
                "Write UID block 0?",
                (
                    "You enabled writing block 0.\n\n"
                    "This is only for UID-changeable magic cards. On a normal MIFARE Classic card it will fail; "
                    "on some magic cards bad data can brick the card.\n\n"
                    "Write block 0 anyway?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        if not self.worker:
            self.start_connection()
            if not self.worker:
                return

        self.write_queue = queue
        self.write_total = len(queue)
        self.write_done = 0
        self.write_failures = []
        self.write_running = True
        self.write_button.setEnabled(False)
        self.write_uid_block_check.setEnabled(False)
        self.status_label.setText(f"Writing 0/{self.write_total} blocks...")
        self.send_next_write_block()

    def probe_magic_uid(self) -> None:
        if not self.worker:
            self.start_connection()
            if not self.worker:
                return
        self.worker.send_command("PND1 MAGIC_PROBE")
        self.status_label.setText("Magic probe requested...")

    def send_next_write_block(self) -> None:
        if not self.write_running or not self.worker:
            return
        if not self.write_queue:
            self.write_running = False
            self.write_button.setEnabled(bool(self.write_bytes))
            self.write_uid_block_check.setEnabled(True)
            if self.write_failures:
                self.status_label.setText(
                    f"Write finished with {len(self.write_failures)} failed blocks: {', '.join(self.write_failures[:8])}"
                )
            elif self.write_uid_block_requested and self.write_uid_block_verified:
                self.status_label.setText(
                    f"Write complete: UID block 0 was written and verified ({self.write_done}/{self.write_total} blocks)"
                )
            elif self.write_uid_block_requested:
                self.status_label.setText(
                    "Write finished, but UID block 0 was not verified; treat this as NOT OK"
                )
            else:
                self.status_label.setText(f"Write complete: {self.write_done}/{self.write_total} blocks")
            return

        block, data = self.write_queue.pop(0)
        verify = " VERIFY" if self.write_verify_check.isChecked() else ""
        allow_uid = " ALLOW0" if block == 0 and self.write_uid_block_check.isChecked() else ""
        self.worker.send_command(f"PND1 WRITE {block} {data.hex().upper()}{verify}{allow_uid}")

    def handle_write_result(self, fields: dict[str, str]) -> None:
        if not self.write_running:
            return
        block = fields.get("block", "?")
        status = fields.get("status", "unknown")
        if status == "ok":
            self.write_done += 1
            if block == "0" and self.write_uid_block_requested:
                self.write_uid_block_verified = True
        elif status != "skipped_protected":
            self.write_failures.append(f"{block}:{status}")
            if block == "0":
                self.write_queue = []
                self.write_running = False
                self.write_button.setEnabled(bool(self.write_bytes))
                self.write_uid_block_check.setEnabled(True)
                self.status_label.setText(f"UID block 0 failed ({status}); write stopped")
                return
        self.status_label.setText(f"Writing {self.write_done}/{self.write_total} blocks...")
        self.send_next_write_block()

    def update_write_verify_dependency(self, enabled: bool) -> None:
        if enabled:
            self.write_verify_check.setChecked(True)
            self.write_verify_check.setEnabled(False)
            self.write_verify_check.setToolTip(
                "Required for UID block 0 writes: firmware must read the new UID back successfully."
            )
            self.write_button.setToolTip("Writes data blocks and verifies rewritten UID block 0 on magic blanks")
        else:
            self.write_verify_check.setEnabled(True)
            self.write_verify_check.setToolTip("Reads blocks back after writing when enabled.")
            self.write_button.setToolTip("Writes safe MIFARE Classic data blocks, skipping UID and trailer blocks")

    def handle_magic_result(self, fields: dict[str, str]) -> None:
        gen1a = fields.get("gen1a", "unknown")
        if gen1a == "ok":
            self.status_label.setText("Magic probe: Gen1A backdoor is supported")
        elif gen1a == "failed":
            self.status_label.setText("Magic probe: Gen1A backdoor is not supported")
        else:
            self.status_label.setText(f"Magic probe: {gen1a}")

    def _is_mifare_classic_trailer_block(self, block: int) -> bool:
        if block < 128:
            return block % 4 == 3
        return (block - 128) % 16 == 15

    def populate_hex_table(
        self,
        table: QTableWidget,
        data: bytes,
        block_statuses: list[str] | None = None,
        enable_brute: bool = False,
    ) -> None:
        row_count = (len(data) + 15) // 16
        table.setRowCount(row_count)
        sector_action_rows: dict[int, int] = {}
        if enable_brute:
            statuses = block_statuses or []
            for row, status in enumerate(statuses[:row_count]):
                if status not in {"NN", "MS"}:
                    continue
                sector_start = self._mifare_classic_sector_first_block(row)
                action_row = sector_start if sector_start < row_count else row
                sector_action_rows.setdefault(action_row, row)

        for row in range(row_count):
            offset = row * 16
            offset_item = QTableWidgetItem(f"{offset:08X}")
            offset_item.setBackground(QBrush(QColor("#121c28")))
            offset_item.setForeground(QBrush(QColor("#8fb3d9")))
            offset_item.setToolTip("Byte offset / address")
            table.setItem(row, 0, offset_item)
            status = block_statuses[row] if block_statuses and row < len(block_statuses) else "OK"
            for column in range(16):
                index = offset + column
                value = f"{data[index]:02X}" if index < len(data) else ""
                item = QTableWidgetItem(value)
                if status == "NN":
                    item.setText("NN")
                    item.setBackground(QBrush(QColor("#52262b")))
                    item.setForeground(QBrush(QColor("#ffb1b8")))
                    item.setToolTip("NN: block was authenticated but not read successfully")
                elif status == "MS":
                    item.setText("MS")
                    item.setBackground(QBrush(QColor("#4a3d17")))
                    item.setForeground(QBrush(QColor("#ffd36a")))
                    item.setToolTip("MS: sector key is missing from the current dictionary")
                else:
                    item.setBackground(QBrush(QColor("#0b0f14" if row % 2 == 0 else "#0f141b")))
                    item.setForeground(QBrush(QColor("#dbe6f3")))
                table.setItem(row, column + 1, item)

            if enable_brute and table.columnCount() >= 18:
                table.removeCellWidget(row, 17)
                self._set_service_table_item(table, row, 17, "")
                if row in sector_action_rows:
                    self._set_brute_progress_widget(table, row, sector_action_rows[row], "ready", True)

    def _set_service_table_item(self, table: QTableWidget, row: int, column: int, value: str) -> None:
        item = QTableWidgetItem(value)
        item.setBackground(QBrush(QColor("#111927")))
        item.setForeground(QBrush(QColor("#9fb3c8")))
        table.setItem(row, column, item)

    def _set_brute_progress_widget(
        self,
        table: QTableWidget,
        row: int,
        block: int,
        text: str,
        show_button: bool,
    ) -> None:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(6)
        if show_button:
            button = QPushButton("Brute")
            button.setStyleSheet(
                "QPushButton { background: #33404f; padding: 1px 8px; } "
                "QPushButton:hover { background: #40546a; }"
            )
            button.clicked.connect(lambda _checked=False, target_block=block: self.start_brute_for_block(target_block))
            layout.addWidget(button)

        status = QLabel(text)
        status.setObjectName("bruteStatus")
        status.setStyleSheet("color: #9fb3c8; background: transparent;")
        status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(status, 1)
        table.setCellWidget(row, 17, container)

    def _device_detail_fields(self) -> list[tuple[str, str]]:
        return [
            ("type", "Type"),
            ("protocol", "Protocol"),
            ("uid", "UID"),
            ("uid_length", "UID len"),
            ("family", "Family"),
            ("memory_read", "Memory"),
            ("block_size", "Block size"),
            ("num_blocks", "Blocks"),
            ("atqa", "ATQA"),
            ("sak", "SAK"),
            ("rc", "RC"),
            ("read_step", "Read step"),
            ("dsfid", "DSFID"),
            ("afi", "AFI"),
            ("ic_reference", "IC ref"),
        ]

    def _device_title_widget(self, key: str, title: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: 600; color: #9fb3c8;")
        title_label.setFixedWidth(66)
        layout.addWidget(title_label)

        tooltip = self._device_field_tooltips().get(key)
        if tooltip:
            help_button = QToolButton()
            help_button.setText("?")
            help_button.setFixedSize(18, 18)
            help_button.setAutoRaise(True)
            help_button.setCursor(Qt.PointingHandCursor)
            help_button.setToolTip(tooltip)
            help_button.clicked.connect(
                lambda _checked=False, button=help_button, text=tooltip: QToolTip.showText(
                    button.mapToGlobal(button.rect().bottomLeft()),
                    text,
                    button,
                )
            )
            help_button.setStyleSheet(
                "border: 1px solid #60728a; border-radius: 8px; color: #d8dee9; background: #1f2a36;"
            )
            layout.addWidget(help_button)

        layout.addStretch(1)
        return container

    def _device_field_tooltips(self) -> dict[str, str]:
        return {
            "atqa": (
                "RU: ATQA - 2 байта ответа ISO14443A на первичный запрос. "
                "Помогает определить семейство и возможности метки.\n"
                "EN: ATQA (Answer To Request) - 2 bytes from ISO14443A anti-collision. "
                "Helps identify card family and capabilities."
            ),
            "sak": (
                "RU: SAK - байт ответа после выбора ISO14443A-метки. "
                "Часто показывает, это MIFARE Classic, Ultralight/NTAG и т.п.\n"
                "EN: SAK (Select Acknowledge) - ISO14443A select response byte. "
                "Often indicates MIFARE Classic, Ultralight/NTAG, etc."
            ),
            "rc": (
                "RU: RC - код результата операции чтения/получения информации. Обычно 0 означает OK.\n"
                "EN: RC - return/status code from the read/info operation. Usually 0 means OK."
            ),
            "dsfid": (
                "RU: DSFID - ISO15693 идентификатор формата хранения данных, если метка его сообщает.\n"
                "EN: DSFID - ISO15693 Data Storage Format Identifier reported by the tag when available."
            ),
            "afi": (
                "RU: AFI - ISO15693 идентификатор семейства приложения. Используется для классификации/фильтрации меток.\n"
                "EN: AFI - ISO15693 Application Family Identifier used to categorize/filter tags."
            ),
        }

    def update_current_device_details(self, metadata: dict, folder: str) -> None:
        self.current_device_label.setText(self._format_current_device(metadata, folder))
        values = {
            "type": metadata.get("type", "-"),
            "protocol": metadata.get("protocol", "-"),
            "uid": metadata.get("uid", "-"),
            "uid_length": metadata.get("uid_length", "-"),
            "family": metadata.get("family", "-"),
            "memory_read": metadata.get("memory_read", "-"),
            "block_size": metadata.get("block_size") or "-",
            "num_blocks": metadata.get("num_blocks") or "-",
            "atqa": metadata.get("atqa", "-"),
            "sak": metadata.get("sak", "-"),
            "rc": metadata.get("rc", "-"),
            "read_step": metadata.get("read_step", "-"),
            "dsfid": metadata.get("dsfid") or "-",
            "afi": metadata.get("afi") or "-",
            "ic_reference": metadata.get("ic_reference") or "-",
        }
        for key, label in self.device_field_labels.items():
            value = str(values.get(key, "-"))
            label.setText(value)
            label.setToolTip(value if value != "-" else "")

    def _format_current_device(self, metadata: dict, folder: str) -> str:
        return (
            f"Current tag: {metadata.get('type', '-')} | "
            f"UID {metadata.get('uid', '-')} | "
            f"memory {metadata.get('memory_read', '-')}"
        )

    def _set_reader_online(self, online: bool) -> None:
        self._set_indicator(self.reader_indicator, online)
        self.reader_state_label.setText("Reader: online" if online else "Reader: offline")
        self.read_button.setEnabled(online)
        self.current_device_refresh_button.setEnabled(online)

    def _set_tag_online(self, online: bool) -> None:
        self._set_indicator(self.tag_indicator, online)
        if not online:
            self.current_device_label.setText("Current tag: none")
            for label in self.device_field_labels.values():
                label.setText("-")

    def _set_indicator(self, label: QLabel, online: bool) -> None:
        color = "#20b15a" if online else "#c62828"
        label.setFixedSize(14, 14)
        label.setStyleSheet(f"border-radius: 7px; background-color: {color};")

    def set_status(self, status: str) -> None:
        if status.startswith("Connected"):
            self.last_logged_device_state = None
            self._set_reader_online(True)
            if not self.scan_timer.isActive():
                self.scan_timer.start()
            self.scan_current_device()
        elif status == "Disconnected":
            self.last_logged_device_state = None
            self._set_reader_online(False)
            self.scan_timer.stop()
        self.status_label.setText(status)

    def show_error(self, message: str) -> None:
        self.read_running = False
        self._set_reader_online(False)
        self.read_button.setEnabled(False)
        self.current_device_refresh_button.setEnabled(False)
        self.scan_timer.stop()
        self.log_view.appendPlainText(message)
        self.status_label.setText(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.setValue("connection/port", self.port_combo.currentData() or "")
        self.settings.setValue("paths/read_export", self.read_export_path_edit.text())
        self.settings.setValue("paths/write_import", self.write_import_path_edit.text())
        if self.worker:
            self.worker.stop()
            self.worker.wait(1500)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
