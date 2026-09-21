from __future__ import annotations

from .schemas import StageName


STAGE_ORDER = [StageName.REFERENCES, StageName.GEOMETRY, StageName.TEXTURES, StageName.RETOPOLOGY, StageName.RIG, StageName.MOTIONS, StageName.EXPORT]
STAGE_DEPENDENCIES: dict[StageName, tuple[StageName, ...]] = {
    StageName.REFERENCES: (),
    StageName.GEOMETRY: (StageName.REFERENCES,),
    StageName.TEXTURES: (StageName.GEOMETRY,),
    StageName.RETOPOLOGY: (StageName.TEXTURES,),
    StageName.RIG: (StageName.RETOPOLOGY,),
    StageName.MOTIONS: (StageName.RIG,),
    StageName.EXPORT: (StageName.MOTIONS,),
}


def downstream(stage: StageName) -> list[StageName]:
    index = STAGE_ORDER.index(stage)
    return STAGE_ORDER[index:]
