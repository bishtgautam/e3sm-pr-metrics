"""Map an E3SM pull request to the model components it touches.

Three independent signals are used, and all three are kept so they can be
compared (PR labels are often missing or wrong):

  files  - paths changed by the PR (most reliable)
  labels - GitHub labels on the PR
  branch - E3SM branch convention ``<user>/<comp>/<topic>``

Directory names have changed over the life of the project
(``models/lnd`` -> ``components/clm`` -> ``components/elm``, ``mpas-o`` ->
``mpas-ocean``, ``cam`` -> ``eam``, ``scream`` -> ``eamxx`` ...), so every
historical name seen on master is listed below. Run
``tools/audit_paths.py <E3SM clone>`` to find directories that are not mapped.
"""

import re

# key -> display name, in the order shown in the dashboard
COMPONENTS = {
    "atm": "Atmosphere (EAM)",
    "eamxx": "Atmosphere (EAMxx)",
    "homme": "HOMME dycore",
    "land": "Land (ELM)",
    "river": "River (MOSART)",
    "ocean": "Ocean (MPAS-O/Omega)",
    "seaice": "Sea ice",
    "landice": "Land ice",
    "wave": "Wave (WW3)",
    "coupler": "Coupler/driver",
    "mpas-framework": "MPAS framework",
    "iac": "IAC (GCAM)",
    "emulators": "Emulators",
    "data-stub": "Data/stub models",
    "infrastructure": "Infrastructure (CIME/scripts/CI)",
    "docs": "Documentation",
}

# Directory prefix -> component. Matched on the first two path segments
# (``components/elm``) and then the first segment (``driver-mct``).
PATH_PREFIXES = {
    # land
    "components/elm": "land",
    "components/clm": "land",
    "models/lnd": "land",
    # river
    "components/mosart": "river",
    "components/rtm": "river",
    "models/rof": "river",
    # ocean
    "components/mpas-ocean": "ocean",
    "components/mpas-o": "ocean",
    "components/omega": "ocean",
    "components/pop": "ocean",
    "models/ocn": "ocean",
    # sea ice
    "components/mpas-seaice": "seaice",
    "components/mpas-cice": "seaice",
    "components/cice": "seaice",
    "models/ice": "seaice",
    # land ice
    "components/mpas-albany-landice": "landice",
    "components/mpasli": "landice",
    "components/cism": "landice",
    "components/bisicles-landice": "landice",
    "models/glc": "landice",
    # atmosphere
    "components/eam": "atm",
    "components/cam": "atm",
    "models/atm": "atm",
    "components/eamxx": "eamxx",
    "components/scream": "eamxx",
    "components/homme": "homme",
    "components/homme_v3.0.0": "homme",
    # wave
    "components/ww3": "wave",
    "models/wav": "wave",
    # coupler / driver
    "driver-mct": "coupler",
    "driver-moab": "coupler",
    "driver_cpl": "coupler",
    "driver": "coupler",
    "models/drv": "coupler",
    # others
    "components/mpas-framework": "mpas-framework",
    "components/gcam": "iac",
    "components/iac": "iac",
    "components/emulators": "emulators",
    "components/data_comps": "data-stub",
    "components/stub_comps": "data-stub",
    "components/xcpl_comps": "data-stub",
    "models/data": "data-stub",
    "models/stub": "data-stub",
    "models/testcpl": "data-stub",
    "docs": "docs",
    "doc": "docs",
    # shared build/utility code under components/ and models/
    "components": "infrastructure",  # components/CMakeLists.txt etc.
    "components/cmake": "infrastructure",
    "models/csm_share": "infrastructure",
    "models/utils": "infrastructure",
}
# Anything not matched above (cime_config, cime, externals, share, tools,
# scripts, .github, cmake, components/cmake, machines, ...) is infrastructure.
DEFAULT_PATH_COMPONENT = "infrastructure"

