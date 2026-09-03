"""
tkinter Options dialog: Paths / Sync (minus run_continuously) / Logging /
Ignore sections, bound to a SyncConfig loaded from `config_path`
(Requirements 7, 8).
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from obsidian_sync.config import SyncConfig

PATH_FIELDS = ("local_vault", "icloud_vault", "history_dir", "logs_dir")
INT_FIELDS = (
    "poll_interval", "stability_window", "stabilize_wait",
    "tiny_threshold", "max_concurrent_io", "max_display_length", "log_retention",
)


class OptionsWindow(tk.Toplevel):
    def __init__(self, master, config_path: str, is_running: bool = False):
        super().__init__(master)
        self.title("obsidian-sync Options")
        self.config_path = config_path
        self.is_running = is_running
        self.resizable(False, False)

        try:
            self.config = SyncConfig.from_yaml(config_path)
        except Exception:
            self.config = SyncConfig()

        self._vars = {}
        self._build_ui()

        # Deliberately no self.transient(master): `master` is the tray
        # app's permanently-hidden root, and transient()-against-a-withdrawn
        # master leaves this window stuck "withdrawn" too, invisible at the
        # OS level, even after an explicit deiconify() -- confirmed by hand.
        # transient() only makes sense when the master is a real visible
        # window, which ours never is.
        self.grab_set()
        self.focus_set()

    # -- UI construction --

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_paths_tab(notebook)
        self._build_sync_tab(notebook)
        self._build_logging_tab(notebook)
        self._build_ignore_tab(notebook)

        if self.is_running:
            tk.Label(
                self,
                text="A sync is currently running -- changes apply on its next launch.",
                fg="#8a6d00",
            ).pack(pady=(0, 4))

        button_row = tk.Frame(self)
        button_row.pack(pady=(0, 8))
        tk.Button(button_row, text="Save", command=self._on_save, width=10).pack(side="left", padx=4)
        tk.Button(button_row, text="Cancel", command=self.destroy, width=10).pack(side="left", padx=4)

    def _add_path_field(self, parent, row, label, attr):
        tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
        var = tk.StringVar(value=getattr(self.config, attr))
        self._vars[attr] = var
        tk.Entry(parent, textvariable=var, width=45).grid(row=row, column=1, padx=4, pady=4)
        tk.Button(parent, text="Browse...", command=lambda: self._browse(var)).grid(row=row, column=2, padx=4, pady=4)

    def _browse(self, var: tk.StringVar):
        chosen = filedialog.askdirectory(initialdir=var.get() or None, parent=self)
        if chosen:
            var.set(chosen)

    def _build_paths_tab(self, notebook):
        frame = tk.Frame(notebook)
        notebook.add(frame, text="Paths")
        self._add_path_field(frame, 0, "Local vault:", "local_vault")
        self._add_path_field(frame, 1, "iCloud vault:", "icloud_vault")
        self._add_path_field(frame, 2, "History directory:", "history_dir")
        self._add_path_field(frame, 3, "Logs directory:", "logs_dir")

    def _add_bool_field(self, parent, row, label, attr):
        var = tk.BooleanVar(value=getattr(self.config, attr))
        self._vars[attr] = var
        tk.Checkbutton(parent, text=label, variable=var).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=4, pady=4
        )

    def _add_int_field(self, parent, row, label, attr):
        tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
        var = tk.StringVar(value=str(getattr(self.config, attr)))
        self._vars[attr] = var
        tk.Entry(parent, textvariable=var, width=10).grid(row=row, column=1, sticky="w", padx=4, pady=4)

    def _build_sync_tab(self, notebook):
        # run_continuously is deliberately absent (Requirement 7.3) --
        # the tray manages daemon vs. one-shot mode itself via Start/Run Once.
        frame = tk.Frame(notebook)
        notebook.add(frame, text="Sync")
        self._add_bool_field(frame, 0, "Check iCloud status", "check_icloud_status")
        self._add_int_field(frame, 1, "Poll interval (seconds):", "poll_interval")
        self._add_int_field(frame, 2, "Stability window (seconds):", "stability_window")
        self._add_int_field(frame, 3, "Stabilize wait (seconds):", "stabilize_wait")
        self._add_int_field(frame, 4, "Tiny file threshold (bytes):", "tiny_threshold")
        self._add_int_field(frame, 5, "Max concurrent I/O:", "max_concurrent_io")

    def _build_logging_tab(self, notebook):
        frame = tk.Frame(notebook)
        notebook.add(frame, text="Logging")
        tk.Label(frame, text="Console level:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        level_var = tk.StringVar(value=self.config.console_level)
        self._vars["console_level"] = level_var
        ttk.Combobox(
            frame, textvariable=level_var, values=["quiet", "normal", "verbose"],
            state="readonly", width=12,
        ).grid(row=0, column=1, sticky="w", padx=4, pady=4)
        self._add_bool_field(frame, 1, "Shorten displayed paths", "shorter_paths")
        self._add_int_field(frame, 2, "Max display length:", "max_display_length")
        self._add_int_field(frame, 3, "Log retention (files):", "log_retention")

    def _add_list_field(self, parent, row, label, attr, values):
        tk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", padx=4, pady=4)
        text = tk.Text(parent, width=45, height=5)
        text.insert("1.0", "\n".join(values))
        text.grid(row=row, column=1, padx=4, pady=4)
        self._vars[attr] = text

    def _build_ignore_tab(self, notebook):
        frame = tk.Frame(notebook)
        notebook.add(frame, text="Ignore")
        self._add_list_field(frame, 0, "Patterns (one per line):", "ignore_patterns", self.config.ignore_patterns)
        self._add_list_field(frame, 1, "Directories (one per line):", "ignored_dirs", sorted(self.config.ignored_dirs))
        self._add_list_field(frame, 2, "Files (one per line):", "ignored_files", sorted(self.config.ignored_files))

    # -- save --

    def _lines(self, attr) -> list:
        raw = self._vars[attr].get("1.0", "end")
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _collect_and_validate(self) -> Optional[SyncConfig]:
        """
        Builds a SyncConfig from the current form values, or returns None
        (after showing an error dialog) if validation fails. Split out from
        _on_save so it's testable without needing messagebox/destroy calls
        to actually run in tests.
        """
        cfg = SyncConfig()

        for attr in PATH_FIELDS:
            setattr(cfg, attr, self._vars[attr].get().strip())

        missing = [attr for attr in PATH_FIELDS if not os.path.isdir(getattr(cfg, attr))]
        if missing:
            messagebox.showerror(
                "Invalid path",
                "These paths don't exist:\n" + "\n".join(f"{a}: {getattr(cfg, a) or '(empty)'}" for a in missing),
                parent=self,
            )
            return None

        cfg.check_icloud_status = bool(self._vars["check_icloud_status"].get())
        cfg.shorter_paths = bool(self._vars["shorter_paths"].get())

        try:
            for attr in INT_FIELDS:
                setattr(cfg, attr, int(self._vars[attr].get()))
        except ValueError as e:
            messagebox.showerror("Invalid value", f"One of the numeric fields isn't a valid number: {e}", parent=self)
            return None

        cfg.console_level = self._vars["console_level"].get()

        cfg.ignore_patterns = self._lines("ignore_patterns")
        cfg.ignored_dirs = set(self._lines("ignored_dirs"))
        cfg.ignored_files = set(self._lines("ignored_files"))

        # run_continuously is never edited here (Requirement 7.3) -- carry
        # forward whatever the loaded config already had.
        cfg.run_continuously = self.config.run_continuously

        return cfg

    def _on_save(self):
        cfg = self._collect_and_validate()
        if cfg is None:
            return
        try:
            cfg.save(self.config_path)
        except OSError as e:
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        self.destroy()
