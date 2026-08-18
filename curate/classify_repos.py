#!/usr/bin/env python3
"""Separate real Halide users from vendored bundles in the Lane B pool.

Roughly four fifths of the raw code-search pool are repositories that never use
Halide. OpenCV ships a Halide backend for its DNN module, so every project that
vendors OpenCV sources matches; so does anything carrying a vcpkg port tree, a
site-packages directory, or a `third_party/` bundle.

The rule that works is per matched PATH, not per repository:

    find_package(Halide  at  CMakeLists.txt                       -> a consumer
    find_package(Halide  at  .../cmake/OpenCVDetectHalide.cmake   -> vendoring

Two refinements the obvious version gets wrong, both found by validation:

  * `CMakeLists.txt` ends in `.txt`. Treating `.txt` as documentation classifies
    every CMake consumer line as prose, which silently discards the strongest
    evidence in the pool.

  * A directory named `halide/` does not mean a vendored copy of Halide.
    `flashlight/pkg/halide/HalideInterface.h` is flashlight's own integration
    code. What does mean a vendored copy is Halide's own directory vocabulary
    appearing anywhere in the path -- `frontends/halide/test/integration/xc/`
    is Halide's tree relocated, and `apps/bgu/CMakeLists.txt` at the root is
    Halide itself re-uploaded under another name.

Repositories that embed a Halide tree are NOT resolved here. A fork that extends
Halide and an unmodified re-upload look identical from paths alone; telling them
apart needs a commit diff against upstream. They are set aside under
`halide_copy_or_fork` for that pass rather than guessed at.

Usage:
    python3 curate/classify_repos.py --in data/pools/lane_b.json \
                                     --out data/pools/lane_b_classified.json
"""

import argparse
import json
import re
import sys
from collections import Counter

# Path fragments unique to Halide's own repository layout. Their presence means
# a copy of Halide is embedded, wherever in the tree it is rooted.
HALIDE_LAYOUT = [
    "test/integration/", "tools/gengen.cpp", "src/func.cpp", "src/lower.cpp",
    "apps/bgu/", "apps/blur/", "apps/hist/", "apps/wavelet/", "apps/onnx/",
    "apps/hannk/", "apps/resnet_50/", "apps/hellobaremetal/", "apps/c_backend/",
    "apps/local_laplacian/", "apps/lens_blur/", "apps/interpolate/",
    "apps/camera_pipe/", "apps/stencil_chain/", "apps/nl_means/",
    "apps/max_filter/", "apps/bilateral_grid/", "apps/conv_layer/",
    "apps/harris/", "apps/iir_blur/", "apps/unsharp/", "apps/fft/",
    "apps/depthwise_separable_conv/", "apps/linear_algebra/", "apps/support/",
]

# Third-party projects that ship their own Halide integration, keyed on layout
# fragments rather than plain names because versioned directory names
# (`opencv4.7.0/opencv-4.7.0/...`) defeat name matching.
THIRD_PARTY = {
    "opencv": ["opencv", "modules/dnn/src/", "op_halide", "opencvdetecthalide"],
    "vcpkg": ["vcpkg", "ports/halide"],
    "mediapipe": ["mediapipe"],
    "mnn": ["/mnn/"],
    "ncnn": ["ncnn"],
    "tvm": ["/tvm/"],
    "bundled": [
        "third_party", "thirdparty", "3rdparty", "third-party", "/external/",
        "/extern/", "/vendor", "node_modules", "site-packages", "dist-packages",
        "/_deps/", "/subprojects/",
    ],
}

# Repositories that ARE the third-party project, so their own tree is own code.
CANONICAL = {
    "opencv/opencv", "alibaba/MNN", "google/mediapipe", "Tencent/ncnn",
    "apache/tvm", "microsoft/vcpkg", "halide/Halide",
}

DOCS = re.compile(r"\.(md|rst|html|adoc|ipynb)$", re.I)
CMAKEISH = re.compile(r"(^|/)(CMakeLists\.txt|.*\.cmake)$", re.I)


