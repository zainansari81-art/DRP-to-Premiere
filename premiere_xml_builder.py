"""
Premiere XML Builder
=====================
Generates FCP XML 1.0 format that Premiere Pro can import.
Includes timeline structure, clips, transitions, markers,
speed changes, transforms, and Lumetri LUT references.

FCP XML is the most reliable interchange format for Premiere Pro.
It preserves more data than AAF or EDL.
"""

import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
import math
import uuid


class PremiereXMLBuilder:
    """Builds a Premiere Pro compatible FCP XML file."""

    def __init__(self):
        self.clip_id_counter = 0

    def build(self, timeline_data, output_path, lut_dir, options):
        """
        Build the complete FCP XML file.

        Args:
            timeline_data: Extracted timeline data dict
            output_path: Path to write the .xml file
            lut_dir: Directory containing exported .cube LUT files
            options: Export options dict
        """
        root = self._create_root()
        xmeml = root

        # Project
        project = ET.SubElement(xmeml, "project")
        ET.SubElement(project, "name").text = timeline_data["name"]
        children = ET.SubElement(project, "children")

        # Main sequence
        sequence = self._build_sequence(children, timeline_data, lut_dir, options)

        # Bin for LUTs reference
        if timeline_data.get("lut_map"):
            self._build_lut_bin(children, timeline_data, lut_dir)

        # Write XML
        xml_string = self._prettify(root)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_string)

    def _create_root(self):
        """Create the root xmeml element."""
        root = ET.Element("xmeml")
        root.set("version", "5")
        return root

    def _build_sequence(self, parent, timeline_data, lut_dir, options):
        """Build the main sequence element."""
        seq = ET.SubElement(parent, "sequence")
        seq_id = f"sequence-{self._next_id()}"
        seq.set("id", seq_id)

        fps = timeline_data["fps"]
        width = timeline_data["width"]
        height = timeline_data["height"]
        name = timeline_data["name"]

        ET.SubElement(seq, "name").text = name
        ET.SubElement(seq, "duration").text = str(timeline_data["duration_frames"])

        # Rate
        rate = ET.SubElement(seq, "rate")
        self._add_rate(rate, fps)

        # Timecode
        tc = ET.SubElement(seq, "timecode")
        tc_rate = ET.SubElement(tc, "rate")
        self._add_rate(tc_rate, fps)
        ET.SubElement(tc, "string").text = timeline_data.get("start_timecode", "01:00:00:00")
        ET.SubElement(tc, "frame").text = "0"
        ET.SubElement(tc, "displayformat").text = "NDF"

        # Media
        media = ET.SubElement(seq, "media")

        # Video tracks
        video = ET.SubElement(media, "video")
        video_format = ET.SubElement(video, "format")
        sample_chars = ET.SubElement(video_format, "samplecharacteristics")
        ET.SubElement(sample_chars, "width").text = str(width)
        ET.SubElement(sample_chars, "height").text = str(height)
        sc_rate = ET.SubElement(sample_chars, "rate")
        self._add_rate(sc_rate, fps)
        ET.SubElement(sample_chars, "pixelaspectratio").text = "square"
        ET.SubElement(sample_chars, "fielddominance").text = "none"
        ET.SubElement(sample_chars, "codec").text = ""

        for track_data in timeline_data.get("video_tracks", []):
            self._build_video_track(video, track_data, timeline_data, lut_dir, options)

        # Audio tracks
        if options.get("export_audio", True):
            audio = ET.SubElement(media, "audio")
            audio_format = ET.SubElement(audio, "format")
            audio_sc = ET.SubElement(audio_format, "samplecharacteristics")
            ET.SubElement(audio_sc, "samplerate").text = "48000"
            ET.SubElement(audio_sc, "depth").text = "16"

            for track_data in timeline_data.get("audio_tracks", []):
                self._build_audio_track(audio, track_data, timeline_data, options)

        # Timeline markers
        if options.get("export_markers", True):
            for marker_data in timeline_data.get("markers", []):
                self._add_marker(seq, marker_data, fps)

        return seq

    def _build_video_track(self, video_elem, track_data, timeline_data, lut_dir, options):
        """Build a single video track with all its clips."""
        track = ET.SubElement(video_elem, "track")

        fps = timeline_data["fps"]
        width = timeline_data["width"]
        height = timeline_data["height"]
        lut_map = timeline_data.get("lut_map", {})

        clips = track_data.get("clips", [])

        # Sort clips by start frame
        clips_sorted = sorted(clips, key=lambda c: c.get("start_frame", 0))

        # Fill gaps with empty space and add clips
        current_frame = 0
        for clip in clips_sorted:
            start = clip["start_frame"]

            # Gap filler
            if start > current_frame:
                gap_duration = start - current_frame
                self._add_gap(track, gap_duration, fps)

            # Clip item
            self._build_clip_item(track, clip, fps, width, height, lut_dir, lut_map, options)
            current_frame = clip["end_frame"]

        # Track enabled state
        if not track_data.get("enabled", True):
            ET.SubElement(track, "enabled").text = "FALSE"

    def _build_clip_item(self, track, clip, fps, width, height, lut_dir, lut_map, options):
        """Build a single clip item element."""
        clip_item = ET.SubElement(track, "clipitem")
        clip_item.set("id", f"clipitem-{self._next_id()}")

        name = clip.get("name", "Untitled")
        duration = clip.get("duration_frames", 0)
        start_frame = clip.get("start_frame", 0)
        end_frame = clip.get("end_frame", 0)

        ET.SubElement(clip_item, "name").text = name
        ET.SubElement(clip_item, "duration").text = str(duration)

        rate = ET.SubElement(clip_item, "rate")
        self._add_rate(rate, fps)

        ET.SubElement(clip_item, "start").text = str(start_frame)
        ET.SubElement(clip_item, "end").text = str(end_frame)

        ET.SubElement(clip_item, "enabled").text = "TRUE"

        # Source in/out
        source_start = clip.get("source_start", 0) or 0
        source_end = source_start + duration
        ET.SubElement(clip_item, "in").text = str(source_start)
        ET.SubElement(clip_item, "out").text = str(source_end)

        # File reference
        file_elem = ET.SubElement(clip_item, "file")
        file_id = f"file-{self._next_id()}"
        file_elem.set("id", file_id)

        file_path = clip.get("file_path", "")
        if file_path:
            ET.SubElement(file_elem, "name").text = os.path.basename(file_path)
            ET.SubElement(file_elem, "pathurl").text = self._to_file_url(file_path)

            # Media characteristics
            media_elem = ET.SubElement(file_elem, "media")
            vid_media = ET.SubElement(media_elem, "video")
            sc = ET.SubElement(vid_media, "samplecharacteristics")
            ET.SubElement(sc, "width").text = str(width)
            ET.SubElement(sc, "height").text = str(height)
            sc_rate = ET.SubElement(sc, "rate")
            self._add_rate(sc_rate, fps)

        # Speed / retime
        premiere_speed = clip.get("premiere_speed", {})
        if premiere_speed.get("needs_retime", False):
            speed_elem = ET.SubElement(clip_item, "timebase")
            speed_elem.text = str(int(fps))

            # Add speed filter
            filter_elem = ET.SubElement(clip_item, "filter")
            effect_elem = ET.SubElement(filter_elem, "effect")
            ET.SubElement(effect_elem, "name").text = "Time Remap"
            ET.SubElement(effect_elem, "effectid").text = "timeremap"
            ET.SubElement(effect_elem, "effectcategory").text = "motion"
            ET.SubElement(effect_elem, "effecttype").text = "motion"

            speed_param = ET.SubElement(effect_elem, "parameter")
            ET.SubElement(speed_param, "parameterid").text = "speed"
            ET.SubElement(speed_param, "name").text = "speed"
            ET.SubElement(speed_param, "value").text = str(premiere_speed["percentage"])

            reverse_param = ET.SubElement(effect_elem, "parameter")
            ET.SubElement(reverse_param, "parameterid").text = "reverse"
            ET.SubElement(reverse_param, "name").text = "Reverse"
            ET.SubElement(reverse_param, "value").text = (
                "TRUE" if premiere_speed.get("reverse", False) else "FALSE"
            )

        # Transform / Motion
        premiere_transform = clip.get("premiere_transform", {})
        if options.get("export_transforms", True) and self._has_transform(premiere_transform):
            self._add_motion_effect(clip_item, premiere_transform, width, height)

        # Opacity
        opacity = clip.get("opacity", 100.0)
        if opacity != 100.0:
            self._add_opacity_effect(clip_item, opacity)

        # Blend mode
        blend_mode = clip.get("premiere_blend_mode", "normal")
        if blend_mode != "normal":
            ET.SubElement(clip_item, "compositemode").text = blend_mode

        # LUT / Lumetri color
        clip_id = clip.get("id", "")
        if clip_id in lut_map:
            lut_path = lut_map[clip_id]
            self._add_lumetri_lut(clip_item, lut_path)

        # Crop
        if self._has_crop(premiere_transform):
            self._add_crop_effect(clip_item, premiere_transform)

        # Clip markers
        for marker_data in clip.get("markers", []):
            self._add_marker(clip_item, marker_data, fps)

        return clip_item

    def _build_audio_track(self, audio_elem, track_data, timeline_data, options):
        """Build a single audio track."""
        track = ET.SubElement(audio_elem, "track")
        fps = timeline_data["fps"]

        clips = track_data.get("clips", [])
        clips_sorted = sorted(clips, key=lambda c: c.get("start_frame", 0))

        current_frame = 0
        for clip in clips_sorted:
            start = clip["start_frame"]

            if start > current_frame:
                gap_duration = start - current_frame
                self._add_gap(track, gap_duration, fps)

            self._build_audio_clip_item(track, clip, fps)
            current_frame = clip["end_frame"]

    def _build_audio_clip_item(self, track, clip, fps):
        """Build a single audio clip item."""
        clip_item = ET.SubElement(track, "clipitem")
        clip_item.set("id", f"clipitem-{self._next_id()}")

        ET.SubElement(clip_item, "name").text = clip.get("name", "Audio")
        ET.SubElement(clip_item, "duration").text = str(clip.get("duration_frames", 0))

        rate = ET.SubElement(clip_item, "rate")
        self._add_rate(rate, fps)

        ET.SubElement(clip_item, "start").text = str(clip.get("start_frame", 0))
        ET.SubElement(clip_item, "end").text = str(clip.get("end_frame", 0))
        ET.SubElement(clip_item, "enabled").text = "TRUE"

        source_start = clip.get("source_start", 0) or 0
        ET.SubElement(clip_item, "in").text = str(source_start)
        ET.SubElement(clip_item, "out").text = str(source_start + clip.get("duration_frames", 0))

        # File reference
        file_elem = ET.SubElement(clip_item, "file")
        file_elem.set("id", f"file-{self._next_id()}")
        file_path = clip.get("file_path", "")
        if file_path:
            ET.SubElement(file_elem, "name").text = os.path.basename(file_path)
            ET.SubElement(file_elem, "pathurl").text = self._to_file_url(file_path)

        # Volume
        volume = clip.get("premiere_volume", 0.0)
        if volume != 0.0:
            filter_elem = ET.SubElement(clip_item, "filter")
            effect_elem = ET.SubElement(filter_elem, "effect")
            ET.SubElement(effect_elem, "name").text = "Audio Levels"
            ET.SubElement(effect_elem, "effectid").text = "audiolevels"
            param = ET.SubElement(effect_elem, "parameter")
            ET.SubElement(param, "parameterid").text = "level"
            ET.SubElement(param, "name").text = "Level"
            # Convert dB to linear for FCP XML
            linear = 10 ** (volume / 20.0)
            ET.SubElement(param, "value").text = f"{linear:.4f}"

    def _add_motion_effect(self, clip_item, transform, width, height):
        """Add motion/transform effect to a clip."""
        filter_elem = ET.SubElement(clip_item, "filter")
        effect = ET.SubElement(filter_elem, "effect")
        ET.SubElement(effect, "name").text = "Basic Motion"
        ET.SubElement(effect, "effectid").text = "basic"
        ET.SubElement(effect, "effectcategory").text = "motion"
        ET.SubElement(effect, "effecttype").text = "motion"

        # Scale
        scale_x = transform.get("scale_x", 100)
        if transform.get("uniform_scale", True):
            param = ET.SubElement(effect, "parameter")
            ET.SubElement(param, "parameterid").text = "scale"
            ET.SubElement(param, "name").text = "Scale"
            ET.SubElement(param, "value").text = str(scale_x)
        else:
            for axis, val in [("scaleX", scale_x), ("scaleY", transform.get("scale_y", 100))]:
                param = ET.SubElement(effect, "parameter")
                ET.SubElement(param, "parameterid").text = axis
                ET.SubElement(param, "name").text = f"Scale {axis[-1]}"
                ET.SubElement(param, "value").text = str(val)

        # Position
        pos_x = transform.get("position_x", 0.5)
        pos_y = transform.get("position_y", 0.5)
        if abs(pos_x - 0.5) > 0.001 or abs(pos_y - 0.5) > 0.001:
            center_param = ET.SubElement(effect, "parameter")
            ET.SubElement(center_param, "parameterid").text = "center"
            ET.SubElement(center_param, "name").text = "Center"
            value = ET.SubElement(center_param, "value")
            horiz = ET.SubElement(value, "horiz")
            horiz.text = str(pos_x)
            vert = ET.SubElement(value, "vert")
            vert.text = str(pos_y)

        # Rotation
        rotation = transform.get("rotation", 0)
        if abs(rotation) > 0.01:
            param = ET.SubElement(effect, "parameter")
            ET.SubElement(param, "parameterid").text = "rotation"
            ET.SubElement(param, "name").text = "Rotation"
            ET.SubElement(param, "value").text = str(rotation)

    def _add_opacity_effect(self, clip_item, opacity):
        """Add opacity effect."""
        filter_elem = ET.SubElement(clip_item, "filter")
        effect = ET.SubElement(filter_elem, "effect")
        ET.SubElement(effect, "name").text = "Opacity"
        ET.SubElement(effect, "effectid").text = "opacity"
        ET.SubElement(effect, "effectcategory").text = "motion"
        ET.SubElement(effect, "effecttype").text = "motion"

        param = ET.SubElement(effect, "parameter")
        ET.SubElement(param, "parameterid").text = "opacity"
        ET.SubElement(param, "name").text = "Opacity"
        ET.SubElement(param, "value").text = str(opacity)

    def _add_crop_effect(self, clip_item, transform):
        """Add crop effect."""
        filter_elem = ET.SubElement(clip_item, "filter")
        effect = ET.SubElement(filter_elem, "effect")
        ET.SubElement(effect, "name").text = "Crop"
        ET.SubElement(effect, "effectid").text = "crop"
        ET.SubElement(effect, "effectcategory").text = "motion"
        ET.SubElement(effect, "effecttype").text = "motion"

        for side in ["left", "right", "top", "bottom"]:
            val = transform.get(f"crop_{side}", 0)
            if val > 0:
                param = ET.SubElement(effect, "parameter")
                ET.SubElement(param, "parameterid").text = f"crop{side.capitalize()}"
                ET.SubElement(param, "name").text = f"Crop {side.capitalize()}"
                ET.SubElement(param, "value").text = str(val)

    def _add_lumetri_lut(self, clip_item, lut_path):
        """
        Add a Lumetri Color effect with a LUT reference.

        This tells Premiere to apply the LUT via Lumetri when the
        XML is imported. The LUT path should be relative or absolute.
        """
        filter_elem = ET.SubElement(clip_item, "filter")
        effect = ET.SubElement(filter_elem, "effect")
        ET.SubElement(effect, "name").text = "Lumetri Color"
        ET.SubElement(effect, "effectid").text = "lumetricolor"
        ET.SubElement(effect, "effectcategory").text = "color"
        ET.SubElement(effect, "effecttype").text = "filter"

        # LUT file parameter
        param = ET.SubElement(effect, "parameter")
        ET.SubElement(param, "parameterid").text = "lut"
        ET.SubElement(param, "name").text = "Input LUT"
        ET.SubElement(param, "value").text = self._to_file_url(lut_path)

        # Also add as a generic filter approach for broader compatibility
        filter_elem2 = ET.SubElement(clip_item, "filter")
        effect2 = ET.SubElement(filter_elem2, "effect")
        ET.SubElement(effect2, "name").text = "LUT"
        ET.SubElement(effect2, "effectid").text = "lut3d"

        param2 = ET.SubElement(effect2, "parameter")
        ET.SubElement(param2, "parameterid").text = "lutFile"
        ET.SubElement(param2, "name").text = "LUT File"
        ET.SubElement(param2, "value").text = self._to_file_url(lut_path)

    def _add_marker(self, parent, marker_data, fps):
        """Add a marker element."""
        marker = ET.SubElement(parent, "marker")
        ET.SubElement(marker, "name").text = marker_data.get("name", "")
        ET.SubElement(marker, "comment").text = marker_data.get("note", "")

        frame = marker_data.get("frame", marker_data.get("frame_offset", 0))
        ET.SubElement(marker, "in").text = str(frame)
        ET.SubElement(marker, "out").text = str(
            frame + marker_data.get("duration", 1)
        )

        # Marker color
        color_id = marker_data.get("premiere_color", "0")
        ET.SubElement(marker, "color").text = color_id

    def _add_gap(self, track, duration, fps):
        """Add an empty gap/filler to a track."""
        gap = ET.SubElement(track, "clipitem")
        gap.set("id", f"gap-{self._next_id()}")
        ET.SubElement(gap, "name").text = ""
        ET.SubElement(gap, "duration").text = str(duration)
        rate = ET.SubElement(gap, "rate")
        self._add_rate(rate, fps)
        ET.SubElement(gap, "start").text = "0"
        ET.SubElement(gap, "end").text = str(duration)
        ET.SubElement(gap, "enabled").text = "TRUE"
        ET.SubElement(gap, "in").text = "-1"
        ET.SubElement(gap, "out").text = "-1"

    def _build_lut_bin(self, parent, timeline_data, lut_dir):
        """Build a bin element listing all LUT files for reference."""
        lut_map = timeline_data.get("lut_map", {})
        if not lut_map:
            return

        bin_elem = ET.SubElement(parent, "bin")
        ET.SubElement(bin_elem, "name").text = "LUTs"
        bin_children = ET.SubElement(bin_elem, "children")

        for clip_id, lut_path in lut_map.items():
            clip_elem = ET.SubElement(bin_children, "clip")
            clip_elem.set("id", f"lut-{self._next_id()}")
            ET.SubElement(clip_elem, "name").text = os.path.basename(lut_path)
            file_elem = ET.SubElement(clip_elem, "file")
            ET.SubElement(file_elem, "name").text = os.path.basename(lut_path)
            ET.SubElement(file_elem, "pathurl").text = self._to_file_url(lut_path)

    def _add_rate(self, rate_elem, fps):
        """Add timebase and ntsc flag to a rate element."""
        # Handle common frame rates
        fps_float = float(fps)

        # NTSC rates
        ntsc_rates = {23.976: 24, 29.97: 30, 59.94: 60}
        is_ntsc = False
        timebase = int(round(fps_float))

        for ntsc_fps, tb in ntsc_rates.items():
            if abs(fps_float - ntsc_fps) < 0.01:
                timebase = tb
                is_ntsc = True
                break

        ET.SubElement(rate_elem, "timebase").text = str(timebase)
        ET.SubElement(rate_elem, "ntsc").text = "TRUE" if is_ntsc else "FALSE"

    def _has_transform(self, transform):
        """Check if any transform values differ from default."""
        if not transform:
            return False
        return (
            abs(transform.get("scale_x", 100) - 100) > 0.01
            or abs(transform.get("scale_y", 100) - 100) > 0.01
            or abs(transform.get("position_x", 0.5) - 0.5) > 0.001
            or abs(transform.get("position_y", 0.5) - 0.5) > 0.001
            or abs(transform.get("rotation", 0)) > 0.01
        )

    def _has_crop(self, transform):
        """Check if any crop values are non-zero."""
        if not transform:
            return False
        return any(
            transform.get(f"crop_{s}", 0) > 0
            for s in ["left", "right", "top", "bottom"]
        )

    def _to_file_url(self, path):
        """Convert a filesystem path to a file:// URL."""
        if not path:
            return ""
        # Normalize path
        path = os.path.abspath(path)
        # Convert to file URL
        if os.name == "nt":
            # Windows: file:///C:/path/to/file
            path = path.replace("\\", "/")
            return f"file:///{path}"
        else:
            # macOS/Linux: file:///path/to/file
            return f"file://{path}"

    def _next_id(self):
        """Generate a unique ID."""
        self.clip_id_counter += 1
        return self.clip_id_counter

    def _prettify(self, elem):
        """Return a pretty-printed XML string."""
        rough_string = ET.tostring(elem, encoding="unicode")
        parsed = minidom.parseString(rough_string)
        pretty = parsed.toprettyxml(indent="  ", encoding=None)
        # Remove the XML declaration since we add our own
        lines = pretty.split("\n")
        # Keep the declaration and content
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines[1:])
