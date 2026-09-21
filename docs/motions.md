# Motion Library

The catalog is stored in `motions/motion_catalog.json`. It keeps source URL, license text, commercial-use flag, archive SHA-256, installed files and extracted clip metadata. The API is local-only:

```powershell
$body = @{ source_path = 'D:\downloads\universal-animation-library.zip'; library_id = 'quaternius-universal'; source_id = 'quaternius-universal-animation-library'; license = 'CC0 1.0'; allowed_for_commercial_use = $true } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/motions/register -ContentType 'application/json' -Body $body
```

Use a library id without spaces. The official Quaternius pack is documented as CC0 and retargetable; CMU describes its database as free to use with restrictions against reselling the data directly. Review the current upstream terms before registering any source:

- https://quaternius.com/packs/universalanimationlibrary.html
- https://mocap.cs.cmu.edu/

The installer never scrapes Mixamo, downloads unknown URLs, or fabricates clips. GLB animation names and sampler durations are read from the installed file. FBX/BVH files are registered as metadata-only until the Blender normalization worker is available.
