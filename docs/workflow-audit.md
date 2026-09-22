# Рабочий workflow-аудит Character Factory

Дата аудита: 2026-09-22. Этот документ описывает не «как удобнее написать
код», а какой проверяемый production-flow следует из ТЗ и официальных рабочих
примеров. Любой этап считается реализованным только после реального запуска,
сохранения результата и повторной загрузки результата следующим этапом.

Уточнение шага «Материалы» после разбора реальных артефактов: см.
[materials-investigation.md](materials-investigation.md). Наличие UV/texture и
успешный smoke-test не являются доказательством качества. Подробный bake-flow
и крупные планы из этого расследования заменяют прежнее предположение, будто
достаточно передать четыре референса в неизменённый Paint.

## Зафиксированные решения по моделям

| Этап ТЗ | Рекомендуемый рабочий аналог | Решение для RTX 4070 12 GB | Жёсткое доказательство |
| --- | --- | --- | --- |
| 4 вида → geometry | официальный Hunyuan3D-2mv, `textured_shape_gen_multiview.py` | Hunyuan3D-2mv, только переданные FRONT/LEFT/BACK/RIGHT | provider views совпадают с входами; GLB валиден |
| FRONT → geometry | официальный Hunyuan3D-2 single-view + Paint | Hunyuan shape → отдельный Paint stage; без silent downgrade | actual provider, VRAM, mesh reload, визуальный snapshot |
| image → textured mesh | официальный Tencent flow shape → Paint; для multiview Paint принимает список изображений в `fast_texture_gen_multiview.py` | Paint получает все доступные views, а не только FRONT | UV, embedded textures, material map inventory, front/side/back renders |
| high-fidelity PBR comparator | Microsoft TRELLIS.2 | не включать: upstream требует минимум 24 GB VRAM и Linux; не тратить место на неподходящую установку | зафиксировано как rejected candidate |
| retopology/UV | Blender QuadriFlow/decimate + UV unwrap | KEEP_SOURCE, TRIANGLE и QUAD; после изменения topology обязательны UV и texture-preservation report | manifold/degenerate/UV/texture render checks |
| skeleton + skinning | официальный UniRig: skeleton prediction → skin prediction → merge | отдельный WSL CUDA worker; skeleton надо валидировать и при необходимости canonicalize до skin merge | joint graph, weights, canonical map, GLB reload |
| animation library | Quaternius Universal Animation Library 2 | локальный лицензированный CC0 catalog, canonical normalization через Blender | license, hashes, action catalog, real normalized GLB |
| retarget/graph/IK | Blender actions/NLA/constraints; Blender IK solver supports target, pole, chain length and limits | source action → canonical action → generated rig; IK только как реальные bone constraints | baked clip, state/transition report, IK targets/constraints, visual renders |
| export | Blender GLB/FBX exporter + glTF roundtrip validation | standalone selected actions, embedded textures, manifest | reopen GLB/FBX and inspect meshes/materials/skins/animations |

