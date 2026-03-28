# DRP to Premiere Pro Converter

Converts DaVinci Resolve Studio timelines to Premiere Pro compatible format while **preserving color grades, transitions, transforms, speed changes, and audio**.

## The Problem

Converting DRP to Premiere typically results in:
- Color grades completely stripped
- Transitions missing or broken
- Speed ramps lost
- Transforms reset

## How This Tool Solves It

1. **Color grades** are exported as per-clip `.cube` LUT files via Resolve Studio's API and auto-linked via Lumetri in the Premiere XML
2. **Timeline structure** (cuts, clips, audio) exported as FCP XML — the most reliable interchange format
3. **Transforms** (position, scale, rotation, crop) mapped from Resolve's coordinate system to Premiere's
4. **Speed changes** preserved via time remap effects
5. **Markers** converted with color mapping
6. **Audio levels** and track structure maintained

## Requirements

- **DaVinci Resolve Studio** (paid version required for LUT export API)
- Python 3.6+ (bundled with Resolve)
- Premiere Pro CC 2019+

## Installation

### Quick Install (macOS/Linux)

```bash
cd DRP-to-Premiere
./install.sh
```

### Manual Install

1. Copy all `.py` files to:
   - **macOS:** `~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility/DRP-to-Premiere/`
   - **Windows:** `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\DRP-to-Premiere\`
   - **Linux:** `~/.local/share/DaVinciResolve/Fusion/Scripts/Utility/DRP-to-Premiere/`

2. Create a launcher file named `DRP to Premiere.py` in the parent `Utility` folder:
   ```python
   import sys, os
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), "DRP-to-Premiere"))
   from resolve_to_premiere import main
   main()
   ```

## Usage

### From Inside Resolve

1. Open your project in DaVinci Resolve Studio
2. Go to **Workspace > Scripts > DRP to Premiere**
3. Select the timeline to convert
4. Choose export options
5. Click **Convert to Premiere Pro**

### Standalone

```bash
python3 resolve_to_premiere.py
```

(Requires Resolve Studio to be open in the background)

## Importing in Premiere Pro

1. Open Premiere Pro
2. **File > Import** > select the generated `.xml` file
3. The timeline will be recreated with:
   - All clips in their correct positions
   - LUTs auto-applied via Lumetri Color effects
   - Transforms and speed changes preserved
   - Audio tracks and levels maintained

4. If LUTs don't auto-load, go to **Lumetri Color > Creative > Look > Browse** and point to the `LUTs` folder

## Export Options

| Option | Description |
|--------|-------------|
| Export color grades as LUTs | Export each graded clip's color as a .cube LUT file |
| Preserve transforms | Keep position, scale, rotation, crop values |
| Preserve speed changes | Keep retimes and speed ramps |
| Include audio tracks | Export audio with volume levels |
| Include markers | Convert timeline and clip markers |
| Flatten compound clips | Expand compound clips into individual clips |
| LUT Size (17/33/65) | Higher = more accurate color but larger files |

## What Gets Preserved

| Element | Status |
|---------|--------|
| Cuts / clip positions | Fully preserved |
| Color grades | Exported as .cube LUTs via Studio API |
| Transitions | Mapped to Premiere equivalents |
| Transforms (position, scale, rotation) | Coordinate-system converted |
| Crop | Converted |
| Speed changes | Via Time Remap effect |
| Audio tracks + levels | dB to linear conversion |
| Markers | With color mapping |
| Blend modes | Mapped to Premiere names |

## What Cannot Be Preserved

| Element | Reason |
|---------|--------|
| Fusion effects | No Premiere equivalent — recreate in After Effects |
| Power Windows | Part of color grading nodes — baked into LUT |
| Keyframed color grades | LUT captures a single state — use the most representative frame |
| ResolveFX | Proprietary — find Premiere alternatives |
| Fairlight audio effects | Use Premiere's audio effects instead |

## File Structure

```
YourTimeline_premiere/
├── YourTimeline.xml              # Import this in Premiere
├── LUTs/
│   ├── ClipName_abc123.cube      # Per-clip color grade LUTs
│   ├── ClipName2_def456.cube
│   └── ...
└── _conversion_report.txt        # Detailed conversion log
```

## Troubleshooting

**"Not connected to DaVinci Resolve"**
- Make sure Resolve Studio is running before launching the script
- Check that scripting is enabled: Resolve > Preferences > System > General > External scripting using = Local

**Clips show as offline in Premiere**
- Media files must be accessible from the same paths
- If files moved, use Premiere's "Link Media" to reconnect

**Speed changes not working**
- Complex speed ramps (variable speed) may need manual adjustment
- Constant speed changes should work correctly
