"""
Effects Mapper
===============
Maps DaVinci Resolve effects, transforms, and properties
to their Premiere Pro equivalents.
"""


# Resolve transition names to Premiere equivalents
TRANSITION_MAP = {
    "Cross Dissolve": "Cross Dissolve",
    "Dip to Color Dissolve": "Dip to Black",
    "Smooth Cut": "Morph Cut",
    "Additive Dissolve": "Additive Dissolve",
    "Wipe": "Wipe",
    "Push": "Push",
    "Slide": "Slide",
}

# Resolve composite modes to Premiere blend modes
BLEND_MODE_MAP = {
    "Normal": "normal",
    "Add": "add",
    "Subtract": "subtract",
    "Difference": "difference",
    "Multiply": "multiply",
    "Screen": "screen",
    "Overlay": "overlay",
    "Hard Light": "hardLight",
    "Soft Light": "softLight",
    "Darken": "darken",
    "Lighten": "lighten",
    "Color Dodge": "colorDodge",
    "Color Burn": "colorBurn",
    "Linear Dodge": "linearDodge",
    "Linear Burn": "linearBurn",
    "Exclusion": "exclusion",
    "Hue": "hue",
    "Saturation": "saturation",
    "Color": "color",
    "Luminosity": "luminosity",
}

# Marker color mapping
MARKER_COLOR_MAP = {
    "Blue": "0",
    "Cyan": "1",
    "Green": "2",
    "Yellow": "3",
    "Red": "4",
    "Pink": "5",
    "Purple": "6",
    "Fuchsia": "7",
    "Rose": "7",
    "Lavender": "6",
    "Sky": "1",
    "Mint": "2",
    "Lemon": "3",
    "Sand": "3",
    "Cocoa": "4",
    "Cream": "3",
}


class EffectsMapper:
    """Maps Resolve effects/properties to Premiere equivalents."""

    def map_all(self, timeline_data, options):
        """
        Process all clips in the timeline data and add Premiere-compatible
        effect mappings.
        """
        for track in timeline_data.get("video_tracks", []):
            for clip in track.get("clips", []):
                self._map_clip_effects(clip, options)

        for track in timeline_data.get("audio_tracks", []):
            for clip in track.get("clips", []):
                self._map_audio_effects(clip, options)

        # Map timeline markers
        for marker in timeline_data.get("markers", []):
            marker["premiere_color"] = MARKER_COLOR_MAP.get(
                marker.get("color", "Blue"), "0"
            )

        return timeline_data

    def _map_clip_effects(self, clip, options):
        """Map effects for a single video clip."""
        # Transform mapping (Resolve -> Premiere coordinate system)
        if options.get("export_transforms", True):
            clip["premiere_transform"] = self._map_transform(clip.get("transform", {}))

        # Speed mapping
        if options.get("export_speed", True):
            clip["premiere_speed"] = self._map_speed(clip)

        # Transition mapping
        transitions = clip.get("transitions", {})
        for pos in ["start", "end"]:
            if transitions.get(pos):
                resolve_name = transitions[pos].get("name", "")
                transitions[pos]["premiere_name"] = TRANSITION_MAP.get(
                    resolve_name, "Cross Dissolve"
                )

        # Blend mode mapping
        composite = clip.get("composite_mode", "Normal")
        clip["premiere_blend_mode"] = BLEND_MODE_MAP.get(composite, "normal")

        # Marker colors
        for marker in clip.get("markers", []):
            marker["premiere_color"] = MARKER_COLOR_MAP.get(
                marker.get("color", "Blue"), "0"
            )

        # Flag unsupported effects
        warnings = []
        if clip.get("is_fusion", False):
            warnings.append(
                f"Clip '{clip['name']}' has Fusion effects that cannot be converted. "
                f"These will need to be recreated in Premiere/After Effects."
            )
        clip["effect_warnings"] = warnings

    def _map_transform(self, resolve_transform):
        """
        Map Resolve transform values to Premiere's coordinate system.

        Key differences:
        - Resolve: zoom 1.0 = 100%, position in pixels from center
        - Premiere: scale 100 = 100%, position as % offset from center
        """
        premiere = {}

        # Scale: Resolve uses 1.0 = 100%, Premiere uses 100 = 100%
        premiere["scale_x"] = resolve_transform.get("zoom_x", 1.0) * 100
        premiere["scale_y"] = resolve_transform.get("zoom_y", 1.0) * 100

        # Uniform scale check
        premiere["uniform_scale"] = (
            abs(premiere["scale_x"] - premiere["scale_y"]) < 0.01
        )

        # Position: Resolve uses pixel offset from center,
        # Premiere uses absolute position (0.5 = center)
        premiere["position_x"] = 0.5 + resolve_transform.get("position_x", 0.0)
        premiere["position_y"] = 0.5 + resolve_transform.get("position_y", 0.0)

        # Rotation: both use degrees, but direction might differ
        premiere["rotation"] = resolve_transform.get("rotation", 0.0)

        # Anchor point
        premiere["anchor_x"] = 0.5 + resolve_transform.get("anchor_x", 0.0)
        premiere["anchor_y"] = 0.5 + resolve_transform.get("anchor_y", 0.0)

        # Crop: Resolve uses 0-1 range, Premiere uses percentage of dimension
        premiere["crop_left"] = resolve_transform.get("crop_left", 0.0) * 100
        premiere["crop_right"] = resolve_transform.get("crop_right", 0.0) * 100
        premiere["crop_top"] = resolve_transform.get("crop_top", 0.0) * 100
        premiere["crop_bottom"] = resolve_transform.get("crop_bottom", 0.0) * 100

        # Flip
        premiere["flip_x"] = resolve_transform.get("flip_x", False)
        premiere["flip_y"] = resolve_transform.get("flip_y", False)

        return premiere

    def _map_speed(self, clip):
        """Map speed/retime settings for Premiere."""
        speed = clip.get("speed", 1.0)

        premiere_speed = {
            "rate": speed,
            "percentage": speed * 100,
            "reverse": clip.get("reverse", False) or speed < 0,
            "frame_blending": "frame-sampling",  # Default
        }

        # Premiere represents speed as a fraction
        # 1.0 = normal, 0.5 = half speed, 2.0 = double speed
        if speed != 1.0:
            premiere_speed["needs_retime"] = True
        else:
            premiere_speed["needs_retime"] = False

        return premiere_speed

    def _map_audio_effects(self, clip, options):
        """Map audio-specific effects."""
        # Volume mapping: Resolve and Premiere both use dB
        clip["premiere_volume"] = clip.get("volume", 0.0)

        # Pan mapping
        clip["premiere_pan"] = clip.get("pan", 0.0)
