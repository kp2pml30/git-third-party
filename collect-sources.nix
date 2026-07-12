# Git Third Party
# Copyright (c) 2025 kp2pml30, All rights reserved.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3.0 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library.

# Collect the fully materialized source tree for a git-third-party project.
#
# `collectSources` takes a derivation (or path) that contains a tracked
# `.git-third-party/` directory and returns a *patched* derivation: every
# third-party repository is fetched at its pinned commit, has its stored
# patches applied, and is grafted back into a copy of the input tree at its
# relative path.
#
#   collectSources = drv -> drv
#
# Usage:
#   let gtp = import ./collect-sources.nix { inherit pkgs; };
#   in gtp.collectSources ./.        # or any derivation with .git-third-party/

{ pkgs }:
let
  inherit (pkgs) lib;

  collectSources =
    src:
    let
      config = (builtins.fromJSON (builtins.readFile "${src}/.git-third-party/config.json")).repos;
      repoNames = builtins.attrNames config;

      # Deterministic, path-safe derivation names (a repo path may contain "/").
      slug = name: builtins.hashString "sha256" name;

      fetchAndPatch =
        name:
        let
          repo = config.${name};
          # `builtins.fetchGit` can only fetch all submodules or none. Treat a
          # missing key or a non-empty `submodules` list as "fetch them"; an
          # explicit empty list means "skip submodules".
          withSubmodules = !(repo ? submodules) || repo.submodules != [ ];
          unpatched = builtins.fetchGit {
            url = repo.url;
            rev = repo.commit;
            submodules = withSubmodules;
            shallow = true;
            name = "gtp-${slug name}-unpatched";
          };
        in
        pkgs.applyPatches {
          name = "gtp-${slug name}-patched";
          src = unpatched;
          patches = builtins.genList (
            i: "${src}/.git-third-party/patches/${name}/${toString (i + 1)}"
          ) repo.patches;
        };

      repos = builtins.map (name: {
        inherit name;
        drv = fetchAndPatch name;
      }) repoNames;
    in
    pkgs.stdenvNoCC.mkDerivation {
      name = "git-third-party-src";

      srcs = [ src ] ++ builtins.map (r: r.drv) repos;
      sourceRoot = ".";

      dontUnpack = true;
      dontConfigure = true;
      dontBuild = true;
      dontFixup = true;

      installPhase = ''
        mkdir -p "$out"
        cp --no-preserve=ownership -r ${src}/. "$out/."
        chmod -R u+w "$out"
      ''
      + lib.concatMapStringsSep "\n" (r: ''
        mkdir -p "$out/${r.name}"
        cp --no-preserve=ownership -r ${r.drv}/. "$out/${r.name}/."
      '') repos;
    };
in
{
  inherit collectSources;
}
