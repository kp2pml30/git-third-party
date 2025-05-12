{ rootDerivation
, derivationName
, stdenv
, ... # added for future backwards compatibility
}:
let
	config = builtins.fromJSON (builtins.readFile "${rootDerivation}/.git-third-party/config.json");
	allRepoNames = builtins.attrNames config.repos;
	makeDependentDerivation =
		name:
			let
				cleanName = builtins.head (builtins.tail (builtins.match "^(.*/|)([^/]+)$" name));
				myConfig = config.repos."${name}";
				shouldFetchModules = !(builtins.hasAttr "submodules" myConfig) || myConfig.submodules != [];
				base-src = builtins.fetchGit {
					url = myConfig.url;
					rev = myConfig.commit;
					submodules = shouldFetchModules;
					#fetchSubmodules = shouldFetchModules;
					# fetchLFS = true;
					shallow = true;
				};
		in stdenv.mkDerivation {
			name = "git3party_${derivationName}_${cleanName}";
			src = base-src;
			patches =
				builtins.map
					(num: "${rootDerivation}/.git-third-party/patches/${name}/${toString num}")
					(builtins.genList (x: x + 1) myConfig.patches);
			phases = [ "unpackPhase" "patchPhase" "installPhase" ];

			#outputHashMode = "recursive";

			installPhase = ''
				cp -r . "$out"
			'';
		};
	dependentDerivations = builtins.map (name: { name = name; der = makeDependentDerivation name; }) allRepoNames;

	cpFlags = "--no-preserve=ownership,mode --preserve=xattr";

	copyLines = builtins.concatStringsSep "\n" ([
		"cp ${cpFlags} -r '${rootDerivation}/.' ."
	] ++ builtins.map (nameDer: "mkdir -p '${nameDer.name}'\ncp ${cpFlags} -r '${nameDer.der}'/. '${nameDer.name}'") dependentDerivations);
in
	stdenv.mkDerivation {
		name = derivationName;

		srcs = [
			rootDerivation
		] ++ (builtins.map (x: x.name) dependentDerivations);

		phases = [ "unpackPhase" "installPhase" ];

		#outputHashMode = "recursive";

		unpackPhase = copyLines;

		installPhase = ''
			cp -r . "$out"
		'';
	}
