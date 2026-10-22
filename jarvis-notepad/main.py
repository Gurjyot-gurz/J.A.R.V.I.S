#!/usr/bin/env python3
"""
JARVIS Notepad  --  a system notes app (dark, Apple-Notes-flavored).

Features
--------
* Sidebar of note cards on the left.
* Rich editor on the right (title + body).
* Link notes together ("connect one note to another") via a Linked Notes
  section; linked notes are clickable chips that open each other.
* Search box in the top-right (Apple-style): matches note titles AND the
  text inside note bodies. Results render on a dedicated "Search Results"
  page showing every matched note with a snippet; click a result to open
  it and jump to the matched text.
* Everything persists to a local JSON file.

Run:  python main.py
Build: run build.bat  (PyInstaller -> one .exe)
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from typing import List, Dict, Optional

from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QListWidget, QListWidgetItem, QMenu, QScrollArea,
    QFrame, QDialog, QComboBox, QSizePolicy, QToolButton,
    QMessageBox, QGraphicsDropShadowEffect, QAbstractItemView
)
from PyQt5.QtGui import QFont, QTextCursor, QColor, QIcon, QKeySequence, QPalette


STORAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.json")


def format_timestamp(dt_str: str) -> str:
    """Format an ISO timestamp into human readable relative date/time."""
    try:
        dt = datetime.fromisoformat(dt_str)
        now = datetime.now()
        if dt.date() == now.date():
            return dt.strftime("%I:%M %p").lstrip("0")
        elif (now - dt).days == 1:
            return "Yesterday"
        elif (now - dt).days < 7:
            return dt.strftime("%A")
        else:
            return dt.strftime("%b %d, %Y")
    except Exception:
        return dt_str


class Note:
    """Note data model."""
    def __init__(
        self,
        note_id: Optional[str] = None,
        title: str = "New Note",
        content: str = "",
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        linked_ids: Optional[List[str]] = None
    ):
        self.id = note_id or str(uuid.uuid4())
        self.title = title
        self.content = content
        now = datetime.now().isoformat()
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self.linked_ids = linked_ids or []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "linked_ids": self.linked_ids
        }

    @classmethod
    def from_dict(cls, data: dict) -> Note:
        return cls(
            note_id=data.get("id"),
            title=data.get("title", "Untitled Note"),
            content=data.get("content", ""),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            linked_ids=data.get("linked_ids", [])
        )

    def get_preview(self) -> str:
        lines = [line.strip() for line in self.content.splitlines() if line.strip()]
        if lines:
            return lines[0][:60]
        return "No additional text"


class LinkNoteDialog(QDialog):
    """Dialog to select a note to link with the current note."""
    def __init__(self, current_note: Note, all_notes: List[Note], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Note")
        self.setFixedSize(360, 220)
        self.setStyleSheet("""
            QDialog {
                background-color: #252526;
                color: #e0e0e0;
                border-radius: 8px;
            }
            QLabel {
                color: #dcdcdc;
                font-size: 13px;
            }
            QComboBox {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QPushButton {
                background-color: #e5b567;
                color: #121212;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #f0c377;
            }
            QPushButton#cancelBtn {
                background-color: #383838;
                color: #cccccc;
            }
            QPushButton#cancelBtn:hover {
                background-color: #484848;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        label = QLabel("Select a note to link to this note:")
        layout.addWidget(label)

        self.combo = QComboBox()
        self.notes_map = {}

        # Exclude current note and already linked notes
        available_notes = [
            n for n in all_notes
            if n.id != current_note.id and n.id not in current_note.linked_ids
        ]

        if not available_notes:
            self.combo.addItem("No available notes to link")
            self.combo.setEnabled(False)
        else:
            for note in available_notes:
                display_text = note.title if note.title.strip() else "Untitled Note"
                self.combo.addItem(display_text, note.id)
                self.notes_map[self.combo.count() - 1] = note.id

        layout.addWidget(self.combo)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.link_btn = QPushButton("Link Note")
        if not available_notes:
            self.link_btn.setEnabled(False)
        self.link_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.link_btn)

        layout.addLayout(btn_layout)

    def get_selected_note_id(self) -> Optional[str]:
        idx = self.combo.currentIndex()
        return self.combo.itemData(idx)


