#!/usr/bin/env python3
"""
DRP to Premiere Pro Converter
==============================
A DaVinci Resolve Studio script that exports your timeline to a Premiere Pro
compatible format while preserving color grades, transitions, effects,
speed changes, and audio.

Requires DaVinci Resolve Studio (paid version) for full LUT export support.

Usage:
  - Place this folder in your Resolve Scripts directory
  - Run from: Workspace > Scripts > DRP-to-Premiere
  - Or run standalone: python3 resolve_to_premiere.py

Output:
  - FCP XML file (importable by Premiere Pro)
  - Per-clip .cube LUT files (color grades preserved)
  - Conversion report with clip-to-LUT mapping
"""

import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import traceback

# Add Resolve scripting API paths
RESOLVE_SCRIPT_PATHS = [
    # macOS
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
    os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"),
    # Windows
    r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
    os.path.expandvars(r"%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"),
    # Linux
    "/opt/resolve/Developer/Scripting/Modules",
    "/opt/resolve/libs/Fusion/",
]

for path in RESOLVE_SCRIPT_PATHS:
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

# Import our modules
from timeline_extractor import TimelineExtractor
from lut_exporter import LUTExporter
from premiere_xml_builder import PremiereXMLBuilder
from effects_mapper import EffectsMapper


def get_resolve():
    """Connect to running DaVinci Resolve instance."""
    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except ImportError:
        return None


