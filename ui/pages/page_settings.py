"""
Page 3: Settings - Configure processing options.
"""

import customtkinter as ctk
import tkinter as tk
import os


class PageSettings(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.card_vars = {}
        self.create_cards()

    def create_cards(self):
        settings_config = [
            {
                "title": "GPS",
                "icon": "",
                "desc": "Enable/disable location data. When enabled, latitude "
                        "and longitude from metadata files will be written to images.",
                "key": "gps_enabled"
            },
            {
                "title": "Timezone",
                "icon": "",
                "desc": "Enable/disable timezone correction. Uses GPS to detect "
                        "location and apply the correct local timezone to timestamps.",
                "key": "timezone_enabled"
            },
            {
                "title": "Files Without Metadata",
                "icon": "",
                "desc": "Move files without matching JSON metadata to a separate "
                        "'Unmatched' folder in the output directory.",
                "key": "unmatched_enabled"
            },
            {
                "title": "Anonymous Logging",
                "icon": "",
                "desc": "Enable/disable anonymous usage logs for debugging purposes.",
                "key": "anonymous_logging"
            }
        ]

        for idx, config in enumerate(settings_config):
            row = idx // 2
            col = idx % 2
            self.create_card(config, row, col)

        self.create_output_mode_selector()
        self.create_performance_card()

    def create_card(self, config, row, col):
        card = ctk.CTkFrame(self, corner_radius=10, border_width=1)
        card.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
        card.grid_columnconfigure(1, weight=1)

        icon_lbl = ctk.CTkLabel(
            card, text=config["icon"], font=ctk.CTkFont(size=24)
        )
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=15, pady=15, sticky="n")

        title_lbl = ctk.CTkLabel(
            card, text=config["title"],
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_lbl.grid(row=0, column=1, padx=(0, 15), pady=(15, 5), sticky="w")

        desc_lbl = ctk.CTkLabel(
            card, text=config["desc"],
            font=ctk.CTkFont(size=12), text_color="gray",
            wraplength=250, justify="left"
        )
        desc_lbl.grid(row=1, column=1, padx=(0, 15), pady=(0, 15), sticky="w")

        var = tk.IntVar(
            value=1 if self.app.app_state["settings"].get(config["key"], True) else 0
        )
        self.card_vars[config["key"]] = var

        radio_frame = ctk.CTkFrame(card, fg_color="transparent")
        radio_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="w")

        ctk.CTkRadioButton(
            radio_frame, text="Enable", variable=var, value=1,
            command=self.on_setting_change
        ).pack(side="left", padx=(0, 20))

        ctk.CTkRadioButton(
            radio_frame, text="Disable", variable=var, value=0,
            command=self.on_setting_change
        ).pack(side="left")

    def create_output_mode_selector(self):
        mode_frame = ctk.CTkFrame(self, corner_radius=10, border_width=1)
        mode_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=15, sticky="ew")

        ctk.CTkLabel(
            mode_frame, text="Output Mode:",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left", padx=20, pady=15)

        self.mode_var = tk.StringVar(
            value=self.app.app_state["settings"].get("output_mode", "copy")
        )
        
        radio_container = ctk.CTkFrame(mode_frame, fg_color="transparent")
        radio_container.pack(side="left", fill="both", expand=True)

        ctk.CTkRadioButton(
            radio_container, text="Copy files to destination (Safe)",
            variable=self.mode_var, value="copy",
            command=self._on_mode_change
        ).pack(side="top", anchor="w", padx=20, pady=(10, 5))
        
        self.copy_warning_label = ctk.CTkLabel(
            radio_container, 
            text="Warning: 'Copy' mode limits speed to your hard drive's Read/Write limits.",
            font=ctk.CTkFont(size=11), text_color=("#D35400", "#E67E22")
        )
        # Pack only if copy is selected
        if self.mode_var.get() == "copy":
            self.copy_warning_label.pack(side="top", anchor="w", padx=40, pady=(0, 5))

        ctk.CTkRadioButton(
            radio_container, text="Modify in-place (keeps backups)",
            variable=self.mode_var, value="in-place",
            command=self._on_mode_change
        ).pack(side="top", anchor="w", padx=20, pady=(5, 10))

    def _on_mode_change(self):
        if self.mode_var.get() == "copy":
            self.copy_warning_label.pack(side="top", anchor="w", padx=40, pady=(0, 5))
        else:
            self.copy_warning_label.pack_forget()
            
            # Prevent In-Place mode if any input is a ZIP file
            inputs = self.app.app_state.get("inputs", [])
            has_zip = any(inp.is_file() and inp.suffix.lower() == '.zip' for inp in inputs)
            if has_zip:
                import tkinter.messagebox as messagebox
                messagebox.showwarning(
                    "In-Place Mode Disabled", 
                    "In-Place mode is not supported when processing ZIP archives. Please use Copy mode."
                )
                self.mode_var.set("copy")
                self.copy_warning_label.pack(side="top", anchor="w", padx=40, pady=(0, 5))
                
        self.on_setting_change()

    def create_performance_card(self):
        """High Performance Mode toggle with warning."""
        perf_frame = ctk.CTkFrame(self, corner_radius=10, border_width=1,
                                   border_color=("#E67E22", "#D35400"))
        perf_frame.grid(row=3, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="ew")
        perf_frame.grid_columnconfigure(1, weight=1)

        # Icon
        ctk.CTkLabel(
            perf_frame, text="", font=ctk.CTkFont(size=24)
        ).grid(row=0, column=0, rowspan=2, padx=15, pady=15, sticky="n")

        # Title row with checkbox
        title_row = ctk.CTkFrame(perf_frame, fg_color="transparent")
        title_row.grid(row=0, column=1, padx=(0, 15), pady=(15, 0), sticky="ew")
        title_row.grid_columnconfigure(0, weight=1)

        self.hp_var = tk.BooleanVar(
            value=self.app.app_state["settings"].get("high_performance", False)
        )

        self.hp_checkbox = ctk.CTkCheckBox(
            title_row,
            text="High Performance Mode",
            variable=self.hp_var,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self.on_setting_change,
            onvalue=True,
            offvalue=False
        )
        self.hp_checkbox.grid(row=0, column=0, sticky="w")

        # CPU core count display
        cores = os.cpu_count() or 4
        core_label = ctk.CTkLabel(
            title_row,
            text=f"{cores} cores detected",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60")
        )
        core_label.grid(row=0, column=1, padx=(10, 0), sticky="e")

        # Warning text
        warning_label = ctk.CTkLabel(
            perf_frame,
            text="Uses maximum CPU and disk resources to speed up processing.\n"
                 "Your computer may become less responsive while exporting.",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
            justify="left",
            wraplength=500
        )
        warning_label.grid(row=1, column=1, padx=(0, 15), pady=(5, 15), sticky="w")

    def on_setting_change(self):
        for key, var in self.card_vars.items():
            self.app.app_state["settings"][key] = bool(var.get())
        self.app.app_state["settings"]["output_mode"] = self.mode_var.get()
        self.app.app_state["settings"]["high_performance"] = self.hp_var.get()
        self.app.enable_next(True)
