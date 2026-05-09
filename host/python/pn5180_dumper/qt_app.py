import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports

from PyQt5.QtCore import QSettings, QThread, pyqtSignal
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
from .capture import DumpCapture, save_capture


DEFAULT_BAUD = 460800


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

    def stop(self) -> None:
        self._stop_requested = True

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
        self.write_bytes = b""

        self.setWindowTitle(f"PN5180 Dumper Qt5 v{__version__}")
        self.resize(1080, 720)

        self.reader_indicator = QLabel()
        self.reader_state_label = QLabel("Reader: offline")
        self.port_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh")
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 2_000_000)
        self.baud_spin.setValue(int(self.settings.value("connection/baud", DEFAULT_BAUD)))
        self.baud_spin.setSingleStep(9600)

        self.out_dir_edit = QLineEdit(str(self.settings.value("paths/output_dir", str(Path("captures")))))
        self.browse_button = QPushButton("Browse")
        self.once_check = QCheckBox("Stop after first record")

        self.connect_button = QPushButton("Start capture")
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
        self.read_start_spin = QSpinBox()
        self.read_start_spin.setRange(0, 65535)
        self.read_count_spin = QSpinBox()
        self.read_count_spin.setRange(1, 4096)
        self.read_count_spin.setValue(1)
        self.read_export_path_edit = QLineEdit(str(self.settings.value("paths/read_export", "")))
        self.read_export_browse_button = QPushButton("Browse")
        self.read_export_button = QPushButton("Export dump")
        self.read_export_button.setEnabled(False)
        self.read_hex_table = self._create_hex_table()
        self.read_button = QPushButton("Read")
        self.read_button.setEnabled(False)
        self.read_button.setToolTip("Requires firmware command protocol V2")

        self.write_address_spin = QSpinBox()
        self.write_address_spin.setRange(0, 65535)
        self.write_import_path_edit = QLineEdit(str(self.settings.value("paths/write_import", "")))
        self.write_import_browse_button = QPushButton("Browse")
        self.write_load_button = QPushButton("Load file")
        self.write_hex_table = self._create_hex_table()
        self.write_verify_check = QCheckBox("Verify after write")
        self.write_verify_check.setChecked(True)
        self.write_button = QPushButton("Write")
        self.write_button.setEnabled(False)
        self.write_button.setToolTip("Requires firmware command protocol V2")

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
        connection_layout.addWidget(self.port_combo, 1, 1)
        connection_layout.addWidget(self.refresh_button, 1, 2)
        connection_layout.addWidget(QLabel("Baud"), 1, 3)
        connection_layout.addWidget(self.baud_spin, 1, 4)
        connection_layout.addWidget(QLabel("Output"), 2, 0)
        connection_layout.addWidget(self.out_dir_edit, 2, 1, 1, 4)
        connection_layout.addWidget(self.browse_button, 2, 5)
        connection_layout.addWidget(self.once_check, 3, 1)

        button_row = QHBoxLayout()
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.disconnect_button)
        button_row.addStretch(1)
        button_row.addWidget(self.scan_button)
        connection_layout.addLayout(button_row, 4, 0, 1, 6)

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
        layout.addWidget(QLabel("Start block/page"), 0, 0)
        layout.addWidget(self.read_start_spin, 0, 1)
        layout.addWidget(QLabel("Count"), 0, 2)
        layout.addWidget(self.read_count_spin, 0, 3)
        layout.addWidget(self.read_button, 0, 4)
        layout.addWidget(QLabel("Export path"), 1, 0)
        layout.addWidget(self.read_export_path_edit, 1, 1, 1, 3)
        layout.addWidget(self.read_export_browse_button, 1, 4)
        layout.addWidget(self.read_export_button, 1, 5)
        layout.addWidget(QLabel("Raw dump"), 2, 0, 1, 6)
        layout.addWidget(self.read_hex_table, 3, 0, 1, 6)
        layout.addWidget(
            QLabel("Read will become active after firmware command protocol V2 is implemented."),
            4,
            0,
            1,
            6,
        )
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
        layout.addWidget(QLabel("Raw write buffer"), 2, 0, 1, 6)
        layout.addWidget(self.write_hex_table, 3, 0, 1, 6)
        layout.addWidget(self.write_button, 4, 0, 1, 6)
        layout.addWidget(
            QLabel("Write is intentionally disabled until explicit command-mode safety checks exist."),
            5,
            0,
            1,
            6,
        )
        return tab

    def _create_hex_table(self) -> QTableWidget:
        table = QTableWidget(0, 17)
        table.setHorizontalHeaderLabels(["Offset"] + [f"{i:02X}" for i in range(16)])
        table.setSelectionBehavior(QAbstractItemView.SelectItems)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _connect_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.browse_button.clicked.connect(self.choose_out_dir)
        self.connect_button.clicked.connect(self.start_capture)
        self.disconnect_button.clicked.connect(self.stop_capture)
        self.read_export_browse_button.clicked.connect(self.choose_read_export_path)
        self.read_export_button.clicked.connect(self.export_current_dump)
        self.write_import_browse_button.clicked.connect(self.choose_write_import_path)
        self.write_load_button.clicked.connect(self.load_write_file)
        self.port_combo.currentIndexChanged.connect(self.save_selected_port)

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

    def choose_out_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select capture directory", self.out_dir_edit.text())
        if selected:
            self.out_dir_edit.setText(selected)
            self.settings.setValue("paths/output_dir", selected)

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

    def start_capture(self) -> None:
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "No port", "Select a serial port first.")
            return

        out_dir = Path(self.out_dir_edit.text().strip() or "captures")
        out_dir.mkdir(parents=True, exist_ok=True)

        self.worker = SerialCaptureWorker(
            port=port,
            baud=self.baud_spin.value(),
            out_dir=out_dir,
            once=self.once_check.isChecked(),
        )
        self.worker.line_received.connect(self.append_log)
        self.worker.record_saved.connect(self.add_record)
        self.worker.status_changed.connect(self.set_status)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

        self.settings.setValue("connection/port", port)
        self.settings.setValue("connection/baud", self.baud_spin.value())
        self.settings.setValue("paths/output_dir", str(out_dir))
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.status_label.setText("Connecting...")

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
        self.log_view.appendPlainText(line)

    def add_record(self, metadata: dict, folder: str) -> None:
        self.current_metadata = metadata
        self.current_folder = Path(folder)
        self._set_tag_online(True)
        self.current_device_label.setText(self._format_current_device(metadata, folder))

        dump_path = self.current_folder / "dump.bin"
        if dump_path.exists():
            self.current_dump_bytes = dump_path.read_bytes()
            self.populate_hex_table(self.read_hex_table, self.current_dump_bytes)
            self.read_export_button.setEnabled(True)
            default_export = self.read_export_path_edit.text().strip()
            if not default_export:
                export_path = str(Path(folder) / "export.bin")
                self.read_export_path_edit.setText(export_path)
        else:
            self.current_dump_bytes = b""
            self.populate_hex_table(self.read_hex_table, b"")
            self.read_export_button.setEnabled(False)

        self.status_label.setText(f"Saved record to {folder}")

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
        self.status_label.setText(f"Loaded {len(self.write_bytes)} bytes from {source}")

    def populate_hex_table(self, table: QTableWidget, data: bytes) -> None:
        row_count = (len(data) + 15) // 16
        table.setRowCount(row_count)
        for row in range(row_count):
            offset = row * 16
            table.setItem(row, 0, QTableWidgetItem(f"{offset:08X}"))
            for column in range(16):
                index = offset + column
                value = f"{data[index]:02X}" if index < len(data) else ""
                table.setItem(row, column + 1, QTableWidgetItem(value))
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
        self.settings.setValue("connection/baud", self.baud_spin.value())
        self.settings.setValue("paths/output_dir", self.out_dir_edit.text())
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
