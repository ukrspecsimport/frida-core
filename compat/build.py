#!/usr/bin/env python

import argparse
from collections import OrderedDict
from dataclasses import dataclass
import itertools
import json
import os
from pathlib import Path
import pickle
import platform
import shutil
import subprocess
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "releng" / "meson"))
sys.path.insert(0, str(REPO_ROOT))
from mesonbuild import coredata
from mesonbuild.mesonlib import OptionKey
from releng.env_generic import TOOLCHAIN_ENVVARS


STATE_FILENAME = "state.dat"
DEPFILE_FILENAME = "compat.deps"

HELPER_TARGET = "frida-helper"
HELPER_FILE_WINDOWS = Path("src") / "frida-helper.exe"
HELPER_FILE_UNIX = Path("src") / "frida-helper"

AGENT_TARGET = "frida-agent"
AGENT_FILE_WINDOWS = Path("lib") / "agent" / "frida-agent.dll"
AGENT_FILE_DARWIN = Path("lib") / "agent" / "frida-agent.dylib"
AGENT_FILE_ELF = Path("lib") / "agent" / "frida-agent.so"

GADGET_TARGET = "frida-gadget"
GADGET_FILE_WINDOWS = Path("lib") / "gadget" / "frida-gadget.dll"
GADGET_FILE_DARWIN = Path("lib") / "gadget" / "frida-gadget.dylib"
GADGET_FILE_ELF = Path("lib") / "gadget" / "frida-gadget.so"

SERVER_TARGET = "frida-server"
SERVER_FILE_UNIX = Path("server") / "frida-server"

MSVS_ENVVARS = {
    "PLATFORM",
    "VCINSTALLDIR",
    "INCLUDE",
    "LIB",
}


@dataclass
class Output:
    identifier: str
    name: str
    file: Path
    target: str


@dataclass
class State:
    host_os: str
    host_arch: str
    outputs: Mapping[str, Sequence[Output]]


def main(argv):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    command = subparsers.add_parser("setup", help="setup build directories")
    command.add_argument("builddir", help="build directory", type=Path)
    command.add_argument("host_os", help="operating system binaries are being built for")
    command.add_argument("host_arch", help="architecture binaries are being built for")
    command.add_argument("compat", help="support for targets with a different architecture",
                         type=parse_compat_option_value)
    command.add_argument("assets", help="whether assets are embedded vs installed and loaded at runtime")
    command.add_argument("components", help="which components will be built",
                         type=parse_array_option_value)
    command.set_defaults(func=lambda args: setup(args.builddir,
                                                 args.host_os,
                                                 args.host_arch,
                                                 args.compat,
                                                 args.assets,
                                                 args.components))

    command = subparsers.add_parser("compile", help="compile a specific build directory")
    command.add_argument("builddir", help="build directory", type=Path)
    command.add_argument("top_builddir", help="top build directory", type=Path)
    command.set_defaults(func=lambda args: compile(args.builddir, args.top_builddir))

    args = parser.parse_args()
    if "func" in args:
        args.func(args)
    else:
        parser.print_usage(file=sys.stderr)
        sys.exit(1)


def parse_compat_option_value(v: str) -> set[str]:
    vals = parse_array_option_value(v)

    if len(vals) > 1:
        for choice in {"auto", "disabled"}:
            if choice in vals:
                raise argparse.ArgumentTypeError(f"the compat '{choice}' choice cannot be combined with other choices")

    return vals


def parse_array_option_value(v: str) -> set[str]:
    return {v.strip() for v in v.split(",")}


