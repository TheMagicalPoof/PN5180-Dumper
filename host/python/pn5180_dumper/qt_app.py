import sys
import time
from pathlib import Path

import serial
from serial.tools import list_ports

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
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

        self.setWindowTitle(f"PN5180 Dumper Qt5 v{__version__}")
        self.resize(1080, 720)

        self.port_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh")
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 2_000_000)
        self.baud_spin.setValue(DEFAULT_BAUD)
        self.baud_spin.setSingleStep(9600)

        self.out_dir_edit = QLineEdit(str(Path("captures")))
        self.browse_button = QPushButton("Browse")
        self.once_check = QCheckBox("Stop after first record")

        self.connect_button = QPushButton("Start capture")
        self.disconnect_button = QPushButton("Stop")
        self.disconnect_button.setEnabled(False)

        self.scan_button = QPushButton("Scan")
        self.identify_button = QPushButton("Identify")
        self.read_button = QPushButton("Read")
        self.write_button = QPushButton("Write")
        for button in (self.scan_button, self.identify_button, self.read_button, self.write_button):
            button.setEnabled(False)
            button.setToolTip("Reserved for firmware command protocol V2")

        self.status_label = QLabel("Idle")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)

        self.records_table = QTableWidget(0, 7)
        self.records_table.setHorizontalHeaderLabels(
            ["Type", "UID", "RC", "Blocks", "Block size", "Dump", "Folder"]
        )
        self.records_table.horizontalHeader().setStretchLastSection(True)

        self._build_layout()
        self._connect_signals()
        self.refresh_ports()

    def _build_layout(self) -> None:
        root = QWidget()
        main_layout = QVBoxLayout(root)

        connection_box = QGroupBox("Connection")
        connection_layout = QGridLayout(connection_box)
        connection_layout.addWidget(QLabel("Port"), 0, 0)
        connection_layout.addWidget(self.port_combo, 0, 1)
        connection_layout.addWidget(self.refresh_button, 0, 2)
        connection_layout.addWidget(QLabel("Baud"), 0, 3)
        connection_layout.addWidget(self.baud_spin, 0, 4)
        connection_layout.addWidget(QLabel("Output"), 1, 0)
        connection_layout.addWidget(self.out_dir_edit, 1, 1, 1, 4)
        connection_layout.addWidget(self.browse_button, 1, 5)
        connection_layout.addWidget(self.once_check, 2, 1)

        button_row = QHBoxLayout()
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.disconnect_button)
        button_row.addStretch(1)
        button_row.addWidget(self.scan_button)
        button_row.addWidget(self.identify_button)
        button_row.addWidget(self.read_button)
        button_row.addWidget(self.write_button)
        connection_layout.addLayout(button_row, 3, 0, 1, 6)

        main_layout.addWidget(connection_box)
        main_layout.addWidget(QLabel("Detected records"))
        main_layout.addWidget(self.records_table, 2)
        main_layout.addWidget(QLabel("Serial log"))
        main_layout.addWidget(self.log_view, 3)
        main_layout.addWidget(self.status_label)

        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.browse_button.clicked.connect(self.choose_out_dir)
        self.connect_button.clicked.connect(self.start_capture)
        self.disconnect_button.clicked.connect(self.stop_capture)

    def refresh_ports(self) -> None:
        current = self.port_combo.currentData()
        self.port_combo.clear()
        for port in list_ports.comports():
            label = f"{port.device} - {port.description}"
            self.port_combo.addItem(label, port.device)
        if current:
            index = self.port_combo.findData(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)

    def choose_out_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select capture directory", self.out_dir_edit.text())
        if selected:
            self.out_dir_edit.setText(selected)

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

    def append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def add_record(self, metadata: dict, folder: str) -> None:
        row = self.records_table.rowCount()
        self.records_table.insertRow(row)
        values = [
            metadata.get("type", "-"),
            metadata.get("uid", "-"),
            metadata.get("rc", "-"),
            str(metadata.get("num_blocks") or "-"),
            str(metadata.get("block_size") or "-"),
            "yes" if metadata.get("has_dump") else "no",
            folder,
        ]
        for column, value in enumerate(values):
            self.records_table.setItem(row, column, QTableWidgetItem(value))
        self.status_label.setText(f"Saved record to {folder}")

    def set_status(self, status: str) -> None:
        self.status_label.setText(status)

    def show_error(self, message: str) -> None:
        self.log_view.appendPlainText(message)
        self.status_label.setText(message)

    def closeEvent(self, event) -> None:  # noqa: N802
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

