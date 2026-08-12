from io import BytesIO
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_first_sheet(content: bytes):
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise ValueError("File Excel tidak valid") from exc

    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        for item in root.findall("x:si", NS):
            shared.append("".join(node.text or "" for node in item.iterfind(".//x:t", NS)))

    sheet_name = next((name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")), None)
    if not sheet_name:
        raise ValueError("Worksheet tidak ditemukan")
    root = ElementTree.fromstring(archive.read(sheet_name))
    rows = []
    for row in root.findall(".//x:sheetData/x:row", NS):
        values = []
        for cell in row.findall("x:c", NS):
            reference = cell.attrib.get("r", "A1")
            column_letters = "".join(character for character in reference if character.isalpha())
            column = 0
            for character in column_letters:
                column = column * 26 + ord(character.upper()) - 64
            while len(values) < column - 1:
                values.append("")
            cell_type = cell.attrib.get("t")
            value_node = cell.find("x:v", NS)
            inline_node = cell.find("x:is/x:t", NS)
            raw = inline_node.text if inline_node is not None else (value_node.text if value_node is not None else "")
            if cell_type == "s" and raw != "":
                raw = shared[int(raw)]
            values.append(raw or "")
        rows.append(values)
    return rows