LABELS = {
    "ELM": "land", "FATES": "land", "BGC": "land",
    "MOSART": "river",
    "MPAS-ocean": "ocean", "MPAS-Ocean standalone": "ocean", "OMEGA": "ocean",
    "MPAS-seaice": "seaice", "MPAS-seaice-prescribed": "seaice",
    "CICE": "seaice", "Icepack": "seaice",
    "MPAS-albany-landice": "landice",
    "EAM": "atm", "Atmosphere": "atm", "Atmospheric chemistry": "atm",
    "COSP": "atm", "MMF": "atm", "ZM": "atm", "Radiation": "atm", "SCM": "atm",
    "aquaplanet": "atm",
    "EAMxx": "eamxx", "MAM4xx": "eamxx", "rrtmgpxx": "eamxx", "EKAT": "eamxx",
    "HOMME": "homme", "HOMME standalone": "homme",
    "Wave": "wave",
    "Coupler": "coupler", "MCT": "coupler", "MOAB": "coupler",
    "MPAS-framework": "mpas-framework",
    "GCAM": "iac",
    "AI and emulators": "emulators",
    "data-models": "data-stub", "stub-models": "data-stub",
    "dead-models": "data-stub", "DOCN": "data-stub",
    "CIME": "infrastructure", "Machine Files": "infrastructure",
    "CMake build system": "infrastructure", "Scripts": "infrastructure",
    "Testing": "infrastructure", "PIO": "infrastructure",
    "SCORPIO": "infrastructure", "gptl": "infrastructure",
    "gptl (timer library)": "infrastructure", "workflows": "infrastructure",
    "github_actions": "infrastructure", "gh-action": "infrastructure",
    "Utils": "infrastructure", "inputdata": "infrastructure",
    "run_e3sm": "infrastructure",
    "Documentation": "docs",
}

# Tokens in the branch name (``user/lnd/topic``)
BRANCH_TOKENS = {
    "lnd": "land", "land": "land", "elm": "land", "fates": "land",
    "rof": "river", "river": "river", "mosart": "river",
    "ocn": "ocean", "ocean": "ocean", "mpas-ocean": "ocean", "mpaso": "ocean",
    "omega": "ocean",
    "ice": "seaice", "seaice": "seaice", "sea-ice": "seaice",
    "mpas-seaice": "seaice", "mpassi": "seaice", "cice": "seaice",
    "glc": "landice", "landice": "landice", "mali": "landice",
    "atm": "atm", "eam": "atm", "cam": "atm",
    "eamxx": "eamxx", "scream": "eamxx", "mam4xx": "eamxx",
    "homme": "homme",
    "wav": "wave", "wave": "wave", "ww3": "wave",
    "cpl": "coupler", "coupler": "coupler", "driver": "coupler",
    "mct": "coupler", "moab": "coupler",
    "mpas-framework": "mpas-framework", "mpas": "mpas-framework",
    "iac": "iac", "gcam": "iac",
    "emulators": "emulators",
    "docs": "docs", "doc": "docs",
    "cime": "infrastructure", "machinefiles": "infrastructure",
    "machines": "infrastructure", "ci": "infrastructure",
    "cmake": "infrastructure", "scripts": "infrastructure",
    "tools": "infrastructure", "pes": "infrastructure",
}


def path_dir(path):
    """Reduce a file path to the prefix used for classification."""
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] in ("components", "models"):
        return "/".join(parts[:2])
    if len(parts) >= 2:
        return parts[0]
    return path  # a top-level file such as README.md


def from_dirs(dirs):
    out = set()
    for d in dirs:
        first = d.split("/")[0]
        out.add(PATH_PREFIXES.get(d) or PATH_PREFIXES.get(first)
                or DEFAULT_PATH_COMPONENT)
    return sorted(out)


def from_labels(labels):
    return sorted({LABELS[l] for l in labels if l in LABELS})


def from_branch(branch):
    out = set()
    for seg in (branch or "").lower().split("/")[:-1]:
        for tok in (seg, re.split(r"[-_]", seg)[0]):
            if tok in BRANCH_TOKENS:
                out.add(BRANCH_TOKENS[tok])
                break
    return sorted(out)


def classify(dirs, labels, branch):
    """Return all three signals plus the best guess.

    The best guess prefers files, then labels, then branch. If a PR touches
    model code, the infrastructure tag is dropped unless infrastructure is all
    it touches, so a land PR that also edits cime_config stays a land PR.
    """
    by = {
        "files": from_dirs(dirs),
        "labels": from_labels(labels),
        "branch": from_branch(branch),
    }
    best = by["files"] or by["labels"] or by["branch"]
    minor = {"infrastructure", "docs"}
    if any(c not in minor for c in best):
        best = [c for c in best if c not in minor]
    return best, by
