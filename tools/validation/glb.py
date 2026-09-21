from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_COMPONENT_FORMAT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


@dataclass
class GlbValidationReport:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mesh_count: int = 0
    primitive_count: int = 0
    vertex_count: int = 0
    face_count: int = 0
    material_count: int = 0
    texture_count: int = 0
    skin_count: int = 0
    animation_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class GlbReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.document: dict[str, Any] = {}
        self.binary = b""

    def read(self) -> None:
        raw = self.path.read_bytes()
        if len(raw) < 12:
            raise ValueError("GLB header is truncated")
        magic, version, declared_length = struct.unpack_from("<4sII", raw, 0)
        if magic != b"glTF":
            raise ValueError("Invalid GLB magic")
        if version != 2:
            raise ValueError(f"Unsupported GLB version {version}")
        if declared_length != len(raw):
            raise ValueError(f"GLB length mismatch: header says {declared_length}, file is {len(raw)} bytes")
        offset = 12
        json_chunk: bytes | None = None
        while offset < len(raw):
            if offset + 8 > len(raw):
                raise ValueError("GLB chunk header is truncated")
            chunk_length, chunk_type = struct.unpack_from("<I4s", raw, offset)
            offset += 8
            end = offset + chunk_length
            if end > len(raw):
                raise ValueError("GLB chunk extends beyond file")
            chunk = raw[offset:end]
            offset = end
            if chunk_type == b"JSON":
                if json_chunk is not None:
                    raise ValueError("GLB contains multiple JSON chunks")
                json_chunk = chunk.rstrip(b" \t\r\n\x00")
            elif chunk_type == b"BIN\x00":
                self.binary = chunk
        if json_chunk is None:
            raise ValueError("GLB JSON chunk is missing")
        document = json.loads(json_chunk.decode("utf-8"))
        if not isinstance(document, dict):
            raise ValueError("GLB JSON document must be an object")
        self.document = document

    def accessor_values(self, accessor_index: int) -> list[tuple[int | float, ...]]:
        accessors = self.document.get("accessors", [])
        views = self.document.get("bufferViews", [])
        if accessor_index < 0 or accessor_index >= len(accessors):
            raise ValueError(f"Accessor index {accessor_index} is out of range")
        accessor = accessors[accessor_index]
        view_index = accessor.get("bufferView")
        if view_index is None:
            raise ValueError(f"Accessor {accessor_index} has no bufferView")
        if view_index < 0 or view_index >= len(views):
            raise ValueError(f"BufferView index {view_index} is out of range")
        view = views[view_index]
        component_format = _COMPONENT_FORMAT.get(accessor.get("componentType"))
        components = _TYPE_COMPONENTS.get(accessor.get("type"))
        if component_format is None or components is None:
            raise ValueError(f"Accessor {accessor_index} uses an unsupported component type or shape")
        count = int(accessor.get("count", 0))
        if count < 0:
            raise ValueError(f"Accessor {accessor_index} has a negative count")
        scalar_size = struct.calcsize("<" + component_format)
        element_size = scalar_size * components
        stride = int(view.get("byteStride", element_size))
        if stride < element_size:
            raise ValueError(f"BufferView {view_index} stride is smaller than its element")
        base = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
        view_length = int(view.get("byteLength", 0))
        if base < 0 or base + max(0, (count - 1) * stride + element_size) > int(view.get("byteOffset", 0)) + view_length:
            raise ValueError(f"Accessor {accessor_index} reads beyond its bufferView")
        values: list[tuple[int | float, ...]] = []
        for index in range(count):
            start = base + index * stride
            values.append(tuple(struct.unpack_from("<" + component_format * components, self.binary, start)))
        return values


def validate_glb(path: Path, require_skeleton: bool = False, require_animations: bool = False) -> GlbValidationReport:
    report = GlbValidationReport(valid=False)
    if not path.is_file():
        report.errors.append(f"GLB does not exist: {path}")
        return report
    if path.stat().st_size == 0:
        report.errors.append("GLB is empty")
        return report
    reader = GlbReader(path)
    try:
        reader.read()
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        report.errors.append(str(error))
        return report
    document = reader.document
    asset = document.get("asset", {})
    if asset.get("version") != "2.0":
        report.errors.append("GLB asset.version must be 2.0")
    buffers = document.get("buffers", [])
    if not buffers:
        report.errors.append("GLB has no buffers")
    elif int(buffers[0].get("byteLength", 0)) > len(reader.binary):
        report.errors.append("Embedded BIN chunk is shorter than buffers[0].byteLength")
    meshes = document.get("meshes", [])
    report.mesh_count = len(meshes)
    report.material_count = len(document.get("materials", []))
    report.texture_count = len(document.get("textures", []))
    report.skin_count = len(document.get("skins", []))
    report.animation_count = len(document.get("animations", []))
    if not meshes:
        report.errors.append("GLB contains no meshes")
    accessors = document.get("accessors", [])
    for mesh_index, mesh in enumerate(meshes):
        primitives = mesh.get("primitives", [])
        if not primitives:
            report.errors.append(f"Mesh {mesh_index} contains no primitives")
        for primitive_index, primitive in enumerate(primitives):
            report.primitive_count += 1
            attributes = primitive.get("attributes", {})
            position_accessor = attributes.get("POSITION")
            if position_accessor is None:
                report.errors.append(f"Mesh {mesh_index} primitive {primitive_index} has no POSITION attribute")
                continue
            try:
                positions = GlbReader.accessor_values(reader, position_accessor)
            except ValueError as error:
                report.errors.append(str(error))
                continue
            report.vertex_count += len(positions)
            if any(not all(math.isfinite(float(component)) for component in position) for position in positions):
                report.errors.append(f"Mesh {mesh_index} primitive {primitive_index} contains non-finite positions")
            if primitive.get("indices") is not None:
                try:
                    indices = GlbReader.accessor_values(reader, primitive["indices"])
                    flat_indices = [int(value[0]) for value in indices]
                    report.face_count += len(flat_indices) // 3
                    if any(index < 0 or index >= len(positions) for index in flat_indices):
                        report.errors.append(f"Mesh {mesh_index} primitive {primitive_index} has an out-of-range index")
                except ValueError as error:
                    report.errors.append(str(error))
            else:
                report.face_count += len(positions) // 3
            material_index = primitive.get("material")
            if material_index is not None and (material_index < 0 or material_index >= report.material_count):
                report.errors.append(f"Mesh {mesh_index} primitive {primitive_index} references a missing material")
    if require_skeleton and report.skin_count == 0:
        report.errors.append("Validated unit requires a skin")
    if require_animations and report.animation_count == 0:
        report.errors.append("Validated unit requires at least one animation")
    report.metadata = {"path": str(path), "size_bytes": path.stat().st_size, "asset": asset}
    report.valid = not report.errors and report.vertex_count > 0 and report.face_count > 0
    return report
