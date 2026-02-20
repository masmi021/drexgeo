#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 2025-11-16
Modified 2025-11-19
Features: PyQtGraph, GPU, Log-Log Fix, Undo, Region Selection

@author: Maxim Smirnov
"""
import sys
import os
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QToolBar, QLabel, QSpinBox,
                             QScrollBar, QSplitter, QFileDialog,
                             QGroupBox, QLineEdit, QFormLayout, QFrame)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
import pyqtgraph as pg

# =========================================================================
# 1. ATS DATA HANDLER
# =========================================================================
class ATSReader:
    def __init__(self, filename=None):
        self.filename = filename
        self.data = None
        self.num_samples = 0
        self.start_time = "2000-01-01 00:00:00"
        self.num_channels = 0

        if filename is None:
            self._generate_mock_data()
        else:
            self.read_ats_file(filename)

    def _generate_mock_data(self):
        self.num_channels = 6
        self.num_samples = 200000
        print(f"Generating mock data: {self.num_channels} channels, {self.num_samples} samples.")
        # Create 6 channels of random walk data
        self.data = np.cumsum(np.random.normal(size=(self.num_channels, self.num_samples)), axis=1)

    def read_ats_file(self, filename):
        try:
            file_size = os.path.getsize(filename)
            with open(filename, 'rb') as f:
                header_offset = 1024
                dt = np.dtype('<i4')
                data_bytes = file_size - header_offset
                samples_in_file = data_bytes // 4

                raw_data = np.fromfile(f, dtype=dt, count=samples_in_file, offset=header_offset)
                self.data = np.array([raw_data])
                self.num_channels = 1
                self.num_samples = samples_in_file
                print(f"Loaded {filename}: {self.num_samples} samples.")
        except Exception as e:
            print(f"Error reading ATS: {e}")
            self._generate_mock_data()

    def get_data_slice(self, start_idx, end_idx):
        start_idx = max(0, start_idx)
        end_idx = min(self.num_samples, end_idx)
        if self.data is not None:
            return self.data[:, start_idx:end_idx]
        return None

# =========================================================================
# 2. MAIN GUI WINDOW
# =========================================================================
class MainQAWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("DREX ts plot")
        self.resize(1200, 800)

        # State Variables
        self.kms_file = ATSReader()
        self.window_length = 2000
        self.segment_number = 0
        self.num_channels_to_plot = 6

        self.plots = []
        self.curves = []

        self.init_ui()
        self.update_ui_state()
        self.replot_all()

    def init_ui(self):
        # --- Toolbar ---
        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)

        btn_open = QAction(QIcon.fromTheme("document-open"), "Open ATS", self)
        btn_open.triggered.connect(self.open_file_dialog)
        self.toolbar.addAction(btn_open)

        self.toolbar.addSeparator()

        lbl_win = QLabel(" Window: ")
        self.toolbar.addWidget(lbl_win)
        self.spin_window = QSpinBox()
        self.spin_window.setRange(100, 1000000)
        self.spin_window.setValue(2000)
        self.spin_window.setSingleStep(500)
        self.spin_window.valueChanged.connect(self.on_window_length_changed)
        self.toolbar.addWidget(self.spin_window)

        self.toolbar.addSeparator()

        # --- "PLOT ALL" BUTTON (CHECKABLE TOGGLE) ---
        self.btn_plot_all = QAction(QIcon.fromTheme("zoom-fit-best"), "Plot All", self)
        self.btn_plot_all.setCheckable(True) # Make it a toggle button
        self.btn_plot_all.setStatusTip("Toggle between Full Data and Segment Mode")
        self.btn_plot_all.toggled.connect(self.action_plot_all_toggled)
        self.toolbar.addAction(self.btn_plot_all)

        btn_reset = QAction(QIcon.fromTheme("zoom-original"), "Auto Scale", self)
        btn_reset.triggered.connect(self.force_auto_scale)
        self.toolbar.addAction(btn_reset)

        # --- Main Layout ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        # Left: Graphics
        self.graph_layout = pg.GraphicsLayoutWidget()
        self.graph_layout.setBackground('w')
        splitter.addWidget(self.graph_layout)
        splitter.setStretchFactor(0, 4)

        # Right: Controls
        controls_panel = QFrame()
        controls_panel.setMaximumWidth(250)
        controls_panel.setStyleSheet("background-color: #f0f0f0; border-left: 1px solid #ccc;")
        vbox_controls = QVBoxLayout(controls_panel)
        splitter.addWidget(controls_panel)
        splitter.setStretchFactor(1, 1)

        # Controls
        grp_channels = QGroupBox("Channels")
        vbox_ch = QVBoxLayout()
        lbl_ch_plot = QLabel("Channels plot")
        self.spin_ch_plot = QSpinBox()
        self.spin_ch_plot.setRange(1, 16)
        self.spin_ch_plot.setValue(6)
        self.spin_ch_plot.valueChanged.connect(self.on_channel_count_changed)
        vbox_ch.addWidget(lbl_ch_plot)
        vbox_ch.addWidget(self.spin_ch_plot)
        grp_channels.setLayout(vbox_ch)
        vbox_controls.addWidget(grp_channels)

        grp_time = QGroupBox("Time Info")
        form_time = QFormLayout()
        self.txt_rx_time = QLineEdit("2000-01-01 00:00:00")
        self.txt_tx_time = QLineEdit("2000-01-01 00:00:00")
        self.txt_rx_time.setReadOnly(True)
        form_time.addRow("Rx Start:", self.txt_rx_time)
        form_time.addRow("Tx Start:", self.txt_tx_time)
        grp_time.setLayout(form_time)
        vbox_controls.addWidget(grp_time)
        vbox_controls.addStretch()

        # --- Bottom Scrollbar ---
        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self.scrollbar.setFixedHeight(20)
        # Using valueChanged ensures both clicks and drags trigger the update
        self.scrollbar.valueChanged.connect(self.on_scroll_interaction)
        main_layout.addWidget(self.scrollbar)

        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label)

    # =========================================================================
    # 3. LOGIC & PLOTTING
    # =========================================================================

    def open_file_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Open ATS File", "", "ATS Files (*.ats);;All Files (*)")
        if fname:
            self.kms_file = ATSReader(fname)
            self.btn_plot_all.setChecked(False) # Reset to segment mode
            self.update_ui_state()
            self.replot_all()

    def update_ui_state(self):
        """Calculates scrollbar limits based on file size and window length."""
        total_samples = self.kms_file.num_samples
        safe_window = max(1, self.window_length)

        # Calculate how many pages (segments) we have
        n_segments = max(0, (total_samples // safe_window) - 1)

        # Update Scrollbar
        self.scrollbar.blockSignals(True) # Prevent triggering update while setting range
        self.scrollbar.setRange(0, n_segments)
        self.scrollbar.setPageStep(1)
        self.scrollbar.blockSignals(False)

        # Update text info
        self.txt_rx_time.setText(str(self.kms_file.start_time))

        # Enable/Disable controls based on Plot All mode
        is_all = self.btn_plot_all.isChecked()
        self.scrollbar.setEnabled(not is_all)
        self.spin_window.setEnabled(not is_all)

    def action_plot_all_toggled(self, checked):
        """Slot for the 'Plot All' toggle button."""
        self.update_ui_state() # Disable/Enable scrollbar
        self.update_plot_data_only() # Refresh data
        self.force_auto_scale() # Ensure we see the full range

        if checked:
            self.status_label.setText(f"Plotting ALL samples ({self.kms_file.num_samples})")
        else:
            self.status_label.setText(f"Switched to Segment Mode")

    def on_window_length_changed(self, val):
        self.window_length = val
        self.btn_plot_all.setChecked(False) # Revert to segment mode
        self.update_ui_state()

        # Clamp segment number to new range
        if self.scrollbar.maximum() < self.segment_number:
            self.segment_number = 0
            self.scrollbar.setValue(0)

        self.update_plot_data_only()

    def on_channel_count_changed(self, val):
        self.num_channels_to_plot = val
        self.replot_all(rebuild_layout=True)

    def on_scroll_interaction(self, val):
        """Handle scrollbar movement."""
        # If we were in Plot All mode, turn it off because user wants to scroll
        if self.btn_plot_all.isChecked():
             self.btn_plot_all.setChecked(False)
             self.update_ui_state()

        self.segment_number = val
        self.update_plot_data_only()

    def force_auto_scale(self):
        for plt in self.plots:
            plt.autoRange()

    def replot_all(self, rebuild_layout=False):
        """Initializes or rebuilds the plot layout structure."""
        if rebuild_layout or len(self.plots) != self.num_channels_to_plot:
            self.graph_layout.clear()
            self.plots = []
            self.curves = []

            first_plot = None
            actual_plots_needed = min(self.num_channels_to_plot, self.kms_file.num_channels)

            # If mocking and requested more channels than exist in mock
            if self.kms_file.num_channels == 0:
                actual_plots_needed = self.num_channels_to_plot

            for i in range(actual_plots_needed):
                p = self.graph_layout.addPlot(row=i, col=0)
                p.showGrid(x=True, y=True, alpha=0.3)
                p.setLabel('left', "mV")
                p.setTitle(f"Ch {i+1}", size="10pt", color='k')

                # Link X-Axis
                if first_plot is None:
                    first_plot = p
                else:
                    p.setXLink(first_plot)

                p.getAxis('left').setPen('k'); p.getAxis('left').setTextPen('k')
                p.getAxis('bottom').setPen('k'); p.getAxis('bottom').setTextPen('k')

                # Blue Color
                blue_pen = pg.mkPen(color="#1f77b4", width=1)
                curve = p.plot(pen=blue_pen)

                self.plots.append(p)
                self.curves.append(curve)

        self.update_plot_data_only()
        self.force_auto_scale() # Reset view on full rebuild

    def update_plot_data_only(self):
        """Fetches data and updates curves AND view range."""

        # 1. Determine Range
        if self.btn_plot_all.isChecked():
            start = 0
            end = self.kms_file.num_samples
            mode_text = "FULL DATASET"
        else:
            start = self.segment_number * self.window_length
            end = start + self.window_length
            mode_text = f"Segment {self.segment_number}"

        # 2. Fetch Data
        data_chunk = self.kms_file.get_data_slice(start, end)

        if data_chunk is None or data_chunk.size == 0:
             self.status_label.setText("No data available.")
             return

        # 3. Create X-Axis
        x_axis = np.arange(start, end)

        # 4. Update Curves
        for i in range(len(self.curves)):
            if i < data_chunk.shape[0]:
                 self.curves[i].setData(x_axis, data_chunk[i])

        # 5. CRITICAL FIX: Force the Camera (ViewBox) to look at the new data range
        # Without this, if you scroll from 0-2000 to 2000-4000,
        # the camera stays at 0-2000 and you see nothing.
        for p in self.plots:
            p.setXRange(start, end, padding=0)
            p.enableAutoRange(axis='y') # Auto-scale Y for the new segment

        self.status_label.setText(f"View: {mode_text} | Samples: {start} - {end}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainQAWindow()
    window.show()
    sys.exit(app.exec())