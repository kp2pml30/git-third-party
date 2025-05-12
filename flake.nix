{
	inputs = {
		nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
		systems = {
			url = "github:nix-systems/default";
			inputs.nixpkgs.follows = "nixpkgs";
		};
		flake-utils = {
			url = "github:numtide/flake-utils";
			inputs.systems.follows = "systems";
			inputs.nixpkgs.follows = "nixpkgs";
		};
	};

	outputs = inputs@{ self, nixpkgs, flake-utils, ... }:
		flake-utils.lib.eachDefaultSystem
			(system:
				let
					pkgs = nixpkgs.legacyPackages.${system};
				in
				{
					devShells.default = pkgs.mkShell {
						packages = with pkgs; [
							python312
							pre-commit
						];

						shellHook = ''
						'';
					};
				}
			);
}