class NoteCardItem(QListWidgetItem):
    """Custom QListWidgetItem holding Note metadata."""
    def __init__(self, note: Note):
        super().__init__()
        self.note_id = note.id
        self.update_content(note)

    def update_content(self, note: Note):
        title = note.title.strip() or "Untitled Note"
        time_str = format_timestamp(note.updated_at)
        preview = note.get_preview()

        self.setText(f"{title}\n{time_str}  •  {preview}")
        self.setSizeHint(QSize(0, 68))


class NoteCardWidget(QWidget):
    """Custom widget rendered inside note sidebar list."""
    def __init__(self, note: Note, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        self.title_label = QLabel(note.title.strip() or "Untitled Note")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #f0f0f0;")

        sub_layout = QHBoxLayout()
        sub_layout.setSpacing(6)

        self.time_label = QLabel(format_timestamp(note.updated_at))
        self.time_label.setStyleSheet("font-size: 12px; color: #e5b567;")

        self.preview_label = QLabel(note.get_preview())
        self.preview_label.setStyleSheet("font-size: 12px; color: #8e8e93;")
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        sub_layout.addWidget(self.time_label)
        sub_layout.addWidget(self.preview_label)

        layout.addWidget(self.title_label)
        layout.addLayout(sub_layout)


class JARVISNotepad(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS Notepad")
        self.resize(1100, 720)

        self.notes: Dict[str, Note] = {}
        self.current_note_id: Optional[str] = None
        self.is_loading_note = False

        self.setup_ui()
        self.apply_styles()
        self.load_notes()

        # Save debounce timer
        self.save_timer = QTimer()
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_current_note)

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main splitter (Sidebar | Content)
        self.splitter = QSplitter(Qt.Horizontal)

        # ------------------ SIDEBAR ------------------
        sidebar = QWidget()
        sidebar.setMinimumWidth(260)
        sidebar.setMaximumWidth(380)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(10)

        # Top Bar in Sidebar
        top_bar = QHBoxLayout()

        app_title = QLabel("JARVIS Notes")
        app_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        app_title.setStyleSheet("color: #ffffff; font-weight: 700;")

        new_btn = QPushButton("+")
        new_btn.setFixedSize(32, 32)
        new_btn.setToolTip("Create New Note (Ctrl+N)")
        new_btn.setShortcut(QKeySequence("Ctrl+N"))
        new_btn.clicked.connect(self.create_new_note)
        new_btn.setStyleSheet("""
            QPushButton {
                background-color: #e5b567;
                color: #121212;
                font-size: 20px;
                font-weight: bold;
                border-radius: 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #f0c377;
            }
        """)

        top_bar.addWidget(app_title)
        top_bar.addStretch()
        top_bar.addWidget(new_btn)

        sidebar_layout.addLayout(top_bar)

        # Search Bar (Top-Right search style, put in header)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search all notes...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.on_search_changed)
        sidebar_layout.addWidget(self.search_input)

        # Note Cards List
        self.note_list = QListWidget()
        self.note_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.note_list.itemSelectionChanged.connect(self.on_note_selected)
        self.note_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.note_list.customContextMenuRequested.connect(self.show_note_context_menu)

        sidebar_layout.addWidget(self.note_list)

        self.splitter.addWidget(sidebar)

        # ------------------ RIGHT STACKED CONTENT ------------------
        self.stack = QStackedWidget()

        # Page 0: Note Editor Page
        self.editor_page = QWidget()
        editor_layout = QVBoxLayout(self.editor_page)
        editor_layout.setContentsMargins(24, 20, 24, 20)
        editor_layout.setSpacing(12)

        # Editor Header
        header_layout = QHBoxLayout()

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Title")
        self.title_edit.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.title_edit.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #ffffff;
                font-size: 22px;
                font-weight: bold;
                padding: 4px 0px;
            }
            QLineEdit:focus {
                border-bottom: 2px solid #e5b567;
            }
        """)
        self.title_edit.textChanged.connect(self.on_note_modified)

        self.date_label = QLabel()
        self.date_label.setStyleSheet("color: #8e8e93; font-size: 12px; margin-right: 12px;")

        link_btn = QPushButton("🔗 Link Note")
        link_btn.setToolTip("Connect this note to another note")
        link_btn.clicked.connect(self.open_link_dialog)
        link_btn.setStyleSheet("""
            QPushButton {
                background-color: #2c2c2e;
                color: #e5b567;
                border: 1px solid #3a3a3c;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3a3a3c;
            }
        """)

        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(34, 34)
        delete_btn.setToolTip("Delete Note")
        delete_btn.clicked.connect(self.delete_current_note)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #2c2c2e;
                color: #ff453a;
                border: 1px solid #3a3a3c;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #3a3a3c;
            }
        """)

        header_layout.addWidget(self.title_edit, stretch=1)
        header_layout.addWidget(self.date_label)
        header_layout.addWidget(link_btn)
        header_layout.addWidget(delete_btn)

        editor_layout.addLayout(header_layout)

        # Linked Notes Section (chips container)
        self.links_frame = QFrame()
        self.links_frame.setStyleSheet("""
            QFrame {
                background-color: #1c1c1e;
                border: 1px solid #2c2c2e;
                border-radius: 8px;
                padding: 6px;
            }
        """)
        links_box = QHBoxLayout(self.links_frame)
        links_box.setContentsMargins(8, 4, 8, 4)
        links_box.setSpacing(8)

        links_label = QLabel("Linked:")
        links_label.setStyleSheet("color: #8e8e93; font-weight: bold; font-size: 12px;")
        links_box.addWidget(links_label)

        self.chips_layout = QHBoxLayout()
        self.chips_layout.setSpacing(6)
        links_box.addLayout(self.chips_layout)
        links_box.addStretch()

        editor_layout.addWidget(self.links_frame)

        # Body Text Editor
        self.body_edit = QTextEdit()
        self.body_edit.setPlaceholderText("Start typing your note...")
        self.body_edit.setFont(QFont("Segoe UI", 13))
        self.body_edit.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                color: #e0e0e0;
                font-size: 15px;
                line-height: 1.5;
            }
        """)
        self.body_edit.textChanged.connect(self.on_note_modified)

        editor_layout.addWidget(self.body_edit, stretch=1)

        self.stack.addWidget(self.editor_page)

        # Page 1: Search Results View
        self.search_page = QWidget()
        search_layout = QVBoxLayout(self.search_page)
        search_layout.setContentsMargins(24, 20, 24, 20)

        self.search_header = QLabel("Search Results")
        self.search_header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.search_header.setStyleSheet("color: #ffffff; margin-bottom: 10px;")
        search_layout.addWidget(self.search_header)

        self.search_results_list = QListWidget()
        self.search_results_list.itemClicked.connect(self.on_search_result_clicked)
        search_layout.addWidget(self.search_results_list)

        self.stack.addWidget(self.search_page)

        # Empty State Widget (When no notes exist)
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.setAlignment(Qt.AlignCenter)

        empty_icon = QLabel("📝")
        empty_icon.setFont(QFont("Segoe UI", 48))
        empty_label = QLabel("No Note Selected")
        empty_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        empty_label.setStyleSheet("color: #8e8e93;")

        create_first_btn = QPushButton("Create a Note")
        create_first_btn.setFixedSize(140, 36)
        create_first_btn.clicked.connect(self.create_new_note)
        create_first_btn.setStyleSheet("""
            QPushButton {
                background-color: #e5b567;
                color: #121212;
                font-weight: bold;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #f0c377;
            }
        """)

        empty_layout.addWidget(empty_icon, alignment=Qt.AlignCenter)
        empty_layout.addWidget(empty_label, alignment=Qt.AlignCenter)
        empty_layout.addSpacing(12)
        empty_layout.addWidget(create_first_btn, alignment=Qt.AlignCenter)

        self.stack.addWidget(self.empty_page)

        self.splitter.addWidget(self.stack)
        self.splitter.setSizes([300, 800])

        main_layout.addWidget(self.splitter)

    def apply_styles(self):
        """Apply dark Apple Notes-style theme stylesheet."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                color: #e0e0e0;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            }
            QSplitter::handle {
                background-color: #2a2a2c;
                width: 1px;
            }
            QLineEdit#search_input, QLineEdit {
                background-color: #2c2c2e;
                color: #ffffff;
                border: 1px solid #3a3a3c;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #e5b567;
            }
            QListWidget {
                background-color: #181819;
                border: 1px solid #2a2a2c;
                border-radius: 8px;
                outline: none;
                padding: 4px;
            }
            QListWidget::item {
                background-color: transparent;
                border-radius: 6px;
                margin-bottom: 4px;
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #38383a;
            }
            QListWidget::item:hover:!selected {
                background-color: #252528;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #424245;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #636366;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    # ------------------ PERSISTENCE ------------------
    def load_notes(self):
        """Load notes from JSON file."""
        if os.path.exists(STORAGE_FILE):
            try:
                with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        note = Note.from_dict(item)
                        self.notes[note.id] = note
            except Exception as e:
                print(f"Error loading notes: {e}")

        # If empty, create a default welcome note
        if not self.notes:
            welcome_note = Note(
                title="Welcome to JARVIS Notes",
                content="JARVIS Notepad is your fast, dark-themed notes app.\n\n"
                        "✨ Features:\n"
                        "• Link notes together using the 'Link Note' button above.\n"
                        "• Search across titles and contents instantly using the search bar.\n"
                        "• Auto-saves automatically as you type.\n\n"
                        "Try creating a new note with Ctrl+N or the '+' button!"
            )
            self.notes[welcome_note.id] = welcome_note
            self.save_all_notes()

        self.refresh_note_list()

        # Select first note
        if self.notes:
            first_id = list(self.notes.keys())[0]
            self.select_note_by_id(first_id)

    def save_all_notes(self):
        """Persist all notes to JSON file."""
        try:
            data = [note.to_dict() for note in self.notes.values()]
            with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving notes: {e}")

    # ------------------ LOGIC & ACTIONS ------------------
    def refresh_note_list(self):
        """Refresh sidebar list items sorted by updated_at descending."""
        self.note_list.blockSignals(True)
        self.note_list.clear()

        sorted_notes = sorted(
            self.notes.values(),
            key=lambda n: n.updated_at,
            reverse=True
        )

        for note in sorted_notes:
            item = QListWidgetItem(self.note_list)
            item.setData(Qt.UserRole, note.id)

            card_widget = NoteCardWidget(note)
            item.setSizeHint(card_widget.sizeHint())
            self.note_list.addItem(item)
            self.note_list.setItemWidget(item, card_widget)

            if note.id == self.current_note_id:
                item.setSelected(True)

        self.note_list.blockSignals(False)

    def select_note_by_id(self, note_id: str, highlight_text: str = ""):
        """Switch to editor view and display the given note."""
        if note_id not in self.notes:
            return

        self.current_note_id = note_id
        note = self.notes[note_id]

        self.is_loading_note = True

        self.title_edit.setText(note.title)
        self.body_edit.setPlainText(note.content)
        self.date_label.setText(format_timestamp(note.updated_at))

        self.update_linked_chips(note)
        self.stack.setCurrentWidget(self.editor_page)

        # Highlight search match if requested
        if highlight_text:
            cursor = self.body_edit.textCursor()
            pos = note.content.lower().find(highlight_text.lower())
            if pos != -1:
                cursor.setPosition(pos)
                cursor.setPosition(pos + len(highlight_text), QTextCursor.KeepAnchor)
                self.body_edit.setTextCursor(cursor)
                self.body_edit.ensureCursorVisible()

        self.is_loading_note = False

        # Highlight in sidebar
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if item.data(Qt.UserRole) == note_id:
                self.note_list.blockSignals(True)
                self.note_list.setCurrentItem(item)
                self.note_list.blockSignals(False)
                break

    def update_linked_chips(self, note: Note):
        """Re-render linked note chips."""
        # Clear existing chips
        while self.chips_layout.count():
            child = self.chips_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not note.linked_ids:
            self.links_frame.hide()
            return

        self.links_frame.show()

        for link_id in list(note.linked_ids):
            if link_id not in self.notes:
                continue
            linked_note = self.notes[link_id]

            # Chip container widget
            chip = QWidget()
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 2, 8, 2)
            chip_layout.setSpacing(4)
            chip.setStyleSheet("""
                QWidget {
                    background-color: #2c2c2e;
                    border: 1px solid #3a3a3c;
                    border-radius: 12px;
                }
                QWidget:hover {
                    background-color: #3a3a3c;
                }
            """)

            chip_btn = QPushButton(f"📄 {linked_note.title or 'Untitled Note'}")
            chip_btn.setFlat(True)
            chip_btn.setStyleSheet("""
                QPushButton {
                    color: #e5b567;
                    border: none;
                    font-size: 12px;
                    font-weight: bold;
                    background: transparent;
                }
            """)
            chip_btn.clicked.connect(lambda _, lid=link_id: self.select_note_by_id(lid))
            chip_layout.addWidget(chip_btn)

            # Unlink button
            unlink_btn = QToolButton()
            unlink_btn.setText("×")
            unlink_btn.setToolTip("Remove link")
            unlink_btn.setStyleSheet("""
                QToolButton {
                    color: #8e8e93;
                    border: none;
                    font-size: 14px;
                    font-weight: bold;
                    background: transparent;
                }
                QToolButton:hover {
                    color: #ff453a;
                }
            """)
            unlink_btn.clicked.connect(lambda _, lid=link_id: self.remove_note_link(lid))
            chip_layout.addWidget(unlink_btn)

            self.chips_layout.addWidget(chip)

    def create_new_note(self):
        """Create a new note and set focus to editor."""
        new_note = Note(title="Untitled Note", content="")
        self.notes[new_note.id] = new_note
        self.save_all_notes()

        self.refresh_note_list()
        self.select_note_by_id(new_note.id)
        self.title_edit.selectAll()
        self.title_edit.setFocus()

    def delete_current_note(self):
        """Delete current note after confirmation."""
        if not self.current_note_id or self.current_note_id not in self.notes:
            return

        note = self.notes[self.current_note_id]
        reply = QMessageBox.question(
            self,
            "Delete Note",
            f"Are you sure you want to delete '{note.title}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Remove link references from other notes
            del_id = self.current_note_id
            del self.notes[del_id]

            for n in self.notes.values():
                if del_id in n.linked_ids:
                    n.linked_ids.remove(del_id)

            self.current_note_id = None
            self.save_all_notes()
            self.refresh_note_list()

            if self.notes:
                first_id = list(self.notes.keys())[0]
                self.select_note_by_id(first_id)
            else:
                self.stack.setCurrentWidget(self.empty_page)

    def open_link_dialog(self):
        """Open dialog to connect current note to another note."""
        if not self.current_note_id or self.current_note_id not in self.notes:
            return

        current_note = self.notes[self.current_note_id]
        dialog = LinkNoteDialog(current_note, list(self.notes.values()), self)

        if dialog.exec_() == QDialog.Accepted:
            selected_id = dialog.get_selected_note_id()
            if selected_id and selected_id in self.notes:
                # Bidirectional link
                if selected_id not in current_note.linked_ids:
                    current_note.linked_ids.append(selected_id)

                other_note = self.notes[selected_id]
                if current_note.id not in other_note.linked_ids:
                    other_note.linked_ids.append(current_note.id)

                self.save_all_notes()
                self.update_linked_chips(current_note)

    def remove_note_link(self, target_id: str):
        """Remove link between current note and target note."""
        if not self.current_note_id or self.current_note_id not in self.notes:
            return

        current_note = self.notes[self.current_note_id]
        if target_id in current_note.linked_ids:
            current_note.linked_ids.remove(target_id)

        if target_id in self.notes:
            target_note = self.notes[target_id]
            if current_note.id in target_note.linked_ids:
                target_note.linked_ids.remove(current_note.id)

        self.save_all_notes()
        self.update_linked_chips(current_note)

    def on_note_selected(self):
        """Handler for selection change in sidebar list."""
        if self.is_loading_note:
            return

        selected_items = self.note_list.selectedItems()
        if selected_items:
            note_id = selected_items[0].data(Qt.UserRole)
            if note_id:
                self.select_note_by_id(note_id)

    def on_note_modified(self):
        """Trigger debounce timer on note title or body edit."""
        if self.is_loading_note or not self.current_note_id:
            return
        self.save_timer.start(400)

    def save_current_note(self):
        """Save active note updates."""
        if not self.current_note_id or self.current_note_id not in self.notes:
            return

        note = self.notes[self.current_note_id]
        note.title = self.title_edit.text()
        note.content = self.body_edit.toPlainText()
        note.updated_at = datetime.now().isoformat()

        self.date_label.setText(format_timestamp(note.updated_at))
        self.save_all_notes()

        # Refresh sidebar card
        self.refresh_note_list()

    def show_note_context_menu(self, pos):
        """Context menu for note item in sidebar."""
        item = self.note_list.itemAt(pos)
        if not item:
            return

        note_id = item.data(Qt.UserRole)
        if not note_id or note_id not in self.notes:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2c2c2e;
                color: #ffffff;
                border: 1px solid #3a3a3c;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #e5b567;
                color: #121212;
            }
        """)

        delete_action = menu.addAction("Delete Note")
        action = menu.exec_(self.note_list.mapToGlobal(pos))

        if action == delete_action:
            self.select_note_by_id(note_id)
            self.delete_current_note()

    # ------------------ SEARCH ------------------
    def on_search_changed(self, text: str):
        """Handle search query update."""
        query = text.strip().lower()

        if not query:
            if self.current_note_id:
                self.stack.setCurrentWidget(self.editor_page)
            elif self.notes:
                first_id = list(self.notes.keys())[0]
                self.select_note_by_id(first_id)
            else:
                self.stack.setCurrentWidget(self.empty_page)
            return

        # Perform search across title and content
        self.search_results_list.clear()
        results = []

        for note in self.notes.values():
            in_title = query in note.title.lower()
            in_content = query in note.content.lower()

            if in_title or in_content:
                results.append((note, in_title, in_content))

        self.search_header.setText(f"Search Results for '{text}' ({len(results)})")

        if not results:
            item = QListWidgetItem(self.search_results_list)
            item.setText("No matching notes found.")
            item.setFlags(Qt.NoItemFlags)
            self.search_results_list.addItem(item)
        else:
            for note, in_title, in_content in results:
                item = QListWidgetItem(self.search_results_list)
                item.setData(Qt.UserRole, note.id)
                item.setData(Qt.UserRole + 1, text)

                # Snippet generation
                snippet = ""
                if in_content:
                    idx = note.content.lower().find(query)
                    start = max(0, idx - 30)
                    end = min(len(note.content), idx + 60)
                    snippet = "..." + note.content[start:end].replace("\n", " ") + "..."
                else:
                    snippet = note.get_preview()

                title = note.title.strip() or "Untitled Note"
                item.setText(f"📄 {title}\n    {snippet}")
                item.setSizeHint(QSize(0, 56))

        self.stack.setCurrentWidget(self.search_page)

    def on_search_result_clicked(self, item: QListWidgetItem):
        """Open selected search result note."""
        note_id = item.data(Qt.UserRole)
        query = item.data(Qt.UserRole + 1) or ""

        if note_id and note_id in self.notes:
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)

            self.select_note_by_id(note_id, highlight_text=query)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette setup
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(24, 24, 25))
    palette.setColor(QPalette.AlternateBase, QColor(35, 35, 35))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(44, 44, 46))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(229, 181, 103))
    palette.setColor(QPalette.Highlight, QColor(56, 56, 58))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = JARVISNotepad()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
