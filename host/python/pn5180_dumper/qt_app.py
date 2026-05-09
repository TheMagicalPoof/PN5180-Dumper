import sys
import time
from queue import Empty, Queue
from pathlib import Path

import serial
from serial.tools import list_ports

from PyQt5.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .capture import DumpCapture, parse_new_metadata, save_capture
from .keys import load_proxmark_mfc_keys


DEFAULT_BAUD = 460800


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
        self.brute_running = False
        self.write_queue: list[tuple[int, bytes]] = []
        self.write_total = 0
        self.write_done = 0
        self.write_failures: list[str] = []
        self.write_running = False

        self.setWindowTitle(f"PN5180 Dumper Qt5 v{__version__}")
        self.resize(1080, 720)

        self.reader_indicator = QLabel()
        self.reader_state_label = QLabel("Reader: offline")
        self.port_combo = QComboBox()

        self.connect_button = QPushButton("Refresh ports and read once")
        self.disconnect_button = QPushButton("Stop")
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

        self.mode_tabs = QTabWidget()
        self.read_export_path_edit = QLineEdit(str(self.settings.value("paths/read_export", "")))
        self.read_export_browse_button = QPushButton("Browse")
        self.read_export_button = QPushButton("Export dump")
        self.read_export_button.setEnabled(False)
        self.read_hex_table = self._create_hex_table(action_columns=True)
        self.stop_brute_button = QPushButton("Stop Brute")
        self.stop_brute_button.setEnabled(True)
        self.reset_button = QPushButton("RESET")

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
        self.write_button = QPushButton("Write")
        self.write_button.setEnabled(False)
        self.write_button.setToolTip("Writes safe MIFARE Classic data blocks, skipping UID and trailer blocks")

        self._build_layout()
        self._connect_signals()
        self._set_indicator(self.reader_indicator, False)
        self._set_indicator(self.tag_indicator, False)
        self.refresh_ports()

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
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.disconnect_button)
        button_row.addStretch(1)
        button_row.addWidget(self.scan_button)
        connection_layout.addLayout(button_row, 3, 0, 1, 6)

        devices_box = QGroupBox("Current device")
        devices_layout = QVBoxLayout(devices_box)
        current_row = QHBoxLayout()
        current_row.addWidget(self.tag_indicator)
        current_row.addWidget(self.current_device_label)
        current_row.addStretch(1)
        devices_layout.addLayout(current_row)

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

    def _build_read_tab(self) -> QWidget:
        tab = QWidget()
        layout = QGridLayout(tab)
        layout.addWidget(QLabel("Export path"), 0, 0)
        layout.addWidget(self.read_export_path_edit, 0, 1, 1, 3)
        layout.addWidget(self.read_export_browse_button, 0, 4)
        layout.addWidget(self.read_export_button, 0, 5)
        layout.addWidget(self.stop_brute_button, 0, 6)
        layout.addWidget(self.reset_button, 0, 7)
        layout.addWidget(QLabel("Raw dump"), 1, 0, 1, 8)
        layout.addWidget(self.read_hex_table, 2, 0, 1, 8)
        return tab

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
            headers.extend(["Brute", "Progress"])
        table = HexTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setToolTip("Select cells and press Ctrl+C to copy the visible table text.")
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _connect_signals(self) -> None:
        self.connect_button.clicked.connect(lambda _checked=False: self.start_capture(request_initial_dump=True))
        self.disconnect_button.clicked.connect(self.stop_capture)
        self.read_export_browse_button.clicked.connect(self.choose_read_export_path)
        self.read_export_button.clicked.connect(self.export_current_dump)
        self.write_import_browse_button.clicked.connect(self.choose_write_import_path)
        self.write_load_button.clicked.connect(self.load_write_file)
        self.write_button.clicked.connect(self.start_write_dump)
        self.port_combo.currentIndexChanged.connect(self.save_selected_port)
        self.stop_brute_button.clicked.connect(self.stop_brute)
        self.reset_button.clicked.connect(self.reset_session)

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

    def start_capture(self, request_initial_dump: bool = True) -> None:
        self.refresh_ports()
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "No port", "Select a serial port first.")
            return

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
        self.status_label.setText("Connecting...")
        if request_initial_dump:
            self.worker.send_command("PND1 DUMP")

    def stop_capture(self) -> None:
        if self.worker:
            self.worker.stop()
            self.status_label.setText("Stopping...")

    def on_worker_finished(self) -> None:
        self.worker = None
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self._set_reader_online(False)

    def append_log(self, line: str) -> None:
        self._set_reader_online(True)
        if line == "INFO no_card":
            self._set_tag_online(False)
        elif line.startswith("TAG_DETECTED "):
            self.update_detected_tag(line[len("TAG_DETECTED "):], "detecting")
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
                self.current_device_label.setText(self._format_current_device(payload, "capturing"))
        elif line.startswith("PND1 BRUTE_RESULT"):
            self.handle_brute_result(self._parse_fields(line))
        elif line.startswith("PND1 WRITE_RESULT"):
            self.handle_write_result(self._parse_fields(line))
        self.log_view.appendPlainText(line)

    def _parse_fields(self, line: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for part in line.split():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            fields[key] = value
        return fields

    def update_detected_tag(self, payload: str, memory_state: str) -> None:
        fields = self._parse_fields(payload)

        metadata = {
            "type": fields.get("type", "-"),
            "uid": fields.get("uid", "-"),
            "memory_read": memory_state,
            "family": fields.get("family", "-"),
            "sak": fields.get("sak", "-"),
            "num_blocks": None,
        }
        self.current_metadata = metadata
        self._set_tag_online(True)
        self.current_device_label.setText(self._format_current_device(metadata, "capturing"))

    def add_record(self, metadata: dict, folder: str) -> None:
        self.current_metadata = metadata
        self.current_folder = Path(folder)
        self._set_tag_online(True)
        self.current_device_label.setText(self._format_current_device(metadata, folder))

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
            self.write_import_path_edit.setText(str(dump_path))
            self.write_bytes = self.current_dump_bytes
            self.populate_hex_table(self.write_hex_table, self.write_bytes)
            self.write_button.setEnabled(bool(self.write_bytes))
        else:
            self.current_dump_bytes = b""
            self.current_block_statuses = []
            self.populate_hex_table(self.read_hex_table, b"")
            self.read_export_button.setEnabled(False)

        self.status_label.setText(f"Saved record to {folder}")

    def start_brute_for_block(self, block: int) -> None:
        if not self.worker:
            self.start_capture(request_initial_dump=False)
            if not self.worker:
                QMessageBox.information(self, "Serial is stopped", "Start capture first and keep the port connected.")
                return
        if self.brute_running:
            QMessageBox.information(self, "Brute is running", "Stop the current brute task first.")
            return

        try:
            self.brute_keys = load_proxmark_mfc_keys()
        except Exception as exc:
            QMessageBox.warning(self, "Dictionary error", f"Could not load Proxmark dictionaries: {exc}")
            return

        self.brute_queue = [(block, key_type, key) for key in self.brute_keys for key_type in ("A", "B")]
        self.brute_total = len(self.brute_queue)
        self.brute_checked = 0
        self.brute_current_block = block
        self.brute_running = True
        self.update_brute_progress(block)
        self.send_next_brute_attempt()

    def stop_brute(self) -> None:
        self.brute_running = False
        self.brute_queue = []
        if self.brute_current_block is not None:
            self.update_brute_progress(self.brute_current_block, "stopped")
        self.status_label.setText("Brute stopped")

    def reset_session(self) -> None:
        self.brute_running = False
        self.brute_queue = []
        self.brute_total = 0
        self.brute_checked = 0
        self.brute_current_block = None

        self.current_metadata = None
        self.current_folder = None
        self.current_dump_bytes = b""
        self.current_block_statuses = []
        self.write_queue = []
        self.write_total = 0
        self.write_done = 0
        self.write_failures = []
        self.write_running = False
        self.write_button.setEnabled(bool(self.write_bytes))
        self.populate_hex_table(self.read_hex_table, b"", enable_brute=True)
        self.read_export_button.setEnabled(False)
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
                self.update_brute_progress(block, "exhausted")
            self.status_label.setText("Brute exhausted the dictionary")
            return

        block, key_type, key = self.brute_queue.pop(0)
        self.brute_checked += 1
        self.brute_current_block = block
        self.update_brute_progress(block)
        self.worker.send_command(f"PND1 BRUTE {block} {key_type} {key}")

    def handle_brute_result(self, fields: dict[str, str]) -> None:
        if not self.brute_running:
            return

        status = fields.get("status", "")
        block_text = fields.get("block")
        if block_text is None:
            self.send_next_brute_attempt()
            return

        block = int(block_text)
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
            self.populate_hex_table(
                self.read_hex_table,
                self.current_dump_bytes,
                self.current_block_statuses,
                enable_brute=True,
            )
            self.brute_running = False
            self.brute_queue = []
            self.update_brute_progress(block, f"found {fields.get('key_type')} {fields.get('key')}")
            self.status_label.setText(f"Recovered block {block}")
            return

        self.send_next_brute_attempt()

    def update_brute_progress(self, block: int, text: str | None = None) -> None:
        if self.read_hex_table.columnCount() < 19:
            return
        remaining = max(self.brute_total - self.brute_checked, 0)
        value = text or f"{remaining}/{self.brute_total}"
        self.read_hex_table.setItem(block, 18, QTableWidgetItem(value))

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
            self.start_capture(request_initial_dump=False)
            if not self.worker:
                return

        self.write_queue = queue
        self.write_total = len(queue)
        self.write_done = 0
        self.write_failures = []
        self.write_running = True
        self.write_button.setEnabled(False)
        self.status_label.setText(f"Writing 0/{self.write_total} blocks...")
        self.send_next_write_block()

    def send_next_write_block(self) -> None:
        if not self.write_running or not self.worker:
            return
        if not self.write_queue:
            self.write_running = False
            self.write_button.setEnabled(bool(self.write_bytes))
            if self.write_failures:
                self.status_label.setText(
                    f"Write finished with {len(self.write_failures)} failed blocks: {', '.join(self.write_failures[:8])}"
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
        elif status != "skipped_protected":
            self.write_failures.append(f"{block}:{status}")
            if block == "0":
                self.write_queue = []
                self.write_running = False
                self.write_button.setEnabled(bool(self.write_bytes))
                self.status_label.setText(f"UID block 0 failed ({status}); write stopped")
                return
        self.status_label.setText(f"Writing {self.write_done}/{self.write_total} blocks...")
        self.send_next_write_block()

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
        for row in range(row_count):
            offset = row * 16
            table.setItem(row, 0, QTableWidgetItem(f"{offset:08X}"))
            status = block_statuses[row] if block_statuses and row < len(block_statuses) else "OK"
            for column in range(16):
                index = offset + column
                value = f"{data[index]:02X}" if index < len(data) else ""
                item = QTableWidgetItem(value)
                if status == "NN":
                    item.setText("NN")
                    item.setBackground(QBrush(QColor("#ffd6d6")))
                    item.setForeground(QBrush(QColor("#9b1c1c")))
                    item.setToolTip("NN: block was authenticated but not read successfully")
                elif status == "MS":
                    item.setText("MS")
                    item.setBackground(QBrush(QColor("#fff2b8")))
                    item.setForeground(QBrush(QColor("#7a5200")))
                    item.setToolTip("MS: sector key is missing from the current dictionary")
                table.setItem(row, column + 1, item)

            if enable_brute and table.columnCount() >= 19:
                if status in {"NN", "MS"}:
                    button = QPushButton("Pick")
                    button.clicked.connect(lambda _checked=False, block=row: self.start_brute_for_block(block))
                    table.setCellWidget(row, 17, button)
                    table.setItem(row, 18, QTableWidgetItem("ready"))
                else:
                    table.removeCellWidget(row, 17)
                    table.setItem(row, 17, QTableWidgetItem(""))
                    table.setItem(row, 18, QTableWidgetItem(""))
        table.resizeColumnsToContents()

    def _format_current_device(self, metadata: dict, folder: str) -> str:
        return (
            f"Current tag: {metadata.get('type', '-')} | "
            f"UID {metadata.get('uid', '-')} | "
            f"memory {metadata.get('memory_read', '-')} | "
            f"blocks {metadata.get('num_blocks') or '-'} | "
            f"saved {folder}"
        )

    def _set_reader_online(self, online: bool) -> None:
        self._set_indicator(self.reader_indicator, online)
        self.reader_state_label.setText("Reader: online" if online else "Reader: offline")

    def _set_tag_online(self, online: bool) -> None:
        self._set_indicator(self.tag_indicator, online)
        if not online:
            self.current_device_label.setText("Current tag: none")

    def _set_indicator(self, label: QLabel, online: bool) -> None:
        color = "#20b15a" if online else "#c62828"
        label.setFixedSize(14, 14)
        label.setStyleSheet(f"border-radius: 7px; background-color: {color};")

    def set_status(self, status: str) -> None:
        if status.startswith("Connected"):
            self._set_reader_online(True)
        elif status == "Disconnected":
            self._set_reader_online(False)
        self.status_label.setText(status)

    def show_error(self, message: str) -> None:
        self._set_reader_online(False)
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
