"""
XML Patcher
===========
Patches a Resolve-exported FCP 7 XML to embed Lumetri Color / LUT
references so Adobe Premiere Pro auto-applies the colour grades on import.
"""

import os
import xml.etree.ElementTree as ET


class XMLPatcher:

    def patch(self, xml_path, lut_map_by_name, lut_dir):
        """
        xml_path          – path to the FCP 7 XML exported by Resolve
        lut_map_by_name   – dict  {clip_filename_stem: absolute_lut_path}
        lut_dir           – folder where .cube files live

        Writes the patched XML back to the same path.
        """
        if not os.path.exists(xml_path):
            return False

        try:
            ET.register_namespace("", "")
            tree = ET.parse(xml_path)
            root = tree.getroot()

            patched = 0
            for clipitem in root.iter("clipitem"):
                lut_path = self._find_lut_for_clip(clipitem, lut_map_by_name, lut_dir)
                if lut_path and os.path.exists(lut_path):
                    self._inject_lumetri_filter(clipitem, lut_path)
                    patched += 1

            tree.write(xml_path, encoding="utf-8", xml_declaration=True)
            return patched > 0

        except Exception as e:
            print(f"XML patch error: {e}")
            return False

    # ------------------------------------------------------------------
    def _find_lut_for_clip(self, clipitem, lut_map_by_name, lut_dir):
        """Try to match a clipitem to a .cube file."""

        # Try <name> element
        name_el = clipitem.find("name")
        if name_el is not None and name_el.text:
            stem = os.path.splitext(name_el.text)[0]
            if stem in lut_map_by_name:
                return lut_map_by_name[stem]

        # Try <file>/<name>
        file_el = clipitem.find("file/name")
        if file_el is not None and file_el.text:
            stem = os.path.splitext(file_el.text)[0]
            if stem in lut_map_by_name:
                return lut_map_by_name[stem]

        # Fuzzy: scan lut_dir for any .cube whose name contains the clip name
        if name_el is not None and name_el.text:
            clip_name = name_el.text.lower()
            try:
                for f in os.listdir(lut_dir):
                    if f.endswith(".cube") and clip_name[:10] in f.lower():
                        return os.path.join(lut_dir, f)
            except Exception:
                pass

        return None

    # ------------------------------------------------------------------
    def _inject_lumetri_filter(self, clipitem, lut_path):
        """
        Add a Lumetri Color filter element to a clipitem.
        Premiere Pro reads this on import and applies the LUT automatically.
        """
        # Remove any existing lumetri filter to avoid duplicates
        for f in list(clipitem.findall("filter")):
            eid = f.find("effect/effectid")
            if eid is not None and eid.text == "lumetri":
                clipitem.remove(f)

        filter_el = ET.SubElement(clipitem, "filter")

        effect = ET.SubElement(filter_el, "effect")
        ET.SubElement(effect, "name").text         = "Lumetri Color"
        ET.SubElement(effect, "effectid").text     = "lumetri"
        ET.SubElement(effect, "effectcategory").text = "color"
        ET.SubElement(effect, "effecttype").text   = "filter"
        ET.SubElement(effect, "mediatype").text    = "video"
        ET.SubElement(effect, "pproBypass").text   = "FALSE"

        # Input LUT parameter
        param = ET.SubElement(effect, "parameter")
        ET.SubElement(param, "parameterid").text = "inputLUT"
        ET.SubElement(param, "name").text        = "Input LUT"
        ET.SubElement(param, "value").text       = lut_path

        # Enable Input LUT
        param2 = ET.SubElement(effect, "parameter")
        ET.SubElement(param2, "parameterid").text = "inputLUTEnabled"
        ET.SubElement(param2, "name").text        = "Enable Input LUT"
        ET.SubElement(param2, "value").text       = "TRUE"