class ConverterApp:
    """Main GUI application for the DRP to Premiere converter."""

    def __init__(self, root):
        self.root = root
        self.root.title("DRP to Premiere Pro Converter")
        self.root.geometry("620x580")
        self.root.resizable(False, False)

        self.resolve = get_resolve()
        self.project = None
        self.timelines = []
        self.selected_timeline = None

        self._build_ui()
        self._connect_resolve()

    def _build_ui(self):
        """Build the application UI."""
        # Main frame
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # Title
        title = ttk.Label(main, text="DRP to Premiere Pro Converter",
                          font=("Helvetica", 16, "bold"))
        title.pack(pady=(0, 10))

        # Status
        self.status_var = tk.StringVar(value="Connecting to DaVinci Resolve...")
        status_label = ttk.Label(main, textvariable=self.status_var,
                                 font=("Helvetica", 10))
        status_label.pack(pady=(0, 10))

        # Connection indicator
        self.conn_frame = ttk.Frame(main)
        self.conn_frame.pack(fill=tk.X, pady=(0, 10))
        self.conn_indicator = ttk.Label(self.conn_frame, text="  ", width=2,
                                         background="red")
        self.conn_indicator.pack(side=tk.LEFT, padx=(0, 8))
        self.conn_text = ttk.Label(self.conn_frame, text="Not connected")
        self.conn_text.pack(side=tk.LEFT)

        # Timeline selector
        tl_frame = ttk.LabelFrame(main, text="Timeline", padding=10)
        tl_frame.pack(fill=tk.X, pady=(0, 10))

        self.timeline_var = tk.StringVar()
        self.timeline_combo = ttk.Combobox(tl_frame, textvariable=self.timeline_var,
                                            state="readonly", width=55)
        self.timeline_combo.pack(fill=tk.X)
        self.timeline_combo.bind("<<ComboboxSelected>>", self._on_timeline_select)

        # Options
        opt_frame = ttk.LabelFrame(main, text="Export Options", padding=10)
        opt_frame.pack(fill=tk.X, pady=(0, 10))

        self.export_luts = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Export color grades as LUTs (.cube)",
                        variable=self.export_luts).pack(anchor=tk.W)

        self.export_transforms = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Preserve transforms (position, scale, rotation)",
                        variable=self.export_transforms).pack(anchor=tk.W)

        self.export_speed = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Preserve speed changes / retimes",
                        variable=self.export_speed).pack(anchor=tk.W)

        self.export_audio = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Include audio tracks and levels",
                        variable=self.export_audio).pack(anchor=tk.W)

        self.export_markers = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="Include markers",
                        variable=self.export_markers).pack(anchor=tk.W)

        self.flatten_compound = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="Flatten compound clips",
                        variable=self.flatten_compound).pack(anchor=tk.W)

        # LUT format
        lut_frame = ttk.Frame(opt_frame)
        lut_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(lut_frame, text="LUT Size:").pack(side=tk.LEFT, padx=(0, 5))
        self.lut_size_var = tk.StringVar(value="33")
        lut_size = ttk.Combobox(lut_frame, textvariable=self.lut_size_var,
                                 values=["17", "33", "65"], state="readonly", width=5)
        lut_size.pack(side=tk.LEFT)
        ttk.Label(lut_frame, text="(higher = more accurate color, larger file)").pack(
            side=tk.LEFT, padx=(5, 0))

        # Output path
        out_frame = ttk.LabelFrame(main, text="Output Location", padding=10)
        out_frame.pack(fill=tk.X, pady=(0, 10))

        path_row = ttk.Frame(out_frame)
        path_row.pack(fill=tk.X)

        self.output_var = tk.StringVar(value=os.path.expanduser("~/Desktop"))
        ttk.Entry(path_row, textvariable=self.output_var, width=45).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_row, text="Browse...", command=self._browse_output).pack(
            side=tk.RIGHT, padx=(5, 0))

        # Progress
        self.progress = ttk.Progressbar(main, mode="determinate", length=400)
        self.progress.pack(fill=tk.X, pady=(0, 5))

        self.progress_text = tk.StringVar(value="")
        ttk.Label(main, textvariable=self.progress_text,
                  font=("Helvetica", 9)).pack(pady=(0, 10))

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X)

        self.convert_btn = ttk.Button(btn_frame, text="Convert to Premiere Pro",
                                       command=self._start_conversion)
        self.convert_btn.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="Refresh", command=self._connect_resolve).pack(
            side=tk.RIGHT, padx=(0, 5))

    def _connect_resolve(self):
        """Connect/reconnect to DaVinci Resolve."""
        self.resolve = get_resolve()
        if self.resolve:
            self.conn_text.config(text="Connected to DaVinci Resolve")
            try:
                self.conn_indicator.config(background="green")
            except tk.TclError:
                pass
            self._load_project()
        else:
            self.conn_text.config(text="Not connected - is Resolve running?")
            try:
                self.conn_indicator.config(background="red")
            except tk.TclError:
                pass
            self.status_var.set("Please open DaVinci Resolve and click Refresh")

    def _load_project(self):
        """Load current project and its timelines."""
        if not self.resolve:
            return

        pm = self.resolve.GetProjectManager()
        self.project = pm.GetCurrentProject()

        if not self.project:
            self.status_var.set("No project open in Resolve")
            return

        project_name = self.project.GetName()
        tl_count = self.project.GetTimelineCount()
        self.timelines = []

        for i in range(1, tl_count + 1):
            tl = self.project.GetTimelineByIndex(i)
            self.timelines.append(tl)

        tl_names = [tl.GetName() for tl in self.timelines]
        self.timeline_combo["values"] = tl_names

        if tl_names:
            self.timeline_combo.current(0)
            self.selected_timeline = self.timelines[0]

        self.status_var.set(f"Project: {project_name} | {tl_count} timeline(s)")

    def _on_timeline_select(self, event):
        """Handle timeline selection change."""
        idx = self.timeline_combo.current()
        if 0 <= idx < len(self.timelines):
            self.selected_timeline = self.timelines[idx]

    def _browse_output(self):
        """Browse for output directory."""
        path = filedialog.askdirectory(initialdir=self.output_var.get())
        if path:
            self.output_var.set(path)

    def _start_conversion(self):
        """Start the conversion process in a background thread."""
        if not self.resolve or not self.project or not self.selected_timeline:
            messagebox.showerror("Error", "No timeline selected or Resolve not connected.")
            return

        self.convert_btn.config(state="disabled")
        self.progress["value"] = 0

        thread = threading.Thread(target=self._run_conversion, daemon=True)
        thread.start()

    def _run_conversion(self):
        """Run the full conversion pipeline."""
        try:
            timeline = self.selected_timeline
            tl_name = timeline.GetName()
            output_base = os.path.join(self.output_var.get(), f"{tl_name}_premiere")
            os.makedirs(output_base, exist_ok=True)
            lut_dir = os.path.join(output_base, "LUTs")
            os.makedirs(lut_dir, exist_ok=True)

            options = {
                "export_luts": self.export_luts.get(),
                "export_transforms": self.export_transforms.get(),
                "export_speed": self.export_speed.get(),
                "export_audio": self.export_audio.get(),
                "export_markers": self.export_markers.get(),
                "flatten_compound": self.flatten_compound.get(),
                "lut_size": int(self.lut_size_var.get()),
            }

            # Step 1: Extract timeline data
            self._update_progress(5, "Extracting timeline structure...")
            extractor = TimelineExtractor(self.resolve, self.project, timeline)
            timeline_data = extractor.extract(options)
            self._update_progress(25, f"Extracted {timeline_data['clip_count']} clips")

            # Step 2: Export LUTs
            if options["export_luts"]:
                self._update_progress(30, "Exporting color grades as LUTs...")
                lut_exporter = LUTExporter(self.resolve, self.project, timeline)
                lut_map = lut_exporter.export_all(lut_dir, timeline_data, options)
                timeline_data["lut_map"] = lut_map
                self._update_progress(55, f"Exported {len(lut_map)} LUTs")

            # Step 3: Map effects
            self._update_progress(60, "Mapping effects and transforms...")
            effects_mapper = EffectsMapper()
            timeline_data = effects_mapper.map_all(timeline_data, options)
            self._update_progress(70, "Effects mapped")

            # Step 4: Build Premiere XML
            self._update_progress(75, "Generating Premiere Pro XML...")
            xml_builder = PremiereXMLBuilder()
            xml_path = os.path.join(output_base, f"{tl_name}.xml")
            xml_builder.build(timeline_data, xml_path, lut_dir, options)
            self._update_progress(90, "XML generated")

            # Step 5: Write mapping report
            self._update_progress(92, "Writing conversion report...")
            self._write_report(output_base, tl_name, timeline_data, options)
            self._update_progress(100, "Done!")

            self.root.after(0, lambda: messagebox.showinfo(
                "Success",
                f"Conversion complete!\n\n"
                f"Output: {output_base}\n\n"
                f"To import in Premiere Pro:\n"
                f"1. File > Import > select {tl_name}.xml\n"
                f"2. LUTs are in the LUTs folder\n"
                f"3. Check _conversion_report.txt for details"
            ))

        except Exception as e:
            error_msg = f"Conversion failed:\n{str(e)}\n\n{traceback.format_exc()}"
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
        finally:
            self.root.after(0, lambda: self.convert_btn.config(state="normal"))

    def _update_progress(self, value, text):
        """Thread-safe progress update."""
        self.root.after(0, lambda: self.progress.configure(value=value))
        self.root.after(0, lambda: self.progress_text.set(text))

    def _write_report(self, output_dir, tl_name, timeline_data, options):
        """Write a human-readable conversion report."""
        report_path = os.path.join(output_dir, "_conversion_report.txt")
        with open(report_path, "w") as f:
            f.write(f"DRP to Premiere Pro Conversion Report\n")
            f.write(f"{'=' * 50}\n\n")
            f.write(f"Timeline: {tl_name}\n")
            f.write(f"Resolution: {timeline_data.get('width', '?')}x{timeline_data.get('height', '?')}\n")
            f.write(f"Frame Rate: {timeline_data.get('fps', '?')}\n")
            f.write(f"Total Clips: {timeline_data.get('clip_count', 0)}\n")
            f.write(f"Video Tracks: {len(timeline_data.get('video_tracks', []))}\n")
            f.write(f"Audio Tracks: {len(timeline_data.get('audio_tracks', []))}\n\n")

            # LUT mapping
            lut_map = timeline_data.get("lut_map", {})
            if lut_map:
                f.write(f"Color Grade LUTs\n{'-' * 30}\n")
                for clip_id, lut_file in lut_map.items():
                    clip_name = clip_id
                    # Find the clip name from timeline data
                    for track in timeline_data.get("video_tracks", []):
                        for clip in track.get("clips", []):
                            if clip.get("id") == clip_id:
                                clip_name = clip.get("name", clip_id)
                                break
                    f.write(f"  {clip_name} -> {os.path.basename(lut_file)}\n")
                f.write("\n")

            # Warnings
            warnings = timeline_data.get("warnings", [])
            if warnings:
                f.write(f"Warnings\n{'-' * 30}\n")
                for w in warnings:
                    f.write(f"  - {w}\n")
                f.write("\n")

            # Premiere import instructions
            f.write(f"Import Instructions for Premiere Pro\n{'-' * 30}\n")
            f.write(f"1. Open Premiere Pro\n")
            f.write(f"2. File > Import > select '{tl_name}.xml'\n")
            f.write(f"3. The timeline will be recreated with all clips\n")
            if lut_map:
                f.write(f"4. LUTs are auto-referenced in Lumetri effects\n")
                f.write(f"   If LUTs don't load, set the LUT folder in:\n")
                f.write(f"   Lumetri > Creative > Look > Browse to LUTs folder\n")
            f.write(f"\nNote: Keep the LUTs folder alongside the XML file.\n")


def main():
    root = tk.Tk()

    # Set theme
    style = ttk.Style()
    available_themes = style.theme_names()
    for theme in ["aqua", "clam", "vista"]:
        if theme in available_themes:
            style.theme_use(theme)
            break

    app = ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
