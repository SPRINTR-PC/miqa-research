"""Benchmark NDPI -> DICOM conversion and round-trip tile validation (see the technical
manual page "NDPI to DICOM conversion cost").

Run each phase as its own process so peak memory is per phase, from the project root:

    uv run python tools/benchmarks/ndpi_conversion_bench.py convert CMU-1.ndpi out_dir
    uv run python tools/benchmarks/ndpi_conversion_bench.py bytes   CMU-1.ndpi out_dir
    uv run python tools/benchmarks/ndpi_conversion_bench.py decode  CMU-1.ndpi out_dir

`convert` writes the DICOM set to out_dir (replacing it); `bytes` / `decode` read it back and
compare every tile against the NDPI (compressed bytes, or decoded pixels of both sides).
Prints one JSON line: wall/CPU seconds, peak RSS (MB), tile and mismatch counts.
"""
import sys, time, resource, shutil, json
from pathlib import Path
phase, ndpi, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
t0 = time.perf_counter(); c0 = time.process_time()
info = {}
if phase == "convert":
    sys.path.insert(0, ".")
    import os, django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MiqaResearch.settings")
    django.setup()
    from MiqaResearch.tasks.dicom_handling.ndpi_conversion import convert_ndpi_to_dicom
    if out.exists(): shutil.rmtree(out)
    files = convert_ndpi_to_dicom(ndpi, out)
    info = {"files": len(files), "dicom_bytes": sum(f.stat().st_size for f in files)}
else:
    import imagecodecs
    from wsidicom.geometry import Point
    from opentile import OpenTile
    from wsidicom import WsiDicom
    wsi = WsiDicom.open(out)
    dl = {l.level: l for l in wsi.pyramid.levels}
    first = next(iter(dl.values())).default_instance.tile_size
    tiler = OpenTile.open(ndpi, tile_size=first.width)
    n = bad = nbytes = 0
    for ol in tiler.levels:
        dlv = dl.get(ol.pyramid_index)
        if dlv is None: continue
        inst = dlv.default_instance
        tw, th = ol.tiled_size.width, ol.tiled_size.height
        for y in range(th):
            for x in range(tw):
                a = ol.get_tile((x, y))
                b = inst.image_data.get_encoded_tile(Point(x, y), inst.image_data.default_z, inst.image_data.default_path)
                n += 1; nbytes += len(b)
                if phase == "bytes":
                    if not (b == a or (len(a) % 2 and b == a + b"\x00")): bad += 1
                else:  # decode both sides fully
                    da, db = imagecodecs.jpeg8_decode(a), imagecodecs.jpeg8_decode(b)
                    if da.shape != db.shape or (da != db).any(): bad += 1
    info = {"tiles": n, "mismatches": bad, "dicom_tile_bytes": nbytes}
info.update(phase=phase, wall_s=round(time.perf_counter()-t0,1), cpu_s=round(time.process_time()-c0,1),
            peak_rss_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6))
print(json.dumps(info))