def setup(builddir: Path,
          host_os: str,
          host_arch: str,
          compat: set[str],
          assets: str,
          components: set[str]):
    outputs: Mapping[str, Sequence[Output]] = {}

    if "auto" in compat:
        compat = {"native", "emulated"} if host_os in {"windows", "macos", "ios", "tvos", "android"} else set()
    elif "disabled" in compat:
        compat = set()

    if "native" in compat:
        if host_os == "windows" and host_arch in {"x86_64", "x86"}:
            if host_arch == "x86_64":
                other_arch = "x86"
                kind = "legacy"
            else:
                other_arch = "x86_64"
                kind = "modern"
            outputs[other_arch] = [
                Output(identifier=f"helper_{kind}",
                       name=HELPER_FILE_WINDOWS.name,
                       file=HELPER_FILE_WINDOWS,
                       target=HELPER_TARGET),
                Output(identifier=f"agent_{kind}",
                       name=AGENT_FILE_WINDOWS.name,
                       file=AGENT_FILE_WINDOWS,
                       target=AGENT_TARGET),
            ]
            if "gadget" in components:
                outputs[other_arch] += [
                    Output(identifier=f"gadget_{kind}",
                           name=GADGET_FILE_WINDOWS.name,
                           file=GADGET_FILE_WINDOWS,
                           target=GADGET_TARGET),
                ]

        if host_os in {"macos", "ios", "tvos"} and host_arch in {"arm64e", "arm64"}:
            if host_arch == "arm64e":
                other_arch = "arm64"
                kind = "legacy"
            else:
                other_arch = "arm64e"
                kind = "modern"
            outputs[other_arch] = [
                Output(identifier=f"helper_{kind}",
                       name=f"frida-helper-{other_arch}",
                       file=HELPER_FILE_UNIX,
                       target=HELPER_TARGET),
                Output(identifier=f"agent_{kind}",
                       name=f"frida-agent-{other_arch}.dylib",
                       file=AGENT_FILE_DARWIN,
                       target=AGENT_TARGET),
            ]
            if "gadget" in components:
                outputs[other_arch] += [
                    Output(identifier=f"gadget_{kind}",
                           name=f"frida-gadget-{other_arch}.dylib",
                           file=GADGET_FILE_DARWIN,
                           target=GADGET_TARGET),
                ]
            if "server" in components and assets == "installed":
                outputs[other_arch] += [
                    Output(identifier=f"server_{kind}",
                           name=f"frida-server-{other_arch}",
                           file=SERVER_FILE_UNIX,
                           target=SERVER_TARGET),
                ]

        if host_os == "linux" and host_arch in {"x86_64", "x86"}:
            if host_arch == "x86_64":
                other_arch = "x86"
                kind = "legacy"
            else:
                other_arch = "x86_64"
                kind = "modern"
            outputs[other_arch] = [
                Output(identifier="helper_legacy",
                       name=HELPER_FILE_UNIX.name,
                       file=HELPER_FILE_UNIX,
                       target=HELPER_TARGET),
                Output(identifier="agent_legacy",
                       name=AGENT_FILE_ELF.name,
                       file=AGENT_FILE_ELF,
                       target=AGENT_TARGET),
            ]
            if "gadget" in components:
                outputs[other_arch] += [
                    Output(identifier=f"gadget_{kind}",
                           name=GADGET_FILE_ELF.name,
                           file=GADGET_FILE_ELF,
                           target=GADGET_TARGET),
                ]

        if host_os == "android" and host_arch in {"arm64", "x86_64"}:
            other_arch = "arm" if host_arch == "arm64" else "x86"
            outputs[other_arch] = [
                Output(identifier="helper_legacy",
                       name=HELPER_FILE_UNIX.name,
                       file=HELPER_FILE_UNIX,
                       target=HELPER_TARGET),
                Output(identifier="agent_legacy",
                       name=AGENT_FILE_ELF.name,
                       file=AGENT_FILE_ELF,
                       target=AGENT_TARGET),
            ]
            if "gadget" in components:
                outputs[other_arch] += [
                    Output(identifier="gadget_legacy",
                           name=GADGET_FILE_ELF.name,
                           file=GADGET_FILE_ELF,
                           target=GADGET_TARGET),
                ]

    if "emulated" in compat:
        if host_os == "android" and host_arch in {"x86_64", "x86"}:
            outputs["arm"] = [
                Output(identifier="agent_emulated_legacy",
                       name="frida-agent-arm.so",
                       file=AGENT_FILE_ELF,
                       target=AGENT_TARGET),
            ]
            if host_arch == "x86_64":
                outputs["arm64"] = [
                    Output(identifier="agent_emulated_modern",
                           name="frida-agent-arm64.so",
                           file=AGENT_FILE_ELF,
                           target=AGENT_TARGET),
                ]

    if not outputs:
        return

    state = State(host_os, host_arch, outputs)
    privdir = compute_private_dir(builddir)
    privdir.mkdir(exist_ok=True)
    (privdir / STATE_FILENAME).write_bytes(pickle.dumps(state))

    variable_names, output_names = zip(*[(output.identifier, output.name) \
            for output in itertools.chain.from_iterable(outputs.values())])
    print(f"{','.join(variable_names)} {','.join(output_names)} {DEPFILE_FILENAME}")