def classify_path(repo, entry):
    """entry is 'signature_name:path' as recorded by the harvester."""
    _, _, path = entry.partition(":")
    low = path.lower()
    filename = path.split("/")[-1]

    # Build files first: CMakeLists.txt would otherwise read as documentation.
    if not CMAKEISH.search(path) and DOCS.search(filename):
        return "prose"
    if repo not in CANONICAL:
        for markers in THIRD_PARTY.values():
            if any(marker in low for marker in markers):
                return "third_party"
    if repo != "halide/Halide" and any(m in low for m in HALIDE_LAYOUT):
        return "halide_tree"
    return "own_code"


def verdict_for(record, kinds):
    if kinds["own_code"]:
        return {"consumer": "consumer", "generator": "generator"}.get(
            record["evidence"], "uses_source"
        )
    if kinds["halide_tree"]:
        return "halide_copy_or_fork"  # needs a commit diff, not a guess
    if kinds["third_party"]:
        return "third_party_bundle"
    if kinds["prose"]:
        return "prose_only"
    return "unclear"


def classify(rows):
    out = []
    for record in rows:
        kinds = Counter(classify_path(record["repo"], p) for p in record["paths"])
        enriched = dict(record)
        enriched["path_kinds"] = dict(kinds)
        enriched["verdict"] = verdict_for(record, kinds)
        out.append(enriched)
    return out


# Known repositories with a known correct answer. Run on every change: each of
# the two refinements above was found by a case here failing.
VALIDATION = {
    "keep": ["fixstars/ion-kit", "Tiramisu-Compiler/tiramisu", "exo-lang/exo",
             "halide/Halide", "timothybrooks/hdr-plus", "fixstars/Halide-elements",
             "scanner-research/scanner", "flashlight/flashlight", "pytorch/pytorch",
             "jingpu/Halide-HLS", "KitwareMedical/ITKHalideFilters", "mmperf/mmperf"],
    "review": ["akothen/Hydride", "RafaeNoor/MISAAL", "abadams/Halide",
               "zivid/zivid-halide-fork"],
    "drop": ["proxmox/ceph", "shelltdf/osgall", "guardrailsio/large",
             "michaelchanwahyan/opencv-3.4.1", "FrewenWang/opencv-library"],
}
KEEP = {"consumer", "generator", "uses_source"}


def validate(rows):
    index = {r["repo"]: r for r in rows}
    failures = 0
    for expected, names in VALIDATION.items():
        for name in names:
            record = index.get(name)
            if not record:
                print(f"  ----     {name:44s} not in pool")
                continue
            got = ("keep" if record["verdict"] in KEEP else
                   "review" if record["verdict"] == "halide_copy_or_fork" else "drop")
            ok = got == expected
            failures += not ok
            print(f"  {'OK  ' if ok else '**MISS**':8s} {name:44s} "
                  f"{record['verdict']:20s} {record['path_kinds']}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="src", default="data/pools/lane_b.json")
    parser.add_argument("--out", default="data/pools/lane_b_classified.json")
    args = parser.parse_args()

    rows = json.load(open(args.src))["repos"]
    classified = classify(rows)

    print("verdicts:", dict(Counter(r["verdict"] for r in classified)))
    print("\nvalidation:")
    failures = validate(classified)
    print(f"\n{failures} failure(s)")

    with open(args.out, "w") as handle:
        json.dump({"schema_version": 1, "n_repos": len(classified),
                   "repos": classified}, handle, indent=0)
    print(f"wrote {args.out}")

    # Classification reads at most the paths the harvester recorded per repo,
    # which is a sample rather than the full match list. A repo whose sampled
    # paths all landed inside a vendored tree while its own code also uses
    # Halide would be misfiled, so raising that cap improves this pass.
    thin = sum(1 for r in classified if len(r["paths"]) < 3)
    print(f"note: {thin} repos were classified from fewer than 3 sampled paths")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