Источники рабочих flow: [Hunyuan3D-2 official examples](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/tree/main/examples),
[Hunyuan multiview Paint example](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/examples/fast_texture_gen_multiview.py),
[UniRig official inference and merge flow](https://github.com/VAST-AI-Research/UniRig),
[Blender QuadriFlow retopology](https://docs.blender.org/manual/en/3.0/modeling/meshes/retopology.html),
[Blender IK constraints](https://docs.blender.org/manual/en/4.4/animation/constraints/tracking/ik_solver.html),
[Quaternius UAL2](https://quaternius.com/packs/universalanimationlibrary2.html),
[TRELLIS.2 requirements](https://github.com/microsoft/TRELLIS.2#-installation).

## Реализация по фазам ТЗ

### PHASE 1 — foundation

Browser → React/Three.js → FastAPI → persistent JobStore → one GPU queue →
isolated subprocess workers → Blender headless → `jobs/<id>`. Каждый worker
возвращает JSON protocol с path, settings, logs и validation. SSE только
показывает persisted manifest; прогресс не рисуется от балды.

Готовность: restart API не теряет manifest, повторный запуск не пересчитывает
READY stages, cancellation завершает дочерний процесс, а worker failure
оставляет traceback и VRAM record.

### PHASE 2–3 — references и geometry

FRONT обязателен, остальные slots независимы. Original никогда не изменяется;
processed получает alpha, crop, square padding, scale normalization и quality
report. При 2–4 views передаются только реально существующие named images.
Missing view не синтезируется и не копирует FRONT. DINOv3 — только consistency
warning, не замена визуальной проверке.

Single-view flow больше не использует плохой fallback автоматически: AUTO
выбирает Hunyuan single-view. При его недоступности job получает явный
`MODEL_MISSING`, потому что быстрый провайдер с неприемлемым для персонажа
результатом не является production fallback. Multiview использует Hunyuan3D-2mv.

### PHASE 4 — retopology + UV

KEEP_SOURCE сохраняет исходный mesh. TRIANGLE применяет decimation с заданным
target faces. QUAD сначала чинит входной mesh только явно записанным repair
шагом, запускает QuadriFlow, затем делает unwrap. Если projection/transfer
текстуры не прошёл визуальную проверку, stage не может стать READY.

### PHASE 5 — rigging

UniRig запускается в отдельном WSL process. Сначала skeleton prediction,
затем skeleton validation/refinement, затем skin prediction и merge с исходной
геометрией. Canonical mapping не должен удалять secondary bones. Для
stylized/non-humanoid graph stage должен остановиться с `RIG_VALIDATION_FAILED`,
а не выдавать пустой или декоративный armature.

### PHASE 6–8 — motion, retargeting, graph

Motion library регистрируется с license/source/hash/fps/duration/root-motion
metadata. Каждая source action импортируется в Blender, маппится на canonical
rig, bake'ится, roundtrip-проверяется и только затем появляется в каталоге.
Graph выбирает реальные normalized actions: Idle/Walk/Run/Sprint/Crouch/Jump,
Attack/Hit/Death/Emote; transition, upper-body mask, additive action и
root-motion mode должны быть отражены в report и видны в Unit Tester.

### PHASE 9–11 — equipment, clothing, IK

Одежда — отдельный skinned asset с weight transfer, body mask и clipping
validation. Оружие — rigid socket attachment к canonical bone с provenance и
grip metadata. Hand IK для rifle использует primary grip + secondary grip;
foot IK использует ground raycast и pelvis compensation; look IK ограничивает
neck/head rotation. Наличие target objects без реальных Blender constraints не
считается реализацией.

### PHASE 12 — Unit Tester

Viewport должен загружать именно READY export GLB, проигрывать embedded clips и
shared canonical actions, а WASD/Shift/Ctrl/Space должны менять graph state.
Debug toggles Mesh/Wireframe/Skeleton/Bones/Sockets/IK/Bounds/Normals/Materials
должны менять renderer state, а не только подпись.

### PHASE 13–14 — export и hardening

Export получает выбранные actions, bake'ит только их, сохраняет `unit.glb`,
`unit.fbx`, `unit.manifest.json`, затем заново открывает GLB и проверяет meshes,
materials, textures, skins, bones и animations. Full acceptance требует четыре
валидированных пользовательских views, multiview provider, rig, clothing,
sword, rifle, IK, ten canonical clips и roundtrip export. Если любой пункт
не выполнен, job остаётся FAILED/NEEDS_ATTENTION, а не READY.

## Что сейчас реально закрыто, а что нет

Закрыты отдельные smoke/acceptance срезы для Hunyuan shape/Paint, UniRig,
retarget, graph, equipment, IK и export. Это не доказывает full TЗ: текущий
строгий gate всё ещё требует четыре пользовательских views и визуальную
проверку деформаций.

Текущий обязательный следующий срез: переделать Paint adapter на официальный
multiview input list, удалить SPAR3D из активного registry и external runtime,
затем выполнить один новый full run с четырьмя настоящими views. До этого нельзя
называть качество Tripo-level или считать проект завершённым.
