#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 2025-11-16
Modified 2025-11-19
Features: PyQtGraph, GPU, Log-Log Fix, Undo, Region Selection

@author: Maxim Smirnov (Modified by Assistant)
"""
import sys
import json
import os
import copy  # <-- NEW: Needed for Undo history
import numpy as np
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QWidget,
    QListWidget, QSplitter, QGroupBox, QPushButton,
    QStatusBar, QToolBar, QButtonGroup, QListWidgetItem,
    QStyle
)

import pyqtgraph as pg

# Configuration
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
pg.setConfigOptions(useOpenGL=True)



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("DREX Geophysics - CSEM Editor Pro")
        self.setGeometry(100, 100, 1200, 800)
        self.current_directory = ""

        # Data Storage
        self.active_data = {}
        self.whattoplot = 'xy'

        # --- NEW: Undo History ---
        self.undo_stack = []

        # --- Core Components ---
        self.create_top_toolbar()
        self.create_menu_bar()
        self.setStatusBar(QStatusBar(self))

        # --- Layout ---
        self.file_list_widget = QListWidget()
        self.file_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list_widget.itemSelectionChanged.connect(self.on_file_selection_changed)

        # Pass it to the plot widget
        self.plot_widget = pg.PlotWidget(
            title="Select files to plot"
        )

        self.plot_widget.setLogMode(x=True, y=False)
        self.plot_widget.setLabel('bottom', "Period", units='sec')
        self.plot_widget.setLabel('left', " ")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.getAxis('bottom').enableAutoSIPrefix(False)
        self.plot_widget.getAxis('left').enableAutoSIPrefix(False)

        self.right_panel = self.create_right_panel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.file_list_widget)
        splitter.addWidget(self.plot_widget)
        splitter.addWidget(self.right_panel)
        splitter.setSizes([150, 700, 150])
        self.setCentralWidget(splitter)

# --- NEW: Region of Interest (ROI) Object ---

        # 1. Define the normal pen (e.g., Solid Blue, Width 3)
        thick_blue_pen = pg.mkPen(color='#0000FF', width=3, style=Qt.PenStyle.SolidLine)

        # 2. Define the HOVER pen (e.g., Dashed Red, Width 4)
        hover_red_pen = pg.mkPen(color='#FF0000', width=4, style=Qt.PenStyle.DashLine)

        # 3. Initialize ROI WITHOUT sideScalers
        self.roi = pg.RectROI([0, 0], [1, 1], pen=thick_blue_pen, sideScalers=False)

        # 4. CRITICAL FIX: Set the hover pen to prevent the border from disappearing
        self.roi.hoverPen = hover_red_pen

        # 5. Helper function and Handle Setup (same as before)
        def add_custom_handle(pos, center, cursor_shape):
            handle = self.roi.addScaleHandle(pos, center)
            handle.setCursor(cursor_shape)
            return handle

        # Corner Handles (Diagonal Resize)
        add_custom_handle([1, 1], [0, 0], Qt.CursorShape.SizeFDiagCursor)
        add_custom_handle([0, 0], [1, 1], Qt.CursorShape.SizeFDiagCursor)
        add_custom_handle([1, 0], [0, 1], Qt.CursorShape.SizeFDiagCursor)
        add_custom_handle([0, 1], [1, 0], Qt.CursorShape.SizeFDiagCursor)


        # Vertical Handles (Vertical Resize)
        add_custom_handle([0.5, 1], [0.5, 0], Qt.CursorShape.SizeVerCursor)
        add_custom_handle([0.5, 0], [0.5, 1], Qt.CursorShape.SizeVerCursor)

        # Horizontal Handles (Horizontal Resize)
        add_custom_handle([1, 0.5], [0, 0.5], Qt.CursorShape.SizeHorCursor)
        add_custom_handle([0, 0.5], [1, 0.5], Qt.CursorShape.SizeHorCursor)

        self.roi_visible = False


        # --- NEW: Global Shortcuts ---
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.shortcut_undo.activated.connect(self.undo_last_action)

        self.shortcut_del = QShortcut(QKeySequence("Delete"), self)
        self.shortcut_del.activated.connect(self.delete_points_in_roi)

        # Also map Backspace to delete
        self.shortcut_back = QShortcut(QKeySequence("Backspace"), self)
        self.shortcut_back.activated.connect(self.delete_points_in_roi)

    def create_top_toolbar(self):
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setIconSize(QSize(32, 32))
        self.addToolBar(self.toolbar)
        style = self.style()

        # File Actions
        act_open = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "Open Directory", self)
        act_open.triggered.connect(self.open_directory_dialog)
        self.toolbar.addAction(act_open)

        act_save = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "Save Changes", self)
        act_save.triggered.connect(self.save_changes_to_disk)
        self.toolbar.addAction(act_save)

        self.toolbar.addSeparator()

        # --- NEW: Undo Action ---
        act_undo = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "Undo (Ctrl+Z)", self)
        act_undo.triggered.connect(self.undo_last_action)
        self.toolbar.addAction(act_undo)

        self.toolbar.addSeparator()

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        # Plot Toggles
        self.btn_amp = QPushButton("Rho")
        self.btn_amp.setCheckable(True)
        self.btn_amp.clicked.connect(self.refresh_plot)
        self.toolbar.addWidget(self.btn_amp)
        self.button_group.addButton(self.btn_amp)

        self.btn_ph = QPushButton("Ph")
        self.btn_ph.setCheckable(True)
        self.btn_ph.clicked.connect(self.refresh_plot)
        self.toolbar.addWidget(self.btn_ph)
        self.button_group.addButton(self.btn_ph)

        self.btn_re = QPushButton("Re")
        self.btn_re.setCheckable(True)
        self.btn_re.setChecked(True)
        self.btn_re.clicked.connect(self.refresh_plot)
        self.toolbar.addWidget(self.btn_re)
        self.button_group.addButton(self.btn_re)

        self.btn_im = QPushButton("Im")
        self.btn_im.setCheckable(True)
        self.btn_im.setChecked(True)
        self.btn_im.clicked.connect(self.refresh_plot)
        self.toolbar.addWidget(self.btn_im)
        self.button_group.addButton(self.btn_im)
        self.button_group.buttons()[0].setChecked(True)

    def create_right_panel(self):
        panel_widget = QWidget()
        layout = QVBoxLayout(panel_widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- NEW: Selection Tools Group ---
        group_tools = QGroupBox("Selection Tools")
        tools_layout = QVBoxLayout()

        self.btn_roi = QPushButton("Show Selection Box")
        self.btn_roi.setCheckable(True)
        self.btn_roi.clicked.connect(self.toggle_roi)
        tools_layout.addWidget(self.btn_roi)

        btn_del_roi = QPushButton("Delete Points in Box")
        btn_del_roi.setStyleSheet("color: red;")
        btn_del_roi.clicked.connect(self.delete_points_in_roi)
        tools_layout.addWidget(btn_del_roi)

        tools_layout.addWidget(QPushButton("Ctrl+Z to Undo", flat=True))
        group_tools.setLayout(tools_layout)
        layout.addWidget(group_tools)

        # Component Group
        group_components = QGroupBox("Components")
        comp_layout = QGridLayout()
        labels = ["xx", "xy", "yx", "yy", "det", "phd"]
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        for i, text in enumerate(labels):
            row, col = divmod(i, 2)
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, t=text: self.handle_component_change(t))
            comp_layout.addWidget(btn, row, col)
            self.button_group.addButton(btn)

        self.button_group.buttons()[0].setChecked(True)
        group_components.setLayout(comp_layout)
        layout.addWidget(group_components)

        layout.addStretch()
        return panel_widget

    def create_menu_bar(self):
        menu_bar = self.menuBar()

        # --- File Menu ---
        file_menu = menu_bar.addMenu("&File")

        file_menu.addAction("Open Directory", self.open_directory_dialog)
        file_menu.addAction("Save Changes", self.save_changes_to_disk)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # --- Edit Menu ---
        edit_menu = menu_bar.addMenu("&Edit")

        # FIXED: Create the Action explicitly to avoid argument type errors
        undo_act = QAction("Undo", self)
        undo_act.setShortcut(QKeySequence("Ctrl+Z"))
        undo_act.triggered.connect(self.undo_last_action)

        edit_menu.addAction(undo_act)
    # --- Logic Methods ---

    def push_to_undo_stack(self):
        """Saves a deep copy of current data to history."""
        # Limit stack size to prevent memory issues (e.g., 50 steps)
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

        # We must use deepcopy because dictionaries and numpy arrays are mutable references
        self.undo_stack.append(copy.deepcopy(self.active_data))
        self.statusBar().showMessage("State saved to Undo history.")

    def undo_last_action(self):
        """Restores the last state from history."""
        if not self.undo_stack:
            self.statusBar().showMessage("Nothing to Undo.")
            return

        self.active_data = self.undo_stack.pop()
        self.refresh_plot()
        self.statusBar().showMessage("Undo successful.")

    def toggle_roi(self, checked):
        """Shows or hides the selection box."""
        if checked:
            # Add ROI to plot
            self.plot_widget.addItem(self.roi)
            # Center it in the current view
            view_range = self.plot_widget.viewRange()
            center_x = (view_range[0][0] + view_range[0][1]) / 2
            center_y = (view_range[1][0] + view_range[1][1]) / 2
            width = (view_range[0][1] - view_range[0][0]) / 4
            height = (view_range[1][1] - view_range[1][0]) / 4

            self.roi.setPos([center_x - width/2, center_y - height/2])
            self.roi.setSize([width, height])
            self.roi_visible = True
        else:
            self.plot_widget.removeItem(self.roi)
            self.roi_visible = False

    def delete_points_in_roi(self):
        """Deletes all points currently inside the selection box."""
        if not self.roi_visible or not self.active_data:
            return

        # Save state before deleting
        self.push_to_undo_stack()

        # Get ROI bounds
        # Remember: X-axis is Log10 of frequency in the plot coordinates
        roi_pos = self.roi.pos()
        roi_size = self.roi.size()

        x_min = roi_pos.x()
        x_max = x_min + roi_size.x()
        y_min = roi_pos.y()
        y_max = y_min + roi_size.y()

        points_deleted = 0

        # Iterate over all files
        for file_path, data in self.active_data.items():
            freq = data['freq']
            re = data['re']
            im = data['im']
            amp = 0.2 * 1/freq * re**2 + im**2
            ph = np.angle(re + im*1j, deg=True)

            # We need log10(freq) to compare with ROI X-coordinates
            x_vals = -np.log10(freq)

            # Find indices to DELETE
            # Point must be within X range AND Y range
            # We need to check which buttons are active to know what Y-values to check

            mask_to_delete = np.zeros_like(freq, dtype=bool)

            # Check if point falls in box for any ACTIVE trace
            if self.btn_re.isChecked():
                mask = (x_vals >= x_min) & (x_vals <= x_max) & (re >= y_min) & (re <= y_max)
                mask_to_delete |= mask

            if self.btn_im.isChecked():
                mask = (x_vals >= x_min) & (x_vals <= x_max) & (im >= y_min) & (im <= y_max)
                mask_to_delete |= mask

            if self.btn_amp.isChecked():
                mask = (x_vals >= x_min) & (x_vals <= x_max) & (amp >= y_min) & (amp <= y_max)
                mask_to_delete |= mask

            if self.btn_ph.isChecked():
                mask = (x_vals >= x_min) & (x_vals <= x_max) & (ph >= y_min) & (ph <= y_max)
                mask_to_delete |= mask

            # Identify indices to keep (inverse of delete mask)
            indices_to_keep = ~mask_to_delete

            if np.any(mask_to_delete):
                points_deleted += np.sum(mask_to_delete)
                # Apply filter to all arrays
                data['freq'] = freq[indices_to_keep]
                data['re'] = re[indices_to_keep]
                data['im'] = im[indices_to_keep]
                data['var'] = data['var'][indices_to_keep]

        if points_deleted > 0:
            self.refresh_plot()
            self.statusBar().showMessage(f"Deleted {points_deleted} points inside region.")
        else:
            self.statusBar().showMessage("No points found inside the selection box.")

    # --- Existing Logic (Updated for Undo) ---

    def open_directory_dialog(self):
        dir_name = QFileDialog.getExistingDirectory(self, "Open Directory", "")
        if dir_name:
            self.current_directory = dir_name
            self.file_list_widget.clear()
            self.active_data = {}
            self.undo_stack = [] # Clear undo history on new load
            self.plot_widget.clear()
            try:
                files = sorted([f for f in os.listdir(dir_name) if f.endswith(".json")])
                for file_name in files:
                    item = QListWidgetItem(file_name)
                    self.file_list_widget.addItem(item)
                self.statusBar().showMessage(f"Loaded {len(files)} files.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error: {e}")

    def handle_component_change(self, label):
        self.whattoplot = label
        self.undo_stack = [] # Clear undo when switching components (simpler logic)
        self.load_selected_data_into_memory()
        self.refresh_plot()

    def on_file_selection_changed(self):
        self.load_selected_data_into_memory()
        self.refresh_plot()

    def load_selected_data_into_memory(self):
        self.active_data = {}
        selected_items = self.file_list_widget.selectedItems()
        for item in selected_items:
            file_name = item.text()
            file_path = os.path.join(self.current_directory, file_name)
            try:
                with open(file_path, 'r') as f:
                    json_data = json.load(f)
                if ('Data' in json_data and 'Z' in json_data['Data']):
                    comp_data = json_data['Data']['Z'][self.whattoplot]
                    freq_data = json_data['Data']['Freq']

                    freq = np.array(freq_data)
                    re = np.array(comp_data['Re'])
                    im = np.array(comp_data['Im'])
                    var = np.array(comp_data['Var'])

                    valid_mask = (freq > 0)
                    self.active_data[file_path] = {
                        'freq': freq[valid_mask],
                        're': re[valid_mask],
                        'im': im[valid_mask],
                        'var': var[valid_mask],
                        'original_json': json_data
                    }
            except Exception as e:
                print(f"Error loading {file_name}: {e}")

    def on_point_clicked(self, plot_item, points):
        if not points: return

        # Push state to undo stack BEFORE making changes
        self.push_to_undo_stack()

        point = points[0]
        meta = point.data()
        file_path = meta['file']
        idx_to_remove = meta['idx']

        data_block = self.active_data[file_path]
        data_block['freq'] = np.delete(data_block['freq'], idx_to_remove)
        data_block['re'] = np.delete(data_block['re'], idx_to_remove)
        data_block['im'] = np.delete(data_block['im'], idx_to_remove)
        data_block['var'] = np.delete(data_block['var'], idx_to_remove)

        self.refresh_plot()
        self.statusBar().showMessage("Point deleted. (Ctrl+Z to Undo)")

    def refresh_plot(self):
        self.plot_widget.clear()
        if self.roi_visible:
            self.plot_widget.addItem(self.roi) # Re-add ROI if it was visible

        if not self.active_data: return

        colors = ['b', 'r', 'g', 'c', 'm', 'k']
        file_idx = 0
        for file_path, data in self.active_data.items():
            color = colors[file_idx % len(colors)]
            file_idx += 1

            freq = data['freq']
            re = data['re']
            im = data['im']
            var = data['var']
            sigma = np.sqrt(var) * 2
            x_vals = -np.log10(freq) # Manual Log10 for correct plotting

            def add_trace(y_values, y_errors, symbol, tag):
                err = pg.ErrorBarItem(x=x_vals, y=y_values, top=y_errors, bottom=y_errors, beam=0.05, pen=color)
                self.plot_widget.addItem(err)

                pts_data = [{'file': file_path, 'idx': i, 'type': tag} for i in range(len(freq))]
                scatter = pg.ScatterPlotItem(
                    x=x_vals, y=y_values, data=pts_data,
                    size=12, pen=pg.mkPen('k', width=0.5), brush=color, symbol=symbol,
                    hoverable=True, hoverBrush='w'
                )
                scatter.sigClicked.connect(self.on_point_clicked)
                self.plot_widget.addItem(scatter)

            self.plot_widget.setLogMode(True, False)
            if self.btn_re.isChecked(): add_trace(re, sigma, 'o', 'Re')
            if self.btn_im.isChecked(): add_trace(im, sigma, 'x', 'Im')
            if self.btn_amp.isChecked():
                self.plot_widget.setLogMode(True, True)
                amp = np.sqrt(re**2 + im**2)
                sigma = np.sqrt(var)/amp
                amp = np.log10(0.2/freq*amp**2)
                add_trace(amp, sigma, 's', 'Rho')
            if self.btn_ph.isChecked():
                ph = np.angle(re + im*1j, deg=True)
                add_trace(ph, np.zeros_like(ph), 't', 'Ph')

    def save_changes_to_disk(self):
        if not self.active_data: return
        count = 0
        try:
            for file_path, modified_data in self.active_data.items():
                full_json = modified_data['original_json']
                target_block = full_json['Data']['Z'][self.whattoplot]

                full_json['Data']['Freq'] = modified_data['freq'].tolist()
                target_block['Re'] = modified_data['re'].tolist()
                target_block['Im'] = modified_data['im'].tolist()
                target_block['Var'] = modified_data['var'].tolist()

                with open(file_path, 'w') as f:
                    json.dump(full_json, f, indent=4)
                count += 1
            QMessageBox.information(self, "Success", f"Saved changes to {count} file(s).")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
