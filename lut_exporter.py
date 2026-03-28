"""
LUT Exporter
=============
Exports per-clip color grades from DaVinci Resolve Studio as .cube LUT files.
"""

import os


class LUTExporter:

    # Resolve LUT export type constants (integer values)
    LUT_TYPE_17PT  = 0
    LUT_TYPE_33PT  = 1
    LUT_TYPE_65PT  = 2

    def __init__(self, resolve, project, timeline):
        self.resolve  = resolve
        self.project  = project
        self.timeline = timeline

    # ------------------------------------------------------------------
    def export_all(self, lut_dir, timeline_data, options):
        """
        Try to export a LUT for every clip that has a colour grade.
        Returns  dict  clip_id -> absolute_lut_path
        """
        os.makedirs(lut_dir, exist_ok=True)
        lut_map   = {}
        lut_size  = options.get("lut_size", 33)
        lut_type  = self.LUT_TYPE_33PT if lut_size == 33 else (
                    self.LUT_TYPE_65PT  if lut_size == 65 else self.LUT_TYPE_17PT)

        self.project.SetCurrentTimeline(self.timeline)

        for track in timeline_data.get("video_tracks", []):
            for clip in track.get("clips", []):
                clip_id   = clip["id"]
                clip_name = self._sanitize(clip["name"])
                lut_path  = os.path.join(lut_dir, f"{clip_name}_{clip_id}.cube")

                item = self._find_item(clip)
                if item is None:
                    continue

                if self._export_lut(item, lut_path, lut_type):
                    lut_map[clip_id] = lut_path

        return lut_map

    # ------------------------------------------------------------------
    def _find_item(self, clip):
        """Locate the TimelineItem for this clip dict."""
        try:
            track_idx = clip.get("track_index", 1)
            items = self.timeline.GetItemListInTrack("video", track_idx) or []
            for item in items:
                try:
                    if item.GetStart() == clip.get("start_frame"):
                        return item
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    def _export_lut(self, item, lut_path, lut_type):
        """
        Try every known Resolve Studio API signature for LUT export.
        Returns True if a .cube file was written successfully.
        """

        # --- Strategy 1: timelineItem.ExportLUT(exportType, path) ---
        try:
            fn = getattr(item, "ExportLUT", None)
            if callable(fn):
                if fn(lut_type, lut_path):
                    if os.path.exists(lut_path):
                        return True
        except Exception:
            pass

        # --- Strategy 2: timelineItem.ExportLUT(path, size) ---
        try:
            fn = getattr(item, "ExportLUT", None)
            if callable(fn):
                size_map = {0: 17, 1: 33, 2: 65}
                if fn(lut_path, size_map.get(lut_type, 33)):
                    if os.path.exists(lut_path):
                        return True
        except Exception:
            pass

        # --- Strategy 3: via GetNodeGraph().ExportLUT() ---
        try:
            get_ng = getattr(item, "GetNodeGraph", None)
            if callable(get_ng):
                ng = get_ng()
                if ng:
                    exp = getattr(ng, "ExportLUT", None)
                    if callable(exp):
                        if exp(lut_path, size_map.get(lut_type, 33) if 'size_map' in dir() else 33):
                            if os.path.exists(lut_path):
                                return True
        except Exception:
            pass

        # --- Strategy 4: via GetColorGroup / grade export ---
        try:
            get_cg = getattr(item, "GetColorGroup", None)
            if callable(get_cg):
                cg = get_cg()
                if cg:
                    exp = getattr(cg, "ExportLUT", None)
                    if callable(exp):
                        if exp(lut_path):
                            if os.path.exists(lut_path):
                                return True
        except Exception:
            pass

        return False

    # ------------------------------------------------------------------
    @staticmethod
    def _sanitize(name):
        for ch in '<>:"/\\|?*':
            name = name.replace(ch, "_")
        return name[:50].strip()