def compile(builddir: Path, top_builddir: Path):
    state = pickle.loads((compute_private_dir(builddir) / STATE_FILENAME).read_bytes())

    if platform.system() == "Windows":
        configure_script = "configure.bat"
        make_command = REPO_ROOT / "make.bat"
    else:
        configure_script = "configure"
        make_command = "make"

    source_paths: set[Path] = set()
    options: Optional[Sequence[str]] = None
    for extra_arch, outputs in state.outputs.items():
        workdir = compute_workdir_for_arch(extra_arch, builddir)
        build_env = make_build_environment(workdir)

        if not (workdir / "build.ninja").exists():
            if options is None:
                options = load_meson_options(top_builddir)
            perform(REPO_ROOT / configure_script,
                    f"--host={state.host_os}-{extra_arch}",
                    "--",
                    "-Dhelper_modern=",
                    "-Dhelper_legacy=",
                    "-Dagent_modern=",
                    "-Dagent_legacy=",
                    "-Dagent_emulated_modern=",
                    "-Dagent_emulated_legacy=",
                    *options,
                    env=build_env)

        targets_to_build = [o.target for o in outputs]
        perform(make_command, *targets_to_build,
                cwd=workdir,
                env=build_env)

        for o in outputs:
            shutil.copy(workdir / o.file, builddir / o.name)

        for cmd in json.loads((workdir / "compile_commands.json").read_text(encoding="utf-8")):
            source_paths.add((workdir / Path(cmd["file"])).absolute())

    (builddir / DEPFILE_FILENAME).write_text(generate_depfile(itertools.chain.from_iterable(state.outputs.values()),
                                                              source_paths,
                                                              builddir,
                                                              top_builddir),
                                             encoding="utf-8")


def compute_private_dir(builddir: Path) -> Path:
    return builddir / "arch-support.p"


def compute_workdir_for_arch(arch: str, builddir: Path) -> Path:
    return compute_private_dir(builddir) / arch


def make_build_environment(workdir: Path) -> Mapping[str, str]:
    return {
        "FRIDA_BUILDDIR": str(workdir),
        **scrub_environment(os.environ),
    }


def load_meson_options(top_builddir: Path) -> Sequence[str]:
    return [f"-D{k}={v.value}" for k, v in coredata.load(top_builddir).options.items() \
            if option_should_be_forwarded(k, v)]


def option_should_be_forwarded(k: OptionKey, v: coredata.UserOption[Any]) -> bool:
    if coredata.CoreData.is_per_machine_option(k) \
            and not (k.subproject and k.is_project() and k.machine is coredata.MachineChoice.HOST):
        return False

    if k.as_host() in coredata.BUILTIN_OPTIONS_PER_MACHINE:
        return False

    if k.is_builtin():
        if k.name in {"buildtype", "genvslite"}:
            return False
        if not str(v.value):
            return False

    if k.module == "python":
        if k.name == "install_env" and v.value == "prefix":
            return False
        if not str(v.value):
            return False

    if not k.subproject and k.is_project():
        tokens = k.name.split("_")
        if tokens[0] in {"helper", "agent"} and tokens[-1] in {"modern", "legacy"}:
            return False

    return True


def scrub_environment(env: Mapping[str, str]) -> Mapping[str, str]:
    clean_env = OrderedDict()
    envvars_to_avoid = {*TOOLCHAIN_ENVVARS, *MSVS_ENVVARS}
    for k, v in env.items():
        if k in envvars_to_avoid:
            continue
        if k.upper() == "PATH" and platform.system() == "Windows":
            v = scrub_windows_devenv_dirs_from_path(v, env)
        clean_env[k] = v
    return clean_env


def scrub_windows_devenv_dirs_from_path(raw_path: str, env: Mapping[str, str]) -> str:
    raw_vcinstalldir = env.get("VCINSTALLDIR")
    if raw_vcinstalldir is None:
        return raw_path
    vcinstalldir = Path(raw_vcinstalldir)
    clean_entries = []
    for raw_entry in raw_path.split(";"):
        entry = Path(raw_entry)
        if entry.is_relative_to(vcinstalldir):
            continue
        if "WINDOWS KITS" in [p.upper() for p in entry.parts]:
            continue
        clean_entries.append(raw_entry)
    return ";".join(clean_entries)


def generate_depfile(outputs: Sequence[Output],
                     source_paths: Sequence[Path],
                     builddir: Path,
                     top_builddir: Path) -> str:
    output_relpaths = [(builddir / o.name).relative_to(top_builddir).as_posix() for o in outputs]
    inputs = " ".join([quote(Path(os.path.relpath(p, top_builddir)).as_posix()) for p in source_paths if p.exists()])
    lines = []
    for output in output_relpaths:
        lines.append(f"{output}: {inputs}")
    return "\n".join(lines)


def quote(path: str) -> str:
    if " " not in path:
        return path
    return "\"" + path.replace ("\"", "\\\"") + "\""


def perform(*args, **kwargs):
    try:
        return subprocess.run(args,
                              check=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              encoding="utf-8",
                              **kwargs)
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)
        print("Output:\n\t| " + "\n\t| ".join(e.output.strip().split("\n")), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv)
