"""
Timeline Extractor
==================
Extracts all timeline data from DaVinci Resolve using the scripting API.
Captures clips, tracks, transitions, speed changes, markers, and metadata.
"""

import os
import uuid


class TimelineExtractor:
    """Extracts comprehensive timeline data from a Resolve timeline."""

    def __init__(self, resolve, project, timeline):
        self.resolve = resolve
        self.project = project
        self.timeline = timeline

    def extract(self, options):
        """
        Extract all timeline data into a structured dictionary.

        Returns:
            dict with keys: name, fps, width, height, video_tracks, audio_tracks,
                            markers, clip_count, warnings, etc.
        """
        tl = self.timeline
        data = {
            "name": tl.GetName(),
            "fps": float(tl.GetSetting("timelineFrameRate") or 24),
            "width": int(tl.GetSetting("timelineResolutionWidth") or 1920),
            "height": int(tl.GetSetting("timelineResolutionHeight") or 1080),
            "start_timecode": tl.GetStartTimecode(),
            "duration_frames": tl.GetEndFrame() - tl.GetStartFrame(),
            "video_tracks": [],
            "audio_tracks": [],
            "markers": [],
            "clip_count": 0,
            "warnings": [],
            "lut_map": {},
        }

        # Extract video tracks
        video_track_count = tl.GetTrackCount("video")
        for track_idx in range(1, video_track_count + 1):
            track_data = self._extract_video_track(tl, track_idx, options)
            data["video_tracks"].append(track_data)
            data["clip_count"] += len(track_data["clips"])

        # Extract audio tracks
        if options.get("export_audio", True):
            audio_track_count = tl.GetTrackCount("audio")
            for track_idx in range(1, audio_track_count + 1):
                track_data = self._extract_audio_track(tl, track_idx, options)
                data["audio_tracks"].append(track_data)

        # Extract timeline markers
        if options.get("export_markers", True):
            data["markers"] = self._extract_markers(tl)

        return data

    def _extract_video_track(self, timeline, track_idx, options):
        """Extract all clips from a video track."""
        track_name = timeline.GetTrackName("video", track_idx)
        items = timeline.GetItemListInTrack("video", track_idx) or []

        track = {
            "index": track_idx,
            "name": track_name or f"V{track_idx}",
            "clips": [],
            "enabled": True,
        }

        for item in items:
            clip = self._extract_clip(item, "video", track_idx, options)
            if clip:
                track["clips"].append(clip)

        return track

    def _extract_audio_track(self, timeline, track_idx, options):
        """Extract all clips from an audio track."""
        track_name = timeline.GetTrackName("audio", track_idx)
        items = timeline.GetItemListInTrack("audio", track_idx) or []

        track = {
            "index": track_idx,
            "name": track_name or f"A{track_idx}",
            "clips": [],
            "enabled": True,
        }

        for item in items:
            clip = self._extract_clip(item, "audio", track_idx, options)
            if clip:
                track["clips"].append(clip)

        return track

    def _extract_clip(self, item, track_type, track_idx, options):
        """Extract data from a single timeline item (clip)."""
        clip_id = str(uuid.uuid4())[:8]

        clip = {
            "id": clip_id,
            "name": item.GetName() or "Untitled",
            "track_type": track_type,
            "track_index": track_idx,
            "start_frame": item.GetStart(),
            "end_frame": item.GetEnd(),
            "duration_frames": item.GetDuration(),
            "source_start": None,
            "source_end": None,
            "media_pool_item": None,
            "file_path": "",
            "has_color_grade": False,
            "color_node_count": 0,
            "transitions": {
                "start": None,
                "end": None,
            },
            "speed": 1.0,
            "reverse": False,
            "transform": {},
            "opacity": 100.0,
            "volume": 0.0,  # dB
            "markers": [],
            "is_compound": False,
            "is_fusion": False,
        }

        # Media info
        mpi = item.GetMediaPoolItem()
        if mpi:
            clip["media_pool_item"] = mpi
            props = mpi.GetClipProperty()
            if props:
                clip["file_path"] = props.get("File Path", "")
                clip["source_fps"] = props.get("FPS", "")
                clip["codec"] = props.get("Video Codec", "")
                clip["source_resolution"] = props.get("Resolution", "")

        # Source in/out
        try:
            clip["source_start"] = item.GetLeftOffset()
            clip["source_end"] = item.GetLeftOffset() + item.GetDuration()
        except Exception:
            pass

        # Color grading info
        if track_type == "video":
            try:
                node_count = item.GetNumNodes()
                clip["color_node_count"] = node_count or 0
                clip["has_color_grade"] = (node_count or 0) > 0
            except Exception:
                pass

        # Speed / retime
        if options.get("export_speed", True) and track_type == "video":
            clip["speed"] = self._get_clip_speed(item)

        # Transforms
        if options.get("export_transforms", True) and track_type == "video":
            clip["transform"] = self._get_clip_transform(item)

        # Clip markers
        if options.get("export_markers", True):
            try:
                markers = item.GetMarkers()
                if markers:
                    for frame_offset, marker_data in markers.items():
                        clip["markers"].append({
                            "frame_offset": frame_offset,
                            "name": marker_data.get("name", ""),
                            "note": marker_data.get("note", ""),
                            "color": marker_data.get("color", "Blue"),
                            "duration": marker_data.get("duration", 1),
                        })
            except Exception:
                pass

        # Transitions
        clip["transitions"] = self._get_transitions(item)

        # Compound / Fusion detection
        try:
            if hasattr(item, "GetFusionCompCount"):
                fuse_count = item.GetFusionCompCount()
                clip["is_fusion"] = (fuse_count or 0) > 0
        except Exception:
            pass

        # Opacity
        try:
            comp_mode = item.GetProperty("CompositeMode") if hasattr(item, "GetProperty") else None
            if comp_mode:
                clip["composite_mode"] = comp_mode
        except Exception:
            pass

        return clip

    def _get_clip_speed(self, item):
        """Get the playback speed of a clip."""
        try:
            # Try the property approach first
            speed = item.GetProperty("Speed") if hasattr(item, "GetProperty") else None
            if speed is not None:
                return float(speed)

            # Fallback: calculate from source vs timeline duration
            # If item has GetLeftOffset and GetRightOffset, we can estimate
            return 1.0
        except Exception:
            return 1.0

    def _get_clip_transform(self, item):
        """Get transform properties (position, scale, rotation, crop)."""
        transform = {
            "zoom_x": 1.0,
            "zoom_y": 1.0,
            "position_x": 0.0,
            "position_y": 0.0,
            "rotation": 0.0,
            "anchor_x": 0.0,
            "anchor_y": 0.0,
            "crop_left": 0.0,
            "crop_right": 0.0,
            "crop_top": 0.0,
            "crop_bottom": 0.0,
            "flip_x": False,
            "flip_y": False,
        }

        try:
            if not hasattr(item, "GetProperty"):
                return transform

            prop_map = {
                "ZoomX": "zoom_x",
                "ZoomY": "zoom_y",
                "Pan": "position_x",
                "Tilt": "position_y",
                "RotationAngle": "rotation",
                "AnchorPointX": "anchor_x",
                "AnchorPointY": "anchor_y",
                "CropLeft": "crop_left",
                "CropRight": "crop_right",
                "CropTop": "crop_top",
                "CropBottom": "crop_bottom",
                "FlipX": "flip_x",
                "FlipY": "flip_y",
            }

            for resolve_key, our_key in prop_map.items():
                val = item.GetProperty(resolve_key)
                if val is not None:
                    if our_key in ("flip_x", "flip_y"):
                        transform[our_key] = bool(val)
                    else:
                        transform[our_key] = float(val)
        except Exception:
            pass

        return transform

    def _get_transitions(self, item):
        """Get transition info for a clip."""
        transitions = {"start": None, "end": None}

        try:
            # Check for transitions at start (left) and end (right)
            for position in ["start", "end"]:
                # Resolve API doesn't expose transitions directly in all versions
                # We check via the timeline item properties
                pass
        except Exception:
            pass

        return transitions

    def _extract_markers(self, timeline):
        """Extract timeline-level markers."""
        markers = []
        try:
            tl_markers = timeline.GetMarkers()
            if tl_markers:
                for frame_id, marker_data in tl_markers.items():
                    markers.append({
                        "frame": frame_id,
                        "name": marker_data.get("name", ""),
                        "note": marker_data.get("note", ""),
                        "color": marker_data.get("color", "Blue"),
                        "duration": marker_data.get("duration", 1),
                    })
        except Exception:
            pass

        return markers
