"""
LUT Exporter
=============
Exports per-clip color grades from DaVinci Resolve Studio as .cube LUT files.
Writes a debug log (lut_export_debug.txt) to the LUT folder so you can
diagnose failures if the LUTs folder stays empty.
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
        self._log_lines = []

    # ------------------------------------------------------------------
    def export_all(self, lut_dir, timeline_data, options):
        """
        Try to export a LUT for every clip that has a colour grade.
        Iterates fresh items directly from the timeline (avoids stale
        start_frame mismatches from pre-extracted data).
        Returns  dict  clip_id -> absolute_lut_path
        """
        os.makedirs(lut_dir, exist_ok=True)
        self._log("=== LUT Export Debug Log ===")
        self._log(f"LUT dir: {lut_dir}")

        lut_map   = {}
        lut_size  = options.get("lut_size", 33)
        lut_type  = (self.LUT_TYPE_33PT if lut_size == 33 else
                     self.LUT_TYPE_65PT  if lut_size == 65 else
                     self.LUT_TYPE_17PT)
        size_val  = {self.LUT_TYPE_17PT: 17,
                     self.LUT_TYPE_33PT: 33,
                     self.LUT_TYPE_65PT: 65}[lut_type]

        self._log(f"LUT size: {size_val}pt  (type constant={lut_type})")

        # Set the timeline as current so the Color page context is correct
        try:
            self.project.SetCurrentTimeline(self.timeline)
            self._log("SetCurrentTimeline: OK")
        except Exception as e:
            self._log(f"SetCurrentTimeline FAILED: {e}")

        # Build a start_frame -> clip_id map from pre-extracted data
        # so we can pair fresh items with the correct clip IDs
        sf_to_id   = {}
        sf_to_name = {}
        for track in timeline_data.get("video_tracks", []):
            for clip in track.get("clips", []):
                sf = clip.get("start_frame")
                sf_to_id[sf]   = clip["id"]
                sf_to_name[sf] = clip["name"]

        # Iterate every video track directly from Resolve
        try:
            track_count = self.timeline.GetTrackCount("video")
        except Exception as e:
            self._log(f"GetTrackCount FAILED: {e}")
            self._write_log(lut_dir)
            return lut_map

        self._log(f"Video track count: {track_count}")

        for track_idx in range(1, track_count + 1):
            try:
                items = self.timeline.GetItemListInTrack("video", track_idx) or []
            except Exception as e:
                self._log(f"  Track {track_idx}: GetItemListInTrack FAILED: {e}")
                continue

            self._log(f"  Track {track_idx}: {len(items)} item(s)")

            for item in items:
                try:
                    item_start = item.GetStart()
                    item_name  = item.GetName() or "Untitled"
                except Exception as e:
                    self._log(f"    Item: GetStart/GetName FAILED: {e}")
                    continue

                # Look up clip id / name from pre-extracted data
                clip_id   = sf_to_id.get(item_start,
                            f"t{track_idx}_f{item_start}")
                clip_name = sf_to_name.get(item_start, item_name)

                safe_name = self._sanitize(clip_name)
                lut_path  = os.path.join(lut_dir, f"{safe_name}_{clip_id}.cube")

                self._log(f"    Clip '{clip_name}' start={item_start}")

                success, strategies_tried = self._export_lut(
                    item, lut_path, lut_type, size_val)

                self._log(f"      Strategies tried: {strategies_tried}")

                if success:
                    lut_map[clip_id] = lut_path
                    self._log(f"      SUCCESS -> {os.path.basename(lut_path)}")
                else:
                    self._log(f"      FAILED - no .cube written")

        self._log(f"\nTotal LUTs exported: {len(lut_map)}")
        self._write_log(lut_dir)
        return lut_map

    # ------------------------------------------------------------------
    def _export_lut(self, item, lut_path, lut_type, size_val):
        """
        Try every known Resolve Studio API signature for LUT export.
        Returns (success: bool, list_of_strategy_results: list[str])
        """
        tried = []

        # --- Strategy 1: ExportLUT(exportType, path) ---
        try:
            fn = getattr(item, "ExportLUT", None)
            if callable(fn):
                result = fn(lut_type, lut_path)
                if result and os.path.exists(lut_path) and os.path.getsize(lut_path) > 0:
                    tried.append("S1:OK")
                    return True, tried
                tried.append(f"S1:returned={result}")
            else:
                tried.append(f"S1:not_callable(type={type(fn).__name__})")
        except Exception as e:
            tried.append(f"S1:exception={e}")

        # Remove zero-byte file if created
        self._cleanup(lut_path)

        # --- Strategy 2: ExportLUT(path, size) ---
        try:
            fn = getattr(item, "ExportLUT", None)
            if callable(fn):
                result = fn(lut_path, size_val)
                if result and os.path.exists(lut_path) and os.path.getsize(lut_path) > 0:
                    tried.append("S2:OK")
                    return True, tried
                tried.append(f"S2:returned={result}")
            else:
                tried.append("S2:not_callable")
        except Exception as e:
            tried.append(f"S2:exception={e}")

        self._cleanup(lut_path)

        # --- Strategy 3: GetNodeGraph().ExportLUT(path, size) ---
        try:
            get_ng = getattr(item, "GetNodeGraph", None)
            if callable(get_ng):
                ng = get_ng()
                if ng:
                    exp = getattr(ng, "ExportLUT", None)
                    if callable(exp):
                        result = exp(lut_path, size_val)
                        if result and os.path.exists(lut_path) and os.path.getsize(lut_path) > 0:
                            tried.append("S3:OK")
                            return True, tried
                        tried.append(f"S3:returned={result}")
                    else:
                        tried.append(f"S3:ExportLUT not callable on NodeGraph")
                else:
                    tried.append("S3:GetNodeGraph returned None")
            else:
                tried.append("S3:GetNodeGraph not callable")
        except Exception as e:
            tried.append(f"S3:exception={e}")

        self._cleanup(lut_path)

        # --- Strategy 4: GetColorGroup().ExportLUT(path) ---
        try:
            get_cg = getattr(item, "GetColorGroup", None)
            if callable(get_cg):
                cg = get_cg()
                if cg:
                    exp = getattr(cg, "ExportLUT", None)
                    if callable(exp):
                        result = exp(lut_path)
                        if result and os.path.exists(lut_path) and os.path.getsize(lut_path) > 0:
                            tried.append("S4:OK")
                            return True, tried
                        tried.append(f"S4:returned={result}")
                    else:
                        tried.append("S4:ExportLUT not callable on ColorGroup")
                else:
                    tried.append("S4:GetColorGroup returned None")
            else:
                tried.append("S4:GetColorGroup not callable")
        except Exception as e:
            tried.append(f"S4:exception={e}")

        self._cleanup(lut_path)

        # --- Strategy 5: GalleryStill export workaround ---
        # Some Resolve versions expose LUT export via the Gallery
        try:
            gallery = getattr(self.project, "GetGallery", None)
            if callable(gallery):
                gal = gallery()
                if gal:
                    # Grab a still from this clip and export it as LUT
                    cs = item.GrabStill() if callable(getattr(item, "GrabStill", None)) else None
                    if cs:
                        album = gal.GetCurrentStillAlbum() if callable(getattr(gal, "GetCurrentStillAlbum", None)) else None
                        if album:
                            stills = album.GetStills() or []
                            if stills:
                                last_still = stills[-1]
                                exp = getattr(album, "ExportStills", None)
                                if callable(exp):
                                    result = exp([last_still], lut_dir, "", "cube")
                                    if result and os.path.exists(lut_path) and os.path.getsize(lut_path) > 0:
                                        tried.append("S5:OK")
                                        return True, tried
                                    tried.append(f"S5:ExportStills returned={result}")
                                else:
                                    tried.append("S5:ExportStills not callable")
                            else:
                                tried.append("S5:no stills in album")
                        else:
                            tried.append("S5:no current album")
                    else:
                        tried.append("S5:GrabStill not available/failed")
                else:
                    tried.append("S5:Gallery returned None")
            else:
                tried.append("S5:GetGallery not callable")
        except Exception as e:
            tried.append(f"S5:exception={e}")

        return False, tried

    # ------------------------------------------------------------------
    def _cleanup(self, path):
        """Remove a zero-byte or missing file left by a failed export."""
        try:
            if os.path.exists(path) and os.path.getsize(path) == 0:
                os.remove(path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _log(self, msg):
        self._log_lines.append(str(msg))

    def _write_log(self, lut_dir):
        try:
            log_path = os.path.join(lut_dir, "lut_export_debug.txt")
            with open(log_path, "w") as f:
                f.write("\n".join(self._log_lines))
        except Exception:
            pass

    # ------------------------------------------------------------------
    @staticmethod
    def _sanitize(name):
        for ch in '<>:"/\\|?*':
            name = name.replace(ch, "_")
        return name[:50].strip()
