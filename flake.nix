{
  description = "Patch third-party libraries without forking them";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";

    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ self, nixpkgs, ... }:
    let
      lib = nixpkgs.lib;
      forEachSystem = lib.genAttrs (import inputs.systems);
    in
    {
      # First-class library: `collectSources` turns a tree containing a
      # `.git-third-party/` directory into a fully materialized, patched source
      # derivation. Consume it as `git-third-party.lib.<system>.collectSources`.
      lib = forEachSystem (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        import ./collect-sources.nix { inherit pkgs; }
      );

      # Same capability injected into `pkgs.lib` via `lib.extend`, for callers
      # who prefer to reach it as `pkgs.lib.gitThirdParty.collectSources`.
      # (Extending your own flake `lib` output above is the idiomatic path;
      # this overlay is here to show that adding to `pkgs.lib` is possible.)
      overlays.default = final: _prev: {
        lib = _prev.lib.extend (
          _lfinal: _lprev: {
            gitThirdParty = import ./collect-sources.nix { pkgs = final; };
          }
        );
      };

      packages = forEachSystem (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.stdenv.mkDerivation {
            pname = "git-third-party";
            version = "0.1.0";
            src = ./.;

            # The tool is a single zero-dependency Python script; it only needs
            # a python3 interpreter (baked into the shebang by patchShebangs)
            # and `git` on PATH at runtime.
            nativeBuildInputs = [
              pkgs.python3
              pkgs.makeWrapper
            ];

            dontConfigure = true;
            dontBuild = true;

            installPhase = ''
              runHook preInstall
              install -Dm755 git-third-party $out/bin/git-third-party
              patchShebangs $out/bin/git-third-party
              wrapProgram $out/bin/git-third-party \
                --prefix PATH : ${lib.makeBinPath [ pkgs.git ]}
              runHook postInstall
            '';

            meta = {
              description = "Patch third-party libraries without forking them";
              homepage = "https://github.com/kp2pml30/git-third-party";
              license = lib.licenses.gpl3Only;
              mainProgram = "git-third-party";
            };
          };
        }
      );

      # Expose a formatter command that runs the same pre-commit config used by
      # `nix flake check`.
      formatter = forEachSystem (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          config = self.checks.${system}.pre-commit-check.config;
          inherit (config) package configFile;
        in
        pkgs.writeShellScriptBin "pre-commit-run" ''
          ${pkgs.lib.getExe package} run --all-files --config ${configFile}
        ''
      );

      checks = forEachSystem (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          pre-commit-check = inputs.git-hooks.lib.${system}.run {
            src = ./.;
            hooks = {
              # Validate commit messages against conventional-commit rules
              # (runs on the commit-msg stage, so it is skipped by
              # `nix flake check` / `pre-commit run --all-files`).
              check-commit-message = {
                enable = true;
                name = "check commit message";
                description = "Validate the commit message against conventional-commit rules.";
                entry = "${pkgs.python3}/bin/python3 ${./support/scripts/check-commit-message.py} --message-file";
                language = "system";
                stages = [ "commit-msg" ];
              };

              nixfmt.enable = true;
              ruff-format.enable = true;
            };
          };

          # The pytest suite. Fully offline (it builds local git repos in a
          # temp dir), so it runs inside the nix sandbox.
          tests =
            pkgs.runCommandLocal "git-third-party-tests"
              {
                nativeBuildInputs = [
                  (pkgs.python3.withPackages (ps: [ ps.pytest ]))
                  pkgs.git
                ];
              }
              ''
                cp -r ${./.} src
                chmod -R u+w src
                export HOME="$TMPDIR/home"
                mkdir -p "$HOME"
                cd src
                pytest -q tests
                touch "$out"
              '';
        }
      );

      devShells = forEachSystem (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          inherit (self.checks.${system}.pre-commit-check) shellHook enabledPackages;
        in
        {
          default = pkgs.mkShell {
            inherit shellHook;
            buildInputs = enabledPackages ++ [
              pkgs.python3
              pkgs.python3Packages.pytest
              pkgs.python3Packages.pytest-cov
            ];
          };
        }
      );
    };
}
